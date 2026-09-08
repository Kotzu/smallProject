from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "integrations" / "windows-input" / "run_single_forward_pulse.py"
HOTKEY = ROOT / "integrations" / "windows-input" / "pause_hotkey.py"
SESSION_ISSUER = ROOT / "scripts" / "issue_lab_session_authorization.py"


class SingleForwardPulseRunnerBoundaryTests(unittest.TestCase):
    def test_runner_is_one_pulse_only_and_requires_acknowledgement(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--acknowledge-single-pulse"', source)
        self.assertIn("issue_movement_authorization_snapshot", source)
        self.assertIn("issue_movement_runtime_arm_snapshot", source)
        self.assertIn("SingleForwardPulseCoordinator", source)
        self.assertIn("WindowsSendInputSink", source)
        self.assertIn("PauseHotkeySource", source)
        self.assertNotIn("MOVE_BACKWARD", source)
        self.assertNotIn("TURN_LEFT", source)
        self.assertNotIn("TURN_RIGHT", source)
        self.assertNotIn("server truth", source.lower())

    def test_manual_takeover_uses_register_hotkey_not_a_hook(self):
        source = HOTKEY.read_text(encoding="utf-8")
        self.assertIn("RegisterHotKey", source)
        self.assertIn("VK_PAUSE", source)
        self.assertIn("MOD_NOREPEAT", source)
        self.assertNotIn("SetWindowsHookEx", source)
        self.assertNotIn("GetAsyncKeyState", source)

    def test_session_authorization_issuer_is_temporal_only(self):
        source = SESSION_ISSUER.read_text(encoding="utf-8")
        self.assertIn("issue_session_authorization_snapshot", source)
        self.assertIn("--acknowledge-fixed-ui-session", source)
        self.assertIn("--renewal-parent-sha256", source)
        self.assertNotIn("Start-Process", source)
        self.assertNotIn("SendInput", source)


if __name__ == "__main__":
    unittest.main()
