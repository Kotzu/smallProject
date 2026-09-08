from __future__ import annotations

from dataclasses import replace
from threading import Thread
import unittest

from perfect_assassin.brain.combat import CombatDecision, RogueLevelOneCombatPolicy
from perfect_assassin.execution.combat_authorization import COMBAT_POLICY
from perfect_assassin.execution.combat_gateway import (
    CombatActionGateway,
    CombatExecutionError,
    ControlledCombatEncounter,
    ControlledCombatEncounterFailure,
)
from perfect_assassin.execution.combat_runtime_arm import CombatRuntimeArm
from perfect_assassin.execution.ports import FakeInputSink, ManualMonotonicClock
from tests.test_combat_policy import action, bearing, state


CLOCK_ID = "clock:windows:monotonic"


def runtime_arm(*, expires_at_ms: float = 35_000.0) -> CombatRuntimeArm:
    return CombatRuntimeArm(
        arm_nonce="arm:combat:fixture:one",
        authorization_sha256="A" * 64,
        session_authorization_sha256="C" * 64,
        session_receipt_sha256="D" * 64,
        realm_revalidation_sha256="E" * 64,
        pid=42,
        hwnd="0x0000000000001234",
        process_creation_filetime_utc="134319092265976452",
        windows_session_id=1,
        window_title="World of Warcraft",
        window_class="GxWindowClassD3d",
        executable_path=r"E:\Games\WoW TBC 2.4.3\Wow.exe",
        executable_sha256="F" * 64,
        actor_id="actor:predator:lab",
        actor_instance_id="instance:predator:lab:one",
        client_build="2.4.3.8606",
        build_signature="wow-tbc-243-8606",
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=10_000.0,
        expires_at_monotonic_ms=expires_at_ms,
        policy=dict(COMBAT_POLICY),
    )


def observation(sequence: int, **changes: object):
    values: dict[str, object] = {
        "observation_id": f"combat-hud:fixture:gateway:{sequence}",
        "observation_sha256": f"{sequence:064X}",
        "sequence": sequence,
        "observed_monotonic_s": 10.1,
        "expires_monotonic_s": 10.7,
    }
    values.update(changes)
    return state(
        **values,
    )


def forced_decision(observed, *, action_id: str, control: str) -> CombatDecision:
    return CombatDecision(
        decision_id=f"decision:forced:{action_id}",
        observation=observed,
        action_id=action_id,
        priority_tier="DAMAGE",
        reason_code="fixture_forced_action",
        explanation="Adversarial fixture that must still pass the execution gate.",
        requested_control=control,
        preconditions=("fixture=true",),
        confidence=1.0,
    )


class SequenceSource:
    def __init__(self, observations, bearings=None):
        self._observations = iter(observations)
        self._bearings = None if bearings is None else iter(bearings)

    def next_observation(self):
        return next(self._observations)

    def bearing_for(self, observed):
        if self._bearings is not None:
            return next(self._bearings)
        return None if observed.target is None else bearing(observed)


class CombatActionGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        self.sink = FakeInputSink()
        self.gateway = CombatActionGateway(
            arm=runtime_arm(),
            sink=self.sink,
            clock=self.clock,
        )
        self.policy = RogueLevelOneCombatPolicy()

    def execute_policy(self, observed):
        decision = self.policy.decide(
            observed,
            decision_id=f"decision:{observed.sequence}",
            bearing=None if observed.target is None else bearing(observed),
        )
        return self.gateway.execute(decision, observed)

    def test_high_level_yellow_npc_may_be_faced_but_not_damaged(self) -> None:
        observed = observation(50, in_combat=False)
        assert observed.target is not None
        observed = replace(
            observed,
            target=replace(observed.target, hostile=False, reaction=4, level=25),
        )
        turn = self.policy.decide_facing_only(
            observed,
            decision_id="decision:yellow:turn",
            bearing=bearing(observed, direction="LEFT", offset_x_normalized=-0.5),
        )
        result = self.gateway.execute(turn, observed)
        self.assertEqual(result["control"], "TURN_LEFT")
        damage = forced_decision(
            observed, action_id="rogue.sinister_strike", control="ACTION_SLOT_2"
        )
        with self.assertRaisesRegex(CombatExecutionError, "level exceeds"):
            self.gateway.execute(damage, observed)

    def test_target_attack_builder_and_finisher_map_to_exact_controls(self) -> None:
        no_target = observation(1, target=None, in_combat=False)
        target_result = self.execute_policy(no_target)
        self.assertEqual(target_result["control"], "TARGET_NEAREST_HOSTILE")
        self.assertEqual(self.sink.applied[-1].hold_duration_ms, 25)
        self.assertEqual(self.sink.budgets[-1].max_execution_envelope_ms, 75)

        attack_result = self.execute_policy(observation(2))
        self.assertEqual(attack_result["control"], "ACTION_SLOT_1")

        builder_result = self.execute_policy(
            observation(3, attack=action(current=True), player_energy=45)
        )
        self.assertEqual(builder_result["control"], "ACTION_SLOT_2")

        finisher_result = self.execute_policy(
            observation(
                4,
                attack=action(current=True),
                combo_points=2,
                player_energy=35,
                target=replace(
                    state().target, health_pct=25.0, health_current=10
                ),
            )
        )
        self.assertEqual(finisher_result["control"], "ACTION_SLOT_3")
        self.assertEqual(self.gateway.action_count, 4)
        self.assertEqual(self.sink.release_count, 4)

    def test_target_free_scan_turn_is_bounded_and_cannot_mask_a_target(self) -> None:
        observed = observation(1, target=None, in_combat=False)
        scan = self.policy.decide_acquisition_scan(
            observed,
            decision_id="decision:target-free-scan",
        )
        result = self.gateway.execute(scan, observed)
        self.assertEqual(result["control"], "TURN_RIGHT")
        self.assertIsNone(result["target_identity_crc16"])
        self.assertEqual(self.sink.applied[-1].mouse_delta_x, 24)
        self.assertEqual(self.sink.applied[-1].hold_duration_ms, 200)
        self.assertEqual(self.gateway.turn_count, 1)

        targeted = observation(2, in_combat=False)
        forged = CombatDecision(
            decision_id="decision:forged-target-free-scan",
            observation=targeted,
            action_id="combat.scan_for_hostile_target",
            priority_tier="TARGET_CONTROL",
            reason_code="fixture_forged_scan",
            explanation="A target-bearing frame cannot authorize target-free scanning.",
            requested_control="TURN_RIGHT",
            preconditions=("target=null",),
            confidence=1.0,
        )
        with self.assertRaisesRegex(CombatExecutionError, "target-free pre-combat"):
            self.gateway.execute(forged, targeted)

    def test_visible_hostile_acquisition_is_bound_to_exact_fresh_screen_point(self) -> None:
        observed = observation(
            8,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.31,
            acquisition_y_normalized=0.42,
        )
        acquisition_bearing = replace(
            bearing(
                observed,
                direction="LEFT",
                offset_x_normalized=-0.38,
            ),
            center_y_normalized=0.42,
        )
        decision = CombatDecision(
            decision_id="decision:visible-hostile-acquire",
            observation=observed,
            action_id="combat.acquire_visible_hostile",
            priority_tier="TARGET_CONTROL",
            reason_code="visible_attackable_candidate_screen_bound",
            explanation="Select one exact visible attackable nameplate.",
            requested_control="TARGET_VISIBLE_HOSTILE",
            preconditions=("target=null", "visible_candidate=true"),
            confidence=1.0,
            bearing=acquisition_bearing,
        )

        result = self.gateway.execute(decision, observed)

        primitive = self.sink.applied[-1]
        self.assertEqual(result["control"], "TARGET_VISIBLE_HOSTILE")
        self.assertEqual(primitive.mouse_click_x_normalized, 0.31)
        self.assertEqual(primitive.mouse_click_y_normalized, 0.42)
        self.assertIsNone(primitive.mouse_delta_x)

    def test_exhausted_visual_scan_never_tabs_to_hidden_hostile(self) -> None:
        scan_budget = COMBAT_POLICY["max_turn_pulses"]
        observations = [
            observation(
                sequence,
                target=None,
                in_combat=False,
                observed_monotonic_s=10.1 + (sequence - 1) * 0.1,
                expires_monotonic_s=10.7 + (sequence - 1) * 0.1,
            )
            for sequence in range(1, scan_budget + 2)
        ]
        source = SequenceSource(
            observations,
            bearings=[
                bearing(
                    observed,
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                )
                for observed in observations
            ],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        with self.assertRaisesRegex(
            ControlledCombatEncounterFailure,
            "no visible attackable candidate within bounded search",
        ):
            encounter.run(encounter_id="encounter:fixture:no-hidden-tab")

        controls = [primitive.controls[0] for primitive in sink.applied]
        self.assertEqual(controls, ["TURN_RIGHT"] * scan_budget)
        self.assertNotIn("TARGET_NEAREST_HOSTILE", controls)

    def test_visible_hostile_click_waits_for_target_confirmation_without_spam(self) -> None:
        first = observation(
            1,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.31,
            acquisition_y_normalized=0.42,
        )
        waiting = observation(
            2,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.31,
            acquisition_y_normalized=0.42,
        )
        acquired = observation(3)
        assert acquired.target is not None
        defeated = observation(
            4,
            target=replace(
                acquired.target,
                dead=True,
                health_pct=0.0,
                health_current=0,
            ),
            attack=action(current=True),
        )

        def acquisition_bearing(observed):
            return replace(
                bearing(observed, direction="LEFT", offset_x_normalized=-0.38),
                center_y_normalized=0.42,
            )

        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(
                [first, waiting, acquired, defeated],
                bearings=[
                    acquisition_bearing(first),
                    acquisition_bearing(waiting),
                    bearing(acquired),
                    bearing(defeated),
                ],
            ),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:visible-click")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TARGET_VISIBLE_HOSTILE", "ACTION_SLOT_1"],
        )

    def test_edge_clipped_visible_hostile_is_centered_before_one_click(self) -> None:
        edge = observation(
            1,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.05,
            acquisition_y_normalized=0.50,
        )
        safe = observation(
            2,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.31,
            acquisition_y_normalized=0.42,
        )
        stable = observation(
            3,
            target=None,
            in_combat=False,
            visible_attackable_candidate_count=1,
            acquisition_x_normalized=0.315,
            acquisition_y_normalized=0.421,
        )
        acquired = observation(4)
        assert acquired.target is not None
        defeated = observation(
            5,
            target=replace(
                acquired.target,
                dead=True,
                health_pct=0.0,
                health_current=0,
            ),
            attack=action(current=True),
        )
        edge_bearing = replace(
            bearing(edge, direction="LEFT", offset_x_normalized=-0.90),
            center_y_normalized=0.50,
        )
        safe_bearing = replace(
            bearing(safe, direction="LEFT", offset_x_normalized=-0.38),
            center_y_normalized=0.42,
        )
        stable_bearing = replace(
            bearing(stable, direction="LEFT", offset_x_normalized=-0.37),
            center_y_normalized=0.421,
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(
                [edge, safe, stable, acquired, defeated],
                bearings=[
                    edge_bearing,
                    safe_bearing,
                    stable_bearing,
                    bearing(acquired),
                    bearing(defeated),
                ],
            ),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:edge-candidate")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TURN_LEFT", "TARGET_VISIBLE_HOSTILE", "ACTION_SLOT_1"],
        )
        self.assertLess(sink.applied[0].mouse_delta_x, 0)
        self.assertEqual(sink.applied[1].mouse_click_x_normalized, 0.315)

    def test_moving_visible_candidate_must_settle_before_click(self) -> None:
        samples = [
            observation(
                1,
                target=None,
                in_combat=False,
                visible_attackable_candidate_count=1,
                acquisition_x_normalized=0.31,
                acquisition_y_normalized=0.42,
            ),
            observation(
                2,
                target=None,
                in_combat=False,
                visible_attackable_candidate_count=1,
                acquisition_x_normalized=0.40,
                acquisition_y_normalized=0.48,
            ),
            observation(
                3,
                target=None,
                in_combat=False,
                visible_attackable_candidate_count=1,
                acquisition_x_normalized=0.402,
                acquisition_y_normalized=0.479,
            ),
        ]
        acquired = observation(4)
        assert acquired.target is not None
        defeated = observation(
            5,
            target=replace(
                acquired.target,
                dead=True,
                health_pct=0.0,
                health_current=0,
            ),
            attack=action(current=True),
        )

        def sample_bearing(observed):
            return replace(
                bearing(observed, direction="LEFT", offset_x_normalized=-0.20),
                center_y_normalized=observed.acquisition_y_normalized,
            )

        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(
                [*samples, acquired, defeated],
                bearings=[
                    *(sample_bearing(observed) for observed in samples),
                    bearing(acquired),
                    bearing(defeated),
                ],
            ),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:moving-candidate")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TARGET_VISIBLE_HOSTILE", "ACTION_SLOT_1"],
        )
        self.assertEqual(sink.applied[0].mouse_click_x_normalized, 0.402)
        self.assertEqual(sink.applied[0].mouse_click_y_normalized, 0.479)

    def test_generic_attack_uses_only_the_exact_builder_melee_range_witness(self) -> None:
        observed = observation(
            7,
            attack=action(in_range=None),
            sinister_strike=action(in_range=True),
        )
        decision = self.policy.decide(
            observed,
            decision_id="decision:attack-range-witness",
            bearing=bearing(observed),
        )
        result = self.gateway.execute(decision, observed)
        self.assertEqual(result["control"], "ACTION_SLOT_1")

        unknown = observation(
            2,
            attack=action(in_range=None),
            sinister_strike=action(in_range=None),
        )
        forged = forced_decision(
            unknown,
            action_id="rogue.auto_attack",
            control="ACTION_SLOT_1",
        )
        with self.assertRaisesRegex(CombatExecutionError, "not exact and actionable"):
            self.gateway.execute(forged, unknown)
        self.assertEqual(self.gateway.action_count, 1)
        self.assertEqual(self.sink.release_count, 1)

    def test_approach_requires_explicit_out_of_range_and_is_bounded(self) -> None:
        out_of_range = observation(
            1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        result = self.execute_policy(out_of_range)
        self.assertEqual(result["control"], "MOVE_FORWARD")
        self.assertEqual(self.sink.applied[-1].hold_duration_ms, 250)
        self.assertEqual(self.sink.budgets[-1].max_execution_envelope_ms, 300)

        self.gateway._approach_count = COMBAT_POLICY["max_approach_pulses"]
        with self.assertRaisesRegex(CombatExecutionError, "approach budget"):
            self.execute_policy(replace(out_of_range, sequence=2))
        self.assertEqual(len(self.sink.applied), 1)

    def test_magnetic_orbit_requires_centered_in_combat_melee_witness(self) -> None:
        observed = observation(
            7,
            attack=action(current=True),
            player_energy=20,
            in_combat=True,
        )
        result = self.execute_policy(observed)
        self.assertEqual(result["control"], "STRAFE_RIGHT")
        self.assertEqual(self.sink.applied[-1].hold_duration_ms, 90)
        self.assertEqual(self.sink.budgets[-1].max_execution_envelope_ms, 140)
        self.assertIsNone(self.sink.applied[-1].mouse_delta_x)

        out_of_combat = replace(observed, sequence=2, in_combat=False)
        forged = CombatDecision(
            decision_id="decision:forged-orbit",
            observation=out_of_combat,
            action_id="combat.orbit_target_right",
            priority_tier="TARGET_CONTROL",
            reason_code="fixture_forged_orbit",
            explanation="A forged orbit without combat must be rejected.",
            requested_control="STRAFE_RIGHT",
            preconditions=("in_combat=true",),
            confidence=1.0,
            bearing=bearing(out_of_combat),
        )
        with self.assertRaisesRegex(CombatExecutionError, "active auto-attack"):
            self.gateway.execute(forged, out_of_combat)

    def test_turn_requires_exact_fresh_bearing_and_is_bounded(self) -> None:
        out_of_range = observation(
            1,
            attack=action(in_range=False),
            sinister_strike=action(in_range=False),
            eviscerate=action(in_range=False),
        )
        right_bearing = bearing(
            out_of_range,
            direction="RIGHT",
            offset_x_normalized=0.35,
        )
        decision = self.policy.decide(
            out_of_range,
            decision_id="decision:turn-right",
            bearing=right_bearing,
        )
        result = self.gateway.execute(decision, out_of_range)
        self.assertEqual(result["control"], "TURN_RIGHT")
        self.assertGreater(
            self.sink.applied[-1].mouse_delta_x,
            0,
            "A right-side target must produce native positive RMB motion",
        )
        self.assertEqual(self.sink.applied[-1].hold_duration_ms, 25)
        self.assertEqual(self.sink.budgets[-1].max_execution_envelope_ms, 175)
        self.assertLessEqual(abs(self.sink.applied[-1].mouse_delta_x), 8)

        medium_observation = replace(out_of_range, sequence=2)
        medium = self.policy.decide(
            medium_observation,
            decision_id="decision:turn-medium",
            bearing=bearing(
                medium_observation,
                direction="RIGHT",
                offset_x_normalized=0.5,
            ),
        )
        medium_result = self.gateway.execute(medium, medium_observation)
        self.assertEqual(medium_result["hold_duration_ms"], 25)
        self.assertEqual(medium_result["max_execution_envelope_ms"], 175)
        self.assertLessEqual(abs(medium_result["mouse_delta_x"]), 8)

        far_observation = replace(out_of_range, sequence=3)
        far = self.policy.decide(
            far_observation,
            decision_id="decision:turn-far",
            bearing=bearing(
                far_observation,
                direction="RIGHT",
                offset_x_normalized=0.8,
            ),
        )
        far_result = self.gateway.execute(far, far_observation)
        self.assertEqual(far_result["hold_duration_ms"], 25)
        self.assertEqual(far_result["max_execution_envelope_ms"], 175)
        self.assertLessEqual(abs(far_result["mouse_delta_x"]), 8)

        lost_observation = replace(out_of_range, sequence=4)
        search = self.policy.decide(
            lost_observation,
            decision_id="decision:turn-search",
            bearing=bearing(
                lost_observation,
                tracking_state="LOST",
                direction=None,
                offset_x_normalized=None,
            ),
        )
        search_result = self.gateway.execute(search, lost_observation)
        self.assertEqual(search_result["hold_duration_ms"], 200)
        self.assertEqual(search_result["max_execution_envelope_ms"], 350)

        stale = replace(
            right_bearing,
            observed_monotonic_s=9.0,
            expires_monotonic_s=9.4,
        )
        stale_decision = self.policy.decide(
            out_of_range,
            decision_id="decision:turn-stale",
            bearing=stale,
        )
        with self.assertRaisesRegex(CombatExecutionError, "bearing is stale"):
            self.gateway.execute(stale_decision, out_of_range)

        self.gateway._facing_turn_count = COMBAT_POLICY["max_facing_turn_pulses"]
        with self.assertRaisesRegex(CombatExecutionError, "visible-facing budget"):
            self.gateway.execute(decision, out_of_range)

    def test_player_target_low_health_stale_and_binding_mismatch_never_reach_sink(self) -> None:
        base_target = observation(1).target
        assert base_target is not None
        player_target = observation(1, target=replace(base_target, is_player=True))
        with self.assertRaisesRegex(CombatExecutionError, "player targets"):
            self.gateway.execute(
                forced_decision(
                    player_target,
                    action_id="rogue.auto_attack",
                    control="ACTION_SLOT_1",
                ),
                player_target,
            )

        critical = observation(2, player_health_pct=25.0)
        critical_decision = self.policy.decide(
            critical, decision_id="decision:critical"
        )
        with self.assertRaisesRegex(CombatExecutionError, "not authorized"):
            self.gateway.execute(critical_decision, critical)

        stale = observation(
            3,
            observed_monotonic_s=9.6,
            expires_monotonic_s=10.1,
        )
        with self.assertRaisesRegex(CombatExecutionError, "stale"):
            self.gateway.execute(
                forced_decision(
                    stale,
                    action_id="rogue.auto_attack",
                    control="ACTION_SLOT_1",
                ),
                stale,
            )

        wrong_actor = observation(4, actor_id="actor:someone-else:lab")
        with self.assertRaisesRegex(CombatExecutionError, "binding diverges"):
            self.gateway.execute(
                forced_decision(
                    wrong_actor,
                    action_id="rogue.auto_attack",
                    control="ACTION_SLOT_1",
                ),
                wrong_actor,
            )
        self.assertEqual(self.sink.apply_attempts, [])

    def test_manual_takeover_releases_and_blocks_every_later_action(self) -> None:
        self.gateway.cancel_for_manual_takeover()
        observed = observation(1)
        with self.assertRaisesRegex(CombatExecutionError, "cancelled"):
            self.execute_policy(observed)
        self.assertEqual(self.sink.apply_attempts, [])
        self.assertEqual(self.sink.release_count, 1)

    def test_arm_expiry_and_action_fit_are_checked_before_effect(self) -> None:
        sink = FakeInputSink()
        gateway = CombatActionGateway(
            arm=runtime_arm(expires_at_ms=10_250.0),
            sink=sink,
            clock=self.clock,
        )
        with self.assertRaisesRegex(CombatExecutionError, "cannot fit"):
            gateway.execute(
                forced_decision(
                    observation(1),
                    action_id="rogue.auto_attack",
                    control="ACTION_SLOT_1",
                ),
                observation(1),
            )
        self.assertEqual(sink.apply_attempts, [])

    def test_manual_takeover_interrupts_an_inflight_action(self) -> None:
        sink = FakeInputSink(wait_for_cancellation=True)
        gateway = CombatActionGateway(
            arm=runtime_arm(), sink=sink, clock=self.clock
        )
        observed = observation(1)
        decision = self.policy.decide(
            observed,
            decision_id="decision:inflight",
            bearing=bearing(observed),
        )
        errors: list[BaseException] = []

        def execute() -> None:
            try:
                gateway.execute(decision, observed)
            except BaseException as error:
                errors.append(error)

        worker = Thread(target=execute)
        worker.start()
        self.assertTrue(sink.apply_started.wait(timeout=1.0))
        gateway.cancel_for_manual_takeover()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], CombatExecutionError)
        self.assertRegex(str(errors[0]), "manual takeover")
        self.assertEqual(sink.applied, [])
        self.assertGreaterEqual(sink.release_count, 2)

    def test_concurrent_action_is_refused_instead_of_overlapping_keys(self) -> None:
        sink = FakeInputSink(wait_for_cancellation=True)
        gateway = CombatActionGateway(
            arm=runtime_arm(), sink=sink, clock=self.clock
        )
        observed = observation(1)
        decision = self.policy.decide(
            observed,
            decision_id="decision:first",
            bearing=bearing(observed),
        )
        first_errors: list[BaseException] = []
        worker = Thread(
            target=lambda: self._capture_error(
                first_errors, lambda: gateway.execute(decision, observed)
            )
        )
        worker.start()
        self.assertTrue(sink.apply_started.wait(timeout=1.0))

        with self.assertRaisesRegex(CombatExecutionError, "one in-flight"):
            gateway.execute(
                replace(decision, decision_id="decision:second"), observed
            )
        gateway.cancel_for_manual_takeover()
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(first_errors), 1)
        self.assertEqual(len(sink.apply_attempts), 1)

    def test_release_failure_and_temporal_overrun_fault_the_gate(self) -> None:
        release_sink = FakeInputSink(fail_on_release=True)
        release_gate = CombatActionGateway(
            arm=runtime_arm(), sink=release_sink, clock=self.clock
        )
        observed = observation(1)
        decision = self.policy.decide(
            observed,
            decision_id="decision:release",
            bearing=bearing(observed),
        )
        with self.assertRaisesRegex(CombatExecutionError, "release failed"):
            release_gate.execute(decision, observed)
        self.assertEqual(len(release_sink.applied), 1)

        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)

        class OverrunSink(FakeInputSink):
            def apply_bounded(self, primitive, cancellation, budget) -> None:
                super().apply_bounded(primitive, cancellation, budget)
                clock.advance(budget.max_execution_envelope_ms + 1)

        overrun_sink = OverrunSink()
        overrun_gate = CombatActionGateway(
            arm=runtime_arm(), sink=overrun_sink, clock=clock
        )
        with self.assertRaisesRegex(CombatExecutionError, "exceeded"):
            overrun_gate.execute(decision, observed)
        self.assertEqual(len(overrun_sink.applied), 1)
        with self.assertRaisesRegex(CombatExecutionError, "cancelled"):
            overrun_gate.execute(decision, observed)

    @staticmethod
    def _capture_error(
        errors: list[BaseException], callback
    ) -> None:
        try:
            callback()
        except BaseException as error:
            errors.append(error)


class ControlledCombatEncounterTests(unittest.TestCase):
    def test_one_shot_target_transition_requires_exact_dead_recovery_and_loot(self) -> None:
        live_target = replace(
            state().target,
            health_current=10,
            health_max=40,
            health_pct=25.0,
        )
        other_target = replace(
            live_target,
            identity_crc16=4321,
            health_current=40,
            health_pct=100.0,
        )
        dead_target = replace(
            live_target,
            dead=True,
            health_current=0,
            health_pct=0.0,
            interact_x_normalized=0.55,
            interact_y_normalized=0.48,
        )
        observations = [
            observation(
                1,
                target=live_target,
                in_combat=True,
                attack=action(current=True),
                player_energy=100,
                combo_points=0,
            ),
            observation(
                2,
                target=other_target,
                in_combat=False,
                player_energy=55,
                combo_points=1,
            ),
            observation(
                3,
                target=dead_target,
                in_combat=False,
                player_energy=55,
                loot_event_sequence=0,
            ),
            observation(
                4,
                target=dead_target,
                in_combat=False,
                player_energy=55,
                loot_event_sequence=1,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
            recover_after_kill=True,
        )

        result = encounter.run(encounter_id="encounter:fixture:one-shot-loot")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            result["completion_reason"],
            "one_shot_target_transition_validated_by_recovery",
        )
        self.assertEqual(result["recovery"]["status"], "LOOT_CONFIRMED")
        self.assertEqual(result["recovery"]["target_identity_crc16"], 1234)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_2", "TARGET_LAST_HOSTILE", "INTERACT_TARGET"],
        )

    def test_confirmed_kill_selects_exact_corpse_and_requires_loot_event(self) -> None:
        live_target = replace(
            state().target,
            health_current=40,
            health_max=40,
            health_pct=100.0,
        )
        damaged_target = replace(
            live_target,
            health_current=20,
            health_pct=50.0,
        )
        dead_target = replace(
            live_target,
            dead=True,
            health_current=0,
            health_pct=0.0,
            interact_x_normalized=0.55,
            interact_y_normalized=0.48,
        )
        observations = [
            observation(1, target=live_target, in_combat=True),
            observation(
                2,
                target=damaged_target,
                in_combat=True,
                attack=action(current=True),
                player_energy=0,
            ),
            observation(3, target=None, in_combat=False, player_energy=0),
            observation(
                4,
                target=dead_target,
                in_combat=False,
                player_energy=0,
                loot_event_sequence=0,
            ),
            observation(
                5,
                target=dead_target,
                in_combat=False,
                player_energy=0,
                loot_event_sequence=1,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
            recover_after_kill=True,
        )

        result = encounter.run(encounter_id="encounter:fixture:loot")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["recovery"]["status"], "LOOT_CONFIRMED")
        self.assertEqual(result["recovery"]["target_identity_crc16"], 1234)
        self.assertEqual(result["recovery"]["loot_event_sequence_before"], 0)
        self.assertEqual(result["recovery"]["loot_event_sequence_after"], 1)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_1", "TARGET_LAST_HOSTILE", "INTERACT_TARGET"],
        )

    def test_duplicate_addon_sequence_waits_without_replaying_input(self) -> None:
        first = observation(1)
        duplicate = replace(first, observation_id="combat-hud:fixture:duplicate")
        dead_target = replace(
            first.target, dead=True, health_pct=0.0, health_current=0
        )
        observations = [
            first,
            duplicate,
            observation(2, target=dead_target, attack=action(current=True)),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:duplicate")
        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(len(sink.applied), 1)
        self.assertEqual(sink.applied[0].controls, ("ACTION_SLOT_1",))

    def test_one_exact_target_progresses_through_bounded_rotation_to_defeat(self) -> None:
        observations = [
            observation(1, target=None, in_combat=False),
            observation(
                2,
                attack=action(in_range=False),
                sinister_strike=action(in_range=False),
                eviscerate=action(in_range=False),
            ),
            observation(3),
            observation(4, attack=action(current=True), player_energy=60),
            observation(
                5,
                attack=action(current=True),
                combo_points=2,
                player_energy=50,
                target=replace(
                    state().target, health_pct=25.0, health_current=10
                ),
            ),
            observation(
                6,
                attack=action(current=True),
                combo_points=0,
                target=replace(
                    observation(6).target,
                    dead=True,
                    health_pct=0.0,
                    health_current=0,
                ),
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(),
                sink=sink,
                clock=clock,
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:one")
        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 1234)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            [
                "TURN_RIGHT",
                "MOVE_FORWARD",
                "ACTION_SLOT_1",
                "ACTION_SLOT_2",
                "ACTION_SLOT_3",
            ],
        )
        self.assertEqual(result["actions_executed"], 5)
        self.assertTrue(result["decisions"][0]["created_at"].endswith("Z"))

    def test_target_change_mid_encounter_stops_before_second_target_action(self) -> None:
        first = observation(1)
        second_target = replace(first.target, identity_crc16=4321)
        observations = [
            first,
            observation(2, target=second_target, attack=action(current=True)),
            observation(3, target=second_target, attack=action(current=True)),
            observation(4, target=second_target, attack=action(current=True)),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )
        with self.assertRaisesRegex(
            ControlledCombatEncounterFailure, "continuity changed"
        ) as raised:
            encounter.run(encounter_id="encounter:fixture:target-swap")
        failure = raised.exception.to_record()
        self.assertEqual(failure["status"], "STOPPED_FAIL_CLOSED")
        self.assertEqual(failure["error_type"], "CombatExecutionError")
        self.assertEqual(failure["actions_executed"], 1)
        self.assertEqual(len(failure["decisions"]), 1)
        self.assertEqual(len(failure["executions"]), 1)
        self.assertFalse(failure["execution_authority"])
        self.assertEqual(len(sink.applied), 1)
        self.assertGreaterEqual(sink.release_count, 2)

    def test_one_frame_target_identity_mismatch_is_debounced_without_input(self) -> None:
        first = observation(1)
        torn_target = replace(first.target, identity_crc16=4321)
        defeated = replace(first.target, dead=True, health_current=0, health_pct=0.0)
        observations = [
            first,
            observation(2, target=torn_target, attack=action(current=True)),
            observation(3, target=first.target, attack=action(current=True)),
            observation(4, target=defeated, attack=action(current=True)),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:torn-target-crc")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], first.target.identity_crc16)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_1", "ACTION_SLOT_2"],
        )

    def test_next_encounter_cycles_past_selected_looted_corpse(self) -> None:
        live = observation(2).target
        assert live is not None
        live = replace(live, identity_crc16=4321)
        corpse = replace(
            live,
            identity_crc16=1234,
            dead=True,
            health_current=0,
            health_pct=0.0,
        )
        defeated = replace(live, dead=True, health_current=0, health_pct=0.0)
        observations = [
            observation(1, target=corpse, in_combat=False),
            observation(2, target=live, in_combat=False),
            observation(3, target=live, attack=action(current=True), in_combat=True),
            observation(4, target=defeated, attack=action(current=True), in_combat=False),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
            advance_past_initial_dead_target=True,
        )

        result = encounter.run(encounter_id="encounter:fixture:post-loot-next-hunt")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 4321)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TARGET_NEAREST_HOSTILE", "ACTION_SLOT_1", "ACTION_SLOT_2"],
        )

    def test_sinister_waits_for_observed_effect_before_replaying(self) -> None:
        first_target = replace(
            state().target,
            health_current=40,
            health_max=40,
            health_pct=100.0,
        )
        progressed_target = replace(
            first_target,
            health_current=32,
            health_pct=80.0,
        )
        observations = [
            observation(
                1,
                target=first_target,
                attack=action(current=True),
                player_energy=100,
            ),
            observation(
                2,
                target=first_target,
                attack=action(current=True),
                player_energy=100,
            ),
            observation(
                3,
                target=progressed_target,
                attack=action(current=True),
                player_energy=55,
                combo_points=1,
            ),
            observation(
                4,
                target=replace(
                    progressed_target,
                    dead=True,
                    health_current=0,
                    health_pct=0.0,
                ),
                attack=action(current=True),
                player_energy=10,
                combo_points=2,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        waits: list[int] = []
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=lambda milliseconds: (
                waits.append(milliseconds),
                clock.advance(milliseconds),
            ),
        )

        result = encounter.run(encounter_id="encounter:fixture:damage-confirmation")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_2", "ACTION_SLOT_2"],
        )
        self.assertGreaterEqual(waits.count(100), 3)

    def test_conservative_finisher_target_transition_confirms_defeat(self) -> None:
        target = replace(
            state().target,
            health_current=8,
            health_max=40,
            health_pct=20.0,
        )
        next_target = replace(
            target,
            identity_crc16=4321,
            health_current=40,
            health_pct=100.0,
        )
        observations = [
            observation(
                1,
                target=target,
                attack=action(current=True),
                player_energy=35,
                player_attack_power=600,
                combo_points=1,
                in_combat=True,
            ),
            observation(
                2,
                target=next_target,
                attack=action(current=False),
                player_energy=0,
                player_attack_power=600,
                combo_points=0,
                in_combat=False,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:lethal-transition")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 1234)
        self.assertEqual(
            result["completion_reason"],
            "conservative_lethal_finisher_target_transition",
        )
        self.assertEqual(result["final_target_health_before_finisher"], 8)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_3"],
        )

    def test_likely_only_finisher_target_transition_still_fails_closed(self) -> None:
        target = replace(
            state().target,
            health_current=18,
            health_max=40,
            health_pct=45.0,
        )
        next_target = replace(
            target,
            identity_crc16=4321,
            health_current=40,
            health_pct=100.0,
        )
        observations = [
            observation(
                1,
                target=target,
                attack=action(current=True),
                player_energy=35,
                player_attack_power=600,
                combo_points=1,
                in_combat=True,
            ),
            observation(
                2,
                target=next_target,
                attack=action(current=False),
                player_energy=0,
                player_attack_power=600,
                combo_points=0,
                in_combat=False,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        with self.assertRaisesRegex(
            ControlledCombatEncounterFailure,
            "before damage confirmation",
        ):
            encounter.run(encounter_id="encounter:fixture:likely-transition")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_3"],
        )

    def test_lethal_finisher_waits_for_target_clear_combat_flag_settle(self) -> None:
        target = replace(
            state().target,
            health_current=8,
            health_max=40,
            health_pct=20.0,
        )
        observations = [
            observation(
                1,
                target=target,
                attack=action(current=True),
                player_energy=35,
                player_attack_power=600,
                combo_points=1,
                in_combat=True,
            ),
            observation(2, target=None, in_combat=True),
            observation(3, target=None, in_combat=True),
            observation(4, target=None, in_combat=False),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:lethal-settle")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            result["completion_reason"],
            "conservative_lethal_finisher_target_transition",
        )
        self.assertEqual(result["target_identity_crc16"], target.identity_crc16)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_3"],
        )

    def test_damaged_target_cleared_out_of_combat_confirms_defeat(self) -> None:
        first_target = replace(
            state().target,
            health_current=40,
            health_max=40,
            health_pct=100.0,
        )
        damaged_target = replace(
            first_target,
            health_current=24,
            health_pct=60.0,
        )
        observations = [
            observation(1, target=first_target, attack=action(current=False)),
            observation(
                2,
                target=damaged_target,
                attack=action(current=True),
                player_energy=10,
                in_combat=True,
            ),
            observation(
                3,
                target=None,
                attack=action(current=False),
                player_energy=20,
                in_combat=False,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:cleared-target")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 1234)
        self.assertEqual(
            result["completion_reason"],
            "damaged_locked_target_cleared_out_of_combat",
        )
        self.assertEqual(result["final_target_health_observed"], 24)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_1"],
        )

    def test_damage_progress_gets_input_free_kill_settle_after_turn_budget(self) -> None:
        first_target = observation(1).target
        assert first_target is not None
        damaged_target = replace(
            first_target,
            health_current=24,
            health_pct=60.0,
        )
        turn_budget = COMBAT_POLICY["max_facing_turn_pulses"]
        turning = [
            observation(
                sequence,
                target=damaged_target,
                attack=action(current=True),
                player_energy=10,
                in_combat=True,
                observed_monotonic_s=10.1 + (sequence - 1) * 0.1,
                expires_monotonic_s=10.7 + (sequence - 1) * 0.1,
            )
            for sequence in range(2, turn_budget + 3)
        ]
        cleared = observation(
            turn_budget + 3,
            target=None,
            attack=action(current=False),
            player_energy=20,
            in_combat=False,
            observed_monotonic_s=10.1 + (turn_budget + 2) * 0.1,
            expires_monotonic_s=10.7 + (turn_budget + 2) * 0.1,
        )
        first = observation(1, target=first_target, attack=action(current=False))
        source = SequenceSource(
            [first, *turning, cleared],
            bearings=[
                bearing(first),
                *[
                    bearing(
                        observed,
                        direction="LEFT",
                        offset_x_normalized=-0.35,
                    )
                    for observed in turning
                ],
                None,
            ],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:kill-settle")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            result["completion_reason"],
            "damaged_locked_target_cleared_out_of_combat",
        )
        controls = [primitive.controls[0] for primitive in sink.applied]
        self.assertEqual(controls[0], "ACTION_SLOT_1")
        self.assertEqual(controls[1:], ["TURN_LEFT"] * turn_budget)
        self.assertNotIn("TARGET_NEAREST_HOSTILE", controls)

    def test_undamaged_locked_target_disappearance_still_fails_closed(self) -> None:
        observations = [
            observation(1, attack=action(current=False)),
            observation(2, target=None, in_combat=False),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        with self.assertRaisesRegex(
            ControlledCombatEncounterFailure,
            "disappeared without defeat evidence",
        ):
            encounter.run(encounter_id="encounter:fixture:unsafe-clear")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["ACTION_SLOT_1"],
        )

    def test_precombat_search_can_cycle_one_unreachable_target_then_locks_damage_target(self) -> None:
        out_of_range = {
            "attack": action(in_range=False),
            "sinister_strike": action(in_range=False),
            "eviscerate": action(in_range=False),
            "in_combat": False,
        }
        first_target_observations = [
            observation(sequence, **out_of_range)
            for sequence in range(1, 12)
        ]
        first_target = first_target_observations[-1].target
        assert first_target is not None
        second_target = replace(first_target, identity_crc16=4321, level=1)
        observations = [
            *first_target_observations,
            observation(12, target=second_target),
            observation(
                13,
                target=second_target,
                attack=action(current=True),
                player_energy=60,
            ),
            observation(
                14,
                target=replace(
                    second_target, dead=True, health_pct=0.0, health_current=0
                ),
                attack=action(current=True),
                player_energy=15,
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=lambda _milliseconds: None,
        )

        result = encounter.run(encounter_id="encounter:fixture:target-search")
        controls = [primitive.controls[0] for primitive in sink.applied]
        self.assertEqual(controls[:10], ["MOVE_FORWARD"] * 10)
        self.assertEqual(
            controls[10:],
            ["TARGET_NEAREST_HOSTILE", "ACTION_SLOT_1", "ACTION_SLOT_2"],
        )
        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 4321)
        self.assertEqual(
            result["decisions"][10]["action_id"],
            "combat.cycle_hostile_target",
        )

    def test_precombat_search_cycles_unsafe_level_without_damage_or_approach(self) -> None:
        first_target = observation(1).target
        assert first_target is not None
        risky = replace(first_target, identity_crc16=1234, level=3)
        safe_dead = replace(
            first_target,
            identity_crc16=4321,
            level=1,
            dead=True,
            health_pct=0.0,
            health_current=0,
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource([
                observation(1, target=risky, in_combat=False),
                observation(2, target=safe_dead, in_combat=False),
            ]),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:unsafe-level-cycle")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TARGET_NEAREST_HOSTILE"],
        )
        self.assertEqual(
            result["decisions"][0]["reason_code"],
            "current_target_level_out_of_bounds",
        )

    def test_precombat_visual_search_cycles_before_any_damage(self) -> None:
        lost_observations = []
        turn_budget = COMBAT_POLICY["max_turn_pulses"]
        for sequence in range(1, turn_budget + 2):
            observed_at = 10.1 + (sequence - 1) * 0.1
            observed = observation(
                sequence,
                in_combat=False,
                observed_monotonic_s=observed_at,
                expires_monotonic_s=observed_at + 0.6,
            )
            lost_observations.append(
                (
                    observed,
                    bearing(
                        observed,
                        tracking_state="LOST",
                        direction=None,
                        offset_x_normalized=None,
                    ),
                )
            )
        first_target = lost_observations[-1][0].target
        assert first_target is not None
        second_target = replace(first_target, identity_crc16=4321)
        final = observation(
            turn_budget + 2,
            target=replace(
                second_target, dead=True, health_pct=0.0, health_current=0
            ),
            in_combat=False,
            observed_monotonic_s=10.1 + (turn_budget + 1) * 0.1,
            expires_monotonic_s=10.7 + (turn_budget + 1) * 0.1,
        )
        source = SequenceSource(
            [item[0] for item in lost_observations] + [final],
            bearings=[item[1] for item in lost_observations]
            + [bearing(final)],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:visual-cycle")
        controls = [primitive.controls[0] for primitive in sink.applied]
        self.assertEqual(controls[:turn_budget], ["TURN_RIGHT"] * turn_budget)
        self.assertEqual(controls[turn_budget], "TARGET_NEAREST_HOSTILE")
        self.assertNotIn("ACTION_SLOT_1", controls)
        self.assertEqual(
            result["decisions"][turn_budget]["reason_code"],
            "current_target_not_visually_reacquired",
        )

    def test_exact_target_is_preserved_when_visual_turn_budget_is_exhausted(self) -> None:
        turn_budget = COMBAT_POLICY["max_facing_turn_pulses"]
        observations = [
            observation(
                sequence,
                in_combat=False,
                observed_monotonic_s=10.1 + (sequence - 1) * 0.1,
                expires_monotonic_s=10.7 + (sequence - 1) * 0.1,
            )
            for sequence in range(1, turn_budget + 2)
        ]
        source = SequenceSource(
            observations,
            bearings=[
                bearing(
                    observed,
                    tracking_state="VISIBLE",
                    direction="RIGHT",
                    offset_x_normalized=0.35,
                )
                for observed in observations
            ],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
            preserve_selected_target=True,
        )

        with self.assertRaises(ControlledCombatEncounterFailure) as raised:
            encounter.run(encounter_id="encounter:fixture:preserve-exact-target")

        failure = raised.exception.to_record()
        controls = [primitive.controls[0] for primitive in sink.applied]
        self.assertEqual(controls, ["TURN_RIGHT"] * turn_budget)
        self.assertNotIn("TARGET_NEAREST_HOSTILE", controls)
        self.assertEqual(
            failure["detail"],
            "exact selected target was not visually reacquired within the turn budget",
        )

    def test_transient_bearing_loss_waits_without_coarse_search_turn(self) -> None:
        observations = [
            observation(1, in_combat=False),
            observation(2, in_combat=False),
            observation(3, in_combat=False),
            observation(4, in_combat=False),
            observation(
                5,
                target=replace(
                    state().target, dead=True, health_pct=0.0, health_current=0
                ),
                in_combat=False,
            ),
        ]
        source = SequenceSource(
            observations,
            bearings=[
                bearing(observations[0], direction="RIGHT", offset_x_normalized=0.4),
                bearing(
                    observations[1],
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                ),
                bearing(
                    observations[2],
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                ),
                bearing(observations[3], direction="RIGHT", offset_x_normalized=0.35),
                bearing(observations[4]),
            ],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        waits: list[int] = []
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=lambda milliseconds: (waits.append(milliseconds), clock.advance(milliseconds)),
        )

        result = encounter.run(encounter_id="encounter:fixture:transient-occlusion")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TURN_RIGHT", "TURN_RIGHT"],
        )
        self.assertEqual(waits.count(50), 2)
        self.assertNotIn(
            "combat.search_selected_target",
            [decision["action_id"] for decision in result["decisions"]],
        )

    def test_sustained_bearing_loss_starts_search_only_after_debounce_budget(self) -> None:
        lost_count = 11
        observations = [
            observation(1, in_combat=False),
            *[
                observation(
                    sequence,
                    in_combat=False,
                    observed_monotonic_s=10.1 + index * 0.05,
                    expires_monotonic_s=10.7 + index * 0.05,
                )
                for index, sequence in enumerate(range(2, 2 + lost_count))
            ],
            observation(
                2 + lost_count,
                observed_monotonic_s=10.6,
                expires_monotonic_s=11.2,
                target=replace(
                    state().target, dead=True, health_pct=0.0, health_current=0
                ),
                in_combat=False,
            ),
        ]
        bearings = [
            bearing(observations[0], direction="RIGHT", offset_x_normalized=0.4),
            *[
                bearing(
                    item,
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                )
                for item in observations[1 : 1 + lost_count]
            ],
            bearing(observations[-1]),
        ]
        source = SequenceSource(observations, bearings=bearings)
        clock = ManualMonotonicClock(CLOCK_ID, 10_100.0)
        sink = FakeInputSink()
        waits: list[int] = []
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=lambda milliseconds: (waits.append(milliseconds), clock.advance(milliseconds)),
        )

        result = encounter.run(encounter_id="encounter:fixture:sustained-occlusion")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TURN_RIGHT", "TURN_RIGHT"],
        )
        self.assertEqual(waits.count(50), 10)
        self.assertEqual(
            [decision["action_id"] for decision in result["decisions"]],
            [
                "combat.turn_toward_target_right",
                "combat.search_selected_target",
                "combat.target_defeated",
            ],
        )

    def test_target_cycle_waits_for_bounded_observation_transition(self) -> None:
        out_of_range = {
            "attack": action(in_range=False),
            "sinister_strike": action(in_range=False),
            "eviscerate": action(in_range=False),
            "in_combat": False,
        }
        first = [observation(sequence, **out_of_range) for sequence in range(1, 12)]
        first_target = first[-1].target
        assert first_target is not None
        second_target = replace(first_target, identity_crc16=4321)
        observations = [
            *first,
            observation(12, **out_of_range),
            observation(13, **out_of_range),
            observation(14, target=second_target),
            observation(
                15,
                target=replace(
                    second_target, dead=True, health_pct=0.0, health_current=0
                ),
            ),
        ]
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        waits: list[int] = []
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=SequenceSource(observations),
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=waits.append,
        )

        result = encounter.run(encounter_id="encounter:fixture:delayed-target-cycle")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 4321)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["MOVE_FORWARD"] * 10
            + ["TARGET_NEAREST_HOSTILE", "ACTION_SLOT_1"],
        )
        self.assertGreaterEqual(waits.count(50), 2)

    def test_pre_damage_hostile_aggro_can_rebind_but_damage_locks_target(self) -> None:
        first = observation(1, in_combat=False)
        assert first.target is not None
        reactive_target = replace(first.target, identity_crc16=4321)
        engaged = observation(
            2,
            target=reactive_target,
            in_combat=True,
            attack=action(current=True, in_range=True),
            sinister_strike=action(in_range=True),
            eviscerate=action(in_range=True),
            player_energy=60,
        )
        defeated = observation(
            3,
            target=replace(
                reactive_target, dead=True, health_pct=0.0, health_current=0
            ),
            in_combat=True,
            attack=action(current=True, in_range=True),
        )
        source = SequenceSource(
            [first, engaged, defeated],
            bearings=[
                bearing(
                    first,
                    tracking_state="LOST",
                    direction=None,
                    offset_x_normalized=None,
                ),
                bearing(engaged),
                bearing(defeated),
            ],
        )
        clock = ManualMonotonicClock(CLOCK_ID, 10_200.0)
        sink = FakeInputSink()
        encounter = ControlledCombatEncounter(
            gateway=CombatActionGateway(
                arm=runtime_arm(), sink=sink, clock=clock
            ),
            observations=source,
            policy=RogueLevelOneCombatPolicy(),
            clock=clock,
            wait_ms=clock.advance,
        )

        result = encounter.run(encounter_id="encounter:fixture:reactive-aggro")

        self.assertEqual(result["status"], "TARGET_DEFEATED")
        self.assertEqual(result["target_identity_crc16"], 4321)
        self.assertEqual(
            [primitive.controls[0] for primitive in sink.applied],
            ["TURN_RIGHT", "ACTION_SLOT_2"],
        )


if __name__ == "__main__":
    unittest.main()
