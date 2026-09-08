from __future__ import annotations

import importlib
import sys
from pathlib import Path
import unittest

import numpy as np

from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

detector_module = importlib.import_module("player_actor_detector")


class PlayerActorDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "player-actor-anchor-tbc243-predator-v2.json"
        )
        self.detector = detector_module.PlayerActorAnchorDetector(self.profile)
        self.validator = ContractValidator(
            ROOT / "contracts" / "player-actor-anchor.schema.json"
        )

    @staticmethod
    def actor_frame(*, actor: bool) -> np.ndarray:
        frame = np.zeros((360, 640, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        # Neutral-bright head and a separated right shoulder/arm component.
        if actor:
            frame[165:192, 330:350, :3] = 185
            frame[198:242, 370:392, :3] = 180
        return frame

    def test_profile_is_explicitly_candidate_and_fail_closed(self) -> None:
        self.assertEqual(self.profile["client_build"], "2.4.3.8606")
        self.assertEqual(self.profile["profile"], "player_actor_anchor_tbc243_v2")
        self.assertEqual(self.profile["profile_version"], "0.2.0")
        self.assertEqual(self.profile["calibration_state"], "retained_video_candidate")
        self.assertEqual(self.profile["sample_stride"], 4)
        self.assertEqual(self.profile["detector_deadline_ms"], 12.0)
        self.assertLess(self.profile["detector_deadline_ms"], 50.0)
        self.assertFalse(self.profile["execution_authority"])

    def test_v2_keeps_a_left_of_center_actor_that_v1_rejected(self) -> None:
        frame = self.actor_frame(actor=False)
        frame[165:192, 304:324, :3] = 185
        frame[198:242, 370:392, :3] = 180
        visible = self.detector.detect(frame, observed_at_s=10.0)
        v1 = detector_module.PlayerActorAnchorDetector(
            detector_module.load_profile(
                ROOT / "config" / "pose" / "player-actor-anchor-tbc243-predator-v1.json"
            )
        )
        rejected = v1.detect(frame, observed_at_s=10.1)
        self.assertEqual(visible["tracking_state"], "VISIBLE")
        self.assertEqual(rejected["tracking_state"], "LOST")

    def test_head_and_body_are_required_for_visible_state(self) -> None:
        visible = self.detector.detect(self.actor_frame(actor=True), observed_at_s=10.0)
        missing = self.detector.detect(self.actor_frame(actor=False), observed_at_s=10.1)
        self.assertEqual(visible["tracking_state"], "VISIBLE")
        self.assertGreaterEqual(visible["confidence"], 0.55)
        self.assertIsNotNone(visible["actor_anchor"])
        self.assertEqual(missing["tracking_state"], "LOST")
        self.assertEqual(missing["confidence"], 0.0)
        self.assertIsNone(missing["actor_anchor"])
        self.assertFalse(missing["execution_authority"])
        self.validator.validate(visible)
        self.validator.validate(missing)

    def test_head_without_lower_support_is_not_enough(self) -> None:
        frame = self.actor_frame(actor=False)
        frame[165:192, 330:350, :3] = 185
        result = self.detector.detect(frame, observed_at_s=11.0)
        self.assertEqual(result["tracking_state"], "LOST")
        self.assertIn("not_found", result["reason"])

    def test_noise_outside_actor_roi_is_ignored(self) -> None:
        frame = self.actor_frame(actor=False)
        frame[20:100, 20:100, :3] = 255
        result = self.detector.detect(frame, observed_at_s=12.0)
        self.assertEqual(result["tracking_state"], "LOST")

    def test_detector_error_is_unknown_and_still_contract_valid(self) -> None:
        result = self.detector.failure_record(
            observed_at_s=13.0,
            reason="actor_detector_error:deadline",
            sampled_width=911,
            sampled_height=524,
        )
        self.assertEqual(result["tracking_state"], "UNKNOWN")
        self.assertEqual(result["confidence"], 0.0)
        self.assertIsNone(result["actor_anchor"])
        self.assertEqual(result["metrics"]["sampled_width"], 911)
        self.assertEqual(result["metrics"]["sampled_height"], 524)
        self.validator.validate(result)

    def test_v2_handles_the_lab_4k_capture_with_the_bounded_deadline(self) -> None:
        # The LAB window is commonly captured at 3643x2093.  Stride 4 keeps
        # the visual check inside the 12 ms budget without relaxing any
        # visibility or confidence threshold.
        height, width = 2093, 3643
        frame = np.zeros((height, width, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        frame[940:1040, 1745:1845, :3] = 185
        frame[1110:1210, 1930:1990, :3] = 180
        result = self.detector.detect(frame, observed_at_s=14.0)
        self.assertEqual(result["tracking_state"], "VISIBLE")
        self.assertEqual(result["metrics"]["sampled_width"], 911)
        self.assertEqual(result["metrics"]["sampled_height"], 524)


if __name__ == "__main__":
    unittest.main()
