from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.dynamic_experience import (
    DynamicExperienceStore,
    escaped_risk_observation,
)
from perfect_assassin.movement.destination_sequence import (
    load_destination_sequence,
    validate_destination_sequence_catalog,
)
from perfect_assassin.runtime_paths import external_runtime_root


NAVIGATION_RUNNER = (
    ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
)
COMBAT_RUNNER = (
    ROOT / "integrations" / "windows-input" / "run_controlled_combat.py"
)
DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
DEFAULT_WORKER = (
    ROOT / "data" / "runtime" / "native-build"
    / "pa_nav_probe-v34" / "Debug" / "pa_nav_probe.exe"
)
DEFAULT_WORLD_PACK_PROFILE = (
    ROOT / "config" / "navigation"
    / "world-pack-runtime-tbc243-azeroth-full-v3.json"
)
EXTERNAL_RUNTIME_ROOT = external_runtime_root(ROOT)
DEFAULT_WORLD_PACK_STORE = EXTERNAL_RUNTIME_ROOT / "worldpacks"
DEFAULT_WORLD_STRUCTURE_INDEX = (
    ROOT / "data" / "runtime" / "client-catalog" / "tbc243-8606"
    / "azeroth-full-v3-world-structure-index-v1.json"
)
DEFAULT_SEMANTIC_CATALOG = (
    ROOT / "config" / "movement-lab" / "semantic-destinations-tbc243.json"
)
DEFAULT_ZONE_TRANSFORM_CATALOG = (
    ROOT / "config" / "pose" / "world-map-zone-transforms-tbc243-8606.json"
)
DEFAULT_RESULT = (
    ROOT / "data" / "runtime" / "navigation-f3b"
    / "journey-combat-supervisor-latest.json"
)
DEFAULT_DYNAMIC_EXPERIENCE_STORE = (
    EXTERNAL_RUNTIME_ROOT / "memory"
    / "dynamic-experience-v1.sqlite3"
)
RESULT_VALIDATOR = ContractValidator(
    ROOT / "contracts" / "journey-combat-supervisor-result.schema.json"
)
CHILD_CREATION_FLAGS = 0x08000000 if os.name == "nt" else 0


class JourneyCombatSupervisorError(RuntimeError):
    pass


def _write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                record,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _typed_result_from_stdout(
    stdout: str,
    *,
    record_types: set[str],
    stderr: str = "",
) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("record_type") in record_types:
            return record
    diagnostic = (stderr.strip() or stdout.strip())[-2_000:]
    detail = "child runner emitted no recognized result record"
    if diagnostic:
        detail += f"; child diagnostic: {diagnostic}"
    raise JourneyCombatSupervisorError(detail)


def journey_supervisor_action(
    navigation_result: dict[str, Any],
    *,
    combat_handoffs_used: int,
    maximum_combat_handoffs: int,
) -> str:
    status = navigation_result.get("status")
    if status == "ARRIVED":
        return "COMPLETE"
    if status == "COMBAT_HANDOFF_REQUIRED":
        return (
            "HANDOFF_COMBAT"
            if combat_handoffs_used < maximum_combat_handoffs
            else "STOP_COMBAT_BUDGET"
        )
    if status in {
        "CONTROL_FRAME_BUDGET_EXHAUSTED",
        "SEMANTIC_FRONTIER_REPLAN_REQUIRED",
    }:
        return "RESUME_NAVIGATION"
    if status == "RUNTIME_ARM_EXPIRED":
        return "STOP_RUNTIME_ARM_EXPIRED"
    if status in {"MANUAL_TAKEOVER", "OPERATOR_STOPPED"}:
        return "STOP_OPERATOR"
    return "STOP_FAIL_CLOSED"


def _navigation_command(
    args: argparse.Namespace,
    destination_id: str | None = None,
    *,
    resume_result: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(NAVIGATION_RUNNER),
        "--session-authorization-file", str(args.session_authorization_file),
        "--session-receipt", str(args.session_receipt),
        "--worker", str(args.worker),
        "--map-id", str(getattr(args, "map_id", 0)),
        "--world-pack-profile", str(args.world_pack_profile),
        "--world-pack-store", str(args.world_pack_store),
        "--world-structure-index", str(args.world_structure_index),
        "--semantic-catalog", str(args.semantic_catalog),
        "--expected-zone-index", str(args.expected_zone_index),
        "--zone-transform-catalog", str(
            getattr(args, "zone_transform_catalog", DEFAULT_ZONE_TRANSFORM_CATALOG)
        ),
        "--start-world-z-hint", str(args.start_world_z_hint),
        "--max-control-frames", str(args.max_control_frames),
        "--steering-controller", getattr(
            args, "steering_controller", "geometric_predictive_v1",
        ),
        "--mppi-batch-size", str(getattr(args, "mppi_batch_size", 1_000)),
        "--mppi-time-steps", str(getattr(args, "mppi_time_steps", 56)),
        "--dynamic-experience-store", str(args.dynamic_experience_store),
        "--minimum-travel-health-fraction", "0.55",
        "--acknowledge-navmesh-roaming",
    ]
    if getattr(args, "continue_through_routine_aggro", False):
        command.append("--continue-through-routine-aggro")
    continuous_authorization = getattr(args, "continuous_motion_authorization_file", None)
    continuous_arm = getattr(args, "continuous_motion_arm_file", None)
    continuous_revalidation = getattr(args, "continuous_motion_revalidation_file", None)
    if continuous_authorization is not None:
        command.extend([
            "--continuous-motion-authorization-file",
            str(continuous_authorization),
        ])
    if continuous_arm is not None:
        command.extend(["--continuous-motion-arm-file", str(continuous_arm)])
    if continuous_revalidation is not None:
        command.extend([
            "--continuous-motion-revalidation-file",
            str(continuous_revalidation),
        ])
    runtime_arm_wait_seconds = float(
        getattr(args, "runtime_arm_wait_seconds", 0.0)
    )
    if runtime_arm_wait_seconds > 0.0:
        command.extend([
            "--runtime-arm-wait-seconds",
            str(runtime_arm_wait_seconds),
        ])
    if args.structure_access_graph is not None:
        command.extend([
            "--structure-access-graph", str(args.structure_access_graph),
        ])
        producer = getattr(args, "structure_probe_worker", None)
        if producer is not None:
            command.extend(["--structure-probe-worker", str(producer)])
    if args.operator_control_file is not None:
        command.extend([
            "--operator-control-file", str(args.operator_control_file),
        ])
    if args.operator_path is not None:
        command.extend(["--operator-path", str(args.operator_path)])
    elif getattr(args, "goal_normalized_x", None) is not None:
        command.extend([
            "--goal-normalized-x", str(args.goal_normalized_x),
            "--goal-normalized-y", str(args.goal_normalized_y),
        ])
    else:
        command.extend([
            "--semantic-destination-id",
            destination_id if destination_id is not None else args.semantic_destination_id,
        ])
    if resume_result is not None:
        command.extend(["--resume-result", str(resume_result)])
    if getattr(args, "leveling_plan_file", None) is not None:
        command.extend(["--leveling-plan-file", str(args.leveling_plan_file)])
    traversed_surface_prior = getattr(args, "traversed_surface_prior", None)
    if traversed_surface_prior is not None:
        command.extend([
            "--traversed-surface-prior", str(traversed_surface_prior),
        ])
    if args.activate_stealth:
        command.append("--activate-stealth")
    return command


def _combat_command(
    args: argparse.Namespace,
    navigation_result: dict[str, Any] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(COMBAT_RUNNER),
        "--session-authorization-file", str(args.session_authorization_file),
        "--session-receipt", str(args.session_receipt),
        "--acknowledge-controlled-combat",
    ]
    if args.operator_control_file is not None:
        command.extend([
            "--operator-control-file", str(args.operator_control_file),
        ])
    if navigation_result is not None and navigation_result.get("result_path"):
        command.extend([
            "--navigation-handoff-result",
            str(navigation_result["result_path"]),
        ])
    return command


def _publish(
    args: argparse.Namespace,
    *,
    supervisor_id: str,
    status: str,
    combat_handoffs_used: int,
    steps: list[dict[str, Any]],
) -> None:
    record = {
        "record_type": "journey_combat_supervisor_result",
        "schema_version": "1.0",
        "supervisor_id": supervisor_id,
        "status": status,
        "map_id": int(getattr(args, "map_id", 0)),
        "destination_mode": (
            "OPERATOR_PATH"
            if args.operator_path is not None
            else "NORMALIZED_GOAL"
            if getattr(args, "goal_normalized_x", None) is not None
            else "SEMANTIC_SEQUENCE"
            if getattr(args, "destination_sequence_file", None) is not None
            else "SEMANTIC"
        ),
        "semantic_destination_id": args.semantic_destination_id,
        "semantic_destination_ids": getattr(args, "semantic_destination_ids", None),
        "destination_sequence_file": (
            None
            if getattr(args, "destination_sequence_file", None) is None
            else str(args.destination_sequence_file.resolve())
        ),
        "operator_path": (
            None if args.operator_path is None else str(args.operator_path.resolve())
        ),
        "combat_handoffs_used": combat_handoffs_used,
        "steps": steps,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "execution_authority": False,
    }
    RESULT_VALIDATOR.validate(record)
    _write_json_atomic(args.result_file, record)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sequence separately authorized navigation and combat, then replan "
            "the unchanged journey from the fresh live position."
        )
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument(
        "--continuous-motion-authorization-file",
        type=Path,
        help="approved F4a movement authorization for the navigation child",
    )
    parser.add_argument(
        "--continuous-motion-arm-file",
        type=Path,
        help="short-lived F4a movement arm for the navigation child",
    )
    parser.add_argument(
        "--continuous-motion-revalidation-file",
        type=Path,
        help="fresh realm binding used to issue the F4a arm",
    )
    parser.add_argument(
        "--runtime-arm-wait-seconds",
        type=float,
        default=0.0,
        help=(
            "bounded wait after read-only child preflight for the operator "
            "to replace an expired F4a arm"
        ),
    )
    parser.add_argument(
        "--resume-on-runtime-arm-expiry",
        action="store_true",
        help=(
            "after a fail-closed F4a expiry, start another bounded navigation "
            "slice from the child checkpoint; a fresh arm must be supplied "
            "during the bounded wait"
        ),
    )
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--structure-probe-worker", type=Path)
    parser.add_argument(
        "--world-pack-profile", type=Path, default=DEFAULT_WORLD_PACK_PROFILE,
    )
    parser.add_argument(
        "--world-pack-store", type=Path, default=DEFAULT_WORLD_PACK_STORE,
    )
    parser.add_argument(
        "--world-structure-index", type=Path,
        default=DEFAULT_WORLD_STRUCTURE_INDEX,
    )
    parser.add_argument("--structure-access-graph", type=Path)
    parser.add_argument(
        "--semantic-catalog", type=Path, default=DEFAULT_SEMANTIC_CATALOG,
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--semantic-destination-id")
    destination.add_argument("--destination-sequence-file", type=Path)
    destination.add_argument("--operator-path", type=Path)
    destination.add_argument("--goal-normalized-x", type=float)
    parser.add_argument("--goal-normalized-y", type=float)
    parser.add_argument("--leveling-plan-file", type=Path)
    parser.add_argument("--map-id", type=int, default=0)
    parser.add_argument(
        "--expected-zone-index", type=int, choices=range(0, 65_536), default=25,
    )
    parser.add_argument(
        "--zone-transform-catalog", type=Path,
        default=DEFAULT_ZONE_TRANSFORM_CATALOG,
    )
    parser.add_argument("--start-world-z-hint", type=float, default=100.0)
    parser.add_argument("--operator-control-file", type=Path)
    parser.add_argument(
        "--traversed-surface-prior", type=Path,
        help=(
            "optional operator recording used as validated local evidence; "
            "omitted for autonomous navigation"
        ),
    )
    parser.add_argument("--max-control-frames", type=int, default=12_000)
    parser.add_argument(
        "--steering-controller",
        choices=(
            "geometric_predictive_v1",
            "continuous_trajectory_v1",
            "adaptive_trajectory_v1",
            "pa_mppi_v1",
        ),
        default="geometric_predictive_v1",
    )
    parser.add_argument("--mppi-batch-size", type=int, default=1_000)
    parser.add_argument("--mppi-time-steps", type=int, default=56)
    parser.add_argument("--maximum-navigation-cycles", type=int, default=64)
    parser.add_argument("--maximum-combat-handoffs", type=int, default=24)
    parser.add_argument("--combat-timeout-s", type=float, default=120.0)
    parser.add_argument("--activate-stealth", action="store_true")
    parser.add_argument(
        "--continue-through-routine-aggro",
        action="store_true",
        help=(
            "keep travelling through ordinary aggro instead of treating it "
            "as a route-planning failure"
        ),
    )
    parser.add_argument("--result-file", type=Path, default=DEFAULT_RESULT)
    parser.add_argument(
        "--dynamic-experience-store",
        type=Path,
        default=DEFAULT_DYNAMIC_EXPERIENCE_STORE,
    )
    parser.add_argument(
        "--acknowledge-autonomous-journey-combat", action="store_true",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.acknowledge_autonomous_journey_combat is not True:
        raise SystemExit("--acknowledge-autonomous-journey-combat is required")
    if (
        (args.continuous_motion_authorization_file is None)
        != (args.continuous_motion_arm_file is None)
    ):
        raise SystemExit(
            "continuous motion authorization and runtime arm must be supplied together"
        )
    if (
        args.continuous_motion_arm_file is not None
        and args.continuous_motion_revalidation_file is None
    ):
        raise SystemExit(
            "continuous motion runtime arm also requires realm revalidation"
        )
    if not 20 <= args.max_control_frames <= 18_000:
        raise SystemExit("--max-control-frames must be in [20, 18000]")
    if not 0.0 <= args.runtime_arm_wait_seconds <= 300.0:
        raise SystemExit("--runtime-arm-wait-seconds must be in [0, 300]")
    if args.resume_on_runtime_arm_expiry and args.runtime_arm_wait_seconds <= 0.0:
        raise SystemExit(
            "--resume-on-runtime-arm-expiry requires a positive "
            "--runtime-arm-wait-seconds"
        )
    if not 32 <= args.mppi_batch_size <= 20_000:
        raise SystemExit("--mppi-batch-size must be in [32, 20000]")
    if not 12 <= args.mppi_time_steps <= 160:
        raise SystemExit("--mppi-time-steps must be in [12, 160]")
    if not 1 <= args.maximum_navigation_cycles <= 128:
        raise SystemExit("--maximum-navigation-cycles must be in [1, 128]")
    if not 0 <= args.map_id <= 65_535:
        raise SystemExit("--map-id must be in [0, 65535]")
    if (args.goal_normalized_x is None) != (args.goal_normalized_y is None):
        raise SystemExit("normalized leveling goal requires both X and Y")
    if args.goal_normalized_x is not None and not all(
        0.0 <= value <= 1.0
        for value in (args.goal_normalized_x, args.goal_normalized_y)
    ):
        raise SystemExit("normalized leveling goal must be in [0, 1]")
    if not 0 <= args.maximum_combat_handoffs <= 64:
        raise SystemExit("--maximum-combat-handoffs must be in [0, 64]")
    if not 10.0 <= args.combat_timeout_s <= 300.0:
        raise SystemExit("--combat-timeout-s must be in [10, 300]")

    destination_sequence = None
    if args.destination_sequence_file is not None:
        try:
            destination_sequence = load_destination_sequence(
                args.destination_sequence_file
            )
        except (OSError, ValueError, TypeError) as error:
            raise SystemExit(f"invalid destination sequence: {error}") from error
        if (
            destination_sequence.map_id is not None
            and destination_sequence.map_id != args.map_id
        ):
            raise SystemExit(
                "destination sequence map_id does not match the selected WorldPack map"
            )
        try:
            validate_destination_sequence_catalog(
                destination_sequence, args.semantic_catalog,
            )
        except (OSError, ValueError, TypeError) as error:
            raise SystemExit(f"invalid destination sequence catalog: {error}") from error
        args.semantic_destination_ids = list(destination_sequence.destination_ids)
    else:
        args.semantic_destination_ids = (
            None
            if args.semantic_destination_id is None
            else [args.semantic_destination_id]
        )
    destination_ids = (
        destination_sequence.expanded_destination_ids()
        if destination_sequence is not None
        else (args.semantic_destination_id,)
    )
    destination_index = 0

    supervisor_id = f"journey-combat:{uuid4()}"
    steps: list[dict[str, Any]] = []
    combat_handoffs_used = 0
    _publish(
        args,
        supervisor_id=supervisor_id,
        status="STARTING",
        combat_handoffs_used=0,
        steps=steps,
    )
    terminal_status = "STOPPED_NAVIGATION_BUDGET"
    resume_result_for_navigation: Path | None = None
    for cycle in range(1, args.maximum_navigation_cycles + 1):
        try:
            navigation = subprocess.run(
                _navigation_command(
                    args,
                    destination_ids[destination_index],
                    resume_result=resume_result_for_navigation,
                ),
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=1_800.0,
                check=False,
                creationflags=CHILD_CREATION_FLAGS,
            )
            navigation_result = _typed_result_from_stdout(
                navigation.stdout,
                record_types={"navmesh_roaming_result"},
                stderr=navigation.stderr,
            )
        except (OSError, subprocess.TimeoutExpired, JourneyCombatSupervisorError) as error:
            steps.append({
                "kind": "CHILD_ERROR",
                "cycle": cycle,
                "status": "NAVIGATION_CHILD_FAILED",
                "runner": "NAVIGATION",
                "error_type": type(error).__name__,
                # Preserve the exception tail where Python places the actual
                # error type and message, rather than only the traceback head.
                "detail": str(error)[-1_000:],
                "execution_authority": False,
            })
            terminal_status = "STOPPED_CHILD_ERROR"
            break
        # A checkpoint is single-use metadata for the next child only.  Never
        # carry it across an unrelated status or destination transition.
        resume_result_for_navigation = None
        action = journey_supervisor_action(
            navigation_result,
            combat_handoffs_used=combat_handoffs_used,
            maximum_combat_handoffs=args.maximum_combat_handoffs,
        )
        if (
            action == "STOP_RUNTIME_ARM_EXPIRED"
            and args.resume_on_runtime_arm_expiry
        ):
            checkpoint = navigation_result.get("result_path")
            if isinstance(checkpoint, str) and checkpoint.strip():
                # The child has already released every control. Re-entry is
                # allowed only through read-only preflight and a newly issued
                # arm observed during its bounded wait.
                resume_result_for_navigation = Path(checkpoint)
                action = "RESUME_NAVIGATION"
        navigation_step = {
            "kind": "NAVIGATION_CYCLE",
            "cycle": cycle,
            "run_id": navigation_result.get("run_id"),
            "status": navigation_result.get("status"),
            "action": action,
            "final_world": navigation_result.get("final_world"),
            "resume_policy": navigation_result.get("resume_policy"),
            "execution_authority": False,
        }
        for evidence_key in (
            "in_combat",
            "health_fraction",
            "minimum_travel_health_fraction",
        ):
            if evidence_key in navigation_result:
                navigation_step[evidence_key] = navigation_result[evidence_key]
        steps.append(navigation_step)
        _publish(
            args,
            supervisor_id=supervisor_id,
            status="RUNNING",
            combat_handoffs_used=combat_handoffs_used,
            steps=steps,
        )
        if action == "COMPLETE":
            if destination_index + 1 < len(destination_ids):
                previous_destination = destination_ids[destination_index]
                destination_index += 1
                steps.append({
                    "kind": "DESTINATION_TRANSITION",
                    "cycle": cycle,
                    "status": "NEXT_LEG",
                    "action": "CONTINUE_SEQUENCE",
                    "from_destination_id": previous_destination,
                    "to_destination_id": destination_ids[destination_index],
                    "destination_index": destination_index,
                    "execution_authority": False,
                })
                _publish(
                    args,
                    supervisor_id=supervisor_id,
                    status="RUNNING",
                    combat_handoffs_used=combat_handoffs_used,
                    steps=steps,
                )
                continue
            _publish(
                args,
                supervisor_id=supervisor_id,
                status="ARRIVED",
                combat_handoffs_used=combat_handoffs_used,
                steps=steps,
            )
            print(json.dumps({
                "record_type": "journey_combat_supervisor_result",
                "supervisor_id": supervisor_id,
                "status": "ARRIVED",
                "result_file": str(args.result_file.resolve()),
                "execution_authority": False,
            }, sort_keys=True))
            return 0
        if action == "RESUME_NAVIGATION":
            continue
        if action != "HANDOFF_COMBAT":
            terminal_status = {
                "STOP_OPERATOR": "STOPPED_OPERATOR",
                "STOP_COMBAT_BUDGET": "STOPPED_COMBAT_BUDGET",
                # The result contract intentionally has no separate runtime-arm
                # terminal value.  Keep the precise child status in the
                # navigation step and publish the bounded fail-closed status.
                "STOP_RUNTIME_ARM_EXPIRED": "STOPPED_FAIL_CLOSED",
            }.get(action, "STOPPED_FAIL_CLOSED")
            break

        try:
            combat = subprocess.run(
                _combat_command(args, navigation_result),
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=args.combat_timeout_s,
                check=False,
                creationflags=CHILD_CREATION_FLAGS,
            )
            combat_result = _typed_result_from_stdout(
                combat.stdout,
                record_types={
                    "controlled_combat_result", "controlled_combat_failure",
                },
                stderr=combat.stderr,
            )
        except (OSError, subprocess.TimeoutExpired, JourneyCombatSupervisorError) as error:
            steps.append({
                "kind": "CHILD_ERROR",
                "cycle": cycle,
                "status": "COMBAT_CHILD_FAILED",
                "runner": "COMBAT",
                "error_type": type(error).__name__,
                "detail": str(error)[-1_000:],
                "execution_authority": False,
            })
            terminal_status = "STOPPED_CHILD_ERROR"
            break
        combat_handoffs_used += 1
        combat_succeeded = (
            combat_result.get("record_type") == "controlled_combat_result"
            and combat_result.get("status")
            in {"TARGET_DEFEATED", "ESCAPED_RISKY_AGGRO"}
        )
        escaped_risk_recorded = False
        if combat_result.get("status") == "ESCAPED_RISKY_AGGRO":
            final_world = navigation_result.get("final_world")
            map_name = navigation_result.get("map")
            navmesh_sha256 = navigation_result.get("navmesh_sha256")
            encounter_id = combat_result.get("encounter_id")
            navigation_run_id = navigation_result.get("run_id")
            final_world_z = navigation_result.get("final_world_z_hint")
            if (
                not isinstance(final_world, list)
                or len(final_world) != 2
                or not all(isinstance(value, (int, float)) for value in final_world)
                or not isinstance(map_name, str)
                or not isinstance(navmesh_sha256, str)
                or not isinstance(encounter_id, str)
                or not isinstance(navigation_run_id, str)
                or not isinstance(final_world_z, (int, float, type(None)))
            ):
                combat_succeeded = False
            else:
                observed_at_utc = (
                    datetime.now(timezone.utc).isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                escaped = escaped_risk_observation(
                    session_id=supervisor_id,
                    map_name=map_name,
                    navmesh_sha256=navmesh_sha256,
                    observed_at_utc=observed_at_utc,
                    observer_world_x=float(final_world[0]),
                    observer_world_y=float(final_world[1]),
                    observer_world_z=(
                        None if final_world_z is None else float(final_world_z)
                    ),
                    encounter_id=encounter_id,
                    navigation_run_id=navigation_run_id,
                )
                with DynamicExperienceStore(args.dynamic_experience_store) as store:
                    escaped_risk_recorded = store.append_escaped_risk(escaped)
        steps.append({
            "kind": "COMBAT_CYCLE",
            "cycle": combat_handoffs_used,
            "encounter_id": combat_result.get("encounter_id"),
            "status": combat_result.get("status"),
            "resume_navigation": combat_succeeded,
            "escaped_risk_recorded": escaped_risk_recorded,
            "execution_authority": False,
        })
        _publish(
            args,
            supervisor_id=supervisor_id,
            status="RUNNING" if combat_succeeded else "STOPPED_COMBAT_FAILED",
            combat_handoffs_used=combat_handoffs_used,
            steps=steps,
        )
        if not combat_succeeded:
            terminal_status = "STOPPED_COMBAT_FAILED"
            break

    _publish(
        args,
        supervisor_id=supervisor_id,
        status=terminal_status,
        combat_handoffs_used=combat_handoffs_used,
        steps=steps,
    )
    print(json.dumps({
        "record_type": "journey_combat_supervisor_result",
        "supervisor_id": supervisor_id,
        "status": terminal_status,
        "result_file": str(args.result_file.resolve()),
        "execution_authority": False,
    }, sort_keys=True))
    return 5


if __name__ == "__main__":
    raise SystemExit(run())
