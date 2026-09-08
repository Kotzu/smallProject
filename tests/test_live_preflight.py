from __future__ import annotations

from pathlib import Path
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.live_preflight import (
    build_live_preflight_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _observation(*, observed_s: float = 10.0, facing: float = 0.4) -> dict[str, object]:
    return {
        "tracking_state": "VALID",
        "position": {
            "x": 0.2,
            "y": 0.3,
            "facing_rad": facing,
        },
        "timing": {"observed_monotonic_s": observed_s},
    }


def _visible_camera() -> dict[str, object]:
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


class LivePreflightTests(unittest.TestCase):
    def _ready(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "observation": _observation(),
            "camera_integrity": _visible_camera(),
            "heading_rad": 0.4,
            "heading_source": "COORDINATE_HUD_EXACT",
            "client_facing_source": "COORDINATE_HUD_EXACT",
            "now_monotonic_s": 10.05,
            "capture_latency_ms": 3.0,
            "observation_latency_ms": 5.0,
            "foreground_matches_target": True,
            "evidence_refs": ("fixture:coordinate-hud", "fixture:camera"),
            "capture_origin": "replay_fixture",
        }
        arguments.update(overrides)
        return build_live_preflight_record(**arguments)  # type: ignore[arg-type]

    def test_ready_record_requires_all_four_live_dependencies(self) -> None:
        record = self._ready()
        self.assertEqual(record["status"], "READY")
        self.assertTrue(record["ready"])
        self.assertEqual(record["reasons"], [])
        checks = record["checks"]
        assert isinstance(checks, dict)
        self.assertTrue(checks["camera_integrity_ready"])
        self.assertTrue(checks["heading_integrity_ready"])
        self.assertTrue(checks["foreground_matches_target"])
        self.assertTrue(checks["body_yaw_exact"])

    def test_minimap_heading_is_not_labelled_as_raw_body_yaw(self) -> None:
        record = self._ready(
            heading_rad=0.5,
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
        )
        self.assertEqual(record["status"], "READY")
        checks = record["checks"]
        assert isinstance(checks, dict)
        self.assertFalse(checks["body_yaw_exact"])
        self.assertIsNone(checks["body_yaw_observation_rad"])
        self.assertIsNone(checks["body_camera_yaw_delta_rad"])

    def test_missing_camera_heading_or_foreground_rejects(self) -> None:
        record = self._ready(
            camera_integrity=None,
            heading_rad=None,
            heading_source="UNAVAILABLE",
            client_facing_source="UNAVAILABLE",
            foreground_matches_target=None,
        )
        self.assertEqual(record["status"], "REJECTED")
        self.assertFalse(record["ready"])
        reasons = record["reasons"]
        assert isinstance(reasons, list)
        self.assertIn("camera_camera_integrity_evidence_missing", reasons)
        self.assertIn("heading_not_current_visual", reasons)
        self.assertIn("foreground_target_not_verified", reasons)

    def test_missing_actor_anchor_is_diagnostic_in_normal_navigation(self) -> None:
        record = self._ready(
            camera_integrity=None,
            require_visible_player_anchor=False,
        )
        self.assertEqual(record["status"], "READY")
        self.assertTrue(record["ready"])
        checks = record["checks"]
        assert isinstance(checks, dict)
        self.assertTrue(checks["camera_integrity_ready"])
        self.assertEqual(checks["camera_integrity_state"], "MISSING")

    def test_stale_observation_rejects_even_when_camera_is_visible(self) -> None:
        record = self._ready(
            observation=_observation(observed_s=9.0),
        )
        self.assertEqual(record["status"], "REJECTED")
        self.assertIn("observation_too_old", record["reasons"])

    def test_exact_body_heading_option_rejects_minimap(self) -> None:
        record = self._ready(
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
            require_exact_body_heading=True,
        )
        self.assertFalse(record["ready"])
        self.assertIn("exact_body_heading_missing", record["reasons"])

    def test_exact_body_heading_option_rejects_mixed_controller_heading(self) -> None:
        record = self._ready(
            heading_rad=0.7,
            require_exact_body_heading=True,
        )
        self.assertFalse(record["ready"])
        self.assertIn("exact_body_heading_disagreement", record["reasons"])

    def test_facing_first_rejects_mouse_only_heading_even_with_minimap_yaw(self) -> None:
        record = self._ready(
            heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
            client_facing_source="MINIMAP_VISION_FALLBACK",
        )
        self.assertFalse(record["ready"])
        self.assertIn("heading_not_current_visual", record["reasons"])

    def test_facing_first_rejects_preserved_heading_as_fresh_evidence(self) -> None:
        record = self._ready(
            heading_source="COORDINATE_HUD_EXACT_PRESERVED",
            client_facing_source="COORDINATE_HUD_EXACT",
        )
        self.assertFalse(record["ready"])
        self.assertIn("heading_not_current_visual", record["reasons"])

    def test_record_matches_versioned_contract(self) -> None:
        record = self._ready()
        ContractValidator(
            ROOT / "contracts" / "live-observation-preflight.schema.json"
        ).validate(record)


if __name__ == "__main__":
    unittest.main()
