from __future__ import annotations

import unittest
from pathlib import Path
import json
import sys
import tempfile


RUNNER_PATH = Path(__file__).parents[1] / "integrations" / "windows-input"
if str(RUNNER_PATH) not in sys.path:
    sys.path.insert(0, str(RUNNER_PATH))

from run_movement_lab import _north_up_radar_delta, _read_control

from perfect_assassin.movement.movement_lab import (
    MovementLabSnapshot,
)
from perfect_assassin.movement.client_navmesh import NavPoint
from perfect_assassin.movement.observed_journey_trace import ObservedJourneyTrace


class MovementLabSnapshotTests(unittest.TestCase):
    def test_overlay_has_complete_facing_math_and_redraw_deduplication(self) -> None:
        source = (RUNNER_PATH / "run_movement_lab.py").read_text(encoding="utf-8")
        self.assertIn("from math import cos, hypot, sin", source)
        self.assertIn("render_signature == self._last_render_signature", source)
        self.assertIn("self._root.withdraw()", source)

    def test_overlay_control_is_revisioned_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay-control.json"
            self.assertEqual(_read_control(path), (0, None))
            path.write_text(json.dumps({
                "revision": 7,
                "command": "STOP",
                "execution_authority": False,
            }), encoding="utf-8")
            self.assertEqual(_read_control(path), (7, "STOP"))
            path.write_text('{"revision":-1,"command":"START"}', encoding="utf-8")
            self.assertEqual(_read_control(path), (0, None))

    def test_radar_uses_same_north_up_axes_as_client_atlas(self) -> None:
        self.assertEqual(
            _north_up_radar_delta(
                world_x=11.0, world_y=20.0,
                player_x=10.0, player_y=20.0, scale=3.0,
            ),
            (0.0, -3.0),
        )
        self.assertEqual(
            _north_up_radar_delta(
                world_x=10.0, world_y=19.0,
                player_x=10.0, player_y=20.0, scale=3.0,
            ),
            (3.0, 0.0),
        )

    def test_aligned_arrows_overlap(self) -> None:
        snapshot = MovementLabSnapshot(1.0, "VISIBLE", 22, 0.0)
        vectors = snapshot.arrow_vectors(radius_px=50)
        self.assertEqual(vectors["player"], vectors["target"])

    def test_target_right_arrow_is_right_of_player_facing(self) -> None:
        snapshot = MovementLabSnapshot(1.0, "VISIBLE", 22, 0.5)
        vectors = snapshot.arrow_vectors(radius_px=50)
        self.assertGreater(vectors["target"][0], vectors["player"][0])

    def test_record_round_trip_is_non_authoritative(self) -> None:
        snapshot = MovementLabSnapshot(
            2.5, "VISIBLE", 33, -0.2,
            player_world_x=1680.0,
            player_world_y=412.0,
            player_world_z=-62.1,
            player_facing_rad=0.5,
            body_facing_rad=0.5,
            body_facing_source="COORDINATE_HUD_EXACT",
            camera_yaw_estimate_rad=0.4,
            camera_yaw_source="MOUSE_INTEGRATED_ESTIMATE",
            body_camera_yaw_delta_rad=0.1,
            waypoint_error_rad=0.4,
            controller_state="TRACK",
            navmesh_polygons_world=(
                ((1679.0, 411.0), (1681.0, 411.0), (1680.0, 413.0)),
            ),
            corridor_centerline_world=((1680.0, 412.0), (1683.0, 415.0)),
            traversed_path_world=((1678.0, 410.0), (1680.0, 412.0)),
            target_screen_y_normalized=0.55,
            tether_state="DETOUR_LEFT",
            tether_guidance_error_rad=0.3,
            tether_projected_target_world=(1684.0, 416.0),
            tether_centerline_world=(
                (1680.0, 412.0), (1681.0, 414.0), (1684.0, 416.0),
            ),
        )
        record = snapshot.to_record()
        self.assertFalse(record["execution_authority"])
        self.assertEqual(record["body_facing_source"], "COORDINATE_HUD_EXACT")
        self.assertEqual(record["camera_yaw_source"], "MOUSE_INTEGRATED_ESTIMATE")
        self.assertEqual(MovementLabSnapshot.from_record(record), snapshot)

    def test_body_camera_channels_must_keep_separate_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "body facing provenance"):
            MovementLabSnapshot(
                1.0, "LOST", None, None,
                body_facing_rad=0.5,
            )
        with self.assertRaisesRegex(ValueError, "camera yaw provenance"):
            MovementLabSnapshot(
                1.0, "LOST", None, None,
                camera_yaw_estimate_rad=0.4,
            )
        runner = (RUNNER_PATH / "run_navmesh_roaming.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("body_facing_rad=topographic_body_yaw", runner)
        self.assertIn("camera_yaw_estimate_rad=heading", runner)
        self.assertIn(
            "body_camera_yaw_delta_rad=_body_camera_yaw_delta", runner,
        )

    def test_observed_journey_trace_is_visual_only_and_bounded(self) -> None:
        trace = ObservedJourneyTrace(
            sample_spacing_world=1.0, maximum_points=64,
        )
        for x in range(130):
            trace.observe(NavPoint(float(x), 0.0, 1.0))

        self.assertLessEqual(len(trace.points), 64)
        self.assertGreater(trace.effective_spacing_world, 1.0)
        self.assertGreaterEqual(trace.points[-1].x, 128.0)

    def test_observed_journey_trace_does_not_draw_across_teleport(self) -> None:
        trace = ObservedJourneyTrace()
        trace.observe(NavPoint(0.0, 0.0, 1.0))
        trace.observe(NavPoint(2.0, 0.0, 1.0))
        trace.observe(NavPoint(100.0, 100.0, 3.0))

        self.assertEqual(trace.points, (NavPoint(100.0, 100.0, 3.0),))


if __name__ == "__main__":
    unittest.main()
