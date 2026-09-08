"""Offline counterexample audit, not a live acceptance or collision detector.

The native probe budgets body radius + tracking error around a planned line.
Exercise the real follower in the existing kinematic simulator and measure
distance to that line independently of the follower's progress projector.
No WoW assets, server state, input gateway or runtime configuration is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256
from itertools import pairwise
from math import cos, hypot, pi, sin
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.continuous_trajectory_follower import (
    ContinuousTrajectoryFollower,
)
from perfect_assassin.movement.predictive_steering import PredictiveSteeringController
from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationObservation,
    SteeringSimulationScenario,
    simulate_steering_run,
)

# Explicit audit assumptions, pinned to the native constants by a unit test.
# These do not introduce a new runtime policy or alter the native worker.
BODY_RADIUS = 0.389
TRACKING_MARGIN = 0.30
PROBED_RADIUS = BODY_RADIUS + TRACKING_MARGIN


def line_distance(x: float, y: float, points: tuple[NavPoint, ...]) -> float:
    """Euclidean distance to the entire synthetic XY polyline, no progress state."""
    distances = []
    for start, stop in pairwise(points):
        dx, dy = stop.x - start.x, stop.y - start.y
        length_squared = dx * dx + dy * dy
        fraction = (
            0.0
            if length_squared == 0.0
            else max(
                0.0,
                min(1.0, ((x - start.x) * dx + (y - start.y) * dy) / length_squared),
            )
        )
        distances.append(
            hypot(x - start.x - fraction * dx, y - start.y - fraction * dy)
        )
    if not distances:
        raise ValueError("audit needs a polyline with at least two points")
    return min(distances)


def make_scenario(
    name: str,
    *,
    corner: bool,
    mirror: bool = False,
    angle: float = 0.0,
    translate: tuple[float, float] = (0.0, 0.0),
    noisy: bool = True,
) -> SteeringSimulationScenario:
    def point(x: float, y: float) -> NavPoint:
        y = -y if mirror else y
        return NavPoint(
            x * cos(angle) - y * sin(angle) + translate[0],
            x * sin(angle) + y * cos(angle) + translate[1],
            0.0,
        )

    radius = PROBED_RADIUS
    if corner:
        xy = ((0.0, 0.0), (10.0, 0.0), (10.0, 15.0))
        split = 10.0 - radius
        rectangles = (
            (-radius, -radius, split, radius),
            (split, -radius, 10.0 + radius, 15.0 + radius),
        )
    else:
        xy = ((0.0, 0.0), (25.0, 0.0))
        split = 12.0
        rectangles = (
            (-radius, -radius, split, radius),
            (split, -radius, 25.0 + radius, radius),
        )
    points = tuple(point(x, y) for x, y in xy)
    polygons = []
    for index, (left, bottom, right, top) in enumerate(rectangles):
        vertices = tuple(
            point(x, y)
            for x, y in (
                (left, bottom),
                (right, bottom),
                (right, top),
                (left, top),
            )
        )
        if mirror:
            vertices = tuple(reversed(vertices))
        polygons.append(
            NavPolygon(
                index,
                0,
                0,
                0.0,
                point((left + right) / 2, (bottom + top) / 2),
                vertices,
                frozenset({"ground"}),
            )
        )
    portal_left, portal_right = point(split, radius), point(split, -radius)
    if mirror:
        portal_left, portal_right = portal_right, portal_left
    corridor = NavCorridor(
        "SyntheticTrackingAudit",
        0,
        0,
        points[0],
        points[-1],
        points,
        polygons=tuple(polygons),
        portals=(NavPortal(0, 1, portal_left, portal_right, 2 * radius),),
    )
    return SteeringSimulationScenario(
        name,
        corridor,
        runs=100,
        initial_lateral_jitter_world=0.15 if noisy else 0.0,
        initial_heading_jitter_rad=0.15 if noisy else 0.0,
        minimum_speed_world_per_s=8.75,
        maximum_speed_world_per_s=8.75,
        maximum_allowed_cross_track_world=TRACKING_MARGIN,
        maximum_allowed_pivot_fraction=0.02,
        actor_radius_world=BODY_RADIUS,
    )


def audit_scenario(
    scenario: SteeringSimulationScenario,
    *,
    runs: int = 100,
    controller_factory: Callable[
        [], PredictiveSteeringController
    ] = ContinuousTrajectoryFollower,
) -> dict[str, object]:
    if not 1 <= runs <= 10000:
        raise ValueError("audit runs must be between 1 and 10000")
    violating_runs = arrived = 0
    maximum_distance = maximum_pivot = 0.0
    maximum_sign_changes = 0
    initial_violations = 0
    first_violation = None
    for seed in range(runs):
        observations: list[SteeringSimulationObservation] = []
        result = simulate_steering_run(
            scenario,
            seed=seed,
            controller_factory=controller_factory,
            observation_sink=observations.append,
        )
        distances = [
            line_distance(item.x, item.y, scenario.corridor.points)
            for item in observations
        ]
        initial_violations += distances[0] > TRACKING_MARGIN + 1e-9
        maximum_distance = max(maximum_distance, *distances)
        violations = [
            index
            for index, distance in enumerate(distances)
            if distance > TRACKING_MARGIN + 1e-9
        ]
        violating_runs += bool(violations)
        arrived += result.completed
        maximum_pivot = max(maximum_pivot, result.pivot_fraction)
        maximum_sign_changes = max(maximum_sign_changes, result.steering_sign_changes)
        if violations and first_violation is None:
            index = violations[0]
            first_violation = {
                "seed": seed,
                "observation": asdict(observations[index]),
                "independent_distance_world": distances[index],
                "capsule_bound_world": BODY_RADIUS + distances[index],
            }
    passed = (
        violating_runs == 0
        and arrived == runs
        and maximum_pivot <= scenario.maximum_allowed_pivot_fraction
        and maximum_sign_changes <= scenario.maximum_allowed_steering_sign_changes
    )
    return {
        "scenario_id": scenario.scenario_id,
        "runs": runs,
        "geometry_aware": scenario.corridor.geometry_aware,
        "initial_outside_margin_runs": initial_violations,
        "arrived_runs": arrived,
        "outside_margin_runs": violating_runs,
        "maximum_distance_world": maximum_distance,
        "maximum_capsule_bound_world": BODY_RADIUS + maximum_distance,
        "maximum_pivot_fraction": maximum_pivot,
        "maximum_steering_sign_changes": maximum_sign_changes,
        "status": "PASS" if passed else "FAIL",
        "first_violation": first_violation,
    }


def run_audit(*, runs: int = 100) -> dict[str, object]:
    scenarios = (
        make_scenario("straight-aligned", corner=False, noisy=False),
        make_scenario("straight-perturbed", corner=False),
        make_scenario("left-corner-aligned", corner=True, noisy=False),
        make_scenario("left-corner-perturbed", corner=True),
        make_scenario("right-corner-perturbed", corner=True, mirror=True),
        make_scenario(
            "rotated-translated-corner", corner=True, angle=pi / 3, translate=(40, -30)
        ),
    )
    results = [audit_scenario(scenario, runs=runs) for scenario in scenarios]
    return {
        "schema_version": "1.0",
        "evidence": "synthetic_kinematic_not_live",
        "source_sha256": {
            path: sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "scripts/audit_tracking_clearance.py",
                "src/perfect_assassin/movement/continuous_trajectory_follower.py",
                "src/perfect_assassin/movement/predictive_steering.py",
                "src/perfect_assassin/movement/steering_simulation.py",
                "src/perfect_assassin/movement/client_navmesh.py",
                "native/pa_nav_probe/main.cpp",
            )
        },
        "controller": "ContinuousTrajectoryFollower",
        "body_radius_world": BODY_RADIUS,
        "tracking_margin_world": TRACKING_MARGIN,
        "probed_radius_world": PROBED_RADIUS,
        "status": "PASS" if all(row["status"] == "PASS" for row in results) else "FAIL",
        "limitations": [
            "No native inset/simplifier, raycast, actual wall contact or live input is executed.",
            "Exceeding the capsule bound invalidates this margin assumption; it does not prove collision.",
            "Kinematic observations are exact; pose perturbations and cadence variation are not sensor noise.",
            "A sharp synthetic corner is a stress case, not proof of native path admissibility.",
            "This calls the follower directly, not the full runtime supervisor or adaptive selector.",
            "PASS would cover these fixtures only, not authorize deployment or certify humanlike movement.",
        ],
        "scenarios": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_audit()
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"{report['status']}: {args.output}")
    else:
        print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
