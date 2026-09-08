from __future__ import annotations

import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.combat_range import (
    ROGUE_ABILITY_RANGE_ENVELOPES,
    MeleeRangeRelation,
    RangeBand,
    SpellRangeEnvelope,
    rogue_ability_range,
    selected_target_melee_range_awareness,
)


class SpellRangeEnvelopeTests(unittest.TestCase):
    def test_melee_client_rejection_can_only_mean_too_far(self) -> None:
        melee = SpellRangeEnvelope("rogue.melee", 0.0, 5.0)

        self.assertIs(
            melee.classify(client_in_range=False),
            RangeBand.TOO_FAR,
        )

    def test_ranged_dead_zone_rejection_does_not_guess_a_direction(self) -> None:
        ranged = SpellRangeEnvelope("rogue.ranged", 5.0, 30.0)

        self.assertIs(
            ranged.classify(client_in_range=False),
            RangeBand.OUTSIDE_UNKNOWN,
        )

    def test_distance_distinguishes_both_sides_of_a_range_envelope(self) -> None:
        ranged = SpellRangeEnvelope("rogue.ranged", 5.0, 30.0)

        self.assertIs(
            ranged.classify(client_in_range=False, distance_yards=3.0),
            RangeBand.TOO_CLOSE,
        )
        self.assertIs(
            ranged.classify(client_in_range=False, distance_yards=35.0),
            RangeBand.TOO_FAR,
        )

    def test_client_permission_is_required_even_if_estimate_looks_valid(self) -> None:
        ranged = SpellRangeEnvelope("rogue.ranged", 5.0, 30.0)

        self.assertIs(
            ranged.classify(client_in_range=False, distance_yards=15.0),
            RangeBand.OUTSIDE_UNKNOWN,
        )
        self.assertIs(
            ranged.classify(client_in_range=True, distance_yards=15.0),
            RangeBand.IN_RANGE,
        )

    def test_missing_evidence_is_unknown(self) -> None:
        melee = SpellRangeEnvelope("rogue.melee", 0.0, 5.0)

        self.assertIs(
            melee.classify(client_in_range=None),
            RangeBand.UNKNOWN,
        )

    def test_each_bound_level_one_action_has_its_own_reviewed_envelope(self) -> None:
        expected = {
            "rogue.auto_attack",
            "rogue.sinister_strike",
            "rogue.eviscerate",
        }

        self.assertEqual(set(ROGUE_ABILITY_RANGE_ENVELOPES), expected)
        for ability_id in expected:
            envelope = rogue_ability_range(ability_id)
            self.assertEqual(envelope.ability_id, ability_id)
            self.assertEqual((envelope.min_yards, envelope.max_yards), (0.0, 5.0))

    def test_unreviewed_spell_range_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "not reviewed"):
            rogue_ability_range("rogue.future_spell")

    def test_selected_target_range_fuses_equal_melee_witnesses(self) -> None:
        record = selected_target_melee_range_awareness(
            target_identity_crc16=1234,
            observed_monotonic_s=20.0,
            expires_monotonic_s=20.6,
            ability_witnesses={
                "rogue.auto_attack": True,
                "rogue.sinister_strike": True,
                "rogue.eviscerate": None,
            },
        )
        ContractValidator(
            Path(__file__).parents[1]
            / "contracts" / "selected-target-range-awareness.schema.json"
        ).validate(record)
        self.assertEqual(
            record["derived_relation"],
            MeleeRangeRelation.IN_RANGE_0_TO_5.value,
        )
        self.assertIsNone(record["exact_distance_yards"])
        self.assertFalse(record["execution_authority"])

    def test_selected_target_range_reports_conflicting_client_witnesses(self) -> None:
        record = selected_target_melee_range_awareness(
            target_identity_crc16=1234,
            observed_monotonic_s=20.0,
            expires_monotonic_s=20.5,
            ability_witnesses={
                "rogue.auto_attack": True,
                "rogue.sinister_strike": False,
            },
        )
        self.assertEqual(
            record["derived_relation"],
            MeleeRangeRelation.INCONSISTENT.value,
        )


if __name__ == "__main__":
    unittest.main()
