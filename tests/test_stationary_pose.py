from __future__ import annotations

import json
from math import pi
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.movement.stationary_pose import (
    CALIBRATED_MINIMAP_BODY_FACING_SOURCE,
    EXACT_BODY_FACING_SOURCE,
    ExpectedStationaryLocation,
    LivePoseSample,
    evaluate_stationary_pose,
    load_expected_stationary_location,
    parse_live_pose_state,
)


def sample(index: int, *, x: float = 10.0, facing: float = 1.0) -> LivePoseSample:
    return LivePoseSample(
        sequence=index + 1,
        observed_monotonic_s=10.0 + index * 0.2,
        world_x=x,
        world_y=20.0,
        facing_rad=facing,
        facing_source=EXACT_BODY_FACING_SOURCE,
    )


class StationaryPoseTests(unittest.TestCase):
    def test_fresh_bridge_pose_carries_exact_sources(self) -> None:
        pose = parse_live_pose_state(
            "PA_NAV_VIEWER_STATE 5\nsequence 7\nobserved 10.0\n"
            "pose 1.0 2.0\nfacing 6.2\ncamera_yaw 0.4\n"
            "corridor 0\nend\nfacing_source COORDINATE_HUD_EXACT\n"
            "facing_confidence 1.0\n",
            now_monotonic_s=10.2,
        )
        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertEqual(pose.position_source, "COORDINATE_HUD")
        self.assertEqual(pose.facing_source, EXACT_BODY_FACING_SOURCE)

    def test_visible_minimap_facing_keeps_its_honest_source(self) -> None:
        poses = []
        for index in range(16):
            pose = parse_live_pose_state(
                f"PA_NAV_VIEWER_STATE 5\nsequence {index + 1}\n"
                f"observed {10.0 + index * 0.2}\n"
                "pose 1.0 2.0\nfacing 3.8\ncamera_yaw none\n"
                "corridor 0\nend\nfacing_source MINIMAP_VISION_FALLBACK\n"
                "facing_confidence 0.82\n",
                now_monotonic_s=13.2,
                maximum_age_s=4.0,
            )
            self.assertIsNotNone(pose)
            assert pose is not None
            poses.append(pose)
        self.assertEqual(
            poses[0].facing_source,
            CALIBRATED_MINIMAP_BODY_FACING_SOURCE,
        )
        self.assertEqual(poses[0].facing_confidence, 0.82)
        report = evaluate_stationary_pose(poses)
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(
            report.facing_source,
            CALIBRATED_MINIMAP_BODY_FACING_SOURCE,
        )

    def test_low_confidence_minimap_facing_fails_closed(self) -> None:
        samples = [
            LivePoseSample(
                sequence=index + 1,
                observed_monotonic_s=10.0 + index * 0.2,
                world_x=10.0,
                world_y=20.0,
                facing_rad=1.0,
                facing_source=CALIBRATED_MINIMAP_BODY_FACING_SOURCE,
                facing_confidence=0.69,
            )
            for index in range(16)
        ]
        report = evaluate_stationary_pose(samples)
        self.assertFalse(report.passed)
        self.assertIn("exact_body_facing_missing", report.failures)

    def test_stable_exact_pose_passes(self) -> None:
        report = evaluate_stationary_pose(sample(index) for index in range(16))
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.facing_source, EXACT_BODY_FACING_SOURCE)

    def test_motion_and_missing_facing_fail_closed(self) -> None:
        samples = [sample(index, x=10.0 + index * 0.02) for index in range(16)]
        samples[-1] = LivePoseSample(
            sequence=16,
            observed_monotonic_s=13.0,
            world_x=10.3,
            world_y=20.0,
            facing_rad=None,
        )
        report = evaluate_stationary_pose(samples)
        self.assertFalse(report.passed)
        self.assertIn("actor_not_stationary", report.failures)
        self.assertIn("exact_body_facing_missing", report.failures)

    def test_facing_wraparound_is_not_false_jitter(self) -> None:
        samples = [
            sample(index, facing=(2.0 * pi - 0.01 if index % 2 else 0.01))
            for index in range(16)
        ]
        report = evaluate_stationary_pose(samples)
        self.assertTrue(report.passed, report.failures)

    def test_expected_location_is_loaded_from_catalog_and_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "locations.json"
            catalog.write_text(json.dumps({
                "record_type": "semantic_location_catalog",
                "schema_version": "1.0",
                "map_name": "Azeroth",
                "coordinate_system": "tbc243_client_world_xy",
                "locations": [{
                    "id": "landmark:test-room",
                    "world": [10.0, 20.0],
                    "arrival_radius_yards": 2.0,
                }],
            }), encoding="utf-8")
            expected = load_expected_stationary_location(
                catalog, location_id="landmark:test-room",
            )
        passing = evaluate_stationary_pose(
            (sample(index) for index in range(16)),
            expected_location=expected,
        )
        self.assertTrue(passing.passed, passing.failures)
        self.assertTrue(passing.within_expected_location)
        self.assertEqual(passing.expected_location_id, "landmark:test-room")
        outside = ExpectedStationaryLocation(
            location_id="landmark:elsewhere",
            map_name="Azeroth",
            coordinate_system="tbc243_client_world_xy",
            center_world=(100.0, 200.0),
            arrival_radius_world=2.0,
        )
        failing = evaluate_stationary_pose(
            (sample(index) for index in range(16)),
            expected_location=outside,
        )
        self.assertFalse(failing.passed)
        self.assertFalse(failing.within_expected_location)
        self.assertIn("outside_expected_location", failing.failures)


if __name__ == "__main__":
    unittest.main()
