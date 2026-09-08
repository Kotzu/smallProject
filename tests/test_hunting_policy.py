from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from perfect_assassin.brain.hunting import (
    HybridTargetSearchPolicy,
    SearchPoint,
    SearchRegion,
    TargetSearchState,
    VisibleCandidate,
    compile_target_exact_command,
)
from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]


def region(**changes: object) -> SearchRegion:
    values: dict[str, object] = {
        "region_id": "region:tirisfal:scavenger:one",
        "map_id": "map:tirisfal_glades",
        "anchor": SearchPoint(0.42, 0.51),
        "radius": 0.04,
        "prior_confidence": 0.8,
        "source_origin": "external_research",
        "evidence_refs": ("external-research:synthetic:scavenger:cluster-one",),
        "patrol_points": (SearchPoint(0.41, 0.50), SearchPoint(0.44, 0.53)),
    }
    values.update(changes)
    return SearchRegion(**values)  # type: ignore[arg-type]


def state(**changes: object) -> TargetSearchState:
    values: dict[str, object] = {
        "search_id": "search:scavenger:one",
        "actor_id": "actor:predator:champion",
        "target_profile": "tbc_243_lab",
        "map_id": "map:tirisfal_glades",
        "goal_kind": "hostile_mob",
        "target_names": ("Scavenger",),
        "current_position": SearchPoint(0.10, 0.10),
        "regions": (region(),),
    }
    values.update(changes)
    return TargetSearchState(**values)  # type: ignore[arg-type]


class HybridTargetSearchPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = HybridTargetSearchPolicy()
        self.validator = ContractValidator(ROOT / "contracts" / "target-search.schema.json")

    def assert_valid(self, decision) -> None:  # type: ignore[no-untyped-def]
        self.validator.validate(decision.to_record())

    def test_routes_to_best_known_habitat_before_name_probe(self) -> None:
        decision = self.policy.decide(state(), decision_id="decision:route")
        self.assertEqual(decision.action_id, "hunting.move_to_search_region")
        self.assertEqual(decision.destination, SearchPoint(0.42, 0.51))
        self.assert_valid(decision)

    def test_exact_name_probe_is_local_bounded_and_schema_valid(self) -> None:
        decision = self.policy.decide(
            state(current_position=SearchPoint(0.42, 0.51)),
            decision_id="decision:probe",
        )
        self.assertEqual(decision.action_id, "hunting.probe_exact_name")
        self.assertEqual(decision.command_preview, "/targetexact Scavenger")
        self.assertFalse(decision.to_record()["execution_authority"])
        self.assert_valid(decision)

    def test_visual_evidence_outranks_map_and_name_probe(self) -> None:
        decision = self.policy.decide(
            state(
                visible_candidates=(
                    VisibleCandidate(
                        detection_id="detection:scavenger:7",
                        kind="hostile_mob",
                        confidence=0.92,
                        bearing="RIGHT",
                        name="Scavenger",
                    ),
                )
            ),
            decision_id="decision:vision",
        )
        self.assertEqual(decision.action_id, "hunting.inspect_visible_candidate")
        self.assert_valid(decision)

    def test_client_confirmed_safe_target_is_ready_for_combat(self) -> None:
        decision = self.policy.decide(
            state(current_target_name="Scavenger", current_target_hostile=True),
            decision_id="decision:engage",
        )
        self.assertEqual(decision.action_id, "hunting.engage_confirmed_target")
        self.assert_valid(decision)

    def test_player_target_is_never_accepted(self) -> None:
        decision = self.policy.decide(
            state(
                current_target_name="Scavenger",
                current_target_hostile=True,
                current_target_is_player=True,
            ),
            decision_id="decision:reject-player",
        )
        self.assertEqual(decision.action_id, "hunting.reject_current_target")

    def test_after_probe_policy_sweeps_bounded_camera_sector(self) -> None:
        decision = self.policy.decide(
            state(
                current_position=SearchPoint(0.42, 0.51),
                exact_probed_region_ids=frozenset({"region:tirisfal:scavenger:one"}),
                sweep_step=3,
            ),
            decision_id="decision:sweep",
        )
        self.assertEqual(decision.action_id, "hunting.visual_sweep")
        self.assertEqual(decision.sweep_sector, 3)
        self.assert_valid(decision)

    def test_completed_sweep_follows_evidence_backed_patrol(self) -> None:
        decision = self.policy.decide(
            state(
                current_position=SearchPoint(0.42, 0.51),
                exact_probed_region_ids=frozenset({"region:tirisfal:scavenger:one"}),
                sweep_step=8,
                patrol_index=1,
            ),
            decision_id="decision:patrol",
        )
        self.assertEqual(decision.action_id, "hunting.patrol_search_region")
        self.assertEqual(decision.destination, SearchPoint(0.44, 0.53))
        self.assert_valid(decision)

    def test_negative_evidence_reduces_region_belief(self) -> None:
        original = region()
        revised = replace(original, negative_sweeps=3)
        self.assertLess(revised.belief_score, original.belief_score)

    def test_server_spawn_truth_is_rejected_for_champion_search(self) -> None:
        with self.assertRaises(ValueError):
            region(source_origin="server_spawn_state")

    def test_search_yields_to_combat_controller(self) -> None:
        decision = self.policy.decide(
            state(in_combat=True),
            decision_id="decision:combat-handoff",
        )
        self.assertEqual(decision.action_id, "hunting.stop_unsafe")
        self.assertEqual(decision.reason_code, "combat_owned_by_combat_controller")
        self.assert_valid(decision)

    def test_exact_command_rejects_chat_injection(self) -> None:
        with self.assertRaises(ValueError):
            compile_target_exact_command("Scavenger\n/logout")
        with self.assertRaises(ValueError):
            compile_target_exact_command("Scavenger;/logout")


if __name__ == "__main__":
    unittest.main()
