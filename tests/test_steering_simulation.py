from __future__ import annotations

import unittest
from itertools import pairwise

from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.adaptive_steering import (
    AdaptiveTrajectorySteeringController,
)
from perfect_assassin.movement.mppi_steering import (
    MppiConfiguration,
    MppiSteeringController,
)
from perfect_assassin.movement.predictive_steering import (
    PredictiveSteeringController,
)
from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationScenario,
    simulate_steering_batch,
    steering_run_passes_quality,
)


class SteeringSimulationTests(unittest.TestCase):
    def test_batch_is_deterministic_and_runs_at_least_one_hundred_trials(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(40, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(40, 0, 0)),
        )
        scenario = SteeringSimulationScenario("straight", corridor, runs=100)

        first, first_runs = simulate_steering_batch(scenario, seed_offset=41)
        second, second_runs = simulate_steering_batch(scenario, seed_offset=41)

        self.assertEqual(first, second)
        self.assertEqual(first_runs, second_runs)
        self.assertEqual(first.runs, 100)
        self.assertEqual(first.completed_runs, 100)
        self.assertEqual(first.quality_passed_runs, 100)
        self.assertEqual(first.quality_pass_rate, 1.0)

    def test_arrival_alone_does_not_hide_robotic_steering(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(40, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(40, 0, 0)),
        )
        strict = SteeringSimulationScenario(
            "strict", corridor, runs=100,
            maximum_allowed_cross_track_world=0.1,
        )
        summary, runs = simulate_steering_batch(strict, seed_offset=41)

        self.assertEqual(summary.completed_runs, 100)
        self.assertLess(summary.quality_passed_runs, 100)
        self.assertTrue(any(
            item.completed and not steering_run_passes_quality(strict, item)
            for item in runs
        ))

    def test_scenario_rejects_fewer_than_one_hundred_trials(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(10, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(10, 0, 0)),
        )
        with self.assertRaisesRegex(ValueError, "scenario is invalid"):
            SteeringSimulationScenario("too-small", corridor, runs=99)

    def test_batch_can_evaluate_a_candidate_without_mutating_production(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(40, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(40, 0, 0)),
        )
        scenario = SteeringSimulationScenario("candidate", corridor, runs=100)
        production_gain = PredictiveSteeringController.FOLLOW_YAW_GAIN_PER_S

        class Candidate(PredictiveSteeringController):
            FOLLOW_YAW_GAIN_PER_S = 2.0

        summary, _ = simulate_steering_batch(
            scenario, controller_factory=Candidate,
        )

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(
            PredictiveSteeringController.FOLLOW_YAW_GAIN_PER_S,
            production_gain,
        )

        with self.assertRaisesRegex(TypeError, "incompatible controller"):
            simulate_steering_batch(
                scenario, controller_factory=lambda: object(),  # type: ignore[arg-type]
            )

    def test_static_obstacle_collision_fails_quality_gate(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(20, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(20, 0, 0)),
        )
        scenario = SteeringSimulationScenario(
            "blocked-straight", corridor, runs=100,
            initial_lateral_jitter_world=0.0,
            initial_heading_jitter_rad=0.0,
            static_obstacles=((10.0, 0.0, 0.5),),
        )

        summary, runs = simulate_steering_batch(scenario)

        self.assertEqual(summary.collision_runs, 100)
        self.assertEqual(summary.quality_passed_runs, 0)
        self.assertTrue(all(item.terminal_state == "COLLISION" for item in runs))
        self.assertLessEqual(summary.minimum_obstacle_clearance_world or 0.0, 0.0)

    def test_doodad_detour_keeps_actor_capsule_outside_obstacle(self) -> None:
        points = tuple(
            NavPoint(x, y, 0.0)
            for x, y in (
                (0.0, 0.0), (1.29, -0.49), (2.57, -0.98),
                (3.86, -1.47), (5.15, -1.96), (6.43, -2.45),
                (7.72, -2.94), (17.96, -0.56),
            )
        )
        corridor = NavCorridor(
            "Simulation", 0, 0, points[0], points[-1], points,
            doodad_avoidance_applied=True,
            doodad_detour_count=1,
        )
        scenario = SteeringSimulationScenario(
            "doodad-detour", corridor, runs=100,
            maximum_allowed_cross_track_world=1.8,
            maximum_allowed_pivot_fraction=0.10,
            static_obstacles=((7.12, -0.48, 0.70),),
        )

        summary, _ = simulate_steering_batch(scenario, seed_offset=300_000)

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(summary.collision_runs, 0)
        self.assertEqual(summary.quality_passed_runs, 100)

    def test_narrow_outdoor_hairpin_keeps_outbound_tangent_committed(self) -> None:
        """Do not forget a sharp portal corner while crossing its apex."""

        points = tuple(
            NavPoint(x, y, 0.0)
            for x, y in (
                (0.0, 0.0),
                (15.022949, -2.176392),
                (4.166504, -12.499948),
            )
        )
        width = 2.20362
        polygons = tuple(
            NavPolygon(
                index, 0, 0, 0.0, point,
                (
                    NavPoint(point.x - 0.25, point.y - 0.25, 0.0),
                    NavPoint(point.x + 0.25, point.y - 0.25, 0.0),
                    NavPoint(point.x, point.y + 0.25, 0.0),
                ),
                frozenset({"ground"}),
            )
            for index, point in enumerate(points)
        )
        portals = []
        for index, (start, stop) in enumerate(pairwise(points)):
            dx, dy = stop.x - start.x, stop.y - start.y
            length = (dx * dx + dy * dy) ** 0.5
            nx, ny = -dy / length, dx / length
            half = width * 0.5
            portals.append(NavPortal(
                index, index + 1,
                NavPoint(stop.x + nx * half, stop.y + ny * half, 0.0),
                NavPoint(stop.x - nx * half, stop.y - ny * half, 0.0),
                width,
            ))
        corridor = NavCorridor(
            "Simulation", 0, 0, points[0], points[-1], points,
            polygons=polygons,
            portals=tuple(portals),
        )
        scenario = SteeringSimulationScenario(
            "narrow-outdoor-hairpin", corridor, runs=100,
            maximum_allowed_cross_track_world=2.0,
            maximum_allowed_pivot_fraction=0.30,
            maximum_allowed_steering_sign_changes=6,
        )

        summary, _ = simulate_steering_batch(
            scenario, seed_offset=500_000,
        )

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(summary.quality_passed_runs, 100)
        self.assertLessEqual(summary.maximum_cross_track_world, 2.0)
        self.assertLessEqual(summary.maximum_pivot_fraction, 0.30)

    def test_adaptive_hairpin_regression_exercises_mppi_and_still_passes(self) -> None:
        """The production adaptive selector must be exercised, not only geometry."""

        points = tuple(
            NavPoint(x, y, 0.0)
            for x, y in (
                (0.0, 0.0),
                (15.022949, -2.176392),
                (4.166504, -12.499948),
            )
        )
        width = 2.20362
        portals = tuple(
            NavPortal(index, index + 1, stop, stop, width)
            for index, stop in enumerate(points[1:])
        )
        corridor = NavCorridor(
            "Simulation", 0, 0, points[0], points[-1], points,
            polygons=tuple(
                NavPolygon(
                    index, 0, 0, 0.0, point,
                    (
                        NavPoint(point.x - 0.25, point.y - 0.25, 0.0),
                        NavPoint(point.x + 0.25, point.y - 0.25, 0.0),
                        NavPoint(point.x, point.y + 0.25, 0.0),
                    ),
                    frozenset({"ground"}),
                )
                for index, point in enumerate(points)
            ),
            portals=portals,
        )
        scenario = SteeringSimulationScenario(
            "adaptive-narrow-outdoor-hairpin", corridor, runs=100,
            maximum_allowed_cross_track_world=2.0,
            maximum_allowed_pivot_fraction=0.30,
            maximum_allowed_steering_sign_changes=6,
        )

        def controller_factory() -> AdaptiveTrajectorySteeringController:
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

        summary, _ = simulate_steering_batch(
            scenario, seed_offset=500_000,
            controller_factory=controller_factory,
        )

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(summary.quality_passed_runs, 100)
        self.assertGreater(summary.mppi_active_observations, 0)
        self.assertEqual(summary.collision_runs, 0)


if __name__ == "__main__":
    unittest.main()
