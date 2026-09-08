from dataclasses import replace
import unittest

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.continuous_trajectory_follower import ContinuousTrajectoryFollower
from perfect_assassin.movement.predictive_steering import PredictiveSteeringController, SteeringState


def corridor(z):
    points = (NavPoint(0, 0, z), NavPoint(10, 0, z), NavPoint(30, 0, z))
    return NavCorridor("Fixture", 0, 0, points[0], points[-1], points)


class VerticalCacheTests(unittest.TestCase):
    def test_same_xy_new_height_updates_projection_and_lookahead(self):
        for cls in (PredictiveSteeringController, ContinuousTrajectoryFollower):
            with self.subTest(controller=cls.__name__):
                control = cls()
                lower, upper = corridor(10), corridor(25)
                state = SteeringState(2, 0, 0, 7)
                control.decide(state, lower)
                updated = control.decide(state, upper)
                self.assertEqual(updated.projected_z_world, 25)
                self.assertEqual(updated.lookahead.z, 25)

    def test_changed_interior_height_not_just_endpoints(self):
        lower = corridor(10)
        ramp = replace(lower, points=(lower.start, NavPoint(10, 0, 15), lower.stop))
        control = ContinuousTrajectoryFollower()
        state = SteeringState(5, 0, 0, 7)
        control.decide(state, lower)
        result = control.decide(state, ramp)
        self.assertAlmostEqual(result.projected_z_world, 12.5)
        self.assertGreater(result.lookahead.z, 12.5)

    def test_round_trip_does_not_retain_upper_height(self):
        control = ContinuousTrajectoryFollower()
        state = SteeringState(2, 0, 0, 7)
        for height in (10, 25, 10):
            self.assertEqual(control.decide(state, corridor(height)).projected_z_world, height)

    def test_equal_geometry_keeps_progress_and_actuator_history(self):
        control = ContinuousTrajectoryFollower()
        original = corridor(10)
        control.decide(SteeringState(12, 0, 0, 7), original)
        progress = control._progress_world
        control._trajectory_previous_mouse_delta = 3
        control._previous_mouse_delta = 2
        control._reset_for_corridor(replace(original))
        self.assertEqual(control._progress_world, progress)
        self.assertEqual(control._trajectory_previous_mouse_delta, 3)
        self.assertEqual(control._previous_mouse_delta, 2)

    def test_new_height_matches_fresh_controller_geometry(self):
        upper, lower = corridor(25), corridor(10)
        state = SteeringState(4, .3, .05, 7)
        control = ContinuousTrajectoryFollower()
        control.decide(state, lower)
        actual = control.decide(state, upper)
        fresh = ContinuousTrajectoryFollower().decide(state, upper)
        self.assertEqual(actual.lookahead, fresh.lookahead)
        self.assertEqual(actual.projected_z_world, fresh.projected_z_world)
        self.assertEqual(actual.cross_track_error_world, fresh.cross_track_error_world)


if __name__ == "__main__":
    unittest.main()
