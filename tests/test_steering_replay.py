from __future__ import annotations

import unittest

from scripts import replay_world_steering_corridor as replay


class SteeringReplayTests(unittest.TestCase):
    def test_replay_defaults_match_validated_adaptive_runtime_profile(self) -> None:
        arguments = replay._parse_arguments([
            "--report", "fixture.json",
        ])
        self.assertEqual(arguments.mppi_batch_size, 256)
        self.assertEqual(arguments.mppi_time_steps, 56)
        self.assertEqual(arguments.mppi_replan_interval_ticks, 3)


if __name__ == "__main__":
    unittest.main()
