from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.runtime_paths import external_runtime_root


RUNNER = ROOT / "integrations" / "windows-input" / "run_navmesh_roaming.py"
DEFAULT_ROUTE = (
    ROOT
    / "config"
    / "movement-lab"
    / "deathknell-to-brill-main-road.json"
)
DEFAULT_WORKER = (
    ROOT
    / "data"
    / "runtime"
    / "native-build"
    / "pa_nav_probe-pinned"
    / "Debug"
    / "pa_nav_probe.exe"
)
DEFAULT_NAV_ROOT = (
    external_runtime_root(ROOT) / "navigation" / "tbc243-deathknell-brill-rect-v1"
)
RESULT_ROOT = ROOT / "data" / "runtime" / "journey-routes" / "results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one reviewed multi-stage journey without intermediate teleports."
    )
    parser.add_argument("--session-authorization-file", type=Path, required=True)
    parser.add_argument("--route", type=Path, default=DEFAULT_ROUTE)
    parser.add_argument("--worker", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--nav-root", type=Path, default=DEFAULT_NAV_ROOT)
    parser.add_argument("--max-control-frames-per-stage", type=int, default=1200)
    parser.add_argument("--operator-control-file", type=Path)
    parser.add_argument("--acknowledge-reviewed-journey", action="store_true")
    return parser


def _last_json_line(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                return value
            break
    raise RuntimeError("navigation stage returned no result record")


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.acknowledge_reviewed_journey:
        raise SystemExit("--acknowledge-reviewed-journey is required")
    if not 100 <= args.max_control_frames_per_stage <= 1200:
        raise SystemExit("stage frame budget must be in [100, 1200]")

    route = json.loads(args.route.read_text(encoding="utf-8"))
    goals = route.get("goals")
    if route.get("record_type") != "reviewed_journey_route" or not isinstance(goals, list):
        raise RuntimeError("reviewed journey route is malformed")

    journey_id = f"journey:{uuid4()}"
    resume_result: Path | None = None
    stage_results: list[dict[str, object]] = []
    for index, goal in enumerate(goals, start=1):
        if not isinstance(goal, dict):
            raise RuntimeError("reviewed journey goal is malformed")
        normalized = goal.get("normalized")
        if not isinstance(normalized, list) or len(normalized) != 2:
            raise RuntimeError("reviewed journey goal has no normalized position")
        command = [
            sys.executable,
            str(RUNNER),
            "--session-authorization-file",
            str(args.session_authorization_file),
            "--worker",
            str(args.worker),
            "--nav-root",
            str(args.nav_root),
            "--goal-normalized-x",
            str(normalized[0]),
            "--goal-normalized-y",
            str(normalized[1]),
            "--expected-zone-index",
            str(route["zone_index"]),
            "--start-world-z-hint",
            str(goal["start_world_z_hint"]),
            "--max-control-frames",
            str(args.max_control_frames_per_stage),
            "--acknowledge-navmesh-roaming",
        ]
        if resume_result is not None:
            command.extend(["--resume-result", str(resume_result)])
        if args.operator_control_file is not None:
            command.extend(["--operator-control-file", str(args.operator_control_file)])
        lookahead_world = goal.get("lookahead_world")
        if lookahead_world is not None:
            command.extend(["--lookahead-world", str(lookahead_world)])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=1_800.0 if args.operator_control_file is not None else 90.0,
            check=False,
        )
        try:
            result = _last_json_line(completed.stdout)
        except Exception as error:
            raise RuntimeError(
                f"journey stage {index} failed before result: {completed.stderr[-800:]}"
            ) from error
        result_path = result.get("result_path")
        stage_results.append(
            {
                "index": index,
                "name": goal.get("name"),
                "status": result.get("status"),
                "result_path": result_path,
                "final_world": result.get("final_world"),
                "remaining_world": result.get("remaining_world"),
            }
        )
        print(json.dumps(stage_results[-1], sort_keys=True), flush=True)
        if completed.returncode != 0 or result.get("status") != "ARRIVED":
            break
        if not isinstance(result_path, str):
            raise RuntimeError("navigation stage did not expose its result path")
        resume_result = Path(result_path)

    status = "ARRIVED" if len(stage_results) == len(goals) and all(
        stage["status"] == "ARRIVED" for stage in stage_results
    ) else "STOPPED_AT_STAGE"
    record = {
        "record_type": "reviewed_journey_result",
        "schema_version": "0.1",
        "journey_id": journey_id,
        "route_id": route.get("route_id"),
        "status": status,
        "teleports_after_start": 0,
        "stages": stage_results,
        "execution_authority": False,
    }
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    result_path = RESULT_ROOT / f"{journey_id.replace(':', '-')}.json"
    result_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps({"result_path": str(result_path), **record}, sort_keys=True))
    return 0 if status == "ARRIVED" else 3


if __name__ == "__main__":
    raise SystemExit(run())
