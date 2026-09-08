from __future__ import annotations

import time
import unittest
from dataclasses import replace
from functools import partial
from threading import Event

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.mppi_steering import (
    AsyncMppiSteeringController,
    MppiConfiguration,
    MppiControl,
    MppiDynamicObstacle,
    MppiPlan,
    MppiPlanningSnapshot,
    MppiSteeringController,
    PathIntegralSteeringPlanner,
)
from perfect_assassin.movement.predictive_steering import SteeringIntent, SteeringState
from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationScenario,
    simulate_steering_batch,
)


def _corridor(*coordinates: tuple[float, float]) -> NavCorridor:
    points = tuple(NavPoint(x, y, 0.0) for x, y in coordinates)
    return NavCorridor("Fixture", 31, 31, points[0], points[-1], points)


def _partial_corridor(*coordinates: tuple[float, float]) -> NavCorridor:
    points = tuple(NavPoint(x, y, 0.0) for x, y in coordinates)
    return NavCorridor(
        "Fixture",
        31,
        31,
        points[0],
        points[-1],
        points,
        complete=False,
        requested_stop=NavPoint(points[-1].x + 20.0, points[-1].y, 0.0),
    )


class PathIntegralSteeringPlannerTests(unittest.TestCase):
    def test_configuration_is_bounded(self) -> None:
        self.assertEqual(
            MppiConfiguration().maximum_yaw_acceleration_rad_s2,
            12.0,
        )
        with self.assertRaisesRegex(ValueError, "configuration"):
            MppiConfiguration(batch_size=31)
        with self.assertRaisesRegex(ValueError, "configuration"):
            MppiConfiguration(time_steps=161)

    def test_straight_plan_is_deterministic_and_forward(self) -> None:
        corridor = _corridor((0.0, 0.0), (40.0, 0.0))
        snapshot = MppiPlanningSnapshot(
            7,
            SteeringState(0.0, 0.0, 0.0, 7.0),
            corridor,
        )
        config = MppiConfiguration(batch_size=128, time_steps=24)

        first = PathIntegralSteeringPlanner(config).plan(snapshot)
        second = PathIntegralSteeringPlanner(config).plan(snapshot)

        self.assertEqual(first.status, "READY")
        self.assertEqual(first.controls, second.controls)
        self.assertEqual(first.predicted_path, second.predicted_path)
        self.assertGreater(first.feasible_sample_count, 0)
        self.assertTrue(all(item.forward for item in first.controls))
        self.assertLess(max(abs(item.yaw_rate_rad_s) for item in first.controls), 0.25)
        self.assertGreater(first.predicted_path[-1].x, 7.5)

    def test_right_angle_is_anticipated_inside_the_horizon(self) -> None:
        corridor = _corridor((0.0, 0.0), (10.0, 0.0), (10.0, 12.0))
        snapshot = MppiPlanningSnapshot(
            11,
            SteeringState(0.0, 0.0, 0.0, 7.0),
            corridor,
        )
        plan = PathIntegralSteeringPlanner(
            MppiConfiguration(
                batch_size=512,
                time_steps=56,
                yaw_noise_std_rad_s=0.65,
            )
        ).plan(snapshot)

        self.assertEqual(plan.status, "READY")
        self.assertGreater(max(item.yaw_rate_rad_s for item in plan.controls), 0.20)
        self.assertGreater(plan.predicted_path[-1].y, 3.0)

    def test_switchback_preview_anticipates_the_outbound_leg(self) -> None:
        corridor = _corridor((0.0, 0.0), (12.0, 0.0), (12.0, -20.0))
        snapshot = MppiPlanningSnapshot(
            12,
            SteeringState(0.0, 0.0, 0.0, 7.0),
            corridor,
        )

        plan = PathIntegralSteeringPlanner(
            MppiConfiguration(batch_size=256, time_steps=56),
        ).plan(snapshot)

        self.assertEqual(plan.status, "READY")
        # The nominal horizon must expose the outbound leg before the actor
        # reaches the corner; a short preview would remain almost straight.
        self.assertLess(min(item.yaw_rate_rad_s for item in plan.controls), -0.50)
        self.assertLess(plan.predicted_path[-1].y, -8.0)

    def test_short_complete_corridor_uses_absorbing_terminal_horizon(self) -> None:
        corridor = _corridor((0.0, 0.0), (15.0, 0.0))
        snapshot = MppiPlanningSnapshot(
            13,
            SteeringState(0.0, 0.0, 0.0, 7.0),
            corridor,
        )

        plan = PathIntegralSteeringPlanner(
            MppiConfiguration(
                batch_size=256,
                time_steps=56,
            )
        ).plan(snapshot)

        self.assertEqual(plan.status, "READY")
        self.assertGreater(plan.feasible_sample_count, 0)
        self.assertAlmostEqual(plan.predicted_path[-1].x, 15.0, places=6)
        self.assertAlmostEqual(plan.predicted_path[-1].y, 0.0, places=6)

    def test_large_blocker_fails_closed_when_no_trajectory_fits(self) -> None:
        corridor = _corridor((0.0, 0.0), (30.0, 0.0))
        snapshot = MppiPlanningSnapshot(
            19,
            SteeringState(0.0, 0.0, 0.0, 7.0),
            corridor,
            obstacles=(MppiDynamicObstacle(4.0, 0.0, 5.0),),
        )
        plan = PathIntegralSteeringPlanner(
            MppiConfiguration(
                batch_size=256,
                time_steps=32,
            )
        ).plan(snapshot)

        self.assertEqual(plan.status, "NO_FEASIBLE_TRAJECTORY")
        self.assertEqual(plan.feasible_sample_count, 0)
        self.assertEqual(plan.controls, ())

    def test_closed_loop_curve_stays_smooth_across_pose_variations(self) -> None:
        corridor = _corridor(
            (0.0, 0.0),
            (25.0, 0.0),
            (35.0, 5.0),
            (55.0, 5.0),
        )
        scenario = SteeringSimulationScenario(
            "mppi-closed-loop",
            corridor,
            runs=100,
            maximum_allowed_cross_track_world=2.5,
            maximum_allowed_steering_sign_changes=10,
        )
        controller_factory = partial(
            MppiSteeringController,
            configuration=MppiConfiguration(batch_size=64, time_steps=32),
            replan_interval_ticks=4,
        )

        summary, _ = simulate_steering_batch(
            scenario,
            controller_factory=controller_factory,
        )

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(summary.quality_passed_runs, 100)
        self.assertLessEqual(summary.maximum_steering_sign_changes, 4)
        self.assertGreater(summary.mppi_active_fraction, 0.80)

    def test_async_controller_never_waits_for_planner(self) -> None:
        corridor = _corridor((0.0, 0.0), (40.0, 0.0))
        started = Event()
        release = Event()

        class BlockingPlanner:
            def plan(self, snapshot: MppiPlanningSnapshot) -> MppiPlan:
                started.set()
                if not release.wait(2.0):
                    raise TimeoutError("test planner was not released")
                controls = (
                    MppiControl(True, 0.50, 0.05),
                    MppiControl(True, 0.35, 0.05),
                )
                return MppiPlan(
                    status="READY",
                    snapshot_id=snapshot.snapshot_id,
                    corridor_signature=(
                        PathIntegralSteeringPlanner.corridor_signature(
                            snapshot.corridor,
                        )
                    ),
                    start_x=snapshot.state.x,
                    start_y=snapshot.state.y,
                    start_heading_rad=float(snapshot.state.heading_rad),
                    controls=controls,
                    predicted_path=(
                        NavPoint(snapshot.state.x + 0.35, snapshot.state.y, 0.0),
                        NavPoint(snapshot.state.x + 0.70, snapshot.state.y, 0.0),
                    ),
                    sample_count=64,
                    feasible_sample_count=64,
                    minimum_cost=1.0,
                    planning_duration_ms=20.0,
                    reason="fixture_ready",
                )

        controller = AsyncMppiSteeringController(planner=BlockingPlanner())
        try:
            state = SteeringState(0.0, 0.0, 0.0, 7.0)
            before = time.perf_counter()
            fallback = controller.decide(state, corridor)
            elapsed = time.perf_counter() - before
            self.assertLess(elapsed, 0.10)
            self.assertEqual(fallback.state, "FOLLOW")
            self.assertNotEqual(fallback.reason, "pa_mppi_async_published_trajectory")
            self.assertTrue(started.wait(0.5))
            release.set()
            deadline = time.monotonic() + 1.0
            active = fallback
            while time.monotonic() < deadline:
                active = controller.decide(state, corridor)
                if active.reason == "pa_mppi_async_published_trajectory":
                    break
                time.sleep(0.005)
            self.assertEqual(active.reason, "pa_mppi_async_published_trajectory")
            self.assertEqual(controller.mppi_telemetry.state, "ACTIVE")
            self.assertNotEqual(active.mouse_delta_x, 0)
        finally:
            release.set()
            controller.close()

    def test_async_controller_keeps_one_plan_across_several_control_ticks(self) -> None:
        corridor = _corridor((0.0, 0.0), (40.0, 0.0))

        class ImmediatePlanner:
            def __init__(self) -> None:
                self.calls = 0

            def plan(self, snapshot: MppiPlanningSnapshot) -> MppiPlan:
                self.calls += 1
                return MppiPlan(
                    status="READY",
                    snapshot_id=snapshot.snapshot_id,
                    corridor_signature=(
                        PathIntegralSteeringPlanner.corridor_signature(
                            snapshot.corridor,
                        )
                    ),
                    start_x=snapshot.state.x,
                    start_y=snapshot.state.y,
                    start_heading_rad=float(snapshot.state.heading_rad),
                    controls=tuple(MppiControl(True, 0.0, 0.05) for _ in range(8)),
                    predicted_path=tuple(
                        NavPoint(snapshot.state.x + index * 0.35, 0.0, 0.0)
                        for index in range(1, 9)
                    ),
                    sample_count=64,
                    feasible_sample_count=64,
                    minimum_cost=1.0,
                    planning_duration_ms=0.1,
                    reason="fixture_ready",
                )

        planner = ImmediatePlanner()
        controller = AsyncMppiSteeringController(
            planner=planner,
            replan_interval_ticks=4,
        )
        try:
            state = SteeringState(0.0, 0.0, 0.0, 7.0)
            for _ in range(12):
                controller.decide(state, corridor)
                time.sleep(0.005)
            self.assertGreaterEqual(planner.calls, 2)
            self.assertLessEqual(planner.calls, 4)
        finally:
            controller.close()

    def test_async_corridor_handoff_does_not_expose_shadow_mouse_command(self) -> None:
        first_corridor = _corridor((0.0, 0.0), (40.0, 0.0))
        next_corridor = _corridor((0.0, 0.0), (0.0, 40.0))

        class RightTurnPlanner:
            def plan(self, snapshot: MppiPlanningSnapshot) -> MppiPlan:
                return MppiPlan(
                    status="READY",
                    snapshot_id=snapshot.snapshot_id,
                    corridor_signature=(
                        PathIntegralSteeringPlanner.corridor_signature(
                            snapshot.corridor,
                        )
                    ),
                    start_x=snapshot.state.x,
                    start_y=snapshot.state.y,
                    start_heading_rad=float(snapshot.state.heading_rad),
                    controls=tuple(MppiControl(True, -1.0, 0.05) for _ in range(8)),
                    predicted_path=tuple(
                        NavPoint(snapshot.state.x + index * 0.35, 0.0, 0.0)
                        for index in range(1, 9)
                    ),
                    sample_count=64,
                    feasible_sample_count=64,
                    minimum_cost=1.0,
                    planning_duration_ms=0.1,
                    reason="fixture_ready",
                )

        controller = AsyncMppiSteeringController(
            planner=RightTurnPlanner(),
            replan_interval_ticks=4,
        )
        try:
            state = SteeringState(0.0, 0.0, 0.0, 7.0)
            active = controller.decide(state, first_corridor)
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                active = controller.decide(state, first_corridor)
                if active.reason == "pa_mppi_async_published_trajectory":
                    break
                time.sleep(0.005)
            self.assertGreater(active.mouse_delta_x, 0)

            handoff = controller.decide(state, next_corridor)

            self.assertNotEqual(
                handoff.reason,
                "pa_mppi_async_published_trajectory",
            )
            self.assertGreaterEqual(handoff.mouse_delta_x, 0)
        finally:
            controller.close()

    def test_transient_fallback_preserves_mouse_reversal_hysteresis(self) -> None:
        controller = AsyncMppiSteeringController()
        try:
            positive = SteeringIntent(
                "FOLLOW", 50, 4, NavPoint(1.0, 0.0, 0.0),
                "fixture", 0.0, 0.0, 0.0,
            )
            negative = replace(positive, mouse_delta_x=-4)
            for _ in range(4):
                controller._continuous_fallback_intent(positive)

            first_opposite = controller._continuous_fallback_intent(negative)
            self.assertGreaterEqual(first_opposite.mouse_delta_x, 0)

            for _ in range(3):
                held = controller._continuous_fallback_intent(negative)
                self.assertGreaterEqual(held.mouse_delta_x, 0)
            confirmed = controller._continuous_fallback_intent(negative)
            self.assertLess(confirmed.mouse_delta_x, 0)
        finally:
            controller.close()

    def test_partial_corridor_uses_geometric_frontier_fallback(self) -> None:
        corridor = _partial_corridor((0.0, 0.0), (10.0, 0.0))
        state = SteeringState(0.0, 0.0, 0.0, 7.0)

        synchronous = MppiSteeringController(
            configuration=MppiConfiguration(batch_size=64, time_steps=24),
        )
        sync_intent = synchronous.decide(state, corridor)
        self.assertEqual(sync_intent.state, "FOLLOW")
        self.assertNotEqual(
            sync_intent.reason,
            "pa_mppi_synchronous_evaluation_trajectory",
        )

        asynchronous = AsyncMppiSteeringController()
        try:
            async_intent = asynchronous.decide(state, corridor)
            self.assertEqual(async_intent.state, "FOLLOW")
            self.assertNotEqual(
                async_intent.reason,
                "pa_mppi_async_published_trajectory",
            )
            self.assertEqual(
                asynchronous.mppi_telemetry.fallback_reason,
                "geometric_state:PARTIAL_CORRIDOR",
            )
        finally:
            asynchronous.close()


if __name__ == "__main__":
    unittest.main()
