from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from scripts.audit_player_actor_frames import audit_frames


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "config" / "pose" / "player-actor-anchor-tbc243-predator-v1.json"
V2 = ROOT / "config" / "pose" / "player-actor-anchor-tbc243-predator-v2.json"


def _left_of_center_actor_frame() -> np.ndarray:
    frame = np.zeros((360, 640, 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    frame[165:192, 304:324, :3] = 185
    frame[198:242, 370:392, :3] = 180
    return frame


class PlayerActorFrameAuditTests(unittest.TestCase):
    def test_audit_reports_v2_repair_and_keeps_v1_failure(self) -> None:
        report = audit_frames([("left", _left_of_center_actor_frame())], [V1, V2])

        self.assertEqual(report["profiles"][str(V1)]["state_counts"], {"LOST": 1})
        self.assertEqual(report["profiles"][str(V2)]["state_counts"], {"VISIBLE": 1})
        self.assertFalse(report["input_emitted"])
        self.assertFalse(report["execution_authority"])

    def test_audit_records_invalid_frame_as_detector_error(self) -> None:
        bad = np.zeros((2, 2, 4), dtype=np.uint8)
        report = audit_frames([("bad", bad)], [V2])

        self.assertEqual(
            report["profiles"][str(V2)]["error_counts"],
            {"PlayerActorAnchorError": 1},
        )


if __name__ == "__main__":
    unittest.main()
