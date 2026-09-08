from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
)
from perfect_assassin.movement.steering_simulation import (
    simulate_steering_batch,
)
from scripts.run_steering_monte_carlo import _scenario


TUNING_PIVOT_GAINS = (2.4, 3.4)


def _minimum_tuning_runs(value: str) -> int:
    try:
        runs = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("--runs must be an integer") from error
    if runs < 100:
        raise argparse.ArgumentTypeError("--runs must be at least 100")
    return runs


def _candidate_type(
    *, follow_gain: float, pivot_gain: float, maximum_delta: int,
    desired_heading_slew: float, acceleration_slew: int,
    clearance_preview_multiplier: float,
) -> type[PredictiveSteeringController]:
    return type(
        "SimulatedSteeringCandidate",
        (PredictiveSteeringController,),
        {
            "FOLLOW_YAW_GAIN_PER_S": follow_gain,
            "PIVOT_YAW_GAIN_PER_S": pivot_gain,
            "FOLLOW_MAX_MOUSE_DELTA": maximum_delta,
            "PIVOT_MAX_MOUSE_DELTA": maximum_delta + 2,
            "FOLLOW_DESIRED_HEADING_SLEW_RAD_PER_TICK": desired_heading_slew,
            "MOUSE_ACCEL_SLEW_PER_TICK": acceleration_slew,
            "MOUSE_BRAKE_SLEW_PER_TICK": max(3, acceleration_slew * 2),
            "CURVE_PREVIEW_FREE_HALF_WIDTH_MULTIPLIER": (
                clearance_preview_multiplier
            ),
        },
    )


def _tuning_scenarios(*, runs: int):
    """Use the complete deterministic scenario corpus for every candidate."""

    return (
        _scenario(
            "confined_straight", ((0, 0), (34, 0)), confined=True,
            runs=runs, maximum_cross_track_world=1.50,
            maximum_pivot_fraction=0.03, maximum_steering_sign_changes=3,
        ),
        _scenario(
            "confined_stair_bend",
            ((0, 0), (-23.7, 1.15), (-29.2, 0.08), (-31.4, -3.4),
             (-28.0, -7.5), (-20.0, -11.0)), confined=True,
            runs=runs, maximum_cross_track_world=2.00,
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
            (
                (0.0, 0.0), (1.29, -0.49), (2.57, -0.98),
                (3.86, -1.47), (5.15, -1.96), (6.43, -2.45),
                (7.72, -2.94), (17.96, -0.56),
            ),
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
            (
                (0.0, 0.0),
                (15.022949, -2.176392),
                (4.166504, -12.499948),
            ),
            confined=False, runs=runs, maximum_cross_track_world=2.00,
            maximum_pivot_fraction=0.30, maximum_steering_sign_changes=6,
            portal_width_world=2.20362,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search generic steering actuator tuning offline.",
    )
    parser.add_argument("--runs", type=_minimum_tuning_runs, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenarios = _tuning_scenarios(runs=args.runs)
    candidates: list[dict[str, object]] = []
    for follow_gain in (3.0, 3.2, 3.4):
        # Include the reviewed production pivot gain as a baseline candidate;
        # omitting it would make the search unable to compare against production.
        for pivot_gain in TUNING_PIVOT_GAINS:
            for maximum_delta in (9, 12):
                for desired_heading_slew in (0.30,):
                    for acceleration_slew in (3,):
                        for clearance_preview_multiplier in (1.8, 2.0, 2.2):
                            controller_type = _candidate_type(
                                follow_gain=follow_gain,
                                pivot_gain=pivot_gain,
                                maximum_delta=maximum_delta,
                                desired_heading_slew=desired_heading_slew,
                                acceleration_slew=acceleration_slew,
                                clearance_preview_multiplier=(
                                    clearance_preview_multiplier
                                ),
                            )
                            summaries = [
                                simulate_steering_batch(
                                    scenario,
                                    seed_offset=index * 100_000,
                                    controller_factory=controller_type,
                                )[0]
                                for index, scenario in enumerate(scenarios)
                            ]
                            candidates.append({
                                "follow_gain": follow_gain,
                                "pivot_gain": pivot_gain,
                                "maximum_delta": maximum_delta,
                                "desired_heading_slew": desired_heading_slew,
                                "acceleration_slew": acceleration_slew,
                                "clearance_preview_multiplier": (
                                    clearance_preview_multiplier
                                ),
                                "minimum_quality_pass_rate": min(
                                    item.quality_pass_rate for item in summaries
                                ),
                                "mean_quality_pass_rate": sum(
                                    item.quality_pass_rate for item in summaries
                                ) / len(summaries),
                                "summaries": [asdict(item) for item in summaries],
                            })
    candidates.sort(
        key=lambda item: (
            float(item["minimum_quality_pass_rate"]),
            float(item["mean_quality_pass_rate"]),
        ),
        reverse=True,
    )
    record = {
        "schema_version": "1.0",
        "record_type": "steering_tuning_search",
        "execution_authority": False,
        "candidate_count": len(candidates),
        "runs_per_scenario": args.runs,
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(candidates[:5], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
