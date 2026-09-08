from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import cos, isfinite, pi, sin, sqrt
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
NAV_RUNNER = ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
COMBAT_RUNNER = ROOT / "integrations" / "windows-input" / "run_controlled_combat.py"
RESULT_ROOT = ROOT / "data" / "runtime" / "hunting" / "results"
LOG_ROOT = ROOT / "data" / "runtime" / "hunting" / "logs"
NAV_RESULT_ROOT = ROOT / "data" / "runtime" / "navigation-f3b" / "results"
COMBAT_RESULT_ROOT = ROOT / "data" / "runtime" / "combat-f4a" / "results"
CLIENT_BUILD = 8606
COORDINATE_SYSTEM = "normalized_current_zone_map"
GOLDEN_ANGLE = pi * (3.0 - sqrt(5.0))
SEMANTIC_DESTINATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
LOCAL_REACHABILITY_FAILURES = frozenset({
    "PARTIAL_CORRIDOR_FRONTIER_STUCK",
    "PARTIAL_CORRIDOR_REPLAN_BUDGET_EXHAUSTED",
    "STUCK_REPLAN_REQUIRED",
})
MAX_SEARCH_VANTAGE_OFFSET_WORLD = 8.0
NON_DAMAGE_ACQUISITION_ACTIONS = frozenset({
    "combat.acquire_hostile_target",
    "combat.scan_for_hostile_target",
    "combat.scan_for_hostile_target_left",
    "combat.monitor_continuous_facing",
    "combat.monitor_continuous_reacquisition",
})
NON_DAMAGE_ACQUISITION_CONTROLS = frozenset({
    "TARGET_NEAREST_HOSTILE", "TURN_LEFT", "TURN_RIGHT",
})


class HuntingEngineError(RuntimeError):
    pass


def _read_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise HuntingEngineError(f"{path.name} is unreadable") from error
    if not isinstance(value, dict):
        raise HuntingEngineError(f"{path.name} must contain an object")
    return value


def _atomic_write(path: Path, value: dict[str, object]) -> None:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise HuntingEngineError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise HuntingEngineError(f"{label} is invalid") from error
    if parsed.tzinfo is None:
        raise HuntingEngineError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def load_search_region(path: Path, *, now: datetime) -> dict[str, object]:
    record = _read_object(path)
    center = record.get("center_normalized")
    radius = record.get("radius_normalized")
    evidence_refs = record.get("evidence_refs")
    semantic_entry = record.get("entry_semantic_destination_id")
    if (
        record.get("record_type") != "predator_search_region_memory"
        or record.get("schema_version") != "1.0"
        or record.get("client_build") != CLIENT_BUILD
        or record.get("coordinate_system") != COORDINATE_SYSTEM
        or record.get("map") != "Azeroth"
        or record.get("zone_index") != 25
        or record.get("goal_kind") != "hostile_mob"
        or record.get("source_origin") not in {
            "client_observed", "predator_memory", "route_teacher", "external_research"
        }
        or record.get("execution_authority") is not False
        or not isinstance(center, list)
        or len(center) != 2
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            for value in center
        )
        or isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or not 0.002 <= float(radius) <= 0.05
        or not isinstance(evidence_refs, list)
        or not 1 <= len(evidence_refs) <= 8
        or any(not isinstance(ref, str) or not ref for ref in evidence_refs)
        or (
            semantic_entry is not None
            and (
                not isinstance(semantic_entry, str)
                or SEMANTIC_DESTINATION_ID.fullmatch(semantic_entry) is None
                or ".." in semantic_entry
            )
        )
    ):
        raise HuntingEngineError("search region memory is outside the bounded client contract")
    if _parse_timestamp(record.get("expires_at"), label="expires_at") <= now:
        raise HuntingEngineError("search region memory has expired")
    return record


def patrol_points(
    *, center_x: float, center_y: float, radius: float, count: int,
) -> tuple[tuple[float, float], ...]:
    if not 1 <= count <= 8:
        raise ValueError("patrol point count must remain in [1, 8]")
    points = []
    for index in range(count):
        distance = radius * sqrt((index + 1) / count)
        angle = GOLDEN_ANGLE * index
        points.append((
            min(1.0, max(0.0, center_x + cos(angle) * distance)),
            min(1.0, max(0.0, center_y + sin(angle) * distance)),
        ))
    return tuple(points)


def local_navigation_disposition(record: dict[str, object]) -> str:
    status = record.get("status")
    if status == "ARRIVED":
        return "ACCEPTED_ARRIVAL"
    if status == "SEARCH_VANTAGE_REJECTED":
        return "SKIP_UNSUITABLE_VANTAGE"
    if status not in LOCAL_REACHABILITY_FAILURES:
        return "STOP_FAIL_CLOSED"
    remaining = record.get("remaining_world")
    if (
        not isinstance(remaining, bool)
        and isinstance(remaining, (int, float))
        and isfinite(float(remaining))
        and 0.0 <= float(remaining) <= MAX_SEARCH_VANTAGE_OFFSET_WORLD
    ):
        return "ACCEPTED_NEAR_FRONTIER"
    return "SKIP_UNREACHABLE_SAMPLE"


def combat_search_disposition(record: dict[str, object]) -> str:
    if record.get("status") == "TARGET_DEFEATED":
        return "TARGET_DEFEATED"
    if record.get("status") != "STOPPED_FAIL_CLOSED":
        return "STOP_FAIL_CLOSED"
    detail = record.get("detail")
    if detail == (
        "authorized target cycle did not produce a new target within the "
        "observation budget"
    ):
        return "CONTINUE_PATROL_NO_TARGET"
    if detail == "no visible attackable candidate within bounded search":
        return "CONTINUE_PATROL_NO_VISIBLE_CANDIDATE"
    decisions = record.get("decisions")
    executions = record.get("executions")
    if (
        detail == "combat acquisition deadline expired"
        and isinstance(decisions, list)
        and decisions
        and isinstance(executions, list)
        and all(
            isinstance(decision, dict)
            and decision.get("action_id") in NON_DAMAGE_ACQUISITION_ACTIONS
            for decision in decisions
        )
        and all(
            isinstance(execution, dict)
            and execution.get("control") in NON_DAMAGE_ACQUISITION_CONTROLS
            for execution in executions
        )
    ):
        return "CONTINUE_PATROL_TARGET_BEYOND_VISUAL_RANGE"
    return "STOP_FAIL_CLOSED"


def _new_result(
    root: Path, *, before: set[Path], record_type: str,
) -> tuple[Path, dict[str, object]]:
    candidates = sorted(
        (path for path in root.glob("*.json") if path.resolve() not in before),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if len(candidates) != 1:
        raise HuntingEngineError(
            f"expected exactly one new {record_type} result, found {len(candidates)}"
        )
    record = _read_object(candidates[0])
    return candidates[0].resolve(), record


def _run_child(
    *,
    args: list[str],
    log_path: Path,
    result_root: Path,
    record_type: str,
    timeout_s: float = 180.0,
) -> tuple[int, Path, dict[str, object]]:
    before = {path.resolve() for path in result_root.glob("*.json")}
    completed = subprocess.run(
        args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout, encoding="utf-8")
    result_path, record = _new_result(
        result_root, before=before, record_type=record_type,
    )
    return completed.returncode, result_path, record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Alternate client-navmesh roaming and bounded autonomous NPC combat."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument("--region-memory-file", type=Path, required=True)
    parser.add_argument("--max-patrol-points", type=int, choices=range(1, 9), default=6)
    parser.add_argument("--max-navigation-frames", type=int, default=2600)
    parser.add_argument("--max-entry-navigation-frames", type=int, default=9000)
    parser.add_argument("--acknowledge-autonomous-hunt", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.acknowledge_autonomous_hunt:
        raise SystemExit("--acknowledge-autonomous-hunt is required")
    if not 20 <= args.max_navigation_frames <= 18_000:
        raise SystemExit("--max-navigation-frames must remain in [20, 18000]")
    if not 20 <= args.max_entry_navigation_frames <= 18_000:
        raise SystemExit("--max-entry-navigation-frames must remain in [20, 18000]")
    if not args.session_authorization_file.is_file():
        raise SystemExit("active session authorization is required")
    region = load_search_region(
        args.region_memory_file, now=datetime.now(timezone.utc),
    )
    center = region["center_normalized"]
    assert isinstance(center, list)
    points = patrol_points(
        center_x=float(center[0]),
        center_y=float(center[1]),
        radius=float(region["radius_normalized"]),
        count=args.max_patrol_points,
    )
    run_id = f"hunt:{uuid4()}"
    attempts: list[dict[str, object]] = []
    status = "SEARCH_REGION_EXHAUSTED"
    semantic_entry = region.get("entry_semantic_destination_id")
    patrol_allowed = True
    if isinstance(semantic_entry, str):
        nav_code, nav_path, nav = _run_child(
            args=[
                sys.executable,
                str(NAV_RUNNER),
                "--session-authorization-file", str(args.session_authorization_file),
                "--semantic-destination-id", semantic_entry,
                "--expected-zone-index", "25",
                "--max-control-frames", str(args.max_entry_navigation_frames),
                "--acknowledge-navmesh-roaming",
            ],
            log_path=LOG_ROOT / f"{run_id.rsplit(':', 1)[-1]}-entry-nav.log",
            result_root=NAV_RESULT_ROOT,
            record_type="navmesh roaming",
            timeout_s=480.0,
        )
        attempts.append({
            "phase": "REGION_ENTRY",
            "semantic_destination_id": semantic_entry,
            "navigation_result": str(nav_path),
            "navigation_status": nav.get("status"),
            "navigation_return_code": nav_code,
        })
        if nav.get("status") != "ARRIVED":
            status = "NAVIGATION_STOPPED_FAIL_CLOSED"
            patrol_allowed = False
    for index, (x, y) in enumerate(points if patrol_allowed else ()):
        nav_code, nav_path, nav = _run_child(
            args=[
                sys.executable,
                str(NAV_RUNNER),
                "--session-authorization-file", str(args.session_authorization_file),
                "--goal-normalized-x", repr(x),
                "--goal-normalized-y", repr(y),
                "--expected-zone-index", "25",
                "--max-control-frames", str(args.max_navigation_frames),
                "--arrival-radius-world", "2.0",
                "--require-open-search-vantage",
                "--acknowledge-navmesh-roaming",
            ],
            log_path=LOG_ROOT / f"{run_id.rsplit(':', 1)[-1]}-{index:02d}-nav.log",
            result_root=NAV_RESULT_ROOT,
            record_type="navmesh roaming",
        )
        attempt: dict[str, object] = {
            "phase": "LOCAL_PATROL",
            "patrol_index": index,
            "destination_normalized": [x, y],
            "navigation_result": str(nav_path),
            "navigation_status": nav.get("status"),
            "navigation_return_code": nav_code,
        }
        attempts.append(attempt)
        disposition = local_navigation_disposition(nav)
        attempt["navigation_disposition"] = disposition
        if disposition in {"SKIP_UNREACHABLE_SAMPLE", "SKIP_UNSUITABLE_VANTAGE"}:
            continue
        if disposition == "STOP_FAIL_CLOSED":
            status = "NAVIGATION_STOPPED_FAIL_CLOSED"
            break
        combat_code, combat_path, combat = _run_child(
            args=[
                sys.executable,
                str(COMBAT_RUNNER),
                "--session-authorization-file", str(args.session_authorization_file),
                "--initial-search-direction", "RIGHT" if index % 2 == 0 else "LEFT",
                "--acknowledge-controlled-combat",
            ],
            log_path=LOG_ROOT / f"{run_id.rsplit(':', 1)[-1]}-{index:02d}-combat.log",
            result_root=COMBAT_RESULT_ROOT,
            record_type="controlled combat",
        )
        attempt.update({
            "combat_result": str(combat_path),
            "combat_status": combat.get("status"),
            "combat_detail": combat.get("detail"),
            "combat_return_code": combat_code,
            "target_identity_crc16": combat.get("target_identity_crc16"),
        })
        combat_disposition = combat_search_disposition(combat)
        attempt["combat_disposition"] = combat_disposition
        if combat_disposition == "TARGET_DEFEATED":
            status = "TARGET_DEFEATED"
            break
        if not combat_disposition.startswith("CONTINUE_PATROL_"):
            status = "COMBAT_STOPPED_FAIL_CLOSED"
            break
    result = {
        "record_type": "autonomous_hunt_result",
        "schema_version": "1.0",
        "run_id": run_id,
        "status": status,
        "region_id": region.get("region_id"),
        "region_memory_file": str(args.region_memory_file.resolve()),
        "patrol_point_count": len(points),
        "attempts": attempts,
        "manual_takeover_hotkey": "Pause",
        "execution_authority": False,
    }
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    result_path = RESULT_ROOT / f"autonomous-hunt-{run_id.rsplit(':', 1)[-1]}.json"
    _atomic_write(result_path, result)
    print(json.dumps({"result_path": str(result_path.resolve()), **result}, sort_keys=True))
    return 0 if status == "TARGET_DEFEATED" else 3


if __name__ == "__main__":
    raise SystemExit(run())
