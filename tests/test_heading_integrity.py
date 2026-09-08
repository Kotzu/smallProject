from __future__ import annotations

import unittest

from perfect_assassin.movement.heading_integrity import (
    MAX_HEADING_EVIDENCE_AGE_S,
    assess_heading_integrity,
    is_current_visual_heading,
)
from scripts.replay_heading_integrity import replay_heading_integrity


class HeadingIntegrityTests(unittest.TestCase):
    def test_current_minimap_fusion_allows_control(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=1.2,
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
            observed_monotonic_s=10.0,
            last_visible_observed_s=9.0,
        )
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.state, "VISIBLE")
        self.assertEqual(decision.evidence_age_s, 0.0)

    def test_current_displacement_fused_minimap_heading_allows_control(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=1.2,
            heading_source="DISPLACEMENT_VISIBLE_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
            observed_monotonic_s=10.0,
            last_visible_observed_s=9.0,
        )
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.state, "VISIBLE")
        self.assertEqual(decision.evidence_age_s, 0.0)

    def test_current_displacement_axial_flip_heading_allows_control(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=1.2,
            heading_source="DISPLACEMENT_VISIBLE_HEADING_AXIAL_FLIP_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
            observed_monotonic_s=10.0,
            last_visible_observed_s=9.0,
        )
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.state, "VISIBLE")

    def test_current_exact_hud_heading_allows_control(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=0.4,
            heading_source="COORDINATE_HUD_EXACT",
            client_facing_source="COORDINATE_HUD_EXACT",
            observed_monotonic_s=4.0,
            last_visible_observed_s=None,
        )
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.state, "VISIBLE")

    def test_one_short_missing_frame_is_only_held(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=0.4,
            heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
            client_facing_source="UNAVAILABLE",
            observed_monotonic_s=10.20,
            last_visible_observed_s=10.0,
        )
        self.assertTrue(decision.allow_control)
        self.assertEqual(decision.state, "HELD")
        self.assertAlmostEqual(decision.evidence_age_s or 0.0, 0.20)

    def test_stale_missing_heading_releases_control(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=0.4,
            heading_source="MOUSE_INTEGRATED_MINIMAP_FALLBACK",
            client_facing_source="UNAVAILABLE",
            observed_monotonic_s=10.31,
            last_visible_observed_s=10.0,
        )
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.state, "STALE")
        self.assertGreater(decision.evidence_age_s or 0.0, MAX_HEADING_EVIDENCE_AGE_S)

    def test_unknown_label_cannot_refresh_heading_evidence(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=0.4,
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="invented_source",
            observed_monotonic_s=10.0,
            last_visible_observed_s=None,
        )
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.state, "MISSING")

    def test_raw_source_and_computed_heading_must_match(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=0.4,
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="COORDINATE_HUD_EXACT",
            observed_monotonic_s=10.0,
            last_visible_observed_s=None,
        )
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.state, "MISSING")

    def test_non_finite_heading_is_rejected(self) -> None:
        decision = assess_heading_integrity(
            heading_rad=float("nan"),
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
            observed_monotonic_s=10.0,
            last_visible_observed_s=10.0,
        )
        self.assertFalse(decision.allow_control)
        self.assertEqual(decision.state, "INVALID")

    def test_visual_source_helper_uses_both_channels(self) -> None:
        self.assertTrue(is_current_visual_heading(
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="MINIMAP_VISION_FALLBACK",
        ))
        self.assertFalse(is_current_visual_heading(
            heading_source="VISIBLE_CLIENT_HEADING_FUSED",
            client_facing_source="UNAVAILABLE",
        ))

    def test_live_shaped_replay_stops_at_first_missing_source(self) -> None:
        report = replay_heading_integrity(
            {
                "record_type": "navmesh_roaming_result",
                "run_id": "old-live-trace",
                "status": "RUNTIME_ARM_EXPIRED",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 1,
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "estimated_heading_rad": 1.0,
                        "player_facing_rad": 1.0,
                        "observed_monotonic_s": 100.0,
                    },
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 2,
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "estimated_heading_rad": 1.0,
                        "player_facing_rad": 1.0,
                        "observed_monotonic_s": 100.1,
                    },
                ],
            }
        )

        self.assertTrue(report["stopped_fail_closed"])
        self.assertEqual(report["evaluated_frames_until_stop"], 1)
        self.assertEqual(report["current_visual_heading_frames"], 0)
        self.assertEqual(report["first_rejection"]["state"], "MISSING")
        self.assertEqual(report["first_rejection"]["frame_index"], 1)
        self.assertFalse(report["raw_client_facing_source_complete"])
        self.assertFalse(report["input_emitted"])

    def test_replay_does_not_borrow_camera_yaw_for_missing_visual_facing(self) -> None:
        report = replay_heading_integrity(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 1,
                        "heading_source": "VISIBLE_CLIENT_HEADING_FUSED",
                        "client_facing_source": "MINIMAP_VISION_FALLBACK",
                        "camera_yaw_estimate_rad": 1.0,
                        "player_facing_rad": None,
                        "observed_monotonic_s": 100.0,
                    },
                ],
            }
        )

        self.assertTrue(report["stopped_fail_closed"])
        self.assertEqual(report["evaluated_frames_until_stop"], 1)
        self.assertEqual(report["first_rejection"]["state"], "INVALID")
        self.assertFalse(report["first_rejection"]["raw_client_facing_available"])
        self.assertEqual(report["missing_raw_client_facing_frames"], 1)
        self.assertFalse(report["raw_client_facing_source_complete"])

    def test_replay_does_not_count_unlabelled_player_facing_as_raw(self) -> None:
        report = replay_heading_integrity(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 1,
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "UNAVAILABLE",
                        "player_facing_rad": 0.4,
                        "camera_yaw_estimate_rad": 0.4,
                        "observed_monotonic_s": 100.0,
                    },
                ],
            }
        )

        self.assertFalse(report["first_rejection"]["raw_client_facing_available"])
        self.assertEqual(report["missing_raw_client_facing_frames"], 0)
        self.assertFalse(report["raw_client_facing_source_complete"])

    def test_live_shaped_replay_holds_then_releases_stale_heading(self) -> None:
        report = replay_heading_integrity(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 1,
                        "heading_source": "VISIBLE_CLIENT_HEADING_FUSED",
                        "client_facing_source": "MINIMAP_VISION_FALLBACK",
                        "estimated_heading_rad": 1.0,
                        "player_facing_rad": 1.0,
                        "observed_monotonic_s": 100.0,
                    },
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 2,
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "UNAVAILABLE",
                        "estimated_heading_rad": 1.0,
                        "player_facing_rad": 1.0,
                        "observed_monotonic_s": 100.2,
                    },
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "frame_index": 3,
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "UNAVAILABLE",
                        "estimated_heading_rad": 1.0,
                        "player_facing_rad": 1.0,
                        "observed_monotonic_s": 100.31,
                    },
                ],
            }
        )

        self.assertEqual(report["evaluated_frames_until_stop"], 3)
        self.assertEqual(report["heading_integrity_state_counts"], {
            "VISIBLE": 1,
            "HELD": 1,
            "STALE": 1,
        })
        self.assertEqual(report["first_rejection"]["state"], "STALE")
        self.assertEqual(report["first_rejection"]["frame_index"], 3)
        self.assertTrue(report["stopped_fail_closed"])


if __name__ == "__main__":
    unittest.main()
