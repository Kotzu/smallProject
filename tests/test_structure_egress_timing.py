import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "egress_timing", Path(__file__).resolve().parents[1] / "scripts/report_structure_egress_timing.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def frame(index, stamp):
    return {"kind": "CONTINUOUS_FRAME", "frame_index": index,
            "observed_monotonic_s": stamp,
            "decision_observation": {"observed_monotonic_s": stamp - 0.1}}


class TimingTests(unittest.TestCase):
    def test_arrival_is_not_egress(self):
        record = {"status": "ARRIVED", "actions": [frame(1, 100), frame(2, 109),
                  {"kind": "STRUCTURE_EGRESS_FLYBY", "remaining_to_opening_world": 2.9},
                  frame(3, 110), frame(4, 133.5)]}
        result = module.timing_report(record)
        self.assertEqual(result["first_to_last_post_observation_s"], 33.5)
        event = result["egress_handoffs"][0]
        self.assertAlmostEqual(event["elapsed_lower_s"], 9.1)
        self.assertAlmostEqual(event["elapsed_upper_s"], 10.1)
        self.assertFalse(event["whole_body_exit_confirmed"])
        self.assertIsNone(result["completed_exit_elapsed_s"])
        self.assertFalse(result["human_reference_comparable"])

    def test_no_handoff_does_not_invent_exit(self):
        result = module.timing_report({"actions": [frame(1, 100)]})
        self.assertEqual(result["egress_handoffs"], [])
        self.assertIsNone(result["completed_exit_elapsed_s"])

    def test_unbracketed_handoff_preserves_unknown(self):
        result = module.timing_report({"actions": [frame(1, 100), {"kind": "STRUCTURE_EGRESS_FLYBY"}]})
        self.assertIsNone(result["egress_handoffs"][0]["elapsed_upper_s"])

    def test_bad_clock_rejected(self):
        for stamps in ((101, 100), (100, float("nan"))):
            with self.assertRaises(ValueError):
                module.timing_report({"actions": [frame(i, t) for i, t in enumerate(stamps)]})

    def test_no_frames_rejected(self):
        with self.assertRaises(ValueError):
            module.timing_report({"actions": []})


if __name__ == "__main__":
    unittest.main()
