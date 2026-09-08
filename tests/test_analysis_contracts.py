from __future__ import annotations

import unittest
from pathlib import Path

from perfect_assassin.analysis.gear_policy import GearAvailabilityPolicy, GearPolicyError
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]


class AnalysisContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gear_validator = ContractValidator(ROOT / "contracts" / "gear-analysis.schema.json")
        self.target_validator = ContractValidator(ROOT / "contracts" / "target-profile.schema.json")
        self.policy = GearAvailabilityPolicy()

    @staticmethod
    def request(availability: str = "observed_reward_option") -> dict:
        return {
            "record_type": "gear_analysis_request",
            "schema_version": "0.1",
            "analysis_id": "gear:test:1",
            "champion_id": "champion:predator",
            "target_profile": "tbc_243_lab",
            "optimization_profile": "leveling_balanced",
            "snapshot_hash": "a" * 64,
            "observation_event_ids": ["event:quest:reward"],
            "candidates": [
                {
                    "item_ref": "item:test:dagger",
                    "semantic_slot": "main_hand",
                    "availability": availability,
                    "evidence_refs": ["event:quest:reward"],
                }
            ],
            "created_at": "2026-08-22T12:00:00Z",
        }

    @staticmethod
    def result(recommended: str | None = "item:test:dagger") -> dict:
        return {
            "record_type": "gear_analysis_result",
            "schema_version": "0.1",
            "analysis_id": "gear:test:1",
            "analysis_kind": "counterfactual_analysis",
            "analyzer_id": "leveling_gear_evaluator",
            "analyzer_version": "0.1.0",
            "target_profile": "tbc_243_lab",
            "assumptions": {"fight_duration_seconds": 20},
            "ranking": [
                {
                    "item_ref": "item:test:dagger",
                    "score": 1.0,
                    "metrics": {"pve_damage": 1.0},
                    "reasons": ["Observed quest reward"],
                }
            ],
            "recommended_item_ref": recommended,
            "confidence": 0.5,
            "warnings": ["Synthetic contract fixture"],
            "evidence_refs": ["event:quest:reward"],
            "created_at": "2026-08-22T12:00:01Z",
        }

    def test_observed_reward_can_be_recommended(self) -> None:
        request = self.request()
        result = self.result()
        self.gear_validator.validate(request)
        self.gear_validator.validate(result)
        self.policy.validate_recommendation(request, result)

    def test_researched_item_cannot_be_recommended_as_available(self) -> None:
        request = self.request("researched_only")
        result = self.result()
        self.gear_validator.validate(request)
        self.gear_validator.validate(result)
        with self.assertRaises(GearPolicyError):
            self.policy.validate_recommendation(request, result)

    def test_unknown_target_cannot_negotiate_full_ai(self) -> None:
        invalid = {
            "record_type": "capability_negotiation",
            "schema_version": "0.1",
            "negotiation_id": "negotiation:unknown",
            "fingerprint_id": "fingerprint:unknown",
            "adapter_id": "adapter:none",
            "adapter_version": "0.0.0",
            "status": "unsupported",
            "capability_profile": "deny_all",
            "execution_mode": "FULL_AI",
            "confidence": 1.0,
            "negotiated_at": "2026-08-22T12:00:00Z",
            "evidence_refs": ["probe:unknown"],
        }
        with self.assertRaises(ContractValidationError):
            self.target_validator.validate(invalid)


if __name__ == "__main__":
    unittest.main()
