from __future__ import annotations

from math import atan2, pi
import unittest

from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.continuous_trajectory_follower import (
    ContinuousTrajectoryFollower,
)
from perfect_assassin.movement.predictive_steering import SteeringState
from perfect_assassin.movement.steering_simulation import (
    SteeringSimulationScenario,
    simulate_steering_batch,
)
from perfect_assassin.movement.trajectory_smoothing import smooth_navmesh_corridor


class TrajectorySmoothingTests(unittest.TestCase):
    @staticmethod
    def corridor(*xy: tuple[float, float]) -> NavCorridor:
        points = tuple(NavPoint(x, y, 0.0) for x, y in xy)
        return NavCorridor("Simulation", 0, 0, points[0], points[-1], points)

    def test_right_angle_becomes_dense_continuous_curve(self) -> None:
        result = smooth_navmesh_corridor(
            self.corridor((0, 0), (10, 0), (10, 10)),
            validate_segment=lambda _start, _stop: True,
        )

        self.assertEqual(result.rounded_corner_count, 1)
        self.assertGreater(len(result.points), 5)
        headings = [
            atan2(right.y - left.y, right.x - left.x)
            for left, right in zip(result.points, result.points[1:])
        ]
        changes = [abs(_wrap(right - left)) for left, right in zip(headings, headings[1:])]
        self.assertLess(max(changes), 0.45)
        self.assertEqual(result.points[0], NavPoint(0, 0, 0))
        self.assertEqual(result.points[-1], NavPoint(10, 10, 0))

    def test_invalid_corner_never_invents_a_shortcut(self) -> None:
        source = self.corridor((0, 0), (10, 0), (10, 10))
        result = smooth_navmesh_corridor(
            source,
            validate_segment=lambda start, stop: not (
                start.x > 8.0 and stop.y > 0.0
            ),
        )

        self.assertEqual(result.rounded_corner_count, 0)
        self.assertEqual(result.rejected_corner_count, 1)
        self.assertEqual(result.points, source.points)

    def test_s_passage_is_rounded_without_corner_deletion(self) -> None:
        result = smooth_navmesh_corridor(
            self.corridor((0, 0), (8, 0), (8, 6), (16, 6), (16, 12)),
            validate_segment=lambda _start, _stop: True,
            minimum_turn_radius_world=1.5,
        )

        self.assertEqual(result.rounded_corner_count, 3)
        self.assertGreater(len(result.points), 12)
        self.assertEqual(result.points[0], NavPoint(0, 0, 0))
        self.assertEqual(result.points[-1], NavPoint(16, 12, 0))

    def test_hairpin_above_limit_remains_for_explicit_recovery(self) -> None:
        result = smooth_navmesh_corridor(
            self.corridor((0, 0), (10, 0), (2, 1)),
            validate_segment=lambda _start, _stop: True,
        )

        self.assertEqual(result.rounded_corner_count, 0)
        self.assertEqual(result.points, (NavPoint(0, 0, 0), NavPoint(10, 0, 0), NavPoint(2, 1, 0)))

    def test_smoothed_s_curve_runs_without_robotic_pivoting(self) -> None:
        source = self.corridor((0, 0), (8, 0), (8, 6), (16, 6), (16, 12))
        smoothed = smooth_navmesh_corridor(
            source,
            validate_segment=lambda _start, _stop: True,
            minimum_turn_radius_world=1.5,
        )
        corridor = NavCorridor(
            "Simulation", 0, 0,
            smoothed.points[0], smoothed.points[-1], smoothed.points,
        )
        scenario = SteeringSimulationScenario(
            "continuous-s", corridor, runs=100,
            maximum_allowed_pivot_fraction=0.02,
            maximum_allowed_steering_sign_changes=6,
            maximum_allowed_cross_track_world=2.5,
        )

        summary, _runs = simulate_steering_batch(
            scenario,
            controller_factory=ContinuousTrajectoryFollower,
        )

        self.assertEqual(summary.completed_runs, 100)
        self.assertEqual(summary.quality_passed_runs, 100)
        self.assertLessEqual(summary.maximum_pivot_fraction, 0.02)

    def test_precision_start_aligns_before_forward_motion(self) -> None:
        # This mirrors a client-validated inset around a static object.  The
        # path is straight, but the first visible heading is still half a
        # radian away from its tangent.  W must wait for one fresh aligned
        # observation instead of pushing the actor into the nearby wall.
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(10, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(10, 0, 0)),
            doodad_avoidance_applied=True,
            doodad_detour_count=1,
        )
        follower = ContinuousTrajectoryFollower()

        first = follower.decide(
            SteeringState(0, 0, -0.55, 7.0), corridor,
        )
        self.assertEqual(first.state, "PIVOT")
        self.assertEqual(first.forward_hold_ms, 0)
        self.assertEqual(first.reason, "continuous_precision_initial_alignment")

        still_turning = follower.decide(
            SteeringState(0, 0, -0.34, 7.0), corridor,
        )
        self.assertEqual(still_turning.state, "PIVOT")
        self.assertEqual(still_turning.forward_hold_ms, 0)

        # Begin rolling before a delayed mouse command can overshoot and ask
        # for an opposite correction. Pure pursuit finishes this small,
        # corridor-inset error while the player moves like a human.
        aligned = follower.decide(
            SteeringState(0, 0, -0.30, 7.0), corridor,
        )
        self.assertEqual(aligned.state, "FOLLOW")
        self.assertGreater(aligned.forward_hold_ms, 0)

        # One noisy visual sample after the gate has opened must not restart
        # an endless stationary pivot at the same corridor start.
        noisy = follower.decide(
            SteeringState(0, 0, -0.55, 7.0), corridor,
        )
        self.assertEqual(noisy.state, "FOLLOW")
        self.assertGreater(noisy.forward_hold_ms, 0)

    def test_precision_rolling_start_survives_one_thousand_pose_variations(self) -> None:
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(25, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(25, 0, 0)),
            doodad_avoidance_applied=True,
            doodad_detour_count=1,
        )
        scenario = SteeringSimulationScenario(
            "precision-rolling-start",
            corridor,
            runs=1000,
            initial_lateral_jitter_world=0.15,
            initial_heading_jitter_rad=0.65,
            maximum_allowed_cross_track_world=0.80,
            maximum_allowed_pivot_fraction=0.11,
            maximum_allowed_steering_sign_changes=1,
        )

        summary, _runs = simulate_steering_batch(
            scenario,
            controller_factory=ContinuousTrajectoryFollower,
        )

        self.assertEqual(summary.completed_runs, 1000)
        self.assertEqual(summary.quality_passed_runs, 1000)
        self.assertEqual(summary.collision_runs, 0)
        self.assertLessEqual(summary.maximum_steering_sign_changes, 1)

    def test_rolling_corridor_handoff_keeps_camera_reversal_history(self) -> None:
        follower = ContinuousTrajectoryFollower()
        follower._trajectory_signature = ((-5.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        follower._trajectory_previous_mouse_delta = 0
        follower._trajectory_last_nonzero_mouse_delta = -4
        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(10, 0, 0),
            (NavPoint(0, 0, 0), NavPoint(10, 0, 0)),
            doodad_avoidance_applied=True,
            doodad_detour_count=1,
        )

        intent = follower.decide(
            SteeringState(0, 0, 0.30, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertEqual(intent.mouse_delta_x, 0)
        self.assertEqual(follower._trajectory_last_nonzero_mouse_delta, -4)

    def test_runtime_direction_realign_forces_stationary_pivot(self) -> None:
        corridor = self.corridor((0, 0), (10, 0))
        follower = ContinuousTrajectoryFollower()
        follower.request_stationary_pivot()

        correcting = follower.decide(
            SteeringState(0, 0, 1.20, 7.0), corridor,
        )
        self.assertEqual(correcting.state, "PIVOT")
        self.assertEqual(correcting.forward_hold_ms, 0)

        aligned = follower.decide(
            SteeringState(0, 0, 0.10, 7.0), corridor,
        )
        self.assertEqual(aligned.state, "FOLLOW")
        self.assertGreater(aligned.forward_hold_ms, 0)

    def test_quantised_heading_jitter_does_not_balance_camera(self) -> None:
        corridor = self.corridor((0, 0), (30, 0))
        follower = ContinuousTrajectoryFollower()
        commands = []

        for index in range(24):
            heading = 0.12 if index % 2 == 0 else -0.10
            intent = follower.decide(
                SteeringState(index * 0.25, 0.0, heading, 7.0), corridor,
            )
            commands.append(intent.mouse_delta_x)

        nonzero_signs = [
            1 if command > 0 else -1
            for command in commands
            if command
        ]
        self.assertTrue(nonzero_signs)
        self.assertEqual(len(set(nonzero_signs)), 1)

    def test_persistent_small_heading_reversal_is_eventually_accepted(self) -> None:
        corridor = self.corridor((0, 0), (30, 0))
        follower = ContinuousTrajectoryFollower()
        first = follower.decide(
            SteeringState(0.0, 0.0, 0.12, 7.0), corridor,
        )
        self.assertNotEqual(first.mouse_delta_x, 0)

        commands = [
            follower.decide(
                SteeringState(0.25 + index * 0.25, 0.0, -0.10, 7.0),
                corridor,
            ).mouse_delta_x
            for index in range(16)
        ]

        opposite_indices = [
            index
            for index, command in enumerate(commands)
            if command * first.mouse_delta_x < 0
        ]
        self.assertTrue(opposite_indices)
        self.assertGreaterEqual(
            opposite_indices[0],
            follower.SMALL_REVERSAL_CONFIRMATION_TICKS - 1,
        )

    def test_geometry_aware_bend_brakes_opposite_yaw_before_corner(self) -> None:
        def polygon(index: int, x: float) -> NavPolygon:
            return NavPolygon(
                index, 0, 0, 0.0, NavPoint(x, 0, 0),
                (
                    NavPoint(x - 1, -2, 0),
                    NavPoint(x + 1, -2, 0),
                    NavPoint(x, 2, 0),
                ),
            )

        corridor = NavCorridor(
            "Simulation", 0, 0,
            NavPoint(0, 0, 0), NavPoint(5, -10, 0),
            (NavPoint(0, 0, 0), NavPoint(5, 0, 0), NavPoint(5, -10, 0)),
            (polygon(0, 2), polygon(1, 5)),
            (NavPortal(0, 1, NavPoint(4, -2, 0), NavPoint(6, 2, 0), 4),),
        )
        follower = ContinuousTrajectoryFollower()

        intent = follower.decide(
            # The near carrot asks for a small left correction, while the
            # navmesh corridor visibly turns right immediately afterwards.
            SteeringState(3.5, -0.5, 0.0, 7.0), corridor,
        )

        self.assertEqual(intent.state, "FOLLOW")
        self.assertGreater(intent.forward_hold_ms, 0)
        self.assertEqual(intent.mouse_delta_x, 0)
        self.assertEqual(
            intent.reason,
            "continuous_pure_pursuit_upcoming_bend_brake",
        )



def _wrap(angle: float) -> float:
    while angle > pi:
        angle -= 2 * pi
    while angle < -pi:
        angle += 2 * pi
    return angle


if __name__ == "__main__":
    unittest.main()
