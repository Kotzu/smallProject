from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from math import tau
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPolygon,
    NavPortal,
    NavPoint,
    LocalStaticAwareness,
    RadialClearanceProbe,
)
from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationScenario,
    simulate_steering_batch,
    steering_run_passes_quality,
)


def _simulate_scenario(
    indexed_scenario: tuple[int, SteeringSimulationScenario],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    """Run one deterministic situation in an isolated CPU process."""

    index, scenario = indexed_scenario
    seed_offset = index * 100_000
    summary, runs = simulate_steering_batch(
        scenario, seed_offset=seed_offset,
    )
    failures = [
        asdict(item) for item in runs if not item.completed
    ][:20]
    quality_failures = [
        {
            "seed": seed_offset + run_index,
            **asdict(item),
        }
        for run_index, item in enumerate(runs)
        if not steering_run_passes_quality(scenario, item)
    ][:20]
    return asdict(summary), failures, quality_failures


def _awareness(*, confined: bool) -> LocalStaticAwareness | None:
    if not confined:
        return None
    return LocalStaticAwareness(
        physical_surfaces=frozenset({"wmo"}),
        probe_radius_yards=12.0,
        overhead_clear=False,
        radial_probes=tuple(
            RadialClearanceProbe(index * tau / 16, 1.0, False)
            for index in range(16)
        ),
    )


def _scenario(
    scenario_id: str, points: tuple[tuple[float, float], ...], *, confined: bool,
    runs: int, maximum_cross_track_world: float,
    maximum_pivot_fraction: float,
    maximum_steering_sign_changes: int,
    portal_width_world: float = 6.0,
    static_obstacles: tuple[tuple[float, float, float], ...] = (),
    doodad_avoidance_applied: bool = False,
) -> SteeringSimulationScenario:
    nav = tuple(NavPoint(x, y, 0.0) for x, y in points)
    surface = frozenset({"wmo" if confined else "ground"})
    polygons = tuple(
        NavPolygon(
            index, 0, 0, 0.0, point,
            (
                NavPoint(point.x - 0.25, point.y - 0.25, 0.0),
                NavPoint(point.x + 0.25, point.y - 0.25, 0.0),
                NavPoint(point.x, point.y + 0.25, 0.0),
            ),
            surface,
        )
        for index, point in enumerate(nav)
    )
    portals = []
    for index, (start, stop) in enumerate(zip(nav, nav[1:])):
        dx, dy = stop.x - start.x, stop.y - start.y
        length = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / length, dx / length
        half = portal_width_world * 0.5
        portals.append(NavPortal(
            index, index + 1,
            NavPoint(stop.x + nx * half, stop.y + ny * half, 0.0),
            NavPoint(stop.x - nx * half, stop.y - ny * half, 0.0),
            portal_width_world,
        ))
    return SteeringSimulationScenario(
        scenario_id=scenario_id,
        corridor=NavCorridor(
            "Simulation", 0, 0, nav[0], nav[-1], nav,
            polygons=polygons,
            portals=tuple(portals),
            start_awareness=_awareness(confined=confined),
            doodad_avoidance_applied=doodad_avoidance_applied,
            doodad_detour_count=(1 if doodad_avoidance_applied else 0),
        ),
        runs=runs,
        maximum_allowed_cross_track_world=maximum_cross_track_world,
        maximum_allowed_pivot_fraction=maximum_pivot_fraction,
        maximum_allowed_steering_sign_changes=maximum_steering_sign_changes,
        static_obstacles=static_obstacles,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fast deterministic closed-loop steering simulations.",
    )
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument(
        "--jobs", type=int, default=1,
        help="Independent scenario processes (1-5).",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 5:
        parser.error("--jobs must be between 1 and 5")
    scenarios = (
        _scenario(
            "confined_straight", ((0, 0), (34, 0)), confined=True,
            runs=args.runs, maximum_cross_track_world=1.50,
            maximum_pivot_fraction=0.03, maximum_steering_sign_changes=3,
        ),
        _scenario(
            "confined_stair_bend",
            ((0, 0), (-23.7, 1.15), (-29.2, 0.08), (-31.4, -3.4),
             (-28.0, -7.5), (-20.0, -11.0)),
            confined=True, runs=args.runs, maximum_cross_track_world=2.00,
            maximum_pivot_fraction=0.10, maximum_steering_sign_changes=4,
        ),
        _scenario(
            "narrow_s_gate",
            ((0, 0), (12, 0), (15, 3), (15, 8), (18, 11), (32, 11)),
            confined=False, runs=args.runs, maximum_cross_track_world=1.90,
            maximum_pivot_fraction=0.10, maximum_steering_sign_changes=4,
        ),
        _scenario(
            "open_ground_doodad_gateway",
            (
                (0.0, 0.0), (1.29, -0.49), (2.57, -0.98),
                (3.86, -1.47), (5.15, -1.96), (6.43, -2.45),
                (7.72, -2.94), (17.96, -0.56),
            ),
            confined=False, runs=args.runs,
            maximum_cross_track_world=1.80,
            maximum_pivot_fraction=0.10,
            maximum_steering_sign_changes=4,
            portal_width_world=5.2,
            # One generic freestanding gateway post.  The nav corridor has
            # already detoured around it; steering must not round the detour
            # back into the actor-sized collision envelope.
            static_obstacles=((7.12, -0.48, 0.70),),
            doodad_avoidance_applied=True,
        ),
        _scenario(
            "straight_bridge", ((0, 0), (55, 0)), confined=False,
            runs=args.runs, maximum_cross_track_world=1.75,
            maximum_pivot_fraction=0.02, maximum_steering_sign_changes=2,
        ),
        _scenario(
            "narrow_outdoor_hairpin",
            (
                (0.0, 0.0),
                (15.022949, -2.176392),
                (4.166504, -12.499948),
            ),
            confined=False, runs=args.runs,
            maximum_cross_track_world=2.00,
            maximum_pivot_fraction=0.30,
            maximum_steering_sign_changes=6,
            # Captured from the exact standalone WorldPack corridor that
            # caused the rare 4.43 yd live departure on the road to Brill.
            portal_width_world=2.20362,
        ),
    )
    indexed_scenarios = tuple(enumerate(scenarios))
    if args.jobs == 1:
        scenario_results = tuple(map(_simulate_scenario, indexed_scenarios))
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            scenario_results = tuple(
                executor.map(_simulate_scenario, indexed_scenarios)
            )
    summaries = []
    failures: dict[str, list[dict[str, object]]] = {}
    quality_failures: dict[str, list[dict[str, object]]] = {}
    for scenario, (summary, scenario_failures, scenario_quality_failures) in zip(
        scenarios, scenario_results,
    ):
        summaries.append(summary)
        failures[scenario.scenario_id] = scenario_failures
        quality_failures[scenario.scenario_id] = scenario_quality_failures
    record = {
        "schema_version": "1.0",
        "record_type": "steering_monte_carlo_report",
        "execution_authority": False,
        "summaries": summaries,
        "sample_failures": failures,
        "sample_quality_failures": quality_failures,
    }
    rendered = json.dumps(record, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
