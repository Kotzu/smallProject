from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationObservation,
    simulate_steering_run,
)
from scripts.run_steering_monte_carlo import _scenario


SCENARIOS = {
    "confined_straight": (
        ((0, 0), (34, 0)), True, 1.50, 0.03,
    ),
    "confined_stair_bend": (
        ((0, 0), (-23.7, 1.15), (-29.2, 0.08), (-31.4, -3.4),
         (-28.0, -7.5), (-20.0, -11.0)),
        True, 2.0, 0.10,
    ),
    "narrow_s_gate": (
        ((0, 0), (12, 0), (15, 3), (15, 8), (18, 11), (32, 11)),
        False, 1.90, 0.10, 6.0, (),
    ),
    "open_ground_doodad_gateway": (
        (
            (0.0, 0.0), (1.29, -0.49), (2.57, -0.98),
            (3.86, -1.47), (5.15, -1.96), (6.43, -2.45),
            (7.72, -2.94), (17.96, -0.56),
        ),
        False, 1.80, 0.10, 5.2, ((7.12, -0.48, 0.70),),
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export one deterministic steering trajectory.",
    )
    parser.add_argument("scenario", choices=tuple(SCENARIOS))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario_record = SCENARIOS[args.scenario]
    if len(scenario_record) == 4:
        points, confined, cross_track, pivot_fraction = scenario_record
        portal_width, obstacles = 6.0, ()
    else:
        (
            points, confined, cross_track, pivot_fraction,
            portal_width, obstacles,
        ) = scenario_record
    scenario = _scenario(
        args.scenario, points, confined=confined, runs=100,
        maximum_cross_track_world=cross_track,
        maximum_pivot_fraction=pivot_fraction,
        maximum_steering_sign_changes=4,
        portal_width_world=portal_width,
        static_obstacles=obstacles,
        doodad_avoidance_applied=(
            args.scenario == "open_ground_doodad_gateway"
        ),
    )
    observations: list[SteeringSimulationObservation] = []
    result = simulate_steering_run(
        scenario, seed=args.seed, observation_sink=observations.append,
    )
    record = {
        "schema_version": "1.0",
        "record_type": "steering_simulation_trace",
        "execution_authority": False,
        "scenario_id": args.scenario,
        "seed": args.seed,
        "desired_path": [[point.x, point.y] for point in scenario.corridor.points],
        "result": asdict(result),
        "observations": [asdict(item) for item in observations],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
