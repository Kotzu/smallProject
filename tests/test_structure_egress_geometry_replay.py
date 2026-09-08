import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "egress_geometry_replay", ROOT / "scripts/replay_structure_egress_geometry.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.continuous_trajectory_follower import ContinuousTrajectoryFollower
from perfect_assassin.movement.predictive_steering import SteeringState


class GeometryReplayTests(unittest.TestCase):
    def setUp(self):
        self.corridor = NavCorridor("Fixture", 0, 0, NavPoint(0, 0, 0),
            NavPoint(30, 0, 0), (NavPoint(0, 0, 0), NavPoint(30, 0, 0)))
        follower = ContinuousTrajectoryFollower()
        self.frames = []
        for index in range(10):
            state = SteeringState(1 + index * .25, .2, 0, 7)
            intent = follower.decide(state, self.corridor)
            self.frames.append(dict(frame_index=index + 1,
                decision_observation=dict(world_x=state.x, world_y=state.y,
                    heading_rad=0, speed_world_per_s=7, no_progress_s=0),
                lookahead_world=[intent.lookahead.x, intent.lookahead.y, intent.lookahead.z],
                cross_track_error_world=intent.cross_track_error_world,
                projected_z_world=intent.projected_z_world))

    def test_matching_geometry_is_not_an_actuator_or_live_certificate(self):
        result = module.replay_geometry(self.frames, self.corridor)
        self.assertTrue(result["geometry_matches"])
        self.assertEqual(result["frame_count"], 10)
        self.assertFalse(result["actuator_commands_replayed"])
        self.assertFalse(result["execution_authority"])

    def test_one_mismatched_lookahead_rejects_prefix(self):
        self.frames[4]["lookahead_world"][1] += .1
        self.assertFalse(module.replay_geometry(self.frames, self.corridor)["geometry_matches"])

    def test_wrong_height_rejects_prefix(self):
        self.frames[2]["projected_z_world"] += 3
        self.assertFalse(module.replay_geometry(self.frames, self.corridor)["geometry_matches"])

    def test_missing_decision_sample_is_not_replaced_by_after_position(self):
        del self.frames[0]["decision_observation"]
        with self.assertRaises(KeyError):
            module.replay_geometry(self.frames, self.corridor)

    def test_empty_prefix_is_rejected(self):
        with self.assertRaises(ValueError):
            module.replay_geometry([], self.corridor)
