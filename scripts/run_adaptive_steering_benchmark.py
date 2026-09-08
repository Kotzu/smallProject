from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.adaptive_steering import (
    AdaptiveTrajectorySteeringController,
)
from perfect_assassin.movement.mppi_steering import (
    MppiConfiguration,
    MppiSteeringController,
)
from perfect_assassin.movement.steering_simulation import (
    simulate_steering_batch,
)
from run_steering_monte_carlo import _scenario


def _scenarios(runs: int):
    return (
        _scenario(
            "confined_straight", ((0, 0), (34, 0)), confined=True,
            runs=runs, maximum_cross_track_world=1.50,
            maximum_pivot_fraction=0.03, maximum_steering_sign_changes=3,
        ),
        _scenario(
            "confined_stair_bend",
            ((0, 0), (-23.7, 1.15), (-29.2, 0.08), (-31.4, -3.4),
             (-28.0, -7.5), (-20.0, -11.0)),
            confined=True, runs=runs, maximum_cross_track_world=2.00,
            maximum_pivot_fraction=0.10, maximum_steering_sign_changes=4,
        ),
        _scenario(
            "narrow_s_gate",
            ((0, 0), (12, 0), (15, 3), (15, 8), (18, 11), (32, 11)),
            confined=False, runs=runs, maximum_cross_track_world=1.90,
            maximum_pivot_fraction=0.10, maximum_steering_sign_changes=4,
        ),
        _scenario(
            "open_ground_doodad_gateway",
            ((0.0, 0.0), (1.29, -0.49), (2.57, -0.98), (3.86, -1.47),
             (5.15, -1.96), (6.43, -2.45), (7.72, -2.94), (17.96, -0.56)),
            confined=False, runs=runs, maximum_cross_track_world=1.80,
            maximum_pivot_fraction=0.10, maximum_steering_sign_changes=4,
            portal_width_world=5.2,
            static_obstacles=((7.12, -0.48, 0.70),),
            doodad_avoidance_applied=True,
        ),
        _scenario(
            "straight_bridge", ((0, 0), (55, 0)), confined=False,
            runs=runs, maximum_cross_track_world=1.75,
            maximum_pivot_fraction=0.02, maximum_steering_sign_changes=2,
        ),
        _scenario(
            "narrow_outdoor_hairpin",
            ((0.0, 0.0), (15.022949, -2.176392), (4.166504, -12.499948)),
            confined=False, runs=runs, maximum_cross_track_world=2.00,
            maximum_pivot_fraction=0.30, maximum_steering_sign_changes=6,
            portal_width_world=2.20362,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark the geometry-adaptive steering selector offline."
    )
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 100 <= args.runs <= 100_000:
        parser.error("--runs must be in [100, 100000]")

    def controller_factory() -> AdaptiveTrajectorySteeringController:
        # Synchronous MPPI makes this benchmark deterministic and independent
        # of worker scheduling. Runtime uses the asynchronous equivalent.
        return AdaptiveTrajectorySteeringController(
            mppi_factory=lambda: MppiSteeringController(
                configuration=MppiConfiguration(
                    batch_size=128,
                    time_steps=24,
                    yaw_smoothness_weight=6.0,
                ),
                replan_interval_ticks=3,
            ),
        )

    records = []
    for index, scenario in enumerate(_scenarios(args.runs)):
        summary, runs = simulate_steering_batch(
            scenario,
            seed_offset=index * 100_000,
            controller_factory=controller_factory,
        )
        records.append(asdict(summary))

    report = {
        "schema_version": "1.0",
        "record_type": "adaptive_steering_benchmark",
        "execution_authority": False,
        "controller_id": "adaptive_trajectory_v1",
        "mppi_configuration": {
            "batch_size": 128,
            "time_steps": 24,
            "yaw_smoothness_weight": 6.0,
            "replan_interval_ticks": 3,
        },
        "summaries": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
