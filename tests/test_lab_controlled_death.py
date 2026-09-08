from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Invoke-LabControlledDeath.ps1"


class LabControlledDeathBoundaryTests(unittest.TestCase):
    def test_wrapper_is_one_exact_named_lab_command(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[ValidatePattern('^[A-Za-z][A-Za-z0-9]{1,11}$')]", source)
        self.assertIn('-Command "labkill $PlayerName"', source)
        self.assertIn(
            '"LAB controlled death for $PlayerName is now active."',
            source,
        )
        self.assertNotIn("SendKeys", source)
        self.assertNotIn("Wow.exe", source)


if __name__ == "__main__":
    unittest.main()
