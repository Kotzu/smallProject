from __future__ import annotations

import argparse
from dataclasses import replace
import json
from math import hypot
import os
from pathlib import Path
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.manual_path_recording import ManualPathRecording
from perfect_assassin.movement.operator_demonstration_analysis import (
    analyze_operator_demonstration,
    planned_route_conformity,
)
from perfect_assassin.movement.road_semantic_planner import ClientRoadSemanticPlanner


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--road-sidecar-root", type=Path)
    parser.add_argument("--destination-x", type=float)
    parser.add_argument("--destination-y", type=float)
    args = parser.parse_args()
    timeline = [
        json.loads(line)
        for line in args.timeline.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    recording = ManualPathRecording.from_record(
        json.loads(args.path.read_text(encoding="utf-8"))
    )
    report = analyze_operator_demonstration(timeline, recording)
    optional = (args.road_sidecar_root, args.destination_x, args.destination_y)
    if any(value is not None for value in optional):
        if not all(value is not None for value in optional):
            raise SystemExit("road conformity requires sidecars and both destination values")
        start = recording.vertices[0]
        route = ClientRoadSemanticPlanner(sidecar_root=args.road_sidecar_root).plan(
            start_x=start.x,
            start_y=start.y,
            destination_x=args.destination_x,
            destination_y=args.destination_y,
        )
        planned_points = [(point.x, point.y) for point in route.waypoints]
        closest_index = min(
            range(len(recording.vertices)),
            key=lambda index: hypot(
                recording.vertices[index].x - args.destination_x,
                recording.vertices[index].y - args.destination_y,
            ),
        )
        outbound = replace(
            recording,
            status="RECORDING",
            vertices=recording.vertices[: closest_index + 1],
            imported_feature_id=None,
        )
        return_segment = replace(
            recording,
            status="RECORDING",
            vertices=recording.vertices[closest_index:],
            imported_feature_id=None,
        )
        report["semantic_destination_reach"] = {
            "closest_vertex_index": closest_index,
            "closest_distance_world": hypot(
                recording.vertices[closest_index].x - args.destination_x,
                recording.vertices[closest_index].y - args.destination_y,
            ),
        }
        report["planned_route_conformity"] = {
            "full_capture": planned_route_conformity(recording, planned_points),
            "outbound": planned_route_conformity(outbound, planned_points),
            "return_partial": planned_route_conformity(
                return_segment, planned_points
            ),
        }
    _atomic_json(args.output, report)
    print(json.dumps({"output": str(args.output), "status": "ANALYZED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
