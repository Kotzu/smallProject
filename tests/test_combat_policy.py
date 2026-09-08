from __future__ import annotations

import copy
import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from perfect_assassin.application.combat_intake import (
    decode_combat_observation,
    decode_crc_target_bearing,
)
from perfect_assassin.brain.combat import (
    CombatDecision,
    RogueLevelOneCombatPolicy,
    estimate_rank1_eviscerate,
    validate_combat_decision_semantics,
)
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.domain.combat import (
    CombatActionState,
    CombatObservationState,
    CombatTargetState,
    TargetBearingState,
)
from tests.test_combat_hud import synthetic_combat_hud, valid_packet
from tests.test_coordinate_hud import capture_manifest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
detector_module = importlib.import_module("combat_hud_detector")


def action(
    *,
    exact: bool = True,
    usable: bool = True,
    current: bool = False,
    in_range: bool | None = True,
    ready: bool = True,
) -> CombatActionState:
    return CombatActionState(
        exact_binding=exact,
        usable=usable,
        current=current,
        in_range=in_range,
        cooldown_ready=ready,
        cooldown_remaining_ms=0 if ready or not exact else 500,
    )


def state(**changes: object) -> CombatObservationState:
    values: dict[str, object] = {
        "observation_id": "combat-hud:fixture:policy:1",
        "frame_id": "capture:fixture:policy:1",
        "observation_sha256": "B" * 64,
        "authorization_sha256": "A" * 64,
        "actor_id": "actor:predator:lab",
        "actor_instance_id": "instance:predator:lab:one",
        "target_profile": "tbc_243_lab",
        "sequence": 7,
        "observed_monotonic_s": 10.1,
        "expires_monotonic_s": 10.6,
        "confidence": 1.0,
        "provenance_scope": "lab_evaluation_only",
        "player_alive": True,
        "player_health_pct": 100.0,
        "player_energy": 100,
        "player_attack_power": 20,
        "player_level": 1,
        "in_combat": True,
        "combo_points": 0,
        "target": CombatTargetState(
            identity_crc16=1234,
            hostile=True,
            dead=False,
            is_player=False,
            health_pct=100.0,
            health_current=40,
            health_max=40,
            level=1,
            reaction=2,
        ),
        "attack": action(current=False),
        "sinister_strike": action(),
        "eviscerate": action(),
    }
    values.update(changes)
    return CombatObservationState(**values)  # type: ignore[arg-type]


def bearing(
    observed: CombatObservationState,
    *,
    tracking_state: str = "VISIBLE",
    direction: str | None = "CENTER",
    offset_x_normalized: float | None = 0.0,
) -> TargetBearingState:
    target_identity = (
        None if observed.target is None else observed.target.identity_crc16
    )
    confidence = 0.95 if tracking_state == "VISIBLE" else 0.0
    return TargetBearingState(
        observation_id=f"target-bearing:fixture:{observed.sequence}",
        observation_sha256=f"{observed.sequence + 100:064X}",
        frame_id=observed.frame_id,
        combat_observation_id=observed.observation_id,
        combat_observation_sha256=observed.observation_sha256,
        authorization_sha256=observed.authorization_sha256,
        actor_id=observed.actor_id,
        actor_instance_id=observed.actor_instance_id,
        target_profile=observed.target_profile,
        target_identity_crc16=target_identity,
        tracking_state=tracking_state,
        direction=direction,
        offset_x_normalized=offset_x_normalized,
        center_y_normalized=None,
        observed_monotonic_s=observed.observed_monotonic_s,
        expires_monotonic_s=min(
            observed.expires_monotonic_s,
            observed.observed_monotonic_s + 0.4,
        ),
        confidence=confidence,
        provenance_scope=observed.provenance_scope,
    )


class RogueLevelOneCombatPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = RogueLevelOneCombatPolicy()

    def test_yellow_neutral_npc_is_attackable_but_green_friendly_is_not(self) -> None:
        observed = state(in_combat=False)
        assert observed.target is not None
        yellow_target = replace(observed.target, hostile=False, reaction=4, level=1)
        yellow = replace(observed, target=yellow_target)
        facing = self.policy.decide_facing_only(
            yellow,
            decision_id="decision:yellow:facing",
            bearing=bearing(yellow, direction="LEFT", offset_x_normalized=-0.4),
        )
        self.assertTrue(yellow_target.attackable_npc)
        self.assertEqual(facing.requested_control, "TURN_LEFT")
        self.assertFalse(replace(yellow_target, reaction=5).attackable_npc)

    def decide(self, observed: CombatObservationState) -> CombatDecision:
        return self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:1",
            bearing=None if observed.target is None else bearing(observed),
        )

    def test_survival_and_player_target_preempt_damage(self) -> None:
        critical = self.decide(state(player_health_pct=25.0))
        self.assertEqual(critical.action_id, "combat.request_safe_retreat")
        self.assertEqual(critical.priority_tier, "SURVIVAL")

        player_target = replace(
            state(),
            target=replace(state().target, is_player=True),  # type: ignore[arg-type]
        )
        decision = self.decide(player_target)
        self.assertEqual(decision.action_id, "combat.reject_player_target")
        self.assertIsNone(decision.requested_control)

    def test_target_validation_precedes_rotation(self) -> None:
        self.assertEqual(
            self.decide(state(target=None, in_combat=False)).action_id,
            "combat.acquire_hostile_target",
        )
        risky = replace(
            state(),
            target=replace(state().target, level=3),  # type: ignore[arg-type]
        )
        self.assertEqual(
            self.decide(risky).reason_code,
            "target_level_out_of_bounds",
        )
        dead = replace(
            state(),
            target=replace(
                state().target, dead=True, health_pct=0.0, health_current=0
            ),  # type: ignore[arg-type]
        )
        self.assertEqual(self.decide(dead).action_id, "combat.target_defeated")

    def test_target_free_acquisition_scan_is_precombat_and_non_damaging(self) -> None:
        observed = state(target=None, in_combat=False)
        scan = self.policy.decide_acquisition_scan(
            observed,
            decision_id="combat-decision:fixture:scan",
        )
        self.assertEqual(scan.action_id, "combat.scan_for_hostile_target")
        self.assertEqual(scan.requested_control, "TURN_RIGHT")
        self.assertIsNone(scan.bearing)
        ContractValidator(ROOT / "contracts" / "combat-decision.schema.json").validate(
            scan.to_record(created_at="2026-08-24T12:00:00Z")
        )
        with self.assertRaisesRegex(ValueError, "target-free pre-combat"):
            self.policy.decide_acquisition_scan(
                state(target=None, in_combat=True),
                decision_id="combat-decision:fixture:unsafe-scan",
            )

    def test_exact_action_binding_and_range_are_fail_closed(self) -> None:
        unbound = state(
            sinister_strike=action(
                exact=False,
                usable=False,
                current=False,
                in_range=None,
                ready=False,
            )
        )
        self.assertEqual(
            self.decide(unbound).action_id,
            "combat.stop_action_binding_mismatch",
        )
        out_of_range = state(
            attack=action(current=False, in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        self.assertEqual(
            self.decide(out_of_range).action_id,
            "combat.approach_target",
        )

    def test_out_of_range_target_is_visually_steered_before_forward_motion(self) -> None:
        observed = state(
            attack=action(current=False, in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        left = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:left",
            bearing=bearing(
                observed,
                direction="LEFT",
                offset_x_normalized=-0.2,
            ),
        )
        self.assertEqual(left.action_id, "combat.turn_toward_target_left")
        self.assertEqual(left.requested_control, "TURN_LEFT")

        lost = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:lost",
            bearing=bearing(
                observed,
                tracking_state="LOST",
                direction=None,
                offset_x_normalized=None,
            ),
        )
        self.assertEqual(lost.action_id, "combat.search_selected_target")
        self.assertEqual(lost.requested_control, "TURN_RIGHT")

        unavailable = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:no-bearing",
            bearing=None,
        )
        self.assertEqual(unavailable.action_id, "combat.hold_bearing_unavailable")
        self.assertIsNone(unavailable.requested_control)

    def test_in_range_target_is_faced_before_the_first_damage_action(self) -> None:
        observed = state()
        left = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:in-range-left",
            bearing=bearing(
                observed,
                direction="LEFT",
                offset_x_normalized=-0.75,
            ),
        )
        self.assertEqual(left.action_id, "combat.turn_toward_target_left")
        self.assertEqual(left.requested_control, "TURN_LEFT")

        lost = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:in-range-lost",
            bearing=bearing(
                observed,
                tracking_state="LOST",
                direction=None,
                offset_x_normalized=None,
            ),
        )
        self.assertEqual(lost.action_id, "combat.search_selected_target")
        self.assertEqual(lost.requested_control, "TURN_RIGHT")

    def test_rotation_starts_attack_builds_and_finishes_from_fresh_state(self) -> None:
        start = self.decide(state())
        self.assertEqual(start.action_id, "rogue.auto_attack")
        self.assertEqual(start.requested_control, "ACTION_SLOT_1")

        building = self.decide(state(attack=action(current=True), player_energy=45))
        self.assertEqual(building.action_id, "rogue.sinister_strike")
        self.assertEqual(building.requested_control, "ACTION_SLOT_2")

        finishing = self.decide(
            state(
                attack=action(current=True),
                combo_points=2,
                player_energy=35,
                target=replace(
                    state().target, health_pct=25.0, health_current=10
                ),  # type: ignore[arg-type]
            )
        )
        self.assertEqual(finishing.action_id, "rogue.eviscerate")
        self.assertEqual(finishing.requested_control, "ACTION_SLOT_3")
        self.assertEqual(finishing.reason_code, "finisher_likely_kill_window")

        low_target_finisher = self.decide(
            state(
                attack=action(current=True),
                combo_points=1,
                player_energy=35,
                target=replace(
                    state().target, health_pct=12.5, health_current=5
                ),  # type: ignore[arg-type]
            )
        )
        self.assertEqual(low_target_finisher.action_id, "rogue.eviscerate")

        not_yet_lethal = self.decide(
            state(
                attack=action(current=True),
                combo_points=2,
                player_energy=80,
                target=replace(
                    state().target, health_pct=40.0, health_current=16
                ),  # type: ignore[arg-type]
            )
        )
        self.assertEqual(not_yet_lethal.action_id, "rogue.sinister_strike")

    def test_rank1_finisher_estimate_scales_points_ap_and_overkill(self) -> None:
        one = estimate_rank1_eviscerate(
            combo_points=1, attack_power=20, target_health_current=5
        )
        two = estimate_rank1_eviscerate(
            combo_points=2, attack_power=20, target_health_current=10
        )
        self.assertEqual((one.raw_min, one.raw_max), (6, 10))
        self.assertEqual((two.raw_min, two.raw_max), (12, 16))
        self.assertTrue(one.likely_kill)
        self.assertTrue(two.likely_kill)
        self.assertEqual(one.likely_overkill, 1)

        capped = self.decide(
            state(
                attack=action(current=True),
                combo_points=5,
                player_energy=35,
            )
        )
        self.assertEqual(capped.action_id, "rogue.eviscerate")
        self.assertEqual(capped.reason_code, "finisher_combo_cap_window")

    def test_exact_builder_range_can_witness_melee_for_generic_attack(self) -> None:
        observed = state(
            attack=action(in_range=None),
            sinister_strike=action(in_range=True),
        )
        decision = self.decide(observed)
        self.assertEqual(decision.action_id, "rogue.auto_attack")
        self.assertEqual(decision.requested_control, "ACTION_SLOT_1")

        unknown = state(
            attack=action(in_range=None),
            sinister_strike=action(in_range=None),
        )
        self.assertEqual(
            self.decide(unknown).action_id,
            "combat.hold_range_unknown",
        )

    def test_energy_and_cooldown_windows_orbit_without_repeating_auto_attack(self) -> None:
        energy_orbit = self.decide(
            state(attack=action(current=True), player_energy=20)
        )
        self.assertEqual(energy_orbit.action_id, "combat.orbit_target_right")
        self.assertEqual(energy_orbit.requested_control, "STRAFE_RIGHT")
        self.assertEqual(
            energy_orbit.reason_code,
            "magnetic_orbit_energy_regeneration",
        )

        cooldown_orbit = self.decide(
            state(
                attack=action(current=True),
                sinister_strike=action(ready=False),
                player_energy=100,
            )
        )
        self.assertEqual(
            cooldown_orbit.reason_code,
            "magnetic_orbit_global_cooldown_active",
        )

        odd_target = replace(state().target, identity_crc16=1235)
        assert odd_target is not None
        left = self.decide(
            state(
                attack=action(current=True),
                player_energy=20,
                target=odd_target,
            )
        )
        self.assertEqual(left.action_id, "combat.orbit_target_left")
        self.assertEqual(left.requested_control, "STRAFE_LEFT")

        throttled = self.decide(
            state(
                sequence=8,
                attack=action(current=True),
                player_energy=20,
            )
        )
        self.assertEqual(throttled.action_id, "combat.monitor_auto_attack")
        self.assertIsNone(throttled.requested_control)

        out_of_combat = self.decide(
            state(
                attack=action(current=True),
                player_energy=20,
                in_combat=False,
            )
        )
        self.assertEqual(out_of_combat.action_id, "combat.monitor_auto_attack")
        self.assertIsNone(out_of_combat.requested_control)

    def test_decision_contract_binds_observation_target_and_control(self) -> None:
        decision = self.decide(state())
        record = decision.to_record(created_at="2026-08-24T12:00:00Z")
        ContractValidator(ROOT / "contracts" / "combat-decision.schema.json").validate(record)
        validate_combat_decision_semantics(record)
        forged = copy.deepcopy(record)
        forged["requested_control"] = "ACTION_SLOT_3"
        with self.assertRaisesRegex(ValueError, "diverge"):
            validate_combat_decision_semantics(forged)

        observed = state(sequence=8)
        turn = self.policy.decide(
            observed,
            decision_id="combat-decision:fixture:offset",
            bearing=bearing(
                observed,
                direction="RIGHT",
                offset_x_normalized=0.8,
            ),
        ).to_record(created_at="2026-08-24T12:00:00Z")
        self.assertEqual(turn["bearing_offset_x_normalized"], 0.8)
        forged = copy.deepcopy(turn)
        forged["bearing_offset_x_normalized"] = -0.8
        with self.assertRaisesRegex(ValueError, "bearing offset diverge"):
            validate_combat_decision_semantics(forged)


class CombatObservationIntakeTests(unittest.TestCase):
    def test_crc_bound_visible_observation_crosses_into_domain_state(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        detector = detector_module.CombatHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "combat-hud.schema.json"),
        )
        record = detector.detect(
            capture_manifest(),
            synthetic_combat_hud(valid_packet()),
            observation_id="combat-hud:fixture:intake",
        )
        observed = decode_combat_observation(
            record,
            validator=ContractValidator(ROOT / "contracts" / "combat-hud.schema.json"),
        )
        self.assertEqual(observed.player_energy, 67)
        self.assertTrue(observed.sinister_strike.exact_binding)
        self.assertTrue(observed.eviscerate.exact_binding)
        self.assertEqual(observed.target.identity_crc16, record["target"]["identity_crc16"])  # type: ignore[union-attr]

    def test_exact_geometry_canonicalizes_legacy_direction_at_center_boundary(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        validator = ContractValidator(ROOT / "contracts" / "combat-hud.schema.json")
        detector = detector_module.CombatHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            validator,
        )
        record = detector.detect(
            capture_manifest(),
            synthetic_combat_hud(
                valid_packet(
                    target_bearing_code=5,
                    target_frame_x_normalized=0.55,
                    target_frame_y_normalized=0.44,
                )
            ),
            observation_id="combat-hud:fixture:legacy-bearing-boundary",
        )
        observed = decode_combat_observation(record, validator=validator)
        bearing_state = decode_crc_target_bearing(
            record,
            observed,
            validator=validator,
        )
        self.assertEqual(record["target"]["bearing_direction"], "RIGHT")
        self.assertAlmostEqual(bearing_state.offset_x_normalized or 0.0, 0.10, delta=2 / 255)
        self.assertEqual(bearing_state.direction, "CENTER")


if __name__ == "__main__":
    unittest.main()
