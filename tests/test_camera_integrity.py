from __future__ import annotations

import unittest

from perfect_assassin.movement.camera_integrity import (
    assess_camera_integrity,
    navigation_camera_is_level,
)


def visible_record() -> dict[str, object]:
    return {
        "tracking_state": "VISIBLE",
        "confidence": 0.9,
        "actor_anchor": {
            "left": 0.4,
            "top": 0.4,
            "right": 0.6,
            "bottom": 0.8,
            "center_x": 0.5,
            "center_y": 0.6,
        },
    }


class CameraIntegrityTests(unittest.TestCase):
    def test_visible_anchor_allows_control(self) -> None:
        decision = assess_camera_integrity(visible_record())
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.tracking_state, "VISIBLE")

    def test_lost_anchor_stops_control(self) -> None:
        decision = assess_camera_integrity(
            {"tracking_state": "LOST", "confidence": 0.0, "actor_anchor": None}
        )
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.reason, "player_actor_anchor_lost")

    def test_missing_evidence_stops_control(self) -> None:
        decision = assess_camera_integrity(None)
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.tracking_state, "MISSING")

    def test_low_confidence_or_missing_anchor_stops_control(self) -> None:
        low = visible_record()
        low["confidence"] = 0.2
        self.assertFalse(assess_camera_integrity(low).allow_control)
        missing_anchor = visible_record()
        missing_anchor["actor_anchor"] = None
        self.assertFalse(assess_camera_integrity(missing_anchor).allow_control)

    def test_malformed_anchor_geometry_stops_control(self) -> None:
        malformed = visible_record()
        malformed["actor_anchor"] = {}
        self.assertFalse(assess_camera_integrity(malformed).allow_control)
        reversed_box = visible_record()
        reversed_box["actor_anchor"] = {
            "left": 0.7,
            "top": 0.4,
            "right": 0.3,
            "bottom": 0.8,
            "center_x": 0.5,
            "center_y": 0.6,
        }
        self.assertFalse(assess_camera_integrity(reversed_box).allow_control)

    def test_read_only_mode_can_observe_without_authorizing_input(self) -> None:
        decision = assess_camera_integrity(None, require_visible_anchor=False)
        self.assertTrue(decision.allow_control)
        self.assertEqual(
            decision.reason, "camera_anchor_gate_disabled_for_read_only_mode"
        )

    def test_navigation_camera_rejects_vertical_motion(self) -> None:
        self.assertTrue(
            navigation_camera_is_level(mouse_delta_y=0, mouse_velocity_y_px_s=0.0)
        )
        self.assertFalse(
            navigation_camera_is_level(mouse_delta_y=1, mouse_velocity_y_px_s=0.0)
        )
        self.assertFalse(
            navigation_camera_is_level(mouse_delta_y=0, mouse_velocity_y_px_s=1.0)
        )


if __name__ == "__main__":
    unittest.main()
