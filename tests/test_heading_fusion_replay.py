from __future__ import annotations

import unittest

from scripts.replay_heading_fusion import replay_heading_actions


class HeadingFusionReplayTests(unittest.TestCase):
    def test_replay_uses_bounded_visual_fusion_after_initial_frame(self) -> None:
        result = replay_heading_actions(
            {
                "record_type": "navmesh_roaming_result",
                "run_id": "fixture",
                "status": "ARRIVED",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "MINIMAP_VISION_FALLBACK",
                        "player_facing_rad": 0.20,
                        "observed_monotonic_s": 10.0,
                        "mouse_velocity_x_px_s": 0.0,
                    },
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "MINIMAP_VISION_FALLBACK",
                        "player_facing_rad": 0.60,
                        "observed_monotonic_s": 10.2,
                        "mouse_velocity_x_px_s": 0.0,
                    },
                ],
            }
        )

        self.assertEqual(result["visible_heading_frames"], 2)
        self.assertEqual(result["replayed_visible_fused_frames"], 2)
        self.assertEqual(result["replayed_heading_sources"]["VISIBLE_CLIENT_HEADING_INITIAL"], 1)
        self.assertEqual(result["replayed_heading_sources"]["VISIBLE_CLIENT_HEADING_FUSED"], 1)
        self.assertEqual(result["recorded_client_facing_sources"]["MINIMAP_VISION_FALLBACK"], 2)
        self.assertEqual(result["frames_missing_client_facing_source"], 0)
        self.assertTrue(result["client_facing_source_complete"])
        self.assertLessEqual(result["max_bounded_correction_rad"], 0.25)
        self.assertFalse(result["input_emitted"])
        self.assertFalse(result["server_truth_used"])

    def test_replay_counts_missing_heading_frames_without_failing_open(self) -> None:
        result = replay_heading_actions(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "player_facing_rad": None,
                        "observed_monotonic_s": 10.0,
                        "mouse_velocity_x_px_s": 0.0,
                    }
                ],
            }
        )

        self.assertEqual(result["visible_heading_frames"], 0)
        self.assertEqual(result["replayed_frames"], 0)
        self.assertEqual(result["malformed_frames"], 1)
        self.assertEqual(result["replayed_fused_fraction"], 0.0)
        self.assertEqual(result["frames_missing_client_facing_source"], 1)
        self.assertFalse(result["client_facing_source_complete"])

    def test_replay_rejects_unknown_facing_source_label(self) -> None:
        result = replay_heading_actions(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "client_facing_source": "invented_source",
                        "player_facing_rad": 0.20,
                        "observed_monotonic_s": 10.0,
                        "mouse_velocity_x_px_s": 0.0,
                    }
                ],
            }
        )

        self.assertEqual(result["frames_missing_client_facing_source"], 1)
        self.assertEqual(result["invalid_client_facing_source_frames"], 1)
        self.assertFalse(result["client_facing_source_complete"])

    def test_replay_does_not_treat_minimap_body_field_as_raw_facing(self) -> None:
        result = replay_heading_actions(
            {
                "record_type": "navmesh_roaming_result",
                "actions": [
                    {
                        "kind": "CONTINUOUS_FRAME",
                        "heading_source": "MOUSE_INTEGRATED_MINIMAP_FALLBACK",
                        "client_facing_source": "MINIMAP_VISION_FALLBACK",
                        "body_yaw_observation_rad": 0.20,
                        "observed_monotonic_s": 10.0,
                        "mouse_velocity_x_px_s": 0.0,
                    }
                ],
            }
        )

        self.assertEqual(result["frames_missing_client_facing_source"], 1)
        self.assertEqual(result["invalid_client_facing_source_frames"], 1)


if __name__ == "__main__":
    unittest.main()
