from __future__ import annotations

import copy
import importlib
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from perfect_assassin.adapter.combat_hud import (
    CombatHudProtocolError,
    bits_to_packet,
    decode_packet,
    encode_packet,
    packet_to_bits,
    target_identity_crc16,
    validate_valid_observation_semantics,
)
from perfect_assassin.adapter.coordinate_hud import crc16_ccitt_false
from perfect_assassin.contract_validation import ContractValidator
from tests.test_coordinate_hud import capture_manifest


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
detector_module = importlib.import_module("combat_hud_detector")
probe_module = importlib.import_module("probe_combat_hud")


def valid_packet(**overrides: object) -> bytes:
    values: dict[str, object] = {
        "sequence": 257,
        "player_alive": True,
        "in_combat": True,
        "target_exists": True,
        "target_hostile": True,
        "target_dead": False,
        "target_player": False,
        "slot1_attack_exact": True,
        "slot2_sinister_strike_exact": True,
        "slot3_eviscerate_exact": True,
        "target_bearing_code": 4,
        "player_health_pct": 83.25,
        "player_energy": 67,
        "player_attack_power": 20,
        "target_health_pct": 42.5,
        "target_health_current": 17,
        "target_health_max": 40,
        "combo_points": 2,
        "player_level": 1,
        "target_level": 1,
        "target_reaction": 2,
        "slot1_usable": True,
        "slot1_current": True,
        "slot1_in_range": True,
        "slot2_usable": True,
        "slot2_in_range": True,
        "slot2_cooldown_ready": True,
        "slot2_cooldown_remaining_ms": 0,
        "slot3_usable": True,
        "slot3_in_range": True,
        "slot3_cooldown_ready": True,
        "target_identity_crc16": target_identity_crc16(
            guid="0xF130009610000001", name="Duskbat"
        ),
    }
    values.update(overrides)
    return encode_packet(**values)  # type: ignore[arg-type]


class CombatHudProtocolTests(unittest.TestCase):
    def test_round_trip_keeps_combat_state_and_exact_action_bindings(self) -> None:
        packet = valid_packet()
        decoded = decode_packet(packet)
        self.assertEqual(decoded.sequence, 1)
        self.assertTrue(decoded.in_combat)
        self.assertTrue(decoded.target_hostile)
        self.assertFalse(decoded.target_player)
        self.assertEqual(decoded.player_energy, 67)
        self.assertEqual(decoded.player_attack_power, 20)
        self.assertEqual(decoded.target_health_current, 17)
        self.assertEqual(decoded.target_health_max, 40)
        self.assertEqual(decoded.combo_points, 2)
        self.assertTrue(decoded.slot1_attack_exact)
        self.assertTrue(decoded.slot1_current)
        self.assertTrue(decoded.slot2_sinister_strike_exact)
        self.assertTrue(decoded.slot2_cooldown_ready)
        self.assertTrue(decoded.slot3_eviscerate_exact)
        self.assertEqual(decoded.target_bearing_code, 4)
        self.assertAlmostEqual(
            decoded.target_frame_x_normalized or 0.0,
            0.5,
            delta=1 / 255,
        )
        self.assertTrue(decoded.slot3_usable)
        self.assertAlmostEqual(decoded.target_health_pct or 0, 42.5, delta=100 / 255)
        self.assertEqual(bits_to_packet(packet_to_bits(packet)), packet)

    def test_absent_target_is_explicit_and_cannot_claim_combat(self) -> None:
        packet = valid_packet(
            in_combat=False,
            target_exists=False,
            target_hostile=False,
            target_health_pct=None,
            target_health_current=None,
            target_health_max=None,
            target_level=None,
            target_reaction=None,
            target_identity_crc16=None,
            target_bearing_code=0,
            slot1_usable=False,
            slot1_current=False,
            slot1_in_range=None,
            slot2_usable=False,
            slot2_in_range=None,
            slot2_cooldown_ready=False,
            slot3_usable=False,
            slot3_in_range=None,
            slot3_cooldown_ready=False,
        )
        decoded = decode_packet(packet)
        self.assertFalse(decoded.target_exists)
        self.assertIsNone(decoded.target_identity_crc16)
        self.assertEqual(decoded.visible_attackable_candidate_count, 0)
        with self.assertRaisesRegex(CombatHudProtocolError, "target-dependent"):
            valid_packet(
                in_combat=False,
                target_exists=False,
                target_health_pct=None,
                target_health_current=None,
                target_health_max=None,
                target_level=None,
                target_reaction=None,
                target_identity_crc16=None,
            )

    def test_absent_target_can_publish_bounded_visible_mob_awareness(self) -> None:
        packet = valid_packet(
            in_combat=False,
            target_exists=False,
            target_hostile=False,
            target_health_pct=None,
            target_health_current=None,
            target_health_max=None,
            target_level=None,
            target_reaction=None,
            target_identity_crc16=None,
            target_bearing_code=5,
            visible_attackable_candidate_count=3,
            acquisition_x_normalized=0.65,
            acquisition_y_normalized=0.42,
            slot1_usable=False,
            slot1_current=False,
            slot1_in_range=None,
            slot2_usable=False,
            slot2_in_range=None,
            slot2_cooldown_ready=False,
            slot3_usable=False,
            slot3_in_range=None,
            slot3_cooldown_ready=False,
        )
        decoded = decode_packet(packet)
        self.assertEqual(decoded.visible_attackable_candidate_count, 3)
        self.assertAlmostEqual(decoded.acquisition_x_normalized or 0, 0.65, delta=1/255)
        self.assertAlmostEqual(decoded.acquisition_y_normalized or 0, 0.42, delta=1/255)

    def test_exact_selected_frame_geometry_replaces_coarse_bearing_offset(self) -> None:
        packet = valid_packet(
            target_bearing_code=5,
            target_frame_x_normalized=0.57,
            target_frame_y_normalized=0.44,
        )
        decoded = decode_packet(packet)
        self.assertAlmostEqual(
            (decoded.target_frame_x_normalized or 0.0) * 2.0 - 1.0,
            0.14,
            delta=2 / 255,
        )
        profile = detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        detector = detector_module.CombatHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "combat-hud.schema.json"),
        )
        observation = detector.detect(
            capture_manifest(),
            synthetic_combat_hud(packet),
            observation_id="combat-hud:fixture:exact-bearing",
        )
        self.assertAlmostEqual(
            observation["target"]["bearing_offset_x_normalized"],
            0.14,
            delta=2 / 255,
        )

    def test_corruption_fails_closed_and_low_target_code_decodes(self) -> None:
        packet = bytearray(valid_packet())
        packet[6] ^= 1
        with self.assertRaisesRegex(CombatHudProtocolError, "CRC-16"):
            decode_packet(bytes(packet))

        packet = bytearray(valid_packet())
        packet[13] = 0xE0
        packet[-2:] = crc16_ccitt_false(packet[:-2]).to_bytes(2, "big")
        decoded = decode_packet(bytes(packet))
        self.assertEqual(decoded.target_bearing_code, 7)

    def test_action_state_cannot_be_laundered_without_exact_slot_binding(self) -> None:
        with self.assertRaisesRegex(CombatHudProtocolError, "slot 2 state"):
            valid_packet(slot2_sinister_strike_exact=False)
        with self.assertRaisesRegex(CombatHudProtocolError, "cooldown"):
            valid_packet(
                slot2_cooldown_ready=True,
                slot2_cooldown_remaining_ms=100,
            )
        with self.assertRaisesRegex(CombatHudProtocolError, "slot 3 state"):
            valid_packet(slot3_eviscerate_exact=False)

    def test_dead_state_and_bounded_resources_are_semantic(self) -> None:
        with self.assertRaisesRegex(CombatHudProtocolError, "dead target"):
            valid_packet(
                target_dead=True,
                target_health_pct=42.5,
                target_health_current=17,
            )
        with self.assertRaisesRegex(CombatHudProtocolError, "player_energy"):
            valid_packet(player_energy=101)
        with self.assertRaisesRegex(CombatHudProtocolError, "combo_points"):
            valid_packet(combo_points=6)

    def test_target_fingerprint_is_stable_and_bounded(self) -> None:
        first = target_identity_crc16(guid="0xABC", name="Duskbat")
        self.assertEqual(first, target_identity_crc16(guid="0xABC", name="Duskbat"))
        self.assertNotEqual(first, target_identity_crc16(guid="0xABD", name="Duskbat"))
        self.assertEqual(target_identity_crc16(guid=None, name=None), 0)
        with self.assertRaisesRegex(CombatHudProtocolError, "byte budget"):
            target_identity_crc16(guid="A" * 513, name=None)


def synthetic_combat_hud(packet: bytes) -> np.ndarray:
    frame = np.zeros((600, 800, 4), dtype=np.uint8)
    frame[:, :, 3] = 255

    def rectangle(x: int, y: int, width: int, height: int, bgr: tuple[int, int, int]) -> None:
        frame[y : y + height, x : x + width, :3] = bgr

    base_x, base_y = 16, 16
    rectangle(base_x + 6, base_y + 32, 6, 6, (255, 255, 0))
    rectangle(base_x + 98, base_y + 32, 6, 6, (255, 0, 255))
    rectangle(base_x + 6, base_y + 66, 6, 6, (0, 255, 255))
    rectangle(base_x + 98, base_y + 66, 6, 6, (0, 255, 0))
    for index, bit in enumerate(packet_to_bits(packet)):
        row, column = divmod(index, 16)
        value = 255 if bit else 0
        rectangle(
            base_x + 112 + column * 3,
            base_y + 34 + row * 3,
            2,
            2,
            (value, value, value),
        )
    return frame


class CombatHudDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        self.detector = detector_module.CombatHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "combat-hud.schema.json"),
        )

    def test_visible_packet_becomes_versioned_non_authority_fact(self) -> None:
        observation = self.detector.detect(
            capture_manifest(),
            synthetic_combat_hud(valid_packet()),
            observation_id="combat-hud:fixture:0001",
        )
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertEqual(observation["player"]["energy"], 67)
        self.assertTrue(observation["target"]["hostile"])
        self.assertFalse(observation["target"]["is_player"])
        self.assertTrue(observation["actions"]["slot2_sinister_strike"]["exact_binding"])
        self.assertEqual(observation["provenance"]["scope"], "synthetic_fixture")
        self.assertFalse(observation["execution_authority"])
        validate_valid_observation_semantics(observation)

    def test_visible_attackable_candidates_are_published_without_a_target(self) -> None:
        packet = valid_packet(
            in_combat=False,
            target_exists=False,
            target_hostile=False,
            target_health_pct=None,
            target_health_current=None,
            target_health_max=None,
            target_level=None,
            target_reaction=None,
            target_identity_crc16=None,
            target_bearing_code=5,
            visible_attackable_candidate_count=3,
            acquisition_x_normalized=0.65,
            acquisition_y_normalized=0.42,
            slot1_usable=False,
            slot1_current=False,
            slot1_in_range=None,
            slot2_usable=False,
            slot2_in_range=None,
            slot2_cooldown_ready=False,
            slot3_usable=False,
            slot3_in_range=None,
            slot3_cooldown_ready=False,
        )
        observation = self.detector.detect(
            capture_manifest(),
            synthetic_combat_hud(packet),
            observation_id="combat-hud:fixture:visible-awareness",
        )
        self.assertIsNone(observation["target"])
        self.assertEqual(
            observation["combat"]["visible_attackable_candidate_count"], 3
        )
        self.assertAlmostEqual(
            observation["combat"]["acquisition_x_normalized"], 0.65, delta=1/255
        )
        validate_valid_observation_semantics(observation)

    def test_crc_failure_is_invalid_not_state(self) -> None:
        corrupted = bytearray(valid_packet())
        corrupted[5] ^= 1
        observation = self.detector.detect(
            capture_manifest(),
            synthetic_combat_hud(bytes(corrupted)),
            observation_id="combat-hud:fixture:bad-crc",
        )
        self.assertEqual(observation["tracking_state"], "INVALID")
        self.assertIsNone(observation["player"])

    def test_published_state_cannot_diverge_from_packet(self) -> None:
        observation = self.detector.detect(
            capture_manifest(),
            synthetic_combat_hud(valid_packet()),
            observation_id="combat-hud:fixture:semantic",
        )
        forged = copy.deepcopy(observation)
        forged["player"]["energy"] = 100
        with self.assertRaisesRegex(CombatHudProtocolError, "player state"):
            validate_valid_observation_semantics(forged)

    def test_missing_fiducials_fails_without_fact(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        observation = self.detector.detect(
            capture_manifest(),
            frame,
            observation_id="combat-hud:fixture:not-found",
        )
        self.assertEqual(observation["tracking_state"], "NOT_FOUND")
        self.assertIsNone(observation["actions"])

    def test_cached_marker_geometry_avoids_repeated_full_scene_search(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        detector = detector_module.CombatHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "combat-hud.schema.json"),
            reuse_marker_geometry=True,
        )
        frame = synthetic_combat_hud(valid_packet())

        with patch.object(
            detector_module,
            "locate_visible_hud_markers",
            wraps=detector_module.locate_visible_hud_markers,
        ) as locate:
            first = detector.detect(
                capture_manifest(),
                frame,
                observation_id="combat-hud:fixture:cached-1",
            )
            second = detector.detect(
                capture_manifest(),
                frame.copy(),
                observation_id="combat-hud:fixture:cached-2",
            )

        self.assertEqual(first["tracking_state"], "VALID")
        self.assertEqual(second["tracking_state"], "VALID")
        locate.assert_called_once()

    def test_live_probe_profile_is_hash_pinned_and_non_authority(self) -> None:
        profile, digest = probe_module._load_pinned_profile(
            ROOT / "config" / "combat" / "combat-hud-tbc243-v2.json"
        )
        self.assertEqual(digest, probe_module.SUPPORTED_PROFILE_SHA256)
        self.assertFalse(profile["execution_authority"])
        changed = copy.deepcopy(profile)
        changed["detector_deadline_ms"] = 501
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(probe_module.CombatHudProbeError, "SHA-256"):
                probe_module._load_pinned_profile(path)

    def test_live_probe_opens_provider_before_first_frame(self) -> None:
        source = (INTEGRATION / "probe_combat_hud.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("provider.open()"), 1)
        self.assertLess(source.index("provider.open()"), source.index("provider.next_frame()"))


if __name__ == "__main__":
    unittest.main()
