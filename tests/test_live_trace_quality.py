from __future__ import annotations

import unittest

from perfect_assassin.movement.live_trace_quality import (
    evaluate_live_steering_trace,
)


def _result(commands: list[int], *, pivot_every: int | None = None) -> dict:
    actions = []
    for index, command in enumerate(commands):
        actions.append({
            "kind": "CONTINUOUS_FRAME",
            "observed_monotonic_s": 100.0 + index * 0.1,
            "requested_mouse_delta_x": command,
            "controller_state": (
                "PIVOT" if pivot_every and index % pivot_every == 0 else "FOLLOW"
            ),
        })
    return {"status": "ARRIVED", "actions": actions}


class LiveTraceQualityTests(unittest.TestCase):
    def test_smooth_arrival_passes(self) -> None:
        quality = evaluate_live_steering_trace(
            _result(([0] * 80) + ([1] * 20) + ([0] * 80)),
        )

        self.assertTrue(quality.passed)
        self.assertEqual(quality.steering_sign_changes, 0)

    def test_arrival_does_not_hide_left_right_camera_balance(self) -> None:
        quality = evaluate_live_steering_trace(
            _result([1, -1] * 100),
        )

        self.assertFalse(quality.passed)
        self.assertIn("camera_left_right_balance", quality.failures)

    def test_slow_s_curve_direction_changes_are_not_camera_balance(self) -> None:
        commands: list[int] = []
        for sign in (1, -1) * 10:
            commands.extend([sign] + ([0] * 9))

        quality = evaluate_live_steering_trace(_result(commands))

        self.assertGreater(quality.steering_sign_changes_per_minute, 12.0)
        self.assertEqual(quality.rapid_steering_reversals, 0)
        self.assertNotIn("camera_left_right_balance", quality.failures)

    def test_fast_real_s_bend_is_not_mislabelled_as_camera_balance(self) -> None:
        result = _result([4, -4] * 40)
        for frame in result["actions"]:
            frame["waypoint_error_rad"] = 0.65
            frame["cross_track_error_world"] = 2.0

        quality = evaluate_live_steering_trace(result)

        self.assertGreater(quality.steering_sign_changes, 20)
        self.assertEqual(quality.rapid_steering_reversals, 0)
        self.assertNotIn("camera_left_right_balance", quality.failures)

    def test_capture_gap_with_forward_progress_is_not_called_a_pause(self) -> None:
        actions = [
            {
                "kind": "CONTINUOUS_FRAME",
                "observed_monotonic_s": 90.0 + index * 0.1,
                "requested_mouse_delta_x": 0,
                "controller_state": "FOLLOW",
                "held_controls": ["MOVE_FORWARD"],
                "world_x": float(index),
                "world_y": 0.0,
                "estimated_heading_rad": 0.0,
            }
            for index in range(50)
        ]
        actions.extend([
            {
                "kind": "CONTINUOUS_FRAME",
                "observed_monotonic_s": 95.0,
                "requested_mouse_delta_x": 0,
                "controller_state": "FOLLOW",
                "held_controls": ["MOVE_FORWARD"],
                "world_x": 10.0,
                "world_y": 10.0,
                "estimated_heading_rad": 0.0,
            },
            {
                "kind": "CONTINUOUS_FRAME",
                "observed_monotonic_s": 96.0,
                "requested_mouse_delta_x": 0,
                "controller_state": "FOLLOW",
                "held_controls": ["MOVE_FORWARD"],
                "world_x": 12.0,
                "world_y": 10.0,
                "estimated_heading_rad": 0.05,
            },
        ])
        quality = evaluate_live_steering_trace(
            {"status": "ARRIVED", "actions": actions},
        )

        self.assertTrue(quality.passed)
        self.assertEqual(quality.observation_gaps_over_300ms, 1)
        self.assertEqual(quality.motion_continuity_exempted_gaps, 1)
        self.assertEqual(quality.unexplained_observation_gaps_over_300ms, 0)

    def test_capture_gap_during_a_real_running_curve_is_not_called_a_pause(self) -> None:
        actions = []
        for index in range(50):
            actions.append(
                {
                    "kind": "CONTINUOUS_FRAME",
                    "observed_monotonic_s": 100.0 + index * 0.1,
                    "requested_mouse_delta_x": 0,
                    "controller_state": "FOLLOW",
                    "held_controls": ["MOVE_FORWARD"],
                    "world_x": float(index),
                    "world_y": 0.0,
                    "estimated_heading_rad": 0.0,
                }
            )
        actions.extend(
            [
                {
                    "kind": "CONTINUOUS_FRAME",
                    "observed_monotonic_s": 105.0,
                    "requested_mouse_delta_x": 4,
                    "controller_state": "FOLLOW",
                    "held_controls": ["MOVE_FORWARD"],
                    "world_x": 50.0,
                    "world_y": 0.0,
                    "estimated_heading_rad": 0.0,
                },
                {
                    "kind": "CONTINUOUS_FRAME",
                    "observed_monotonic_s": 105.5,
                    "requested_mouse_delta_x": 4,
                    "controller_state": "FOLLOW",
                    "held_controls": ["MOVE_FORWARD"],
                    "world_x": 52.0,
                    "world_y": 1.5,
                    "estimated_heading_rad": 0.70,
                },
            ]
        )

        quality = evaluate_live_steering_trace(
            {"status": "ARRIVED", "actions": actions},
        )

        self.assertNotIn("control_observation_gap", quality.failures)
        self.assertEqual(quality.motion_continuity_exempted_gaps, 1)

    def test_capture_gap_without_progress_still_fails(self) -> None:
        actions = [
            {
                "kind": "CONTINUOUS_FRAME",
                "observed_monotonic_s": 100.0,
                "requested_mouse_delta_x": 0,
                "controller_state": "FOLLOW",
                "held_controls": ["MOVE_FORWARD"],
                "world_x": 10.0,
                "world_y": 10.0,
                "estimated_heading_rad": 0.0,
            },
            {
                "kind": "CONTINUOUS_FRAME",
                "observed_monotonic_s": 101.0,
                "requested_mouse_delta_x": 0,
                "controller_state": "FOLLOW",
                "held_controls": [],
                "world_x": 10.0,
                "world_y": 10.0,
                "estimated_heading_rad": 0.0,
            },
        ]
        quality = evaluate_live_steering_trace(
            {"status": "ARRIVED", "actions": actions},
        )

        self.assertFalse(quality.passed)
        self.assertIn("control_observation_gap", quality.failures)
        self.assertEqual(quality.motion_continuity_exempted_gaps, 0)
        self.assertEqual(quality.unexplained_observation_gaps_over_300ms, 1)

    def test_arrival_cannot_hide_forward_pressure_against_wall(self) -> None:
        result = _result([0] * 80)
        for index, frame in enumerate(result["actions"]):
            frame["held_controls"] = ["MOVE_FORWARD"]
            frame["no_progress_s"] = 0.1 * index if 8 <= index <= 18 else 0.0

        quality = evaluate_live_steering_trace(result)

        self.assertFalse(quality.passed)
        self.assertIn("forward_input_without_progress", quality.failures)
        self.assertGreater(quality.maximum_forward_no_progress_s, 0.75)
        self.assertGreater(quality.forward_stall_frames, 0)

    def test_short_forward_observation_jitter_does_not_fail_stall_gate(self) -> None:
        result = _result([0] * 80)
        for index, frame in enumerate(result["actions"]):
            frame["held_controls"] = ["MOVE_FORWARD"]
            frame["no_progress_s"] = 0.5 if index == 20 else 0.0

        quality = evaluate_live_steering_trace(result)

        self.assertNotIn("forward_input_without_progress", quality.failures)
        self.assertEqual(quality.maximum_forward_no_progress_s, 0.5)

    def test_client_facing_source_is_reported_without_changing_diagnostic_mode(self) -> None:
        quality = evaluate_live_steering_trace(_result([0] * 80))

        self.assertTrue(quality.passed)
        self.assertEqual(quality.client_facing_source_frames, 0)
        self.assertEqual(quality.frames_missing_client_facing_source, 80)
        self.assertFalse(quality.client_facing_source_complete)

    def test_strict_live_gate_rejects_missing_client_facing_source(self) -> None:
        quality = evaluate_live_steering_trace(
            _result([0] * 80),
            require_client_facing_source=True,
        )

        self.assertFalse(quality.passed)
        self.assertIn("missing_client_facing_source", quality.failures)

    def test_unavailable_client_facing_source_is_incomplete(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame["client_facing_source"] = "UNAVAILABLE"

        quality = evaluate_live_steering_trace(
            result,
            require_client_facing_source=True,
        )

        self.assertEqual(quality.client_facing_source_frames, 0)
        self.assertEqual(quality.frames_missing_client_facing_source, 80)
        self.assertFalse(quality.passed)

    def test_client_facing_source_requires_known_label_and_raw_yaw(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "client_facing_source": "MINIMAP_VISION_FALLBACK",
                    "player_facing_rad": 0.2,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_client_facing_source=True,
        )
        self.assertTrue(quality.passed)
        self.assertEqual(quality.client_facing_source_frames, 80)

        result["actions"][0]["client_facing_source"] = "invented_source"
        quality = evaluate_live_steering_trace(
            result,
            require_client_facing_source=True,
        )
        self.assertFalse(quality.passed)
        self.assertIn("missing_client_facing_source", quality.failures)

    def test_minimap_body_channel_cannot_substitute_for_raw_facing(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "client_facing_source": "MINIMAP_VISION_FALLBACK",
                    "body_yaw_observation_rad": 0.2,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_client_facing_source=True,
        )

        self.assertFalse(quality.passed)
        self.assertEqual(quality.client_facing_source_frames, 0)
        self.assertIn("missing_client_facing_source", quality.failures)

    def test_strict_live_gate_rejects_missing_body_camera_separation(self) -> None:
        quality = evaluate_live_steering_trace(
            _result([0] * 80),
            require_body_camera_separation=True,
        )

        self.assertFalse(quality.passed)
        self.assertIn("missing_body_camera_yaw_separation", quality.failures)

    def test_body_camera_separation_requires_all_three_explicit_values(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "body_yaw_observation_rad": 0.2,
                    "body_yaw_observation_source": "MINIMAP_VISION_FALLBACK",
                    "camera_yaw_estimate_rad": 0.1,
                    "camera_yaw_source": "RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY",
                    "body_camera_yaw_delta_rad": 0.1,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_body_camera_separation=True,
        )

        self.assertTrue(quality.passed)
        self.assertEqual(quality.body_camera_separation_frames, 80)
        self.assertTrue(quality.body_camera_separation_complete)

    def test_strict_live_gate_rejects_missing_camera_integrity(self) -> None:
        quality = evaluate_live_steering_trace(
            _result([0] * 80),
            require_camera_integrity=True,
        )

        self.assertFalse(quality.passed)
        self.assertEqual(quality.camera_integrity_frames, 0)
        self.assertEqual(quality.frames_missing_camera_integrity, 80)
        self.assertFalse(quality.camera_integrity_complete)
        self.assertIn("missing_camera_integrity", quality.failures)

    def test_camera_integrity_requires_visible_anchor_and_confidence_floor(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "camera_integrity_state": "VISIBLE",
                    "camera_integrity_confidence": 0.55,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_camera_integrity=True,
        )

        self.assertTrue(quality.passed)
        self.assertEqual(quality.camera_integrity_frames, 80)
        self.assertTrue(quality.camera_integrity_complete)

        result["actions"][0]["camera_integrity_confidence"] = 0.5499
        quality = evaluate_live_steering_trace(
            result,
            require_camera_integrity=True,
        )
        self.assertFalse(quality.passed)
        self.assertIn("missing_camera_integrity", quality.failures)

    def test_level_rmb_receipt_is_camera_control_integrity_when_scale_changes(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "camera_integrity_state": "LOST",
                    "camera_integrity_confidence": 0.0,
                    "camera_control_integrity_state": "RMB_LEVEL_LOCKED",
                    "camera_yaw_source": "RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY",
                    "mouse_look_held": True,
                    "mouse_delta_y": 0,
                    "mouse_velocity_y_px_s": 0.0,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_camera_integrity=True,
        )

        self.assertTrue(quality.passed)
        self.assertTrue(quality.camera_integrity_complete)

    def test_body_camera_separation_rejects_inconsistent_recorded_delta(self) -> None:
        result = _result([0] * 80)
        for frame in result["actions"]:
            frame.update(
                {
                    "body_yaw_observation_rad": 0.2,
                    "body_yaw_observation_source": "MINIMAP_VISION_FALLBACK",
                    "camera_yaw_estimate_rad": 0.1,
                    "camera_yaw_source": "RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY",
                    "body_camera_yaw_delta_rad": 0.4,
                }
            )

        quality = evaluate_live_steering_trace(
            result,
            require_body_camera_separation=True,
        )

        self.assertFalse(quality.passed)
        self.assertEqual(quality.body_camera_separation_frames, 0)
        self.assertIn("missing_body_camera_yaw_separation", quality.failures)


if __name__ == "__main__":
    unittest.main()
