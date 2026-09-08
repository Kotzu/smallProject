from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MPPI_BATCH_SIZE = 256
DEFAULT_MPPI_TIME_STEPS = 56
DEFAULT_MPPI_REPLAN_INTERVAL_TICKS = 3

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.mppi_steering import (
    MppiConfiguration,
    MppiSteeringController,
)
from perfect_assassin.movement.steering_simulation import (
    simulate_steering_batch,
    steering_run_passes_quality,
)
from perfect_assassin.movement.world_steering_corpus import (
    WorldSteeringCourseRequest,
    build_world_steering_scenario,
)


def _point(record: dict[str, Any]) -> NavPoint:
    return NavPoint(float(record["x"]), float(record["y"]), float(record["z"]))


def corridor_from_report_record(record: dict[str, Any]) -> NavCorridor:
    geometry = record["replay_geometry"]
    points = tuple(_point(item) for item in geometry["raw_points"])
    polygons = tuple(
        NavPolygon(
            index=int(item["index"]),
            area=int(item["area"]),
            polygon_type=int(item["polygon_type"]),
            slope_degrees=float(item["slope_degrees"]),
            centroid=_point(item["centroid"]),
            vertices=tuple(_point(point) for point in item["vertices"]),
            physical_surfaces=frozenset(item["physical_surfaces"]),
        )
        for item in geometry["polygons"]
    )
    portals = tuple(
        NavPortal(
            from_index=int(item["from_index"]),
            to_index=int(item["to_index"]),
            left=_point(item["left"]),
            right=_point(item["right"]),
            width=float(item["width"]),
        )
        for item in geometry["portals"]
    )
    return NavCorridor(
        map_name=str(record["map_name"]),
        adt_x=int(record["grid_x"]),
        adt_y=int(record["grid_y"]),
        start=_point(record["resolved_start"]),
        stop=_point(record["resolved_stop"]),
        points=points,
        polygons=polygons,
        portals=portals,
        doodad_avoidance_applied=bool(
            geometry["steering_attributes"]["doodad_avoidance_applied"],
        ),
        doodad_detour_count=int(
            geometry["steering_attributes"]["doodad_detour_count"],
        ),
        clearance_inset_count=int(
            geometry["steering_attributes"]["clearance_inset_count"],
        ),
    )


def _stable_seed(request_id: str) -> int:
    return int.from_bytes(
        hashlib.sha256(request_id.encode("utf-8")).digest()[:4], "little",
    )


def _parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay one retained real WorldPack corridor without rebuilding or "
            "querying the navmesh."
        ),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument(
        "--mppi-batch-size", type=int, default=DEFAULT_MPPI_BATCH_SIZE,
    )
    parser.add_argument(
        "--mppi-time-steps", type=int, default=DEFAULT_MPPI_TIME_STEPS,
    )
    parser.add_argument(
        "--mppi-replan-interval-ticks",
        type=int,
        default=DEFAULT_MPPI_REPLAN_INTERVAL_TICKS,
    )
    parser.add_argument(
        "--seed-offset", type=int, default=0,
        help="Deterministic non-overlapping shard offset for parallel replay.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main() -> int:
    arguments = _parse_arguments()
    if not 100 <= arguments.runs <= 100_000:
        raise ValueError("runs must be between 100 and 100000")
    if arguments.seed_offset < 0:
        raise ValueError("seed offset must be non-negative")
    report = json.loads(arguments.report.read_text(encoding="utf-8"))
    ContractValidator(
        ROOT / "contracts" / "world-steering-corpus-report.schema.json",
    ).validate(report)
    candidates = [
        item for item in report["corridors"]
        if arguments.request_id is None or item["request_id"] == arguments.request_id
    ]
    if len(candidates) != 1:
        raise ValueError("report selection must resolve exactly one corridor")
    source = candidates[0]
    corridor = corridor_from_report_record(source)
    request = WorldSteeringCourseRequest(
        request_id=source["request_id"],
        map_id=int(source["map_id"]),
        map_name=source["map_name"],
        grid_x=int(source["grid_x"]),
        grid_y=int(source["grid_y"]),
        start=corridor.start,
        stop=corridor.stop,
    )
    scenario = build_world_steering_scenario(
        request, corridor, runs=arguments.runs,
    )
    controller_factory = partial(
        MppiSteeringController,
        configuration=MppiConfiguration(
            batch_size=arguments.mppi_batch_size,
            time_steps=arguments.mppi_time_steps,
        ),
        replan_interval_ticks=arguments.mppi_replan_interval_ticks,
    )
    summary, trials = simulate_steering_batch(
        scenario,
        seed_offset=(
            _stable_seed(request.request_id) + arguments.seed_offset
        ),
        controller_factory=controller_factory,
    )
    result = {
        "record_type": "world_steering_corridor_replay",
        "source_report": str(arguments.report.resolve()),
        "request_id": request.request_id,
        "controller_configuration": {
            "batch_size": arguments.mppi_batch_size,
            "time_steps": arguments.mppi_time_steps,
            "replan_interval_ticks": arguments.mppi_replan_interval_ticks,
            "seed_offset": arguments.seed_offset,
        },
        "summary": asdict(summary),
        "quality_failures": [
            {"trial_index": index, **asdict(trial)}
            for index, trial in enumerate(trials)
            if not steering_run_passes_quality(scenario, trial)
        ],
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
