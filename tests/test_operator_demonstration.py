from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import unittest

from perfect_assassin.movement.operator_demonstration import (
    OperatorDemonstrationTimeline,
)


class OperatorDemonstrationTimelineTests(unittest.TestCase):
    def test_input_pose_and_video_share_one_monotonic_clock(self) -> None:
        stream = StringIO()
        timeline = OperatorDemonstrationTimeline(
            Path("unused.jsonl"),
            recording_id="manual:test",
            target_pid=123,
            target_hwnd=456,
            started_monotonic_ns=1_000_000_000,
            stream=stream,
        )
        timeline.append(
            "WINDOW",
            monotonic_ns=1_050_000_000,
            foreground_matches_target=True,
            payload={"client_width": 2560, "client_height": 1440},
        )
        timeline.append(
            "VIDEO_START",
            monotonic_ns=1_100_000_000,
            foreground_matches_target=True,
            payload={"path": "demo.mp4", "fps": 60},
        )
        timeline.append(
            "KEY",
            monotonic_ns=1_125_000_000,
            foreground_matches_target=True,
            payload={"virtual_key": 87, "state": "DOWN"},
        )
        timeline.append(
            "POSE",
            monotonic_ns=1_150_000_000,
            foreground_matches_target=True,
            payload={"world_x": 12.0, "world_y": 34.0},
        )

        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([record["sequence"] for record in records], [0, 1, 2, 3, 4])
        self.assertEqual(records[1]["elapsed_s"], 0.05)
        self.assertEqual(records[2]["elapsed_s"], 0.1)
        self.assertEqual(records[3]["elapsed_s"], 0.125)
        self.assertEqual(records[4]["elapsed_s"], 0.15)
        self.assertFalse(records[0]["payload"]["execution_authority"])

    def test_rejects_unknown_event_type(self) -> None:
        timeline = OperatorDemonstrationTimeline(
            Path("unused.jsonl"),
            recording_id="manual:test",
            target_pid=123,
            target_hwnd=456,
            started_monotonic_ns=1_000,
            stream=StringIO(),
        )
        with self.assertRaisesRegex(ValueError, "event"):
            timeline.append(
                "UNREVIEWED",
                monotonic_ns=2_000,
                foreground_matches_target=True,
                payload={},
            )


if __name__ == "__main__":
    unittest.main()
