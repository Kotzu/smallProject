from __future__ import annotations

from pathlib import Path
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.lab.entity_awareness import (
    ClientEntityWitness,
    LabGroundTruthEntity,
    evaluate_entity_awareness,
)


ROOT = Path(__file__).resolve().parents[1]


class LabEntityAwarenessTests(unittest.TestCase):
    def test_scoring_keeps_server_truth_in_lab_and_does_not_infer_missing_position(self) -> None:
        record = evaluate_entity_awareness(
            evaluation_id="lab:awareness:001",
            map_name="Azeroth",
            ground_truth=(
                LabGroundTruthEntity("npc:alpha", "hostile_mob", (10.0, 20.0, 3.0)),
                LabGroundTruthEntity("npc:bravo", "friendly_npc", (40.0, 50.0, 4.0)),
            ),
            witnesses=(
                ClientEntityWitness("npc:alpha", "hostile_mob"),
                ClientEntityWitness(None, "unknown"),
            ),
        )
        ContractValidator(
            ROOT / "contracts" / "lab-entity-awareness-evaluation.schema.json"
        ).validate(record)
        self.assertEqual(record["matched_identity_count"], 1)
        self.assertEqual(record["identity_recall"], 0.5)
        self.assertEqual(record["identity_precision"], 0.5)
        self.assertEqual(record["unlocalized_match_count"], 1)
        self.assertEqual(record["position_coverage"], 0.0)
        self.assertEqual(record["ground_truth_origin"], "server_ground_truth")
        self.assertFalse(record["execution_authority"])

    def test_position_error_is_scored_only_when_client_witness_has_coordinates(self) -> None:
        record = evaluate_entity_awareness(
            evaluation_id="lab:awareness:002",
            map_name="Azeroth",
            ground_truth=(
                LabGroundTruthEntity("npc:alpha", "hostile_mob", (0.0, 0.0, 0.0)),
            ),
            witnesses=(
                ClientEntityWitness("npc:alpha", "hostile_mob", (3.0, 4.0, 0.0)),
            ),
        )
        self.assertEqual(record["localized_match_count"], 1)
        self.assertEqual(record["position_coverage"], 1.0)
        self.assertEqual(record["mean_position_error_yards"], 5.0)
        self.assertEqual(record["max_position_error_yards"], 5.0)

    def test_duplicate_ids_and_bad_truth_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ground truth entity IDs"):
            evaluate_entity_awareness(
                evaluation_id="lab:awareness:003",
                map_name="Azeroth",
                ground_truth=(
                    LabGroundTruthEntity("npc:alpha", "hostile_mob", (0.0, 0.0, 0.0)),
                    LabGroundTruthEntity("npc:alpha", "hostile_mob", (1.0, 1.0, 1.0)),
                ),
                witnesses=(),
            )
        with self.assertRaisesRegex(ValueError, "client witness entity IDs"):
            evaluate_entity_awareness(
                evaluation_id="lab:awareness:004",
                map_name="Azeroth",
                ground_truth=(
                    LabGroundTruthEntity("npc:alpha", "hostile_mob", (0.0, 0.0, 0.0)),
                ),
                witnesses=(
                    ClientEntityWitness("npc:alpha", "hostile_mob"),
                    ClientEntityWitness("npc:alpha", "hostile_mob"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
