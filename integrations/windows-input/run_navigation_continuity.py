from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
WINDOWS_INPUT = ROOT / "integrations" / "windows-input"
if str(WINDOWS_INPUT) not in sys.path:
    sys.path.insert(0, str(WINDOWS_INPUT))

from perfect_assassin.movement.client_continuity import (
    ContinuityAction,
    ContinuityPolicy,
    VisibleClientState,
    VisibleClientStateObservation,
)
from run_navmesh_roaming import (
    DEFAULT_ZONE_TRANSFORM_CATALOG,
    _load_zone_transform,
)
from perfect_assassin.runtime_paths import external_runtime_root


NAVIGATION_RUNNER = ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
OPERATOR_SCRIPT = ROOT / "scripts" / "Invoke-LabClientOperator.ps1"
RESET_SCRIPT = ROOT / "scripts" / "Reset-LabPlayerToSpawn.ps1"
GODMODE_SCRIPT = ROOT / "scripts" / "Set-LabCombatProtection.ps1"
DEFAULT_RECEIPT = ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
DEFAULT_WORKER = (
    ROOT / "data" / "runtime" / "native-build"
    / "pa_nav_probe-v25" / "Debug" / "pa_nav_probe.exe"
)
DEFAULT_NAV_ROOT = (
    external_runtime_root(ROOT) / "navigation" / "tbc243-human-road-corridor-v6"
)
DEFAULT_CONTINUITY_STATE = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "continuity" / "latest.json"
)
DEFAULT_SUPERVISOR_RESULT = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "continuity"
    / "supervisor-latest.json"
)


class NavigationContinuityError(RuntimeError):
    pass


def _write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _publish_supervisor_result(
    path: Path,
    *,
    status: str,
    semantic_destination_id: str,
    recovery_actions_used: int,
    steps: list[dict[str, Any]],
    last_result: dict[str, Any] | None,
    corpse_goal_world: tuple[float, float] | None = None,
    recovering_corpse: bool = False,
) -> None:
    _write_json_atomic(path, {
        "record_type": "navigation_continuity_result",
        "schema_version": "1.0",
        "status": status,
        "semantic_destination_id": semantic_destination_id,
        "last_runner_status": (
            None if last_result is None else last_result.get("status")
        ),
        "last_runner_run_id": (
            None if last_result is None else last_result.get("run_id")
        ),
        "recovery_actions_used": recovery_actions_used,
        "recovering_corpse": recovering_corpse,
        "corpse_goal_world": (
            None if corpse_goal_world is None else list(corpse_goal_world)
        ),
        "steps": steps,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "execution_authority": False,
    })


def _result_from_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(record, dict)
            and record.get("record_type") == "navmesh_roaming_result"
        ):
            return record
    raise NavigationContinuityError("navigation runner emitted no result record")


def _visible_observation(result: dict[str, Any]) -> VisibleClientStateObservation:
    raw = result.get("visible_client_state")
    if not isinstance(raw, dict):
        raise NavigationContinuityError("visible client state evidence is missing")
    try:
        state = VisibleClientState(str(raw["state"]))
        confidence = float(raw["confidence"])
    except (KeyError, TypeError, ValueError) as error:
        raise NavigationContinuityError("visible client state evidence is malformed") from error
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict):
        raise NavigationContinuityError("visible client state evidence is malformed")
    return VisibleClientStateObservation(
        state=state,
        confidence=confidence,
        evidence=dict(evidence),
    )


def _corpse_goal_from_result(result: dict[str, Any]) -> tuple[float, float]:
    final_world = result.get("final_world")
    if (
        not isinstance(final_world, list)
        or len(final_world) != 2
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            for value in final_world
        )
    ):
        raise NavigationContinuityError(
            "death observation contains no exact client-visible corpse position"
        )
    return float(final_world[0]), float(final_world[1])


def decide_supervisor_action(
    result: dict[str, Any],
    *,
    policy: ContinuityPolicy,
    recovery_actions_used: int,
    allow_lab_reset: bool,
    allow_lab_death_reset: bool,
    recovering_corpse: bool = False,
) -> str:
    status = result.get("status")
    if recovering_corpse and status == VisibleClientState.IN_WORLD.value:
        return "RESUME_MISSION"
    if status == "ARRIVED":
        return "RETRIEVE_CORPSE" if recovering_corpse else "COMPLETE"
    if status in {
        VisibleClientState.DISCONNECTED_DIALOG.value,
        VisibleClientState.LOGIN_SCREEN.value,
        VisibleClientState.CHARACTER_SELECT.value,
        VisibleClientState.DEAD_IN_WORLD.value,
        VisibleClientState.GHOST_IN_WORLD.value,
        VisibleClientState.UNKNOWN.value,
    }:
        action = policy.decide(
            _visible_observation(result),
            recovery_actions_used=recovery_actions_used,
        )
        if action is ContinuityAction.RELEASE_SPIRIT and allow_lab_death_reset:
            return "RESET_LAB_DEATH"
        return action.value
    if status in {
        "RESET_REQUIRED",
        "STUCK_REPLAN_REQUIRED",
        "PARTIAL_CORRIDOR_FRONTIER_STUCK",
        "PARTIAL_CORRIDOR_REPLAN_BUDGET_EXHAUSTED",
    }:
        return "RESET_LAB_STUCK" if allow_lab_reset else "STOP_STUCK"
    if status == "CONTROL_FRAME_BUDGET_EXHAUSTED":
        return "RESUME_NAVIGATION"
    if status in {"MANUAL_TAKEOVER", "OPERATOR_STOPPED"}:
        return "STOP_OPERATOR"
    return "STOP_FAIL_CLOSED"


def _run_checked(command: list[str], *, timeout_s: float) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-1000:] or completed.stdout.strip()[-1000:]
        raise NavigationContinuityError(detail or "bounded recovery command failed")


def _enable_lab_protection(
    *, player_name: str, wait_for_online_s: float,
) -> bool:
    """Enable test protection before any in-world navigation can be launched.

    Being offline is an expected continuity state, so the first probe is
    allowed to defer.  After EnterWorld the caller uses a bounded wait and
    fails closed if the server never confirms that the character is online.
    """
    deadline = time.monotonic() + max(0.0, wait_for_online_s)
    command = [
        "pwsh", "-NoProfile", "-NonInteractive",
        "-File", str(GODMODE_SCRIPT),
        "-State", "On", "-PlayerName", player_name,
    ]
    while True:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        if completed.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _operator_command(
    *,
    action: str,
    confirmed_visual_state: str,
    operator_authorization_file: Path | None,
) -> None:
    common = [
        "pwsh", "-NoProfile", "-NonInteractive",
        "-File", str(OPERATOR_SCRIPT),
        "-RepositoryRoot", str(ROOT),
    ]
    authorization = (
        []
        if operator_authorization_file is None
        else ["-AuthorizationFile", str(operator_authorization_file)]
    )
    _run_checked(
        [*common, "-Action", "ArmSession", *authorization, "-AcknowledgeRuntimeArm"],
        timeout_s=45.0,
    )
    _run_checked(
        [
            *common,
            "-Action", action,
            *authorization,
            "-ConfirmedVisualState", confirmed_visual_state,
        ],
        timeout_s=45.0,
    )


def _navigation_command(
    args: argparse.Namespace,
    *,
    corpse_goal_world: tuple[float, float] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(NAVIGATION_RUNNER),
        "--session-authorization-file", str(args.session_authorization_file),
        "--session-receipt", str(args.session_receipt),
        "--worker", str(args.worker),
        "--nav-root", str(args.nav_root),
        "--map-id", str(args.map_id),
        "--expected-zone-index", str(args.expected_zone_index),
        "--zone-transform-catalog", str(args.zone_transform_catalog),
        "--max-control-frames", str(args.max_control_frames),
        "--continuity-state-file", str(args.continuity_state_file),
        "--acknowledge-navmesh-roaming",
    ]
    if corpse_goal_world is None:
        command.extend([
            "--semantic-destination-id", args.semantic_destination_id,
        ])
    else:
        transform = _load_zone_transform(
            args.zone_transform_catalog,
            map_id=args.map_id,
            zone_index=args.expected_zone_index,
        )
        normalized_x, normalized_y = transform.normalized_from_world(
            *corpse_goal_world
        )
        command.extend([
            "--goal-normalized-x", f"{normalized_x:.12f}",
            "--goal-normalized-y", f"{normalized_y:.12f}",
            "--arrival-radius-world", "3.0",
            "--allow-ghost-navigation",
        ])
    if args.activate_stealth and corpse_goal_world is None:
        command.append("--activate-stealth")
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep one semantic navigation intent across visible client transitions."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--nav-root", type=Path, default=DEFAULT_NAV_ROOT)
    parser.add_argument("--semantic-destination-id", required=True)
    parser.add_argument(
        "--expected-zone-index", type=int, choices=range(0, 65_536), default=25,
    )
    parser.add_argument("--map-id", type=int, choices=range(0, 65_536), default=0)
    parser.add_argument(
        "--zone-transform-catalog", type=Path,
        default=DEFAULT_ZONE_TRANSFORM_CATALOG,
    )
    parser.add_argument("--max-control-frames", type=int, default=18_000)
    parser.add_argument("--maximum-recovery-actions", type=int, default=8)
    parser.add_argument("--maximum-runner-cycles", type=int, default=16)
    parser.add_argument("--maximum-stable-waits", type=int, default=12)
    parser.add_argument("--continuity-state-file", type=Path, default=DEFAULT_CONTINUITY_STATE)
    parser.add_argument("--result-file", type=Path, default=DEFAULT_SUPERVISOR_RESULT)
    parser.add_argument("--operator-authorization-file", type=Path)
    parser.add_argument("--player-name", default="Predator")
    parser.add_argument("--activate-stealth", action="store_true")
    parser.add_argument("--lab-reset-on-stuck", action="store_true")
    parser.add_argument("--lab-reset-on-death", action="store_true")
    parser.add_argument("--lab-protect-testing", action="store_true")
    parser.add_argument("--acknowledge-navigation-continuity", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.acknowledge_navigation_continuity:
        raise SystemExit("--acknowledge-navigation-continuity is required")
    if not 20 <= args.max_control_frames <= 18_000:
        raise SystemExit("--max-control-frames must be in [20, 18000]")
    if not 1 <= args.maximum_runner_cycles <= 32:
        raise SystemExit("--maximum-runner-cycles must be in [1, 32]")
    if not 1 <= args.maximum_stable_waits <= 60:
        raise SystemExit("--maximum-stable-waits must be in [1, 60]")
    policy = ContinuityPolicy(
        minimum_confidence=0.55,
        maximum_recovery_actions=args.maximum_recovery_actions,
    )
    protection_ready = False
    if args.lab_protect_testing:
        # A disconnected/login client is not an error here.  The supervisor
        # first restores the visible session and arms protection before it is
        # allowed to launch an in-world navigation cycle.
        protection_ready = _enable_lab_protection(
            player_name=args.player_name,
            wait_for_online_s=0.0,
        )

    recovery_actions_used = 0
    stable_waits = 0
    last_result: dict[str, Any] | None = None
    corpse_goal_world: tuple[float, float] | None = None
    recovering_corpse = False
    spirit_release_attempted = False
    corpse_retrieval_attempted = False
    steps: list[dict[str, Any]] = []
    _publish_supervisor_result(
        args.result_file,
        status="STARTING",
        semantic_destination_id=args.semantic_destination_id,
        recovery_actions_used=0,
        steps=steps,
        last_result=None,
        corpse_goal_world=corpse_goal_world,
        recovering_corpse=recovering_corpse,
    )
    for cycle in range(1, args.maximum_runner_cycles + 1):
        if args.lab_protect_testing and not protection_ready:
            protection_ready = _enable_lab_protection(
                player_name=args.player_name,
                wait_for_online_s=0.0,
            )
        completed = subprocess.run(
            _navigation_command(
                args,
                corpse_goal_world=(corpse_goal_world if recovering_corpse else None),
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=1_800.0,
            check=False,
        )
        last_result = _result_from_stdout(completed.stdout)
        action = decide_supervisor_action(
            last_result,
            policy=policy,
            recovery_actions_used=recovery_actions_used,
            allow_lab_reset=args.lab_reset_on_stuck,
            allow_lab_death_reset=args.lab_reset_on_death,
            recovering_corpse=recovering_corpse,
        )
        if action == ContinuityAction.RELEASE_SPIRIT.value and spirit_release_attempted:
            action = "STOP_RELEASE_SPIRIT_FAILED"
        if action == "RETRIEVE_CORPSE" and corpse_retrieval_attempted:
            action = "STOP_RETRIEVE_CORPSE_FAILED"
        step_record = {
            "record_type": "navigation_continuity_step",
            "schema_version": "1.0",
            "cycle": cycle,
            "runner_status": last_result.get("status"),
            "action": action,
            "recovery_actions_used": recovery_actions_used,
            "execution_authority": False,
        }
        steps.append(step_record)
        _publish_supervisor_result(
            args.result_file,
            status="RUNNING",
            semantic_destination_id=args.semantic_destination_id,
            recovery_actions_used=recovery_actions_used,
            steps=steps,
            last_result=last_result,
            corpse_goal_world=corpse_goal_world,
            recovering_corpse=recovering_corpse,
        )
        print(json.dumps(step_record, sort_keys=True), flush=True)
        if action == "COMPLETE":
            _publish_supervisor_result(
                args.result_file,
                status="ARRIVED",
                semantic_destination_id=args.semantic_destination_id,
                recovery_actions_used=recovery_actions_used,
                steps=steps,
                last_result=last_result,
                corpse_goal_world=corpse_goal_world,
                recovering_corpse=recovering_corpse,
            )
            return 0
        if action == "RESUME_MISSION":
            recovering_corpse = False
            corpse_goal_world = None
            spirit_release_attempted = False
            corpse_retrieval_attempted = False
            protection_ready = False
            stable_waits = 0
            continue
        if action == ContinuityAction.RESUME_NAVIGATION.value:
            stable_waits = 0
            continue
        if action == ContinuityAction.RECOVER_CORPSE.value:
            if corpse_goal_world is None:
                raise NavigationContinuityError(
                    "ghost state has no persisted client-visible corpse position"
                )
            recovering_corpse = True
            stable_waits = 0
            continue
        if action == ContinuityAction.WAIT_FOR_STABLE_FRAME.value:
            stable_waits += 1
            if stable_waits > args.maximum_stable_waits:
                break
            time.sleep(0.5)
            continue
        stable_waits = 0
        if action == ContinuityAction.ACKNOWLEDGE_DISCONNECT.value:
            protection_ready = False
            _operator_command(
                action="AcknowledgeDisconnect",
                confirmed_visual_state="DisconnectedDialog",
                operator_authorization_file=args.operator_authorization_file,
            )
        elif action == ContinuityAction.LOGIN.value:
            protection_ready = False
            _operator_command(
                action="Login",
                confirmed_visual_state="LoginScreen",
                operator_authorization_file=args.operator_authorization_file,
            )
        elif action == ContinuityAction.ENTER_WORLD.value:
            protection_ready = False
            _operator_command(
                action="EnterWorld",
                confirmed_visual_state="CharacterSelect",
                operator_authorization_file=args.operator_authorization_file,
            )
            if args.lab_protect_testing:
                protection_ready = _enable_lab_protection(
                    player_name=args.player_name,
                    wait_for_online_s=25.0,
                )
                if not protection_ready:
                    raise NavigationContinuityError(
                        "character entered the world but LAB protection was not confirmed"
                    )
        elif action == ContinuityAction.RELEASE_SPIRIT.value:
            corpse_goal_world = _corpse_goal_from_result(last_result)
            protection_ready = False
            _operator_command(
                action="ReleaseSpirit",
                confirmed_visual_state="DeadInWorld",
                operator_authorization_file=args.operator_authorization_file,
            )
            spirit_release_attempted = True
            recovering_corpse = True
            time.sleep(1.0)
        elif action == "RETRIEVE_CORPSE":
            _operator_command(
                action="RetrieveCorpse",
                confirmed_visual_state="GhostAtCorpse",
                operator_authorization_file=args.operator_authorization_file,
            )
            # Keep corpse mode until an exact alive frame is observed.  A
            # second GHOST arrival means the single retrieval input failed and
            # is stopped above rather than clicked repeatedly.
            corpse_retrieval_attempted = True
            protection_ready = False
            time.sleep(1.0)
        elif action in {"RESET_LAB_STUCK", "RESET_LAB_DEATH"}:
            _run_checked(
                [
                    "pwsh", "-NoProfile", "-NonInteractive",
                    "-File", str(RESET_SCRIPT), "-PlayerName", args.player_name,
                ],
                timeout_s=30.0,
            )
            time.sleep(1.0)
            protection_ready = False
        else:
            break
        recovery_actions_used += 1

    _publish_supervisor_result(
        args.result_file,
        status="STOPPED_FAIL_CLOSED",
        semantic_destination_id=args.semantic_destination_id,
        recovery_actions_used=recovery_actions_used,
        steps=steps,
        last_result=last_result,
        corpse_goal_world=corpse_goal_world,
        recovering_corpse=recovering_corpse,
    )
    print(args.result_file)
    return 5


if __name__ == "__main__":
    raise SystemExit(run())
