from __future__ import annotations

import argparse
import unittest

from scripts.search_steering_tuning import (
    TUNING_PIVOT_GAINS,
    _minimum_tuning_runs,
    _tuning_scenarios,
)


class SteeringTuningCorpusTests(unittest.TestCase):
    def test_tuning_runs_rejects_values_below_simulation_contract(self) -> None:
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "at least 100"):
            _minimum_tuning_runs("50")

        self.assertEqual(_minimum_tuning_runs("100"), 100)

    def test_tuning_grid_includes_reviewed_production_pivot_gain(self) -> None:
        self.assertIn(3.4, TUNING_PIVOT_GAINS)

    def test_tuning_search_uses_complete_hairpin_and_obstacle_corpus(self) -> None:
        scenarios = _tuning_scenarios(runs=100)
        self.assertEqual(
            tuple(item.scenario_id for item in scenarios),
            (
                "confined_straight",
                "confined_stair_bend",
                "narrow_s_gate",
                "open_ground_doodad_gateway",
                "straight_bridge",
                "narrow_outdoor_hairpin",
            ),
        )
        self.assertTrue(scenarios[-1].corridor.portals)
        self.assertEqual(scenarios[-1].corridor.portals[0].width, 2.20362)
        self.assertTrue(scenarios[3].static_obstacles)
        self.assertTrue(scenarios[3].corridor.doodad_avoidance_applied)


if __name__ == "__main__":
    unittest.main()
