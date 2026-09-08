from __future__ import annotations

import copy
from pathlib import Path
import unittest

from perfect_assassin.adapter.coordinate_hud import decode_packet, encode_packet
from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.execution import FakeInputSink, ManualMonotonicClock
from perfect_assassin.execution.single_forward_pulse import (
    POSITION_RADIUS_95,
    SingleForwardPulseCoordinator,
    SingleForwardPulseError,
    validate_single_forward_pulse_result_semantics,
)
from tests.test_movement_runtime_arm import (
    exact_json_bytes,
    issued_authorization_raw,
    load_fixture_arm,
    movement_arm_record,
    session_receipt_record,
)


ROOT = Path(__file__).resolve().parents[1]
OBS_SCHEMA = ROOT / "contracts" / "coordinate-hud.schema.json"
RESULT_SCHEMA = ROOT / "contracts" / "single-forward-pulse-result.schema.json"


class QueueObservations:
    def __init__(self, clock: ManualMonotonicClock, values):
        self.clock = clock
        self.values = iter(values)

    def next_observation(self):
        advance, value = next(self.values, (0.0, None))
        self.clock.advance(advance)
        return value


class ImmediateTakeover:
    def __init__(self):
        self.disarmed = False

    def arm(self, callback):
        callback()

        def disarm():
            self.disarmed = True

        return disarm


def observation(*, arm, sequence=10, x=0.25, y=0.5, timestamp_ms=2000.0, zone=25, frame="frame:f3a:pre", session="session:f3a:one", confidence=0.99):
    packet_raw = encode_packet(
        sequence=sequence,
        position_available=True,
        map_context_ready=True,
        world_map_visible=False,
        x=x,
        y=y,
        continent_index=2,
        zone_index=zone,
    )
    packet = decode_packet(packet_raw)
    actor = {
        "schema_version": "1.0",
        "instance_id": arm.binding.actor_instance_id,
        "actor_role": arm.binding.actor_role,
        "actor_id": arm.binding.actor_id,
        "decision_context": arm.binding.decision_context,
        "memory_namespace": "memory:lab:predator-f3a",
        "expected_character_name": "Predator",
        "credential_alias": "credential:lab:pa_observer",
        "binding_assurance": {
            "state": "configured_expected_only",
            "evidence_refs": ["config:movement:f3a"],
        },
    }
    timestamp_s = timestamp_ms / 1000.0
    return {
        "record_type": "coordinate_hud_observation",
        "schema_version": "2.0",
        "observation_id": f"observation:{frame}",
        "frame_id": frame,
        "session_id": session,
        "target_profile": arm.binding.target_profile,
        "actor_binding": actor,
        "authorization_sha256": arm.binding.authorization_sha256,
        "decision_context": arm.binding.decision_context,
        "client_build": "2.4.3.8606",
        "build_signature": "windows-x86-wow-2.4.3.8606",
        "tracking_state": "VALID",
        "reason": "packet_valid",
        "confidence": confidence,
        "timing": {
            "captured_at": "2026-08-23T12:00:00Z",
            "monotonic_timestamp_s": timestamp_s,
            "frame_age_ms": 0.0,
            "observed_monotonic_s": timestamp_s,
            "age_at_observation_ms": 0.0,
            "freshness_limit_ms": 600.0,
            "expires_monotonic_s": timestamp_s + 0.6,
        },
        "protocol": {
            "magic": 165,
            "version": 3,
            "sequence": packet.sequence,
            "flags": packet_raw[2],
            "crc_valid": True,
            "packet_hex": packet_raw.hex(),
        },
        "position": {
            "coordinate_space": "normalized_current_zone_map",
            "x": packet.x,
            "y": packet.y,
            "continent_index": packet.continent_index,
            "zone_index": packet.zone_index,
        },
        "map_position_available": True,
        "player_state": {
            "dead_or_ghost": packet.player_dead_or_ghost,
            "ghost": packet.player_ghost,
        },
        "provenance": {
            "origin": "visible_addon_hud",
            "capture_origin": "window_capture",
            "capability": "self_map_position",
            "scope": "lab_evaluation_only",
            "profile_id": "coordinate_hud_tbc243_v1",
            "profile_version": "0.2.0",
            "profile_sha256": "C05E2FF78B5857088559EE4C96AA8889C718FDE9A07D2E2748EBB2534FF8958E",
            "profile_calibration_state": "synthetic_verified",
            "evidence_refs": ["profile:coordinate-hud", "capture:window"],
        },
        "execution_authority": False,
    }


class SingleForwardPulseTests(unittest.TestCase):
    def setUp(self):
        self.clock = ManualMonotonicClock("clock:movement:f3a", 2000.0)
        self.auth_raw = issued_authorization_raw()
        self.receipt_raw = exact_json_bytes(session_receipt_record())
        self.arm = load_fixture_arm(
            movement_arm_record(
                session_receipt_raw=self.receipt_raw,
                authorization_raw=self.auth_raw,
            ),
            self.receipt_raw,
            exact_movement_authorization_raw=self.auth_raw,
        )

    def coordinator(self, values, *, sink=None, manual_takeover=None):
        return SingleForwardPulseCoordinator(
            arm=self.arm,
            clock=self.clock,
            sink=sink or FakeInputSink(),
            observations=QueueObservations(self.clock, values),
            observation_validator=ContractValidator(OBS_SCHEMA),
            result_validator=ContractValidator(RESULT_SCHEMA),
            manual_takeover=manual_takeover,
            sleep_ms=self.clock.advance,
        )

    def run_gate(self, pre, post, *, sink=None, post_advance=100.0):
        return self.coordinator(
            [(0.0, pre), (post_advance, post)], sink=sink
        ).run(run_id="run:f3a:test", owner_id="owner:f3a:test")

    def test_two_lsb_displacement_is_proven_and_cleanup_is_mandatory(self):
        pre = observation(arm=self.arm)
        post = observation(
            arm=self.arm,
            sequence=11,
            x=pre["position"]["x"] + 2.0 / 65535.0,
            y=pre["position"]["y"],
            timestamp_ms=2100.0,
            frame="frame:f3a:post",
        )
        sink = FakeInputSink()
        result = self.run_gate(pre, post, sink=sink)
        self.assertEqual(result["status"], "PROVEN_DISPLACEMENT")
        self.assertGreater(result["delta"]["proven_lower_bound"], 0.0)
        self.assertEqual(len(sink.applied), 1)
        self.assertEqual(sink.applied[0].controls, ("MOVE_FORWARD",))
        self.assertEqual(sink.applied[0].hold_duration_ms, 100)
        self.assertEqual(sink.applied[0].max_execution_envelope_ms, 150)
        self.assertTrue(result["cleanup"]["arm_disarmed"])
        self.assertTrue(result["cleanup"]["gateway_closed"])
        ContractValidator(RESULT_SCHEMA).validate(result)

    def test_one_lsb_is_not_laundered_as_proven_motion(self):
        pre = observation(arm=self.arm)
        post = observation(
            arm=self.arm,
            sequence=11,
            x=pre["position"]["x"] + 1.0 / 65535.0,
            timestamp_ms=2100.0,
            frame="frame:f3a:post",
        )
        result = self.run_gate(pre, post)
        self.assertEqual(result["status"], "NO_PROVEN_DISPLACEMENT")
        self.assertEqual(result["delta"]["proven_lower_bound"], 0.0)
        self.assertAlmostEqual(result["delta"]["combined_position_radius_95"], 2 * POSITION_RADIUS_95)

    def test_stale_pre_observation_never_reaches_sink(self):
        pre = observation(arm=self.arm, timestamp_ms=1000.0)
        sink = FakeInputSink()
        result = self.coordinator([(0.0, pre)], sink=sink).run(
            run_id="run:f3a:stale", owner_id="owner:f3a:test"
        )
        self.assertEqual(result["status"], "OBSERVATION_REJECTED")
        self.assertEqual(result["reason"], "OBSERVATION_NOT_FRESH_NOW")
        self.assertEqual(sink.apply_attempts, [])
        self.assertTrue(result["cleanup"]["arm_disarmed"])

    def test_wrong_authorization_never_reaches_sink(self):
        pre = observation(arm=self.arm)
        pre["authorization_sha256"] = "F" * 64
        sink = FakeInputSink()
        result = self.coordinator([(0.0, pre)], sink=sink).run(
            run_id="run:f3a:wrong-auth", owner_id="owner:f3a:test"
        )
        self.assertEqual(result["reason"], "OBSERVATION_AUTHORITY_BINDING_MISMATCH")
        self.assertEqual(sink.apply_attempts, [])

    def test_post_must_be_distinct_and_newer_than_execution(self):
        pre = observation(arm=self.arm)
        same = copy.deepcopy(pre)
        result = self.coordinator(
            [(0.0, pre)] + [(10.0, same)] * 64
        ).run(run_id="run:f3a:same", owner_id="owner:f3a:test")
        self.assertEqual(result["status"], "OBSERVATION_REJECTED")
        self.assertIn(
            result["reason"],
            {"POST_OBSERVATION_LIMIT", "POST_OBSERVATION_DEADLINE", "OBSERVATION_NOT_FRESH_NOW"},
        )

    def test_post_captured_before_completion_is_not_accepted(self):
        pre = observation(arm=self.arm)
        early = observation(
            arm=self.arm,
            sequence=11,
            timestamp_ms=1999.0,
            frame="frame:f3a:early",
        )
        result = self.coordinator(
            [(0.0, pre), (10.0, early)] + [(100.0, None)] * 60
        ).run(run_id="run:f3a:early", owner_id="owner:f3a:test")
        self.assertEqual(result["status"], "OBSERVATION_REJECTED")

    def test_map_change_is_indeterminate_not_success(self):
        pre = observation(arm=self.arm)
        post = observation(
            arm=self.arm,
            sequence=11,
            timestamp_ms=2100.0,
            zone=26,
            frame="frame:f3a:new-zone",
        )
        result = self.run_gate(pre, post)
        self.assertEqual(result["status"], "OBSERVATION_REJECTED")
        self.assertEqual(result["reason"], "MAP_CONTEXT_CHANGED")
        self.assertIsNone(result["delta"])

    def test_source_session_change_is_rejected(self):
        pre = observation(arm=self.arm)
        post = observation(
            arm=self.arm,
            sequence=11,
            timestamp_ms=2100.0,
            frame="frame:f3a:post",
            session="session:f3a:other",
        )
        result = self.run_gate(pre, post)
        self.assertEqual(result["reason"], "POST_SOURCE_CHANGED")

    def test_sink_failure_is_not_reported_as_motion(self):
        pre = observation(arm=self.arm)
        sink = FakeInputSink(fail_on_apply=True)
        result = self.coordinator([(0.0, pre)], sink=sink).run(
            run_id="run:f3a:sink-fail", owner_id="owner:f3a:test"
        )
        self.assertEqual(result["status"], "EXECUTION_REJECTED")
        self.assertEqual(result["execution_result"]["status"], "FAILED")
        self.assertIsNone(result["delta"])
        self.assertTrue(result["cleanup"]["arm_disarmed"])

    def test_manual_takeover_cancels_before_any_input_and_is_disarmed(self):
        pre = observation(arm=self.arm)
        sink = FakeInputSink()
        takeover = ImmediateTakeover()
        result = self.coordinator(
            [(0.0, pre)], sink=sink, manual_takeover=takeover
        ).run(run_id="run:f3a:takeover", owner_id="owner:f3a:test")
        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["reason"], "MANUAL_TAKEOVER")
        self.assertEqual(sink.apply_attempts, [])
        self.assertTrue(takeover.disarmed)
        self.assertTrue(result["cleanup"]["manual_takeover_disarmed"])

    def test_replay_fixture_is_refused_before_execution(self):
        pre = observation(arm=self.arm)
        pre["provenance"]["capture_origin"] = "replay_fixture"
        pre["provenance"]["scope"] = "synthetic_fixture"
        sink = FakeInputSink()
        result = self.coordinator([(0.0, pre)], sink=sink).run(
            run_id="run:f3a:replay", owner_id="owner:f3a:test"
        )
        self.assertEqual(result["reason"], "OBSERVATION_NOT_CONTROLLED_LIVE_LAB")
        self.assertEqual(sink.apply_attempts, [])

    def test_unpinned_live_hud_profile_is_refused_before_execution(self):
        pre = observation(arm=self.arm)
        pre["provenance"]["profile_sha256"] = "A" * 64
        sink = FakeInputSink()
        result = self.coordinator([(0.0, pre)], sink=sink).run(
            run_id="run:f3a:wrong-hud-profile", owner_id="owner:f3a:test"
        )
        self.assertEqual(result["reason"], "OBSERVATION_NOT_CONTROLLED_LIVE_LAB")
        self.assertEqual(sink.apply_attempts, [])

    def test_raw_result_cannot_launder_uncertainty_or_cleanup(self):
        pre = observation(arm=self.arm)
        post = observation(
            arm=self.arm,
            sequence=11,
            x=pre["position"]["x"] + 2.0 / 65535.0,
            timestamp_ms=2100.0,
            frame="frame:f3a:post",
        )
        valid = self.run_gate(pre, post)
        validate_single_forward_pulse_result_semantics(valid)

        forged = copy.deepcopy(valid)
        forged["delta"]["proven_lower_bound"] = 0.0
        with self.assertRaises(SingleForwardPulseError):
            validate_single_forward_pulse_result_semantics(forged)

        forged = copy.deepcopy(valid)
        forged["cleanup"]["gateway_closed"] = False
        with self.assertRaises(SingleForwardPulseError):
            validate_single_forward_pulse_result_semantics(forged)

        forged = copy.deepcopy(valid)
        forged["post_observation"]["session_id"] = "session:f3a:forged"
        with self.assertRaises(SingleForwardPulseError):
            validate_single_forward_pulse_result_semantics(forged)


if __name__ == "__main__":
    unittest.main()
