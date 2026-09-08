from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "integrations" / "windows-input" / "send_input_backend.py"


class WorldDragCursorLayoutTests(unittest.TestCase):
    def test_reviewed_drag_origin_avoids_expanded_chat_and_center_target_lane(self) -> None:
        source = BACKEND.read_text(encoding="utf-8")

        self.assertIn("(width * 72) // 100", source)
        self.assertIn("(height * 38) // 100", source)
        self.assertNotIn("width // 4, (height * 3) // 4", source)


if __name__ == "__main__":
    unittest.main()
