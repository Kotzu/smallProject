import unittest

from perfect_assassin.movement.manual_path_recording import ManualPathRecorder
from perfect_assassin.movement.operator_demonstration_analysis import (
    analyze_operator_demonstration,
)


class OperatorDemonstrationAnalysisTests(unittest.TestCase):
    def test_collapses_key_repeat_and_recovers_button_held_at_session_start(self) -> None:
        recorder = ManualPathRecorder("manual:test", "Reference")
        recorder.observe(x=0.0, y=0.0, observed_monotonic_s=1.0)
        recorder.observe(x=1.0, y=0.0, observed_monotonic_s=1.2)
        records = [
            {"sequence": 0, "kind": "SESSION_START", "elapsed_s": 0.0, "payload": {}},
            {"sequence": 1, "kind": "KEY", "elapsed_s": 0.1,
             "payload": {"virtual_key": 87, "state": "DOWN"}},
            {"sequence": 2, "kind": "KEY", "elapsed_s": 0.2,
             "payload": {"virtual_key": 87, "state": "DOWN"}},
            {"sequence": 3, "kind": "MOUSE_BUTTON", "elapsed_s": 0.4,
             "payload": {"button": "RIGHT", "state": "UP"}},
            {"sequence": 4, "kind": "KEY", "elapsed_s": 0.6,
             "payload": {"virtual_key": 87, "state": "UP"}},
            {"sequence": 5, "kind": "SESSION_STOP", "elapsed_s": 1.0, "payload": {}},
        ]

        report = analyze_operator_demonstration(records, recorder.finish())

        self.assertEqual(report["controls"]["MOVE_FORWARD"]["press_count"], 1)
        self.assertAlmostEqual(report["controls"]["MOVE_FORWARD"]["hold_seconds"], 0.5)
        self.assertTrue(report["controls"]["MOUSE_LOOK_RIGHT"]["started_held"])
        self.assertAlmostEqual(
            report["controls"]["MOUSE_LOOK_RIGHT"]["hold_seconds"], 0.4
        )


if __name__ == "__main__":
    unittest.main()
