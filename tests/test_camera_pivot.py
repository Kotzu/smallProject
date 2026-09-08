from __future__ import annotations

import unittest

from perfect_assassin.movement.camera_pivot import (
    CameraPivotController,
    nearest_navmesh_physical_surfaces,
)
from perfect_assassin.movement.client_navmesh import NavPoint, NavPolygon


class CameraPivotControllerTests(unittest.TestCase):
    def test_nearest_polygon_selects_local_wmo_scene(self) -> None:
        polygons = (
            NavPolygon(0, 0, 0, 0.0, NavPoint(0, 0, 0), (
                NavPoint(-1, -1, 0), NavPoint(1, -1, 0), NavPoint(0, 1, 0),
            ), frozenset({"ground"})),
            NavPolygon(1, 0, 0, 0.0, NavPoint(10, 0, 0), (
                NavPoint(9, -1, 0), NavPoint(11, -1, 0), NavPoint(10, 1, 0),
            ), frozenset({"ground", "wmo"})),
        )
        self.assertEqual(
            nearest_navmesh_physical_surfaces(
                polygons, world_x=9.5, world_y=0.0,
            ),
            frozenset({"ground", "wmo"}),
        )

    def test_initial_wmo_profile_does_not_reset_composition(self) -> None:
        controller = CameraPivotController()
        intent = controller.observe(
            observed_monotonic_s=1.0,
            physical_surfaces=frozenset({"ground", "wmo"}),
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.mode, "WMO_NAV")
        self.assertFalse(intent.restore_composition)

    def test_wmo_seam_does_not_repeat_camera_transition(self) -> None:
        controller = CameraPivotController(
            enter_wmo_after_s=0.2,
            exit_wmo_after_s=0.8,
            minimum_transition_interval_s=0.0,
        )
        controller.observe(
            observed_monotonic_s=1.0,
            physical_surfaces=frozenset({"ground"}),
        )
        self.assertIsNone(controller.observe(
            observed_monotonic_s=1.1,
            physical_surfaces=frozenset({"ground", "wmo"}),
        ))
        entered = controller.observe(
            observed_monotonic_s=1.31,
            physical_surfaces=frozenset({"ground", "wmo"}),
        )
        self.assertEqual(entered.mode, "WMO_NAV")
        self.assertIsNone(controller.observe(
            observed_monotonic_s=1.4,
            physical_surfaces=frozenset({"ground"}),
        ))
        self.assertIsNone(controller.observe(
            observed_monotonic_s=1.5,
            physical_surfaces=frozenset({"ground", "wmo"}),
        ))

    def test_stable_outdoor_exit_restores_high_distant_frame_once(self) -> None:
        controller = CameraPivotController(
            exit_wmo_after_s=0.8,
            minimum_transition_interval_s=0.0,
        )
        controller.observe(
            observed_monotonic_s=1.0,
            physical_surfaces=frozenset({"wmo"}),
        )
        self.assertIsNone(controller.observe(
            observed_monotonic_s=2.0,
            physical_surfaces=frozenset({"ground"}),
        ))
        restored = controller.observe(
            observed_monotonic_s=2.81,
            physical_surfaces=frozenset({"ground"}),
        )
        self.assertEqual(restored.mode, "OUTDOOR_HUNT")
        self.assertTrue(restored.restore_composition)
        self.assertEqual(restored.zoom_out_steps, 5)
        self.assertEqual(restored.pitch_delta_y, 25)
        self.assertIsNone(controller.observe(
            observed_monotonic_s=3.0,
            physical_surfaces=frozenset({"ground"}),
        ))


if __name__ == "__main__":
    unittest.main()
