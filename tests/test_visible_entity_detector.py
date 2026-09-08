from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
detector_module = importlib.import_module("visible_entity_detector")


def draw_bar(
    frame: np.ndarray,
    *,
    center_x: int,
    y: int,
    bgr: tuple[int, int, int],
) -> None:
    frame[y : y + 6, center_x - 45 : center_x + 46, :3] = bgr


class VisibleEntityNameplateDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "navigation" / "visible-entity-nameplates-tbc243-v1.json"
        )
        self.detector = detector_module.VisibleEntityNameplateDetector(profile)

    def test_detects_hostile_neutral_and_friendly_bars(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        draw_bar(frame, center_x=250, y=260, bgr=(20, 30, 220))
        draw_bar(frame, center_x=400, y=300, bgr=(20, 200, 220))
        draw_bar(frame, center_x=550, y=340, bgr=(20, 220, 30))
        result = self.detector.detect(frame, observed_at_s=1.0)
        self.assertEqual({item.reaction for item in result}, {
            "HOSTILE", "NEUTRAL", "FRIENDLY",
        })
        self.assertEqual(len(result), 3)
        self.assertTrue(all(item.confidence >= 0.70 for item in result))

    def test_excludes_coloured_native_ui_regions(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        draw_bar(frame, center_x=100, y=150, bgr=(20, 220, 30))
        draw_bar(frame, center_x=730, y=150, bgr=(20, 220, 30))
        draw_bar(frame, center_x=400, y=260, bgr=(20, 220, 30))
        result = self.detector.detect(frame, observed_at_s=2.0)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].center_x_normalized, 0.0, places=2)

    def test_rejects_large_green_world_texture_as_not_nameplate_shape(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        frame[220:330, 260:540, :3] = (20, 220, 30)
        self.assertEqual(self.detector.detect(frame, observed_at_s=3.0), ())


if __name__ == "__main__":
    unittest.main()
