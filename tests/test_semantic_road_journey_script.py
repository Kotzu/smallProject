from __future__ import annotations

import unittest

from scripts.validate_semantic_road_journey import (
    CASE_NAMES,
    select_validation_cases,
)


class SemanticRoadJourneyScriptTests(unittest.TestCase):
    def test_empty_selection_preserves_full_regression_order(self) -> None:
        self.assertEqual(
            tuple(case[0] for case in select_validation_cases([])),
            CASE_NAMES,
        )

    def test_subset_preserves_canonical_order_not_argument_order(self) -> None:
        selected = select_validation_cases([
            "hill_fixture_requires_reset",
            "canonical_crypt_spawn_to_brill",
        ])
        self.assertEqual(
            tuple(case[0] for case in selected),
            (
                "canonical_crypt_spawn_to_brill",
                "hill_fixture_requires_reset",
            ),
        )

    def test_duplicate_or_unknown_selection_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_validation_cases([
                "canonical_crypt_spawn_to_brill",
                "canonical_crypt_spawn_to_brill",
            ])
        with self.assertRaises(ValueError):
            select_validation_cases(["invented_case"])


if __name__ == "__main__":
    unittest.main()
