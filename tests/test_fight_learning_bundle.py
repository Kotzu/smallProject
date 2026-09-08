from __future__ import annotations

import copy
import unittest

from perfect_assassin.contract_validation import ContractValidationError
from perfect_assassin.lab.fight_learning import (
    FightLearningBundleError,
    validate_fight_learning_bundle,
)


def _bundle() -> dict:
    digest = "a" * 64
    timeline = [
        ("obs:1", "OBSERVATION", "CLIENT_VISIBLE", 0.0),
        ("decision:1", "DECISION", "DECISION_BRAIN", 1.0),
        ("auth:1", "AUTHORIZATION", "EXECUTION_GATEWAY", 2.0),
        ("input:1", "INPUT", "WINDOW_INPUT", 3.0),
        ("effect:1", "EFFECT", "CLIENT_VISIBLE", 103.0),
        ("score:1", "POST_FIGHT_SCORE", "LAB_SCORER_POST_FIGHT", 200.0),
    ]
    return {
        "record_type": "fight_learning_bundle",
        "schema_version": "1.0",
        "encounter_id": "encounter:gurubashi:1",
        "run_id": "run:1",
        "memory_scope": "lab_clone",
        "manifest": {
            "encounter_type": "pvp",
            "target_profile": "tbc_243_lab",
            "client_build": "2.4.3.8606",
            "realm_fingerprint_sha256": digest,
            "brain_version": "candidate:1",
            "policy_sha256": digest,
            "spellbook_sha256": digest,
            "talents_sha256": digest,
            "gear_sha256": digest,
            "map_id": 0,
            "environment_sha256": digest,
            "started_at": "2026-08-29T00:00:00Z",
            "ended_at": "2026-08-29T00:00:10Z",
            "participants": [
                {"participant_ref": "clone:predator", "role": "predator", "class": "rogue", "level": 60, "profile_sha256": digest},
                {"participant_ref": "bot:opponent", "role": "opponent", "class": "mage", "level": 60, "profile_sha256": digest},
            ],
        },
        "timeline": [
            {"sequence": index, "event_id": event_id, "monotonic_ms": timing, "kind": kind, "source": source, "evidence_refs": [], "payload": {}}
            for index, (event_id, kind, source, timing) in enumerate(timeline, start=1)
        ],
        "action_chains": [{
            "action_id": "action:kick:1",
            "observation_ref": "obs:1",
            "decision_ref": "decision:1",
            "authorization_ref": "auth:1",
            "input_ref": "input:1",
            "effect_ref": "effect:1",
            "effect_status": "CONFIRMED",
        }],
        "outcome": "VICTORY",
        "metrics": {"time_to_kill_ms": 10000.0},
        "diagnosis": {
            "primary_cause": "NONE",
            "cause_scores": {"decision": 0.0, "execution": 0.0, "perception": 0.0, "movement_environment": 0.0, "game_variance": 0.1},
            "mistakes": [],
            "counterfactuals": [],
        },
        "promotion": {"status": "CANDIDATE_EVIDENCE", "promotion_eligible": False, "reason": "single fight cannot promote a policy"},
        "artifacts": [{"kind": "VIDEO_CLIP", "artifact_ref": "clip:1", "sha256": digest}],
        "execution_authority": False,
    }


class FightLearningBundleTests(unittest.TestCase):
    def test_complete_chain_is_valid(self) -> None:
        self.assertEqual(validate_fight_learning_bundle(_bundle())["outcome"], "VICTORY")

    def test_lab_scorer_cannot_supply_a_live_decision(self) -> None:
        value = _bundle()
        value["timeline"][1]["source"] = "LAB_SCORER_POST_FIGHT"
        with self.assertRaisesRegex(FightLearningBundleError, "invalid evidence source"):
            validate_fight_learning_bundle(value)

    def test_broken_action_reference_fails(self) -> None:
        value = _bundle()
        value["action_chains"][0]["effect_ref"] = "effect:missing"
        with self.assertRaisesRegex(FightLearningBundleError, "does not reference EFFECT"):
            validate_fight_learning_bundle(value)

    def test_timeline_cannot_move_backwards(self) -> None:
        value = _bundle()
        value["timeline"][2]["monotonic_ms"] = 0.5
        with self.assertRaisesRegex(FightLearningBundleError, "time moved backwards"):
            validate_fight_learning_bundle(value)

    def test_one_fight_can_never_be_promotion_eligible(self) -> None:
        value = copy.deepcopy(_bundle())
        value["promotion"]["promotion_eligible"] = True
        with self.assertRaises(ContractValidationError):
            validate_fight_learning_bundle(value)


if __name__ == "__main__":
    unittest.main()
