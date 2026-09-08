from __future__ import annotations

import copy
import importlib
import sys
import time
import unittest
from pathlib import Path

import numpy as np

from perfect_assassin.adapter.coordinate_hud import (
    CoordinateHudProtocolError,
    bits_to_packet,
    crc16_ccitt_false,
    decode_packet,
    encode_packet,
    packet_to_bits,
)
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

detector_module = importlib.import_module("coordinate_hud_detector")


def capture_manifest(width: int = 800, height: int = 600) -> dict:
    return {
        "record_type": "capture_frame_manifest",
        "schema_version": "2.0",
        "frame_id": "frame:hud:fixture:0001",
        "session_id": "session:hud-fixture",
        "target_profile": "tbc_243_lab",
        "actor_binding": {
            "schema_version": "1.0",
            "instance_id": "instance:fixture:champion",
            "actor_role": "champion_journey",
            "actor_id": "actor:predator:fixture-champion",
            "decision_context": "champion",
            "memory_namespace": "memory:champion:fixture",
            "expected_character_name": "Predator",
            "credential_alias": "credential:fixture:champion",
            "binding_assurance": {
                "state": "configured_expected_only",
                "evidence_refs": ["authorization:fixture:actor-expected"],
            },
        },
        "authorization_sha256": "A" * 64,
        "decision_context": "champion",
        "client_build": "2.4.3.8606",
        "build_signature": "wow-tbc-2.4.3.8606-enGB",
        "provider_id": "capture_replay_fixture",
        "provider_version": "0.1.0",
        "backend": "replay_fixture",
        "source": {
            "source_kind": "replay_fixture",
            "device_index": None,
            "output_index": None,
            "coordinate_space": "replay_fixture_pixels",
            "region": {"left": 0, "top": 0, "width": width, "height": height},
            "window_ref": None,
        },
        "image": {
            "width": width,
            "height": height,
            "row_stride_bytes": width * 4,
            "pixel_format": "BGRA8",
            "orientation": "top_down",
        },
        "timing": {
            "captured_at": "2026-08-22T21:00:00Z",
            "source_timestamp_s": 10.0,
            "monotonic_timestamp_s": 20.0,
            "frame_age_ms": 2.0,
        },
        "provenance": {
            "origin": "replay_fixture",
            "capability": "screen_capture",
            "scope": "synthetic_fixture",
            "confidence": 1.0,
            "evidence_refs": ["fixture:hud:synthetic:0001"],
        },
        "artifact": {
            "persisted": False,
            "media_type": "application/x-perfect-assassin-bgra8",
            "path": None,
            "sha256": None,
        },
        "privacy": {
            "content_class": "game_client_pixels",
            "redaction_state": "in_memory_only",
            "retention": "none",
        },
        "execution_authority": False,
    }


def synthetic_hud(packet: bytes, *, scale: float = 1.0, origin: tuple[int, int] = (16, 16)) -> np.ndarray:
    frame = np.zeros((600, 800, 4), dtype=np.uint8)
    frame[:, :, 3] = 255

    def rectangle(x: float, y: float, width: float, height: float, bgr: tuple[int, int, int]) -> None:
        left, top = int(round(x)), int(round(y))
        right = max(left + 1, int(round(x + width)))
        bottom = max(top + 1, int(round(y + height)))
        frame[top:bottom, left:right, :3] = bgr

    base_x, base_y = origin
    rectangle(base_x + 6 * scale, base_y + 32 * scale, 6 * scale, 6 * scale, (255, 255, 0))
    rectangle(base_x + 98 * scale, base_y + 32 * scale, 6 * scale, 6 * scale, (255, 0, 255))
    rectangle(base_x + 6 * scale, base_y + 66 * scale, 6 * scale, 6 * scale, (0, 255, 255))
    rectangle(base_x + 98 * scale, base_y + 66 * scale, 6 * scale, 6 * scale, (0, 255, 0))
    for index, bit in enumerate(packet_to_bits(packet)):
        row, column = divmod(index, 16)
        value = 255 if bit else 0
        rectangle(
            base_x + (14 + column * 5) * scale,
            base_y + (34 + row * 5) * scale,
            4 * scale,
            4 * scale,
            (value, value, value),
        )
    return frame


class CoordinateHudProtocolTests(unittest.TestCase):
    def test_crc_standard_check_vector(self) -> None:
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_packet_round_trip_and_quantization(self) -> None:
        packet = encode_packet(
            sequence=257,
            position_available=True,
            map_context_ready=True,
            world_map_visible=False,
            x=0.42125,
            y=0.61875,
            continent_index=1,
            zone_index=14,
            facing_rad=1.75,
        )
        decoded = decode_packet(packet)
        self.assertEqual(decoded.sequence, 1)
        self.assertAlmostEqual(decoded.x or 0, 0.42125, delta=1 / 65535)
        self.assertAlmostEqual(decoded.y or 0, 0.61875, delta=1 / 65535)
        self.assertEqual(decoded.zone_index, 14)
        self.assertAlmostEqual(decoded.facing_rad or 0, 1.75, delta=(2 * 3.141592653589793) / 65535)
        self.assertFalse(decoded.player_dead_or_ghost)
        self.assertFalse(decoded.player_ghost)
        self.assertEqual(bits_to_packet(packet_to_bits(packet)), packet)

    def test_dead_and_ghost_states_are_crc_bound(self) -> None:
        dead = decode_packet(encode_packet(
            sequence=1,
            position_available=True,
            map_context_ready=True,
            world_map_visible=False,
            x=0.25,
            y=0.75,
            player_dead_or_ghost=True,
        ))
        ghost = decode_packet(encode_packet(
            sequence=2,
            position_available=True,
            map_context_ready=True,
            world_map_visible=False,
            x=0.25,
            y=0.75,
            player_dead_or_ghost=True,
            player_ghost=True,
        ))
        self.assertTrue(dead.player_dead_or_ghost)
        self.assertFalse(dead.player_ghost)
        self.assertTrue(ghost.player_dead_or_ghost)
        self.assertTrue(ghost.player_ghost)
        with self.assertRaisesRegex(CoordinateHudProtocolError, "ghost state"):
            encode_packet(
                sequence=3,
                position_available=False,
                map_context_ready=False,
                world_map_visible=False,
                x=None,
                y=None,
                player_ghost=True,
            )

    def test_quantization_matches_lua_half_up_at_exact_half_lsb(self) -> None:
        packet = encode_packet(
            sequence=1,
            position_available=True,
            map_context_ready=True,
            world_map_visible=False,
            x=2.5 / 65535,
            y=4.5 / 65535,
        )
        self.assertEqual(int.from_bytes(packet[4:6], "big"), 3)
        self.assertEqual(int.from_bytes(packet[6:8], "big"), 5)

    def test_crc_corruption_fails_closed(self) -> None:
        packet = bytearray(
            encode_packet(
                sequence=1,
                position_available=False,
                map_context_ready=False,
                world_map_visible=False,
                x=None,
                y=None,
            )
        )
        packet[5] ^= 1
        with self.assertRaisesRegex(CoordinateHudProtocolError, "CRC-16"):
            decode_packet(bytes(packet))

    def test_available_position_requires_logically_consistent_map_flags(self) -> None:
        with self.assertRaisesRegex(
            CoordinateHudProtocolError,
            "ready map context",
        ):
            encode_packet(
                sequence=1,
                position_available=True,
                map_context_ready=False,
                world_map_visible=False,
                x=0.25,
                y=0.75,
            )
        with self.assertRaisesRegex(
            CoordinateHudProtocolError,
            "world map is visible",
        ):
            encode_packet(
                sequence=1,
                position_available=True,
                map_context_ready=True,
                world_map_visible=True,
                x=0.25,
                y=0.75,
            )

        valid = bytearray(
            encode_packet(
                sequence=1,
                position_available=True,
                map_context_ready=True,
                world_map_visible=False,
                x=0.25,
                y=0.75,
            )
        )
        for invalid_flags, expected_error in (
            (1, "ready map context"),
            (7, "world map is visible"),
        ):
            with self.subTest(flags=invalid_flags):
                inconsistent = bytearray(valid)
                inconsistent[2] = invalid_flags
                checksum = crc16_ccitt_false(inconsistent[:-2])
                inconsistent[-2:] = checksum.to_bytes(2, "big")
                with self.assertRaisesRegex(
                    CoordinateHudProtocolError,
                    expected_error,
                ):
                    decode_packet(bytes(inconsistent))


class CoordinateHudDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        self.detector = detector_module.CoordinateHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
        )

    @staticmethod
    def packet(*, available: bool = True) -> bytes:
        return encode_packet(
            sequence=23,
            position_available=available,
            map_context_ready=available,
            world_map_visible=False,
            x=0.42125 if available else None,
            y=0.61875 if available else None,
            continent_index=1,
            zone_index=14,
            facing_rad=1.75,
        )

    def detect(self, frame: np.ndarray) -> dict:
        return self.detector.detect(capture_manifest(), frame, observation_id="hud:fixture:0001")

    def test_fast_search_window_preserves_global_marker_geometry(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        detector = detector_module.CoordinateHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
            search_window_fraction=(0.01, 0.07, 0.20, 0.25),
        )
        frame = synthetic_hud(self.packet(), origin=(24, 50))

        markers = detector._locate_markers(
            frame,
            deadline_s=time.monotonic() + 1.0,
        )
        self.assertIsNotNone(markers)
        assert markers is not None
        self.assertAlmostEqual(markers[0][0], 33.0, delta=0.6)
        self.assertAlmostEqual(markers[0][1], 85.0, delta=0.6)

        observation = detector.detect(
            capture_manifest(),
            frame,
            observation_id="hud:fast-window",
        )
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)
        self.assertAlmostEqual(observation["position"]["y"], 0.61875, delta=1 / 65535)

    def test_fast_search_window_rejects_invalid_or_unbounded_rectangles(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        validator = ContractValidator(ROOT / "contracts" / "capture-frame.schema.json")
        observation_validator = ContractValidator(
            ROOT / "contracts" / "coordinate-hud.schema.json"
        )
        for window in (
            (0.20, 0.10, 0.10, 0.20),
            (-0.01, 0.10, 0.20, 0.20),
            (0.01, 0.10, 0.51, 0.20),
            (0.01, 0.10, 0.20, 0.36),
        ):
            with self.subTest(window=window):
                with self.assertRaisesRegex(
                    detector_module.CoordinateHudDetectionError,
                    "fast search window is invalid",
                ):
                    detector_module.CoordinateHudDetector(
                        profile,
                        validator,
                        observation_validator,
                        search_window_fraction=window,
                    )

    def test_cached_marker_geometry_reuses_visible_markers_and_relocalizes_after_move(self) -> None:
        profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        detector = detector_module.CoordinateHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
            reuse_marker_geometry=True,
        )
        first = detector.detect(
            capture_manifest(),
            synthetic_hud(self.packet(), origin=(24, 50)),
            observation_id="hud:cached:first",
        )
        cached_markers = detector._cached_markers
        second = detector.detect(
            capture_manifest(),
            synthetic_hud(self.packet(), origin=(24, 50)),
            observation_id="hud:cached:second",
        )
        self.assertEqual(first["tracking_state"], "VALID")
        self.assertEqual(second["tracking_state"], "VALID")
        self.assertIs(detector._cached_markers, cached_markers)

        moved = detector.detect(
            capture_manifest(),
            synthetic_hud(self.packet(), origin=(120, 80)),
            observation_id="hud:cached:moved",
        )
        self.assertEqual(moved["tracking_state"], "VALID")
        self.assertNotEqual(detector._cached_markers, cached_markers)

    def test_locates_translated_scaled_hud_and_decodes_position(self) -> None:
        for scale, origin in (
            (1.0, (16, 16)),
            (1.0, (16, 100)),
            (1.0, (284, 126)),
            (1.5, (120, 36)),
        ):
            with self.subTest(scale=scale):
                observation = self.detect(synthetic_hud(self.packet(), scale=scale, origin=origin))
                self.assertEqual(observation["tracking_state"], "VALID")
                self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)
                self.assertAlmostEqual(observation["position"]["y"], 0.61875, delta=1 / 65535)
                self.assertAlmostEqual(observation["position"]["facing_rad"], 1.75, delta=(2 * 3.141592653589793) / 65535)
                self.assertEqual(observation["protocol"]["sequence"], 23)
                self.assertEqual(
                    observation["player_state"],
                    {"dead_or_ghost": False, "ghost": False},
                )
                self.assertEqual(observation["decision_context"], "champion")
                self.assertEqual(
                    observation["provenance"]["capture_origin"],
                    "replay_fixture",
                )
                self.assertEqual(
                    observation["provenance"]["scope"],
                    "synthetic_fixture",
                )
                self.assertEqual(observation["schema_version"], "2.0")
                self.assertEqual(
                    observation["actor_binding"],
                    capture_manifest()["actor_binding"],
                )
                self.assertEqual(observation["authorization_sha256"], "A" * 64)
                self.assertEqual(
                    observation["actor_binding"]["binding_assurance"]["state"],
                    "configured_expected_only",
                )
                self.assertEqual(observation["timing"]["freshness_limit_ms"], 600)
                self.assertEqual(observation["timing"]["expires_monotonic_s"], 20.6)
                self.assertFalse(observation["execution_authority"])

    def test_detector_rejects_non_finite_capture_values_before_freshness_checks(self) -> None:
        frame = synthetic_hud(self.packet())
        paths = (
            ("timing", "source_timestamp_s"),
            ("timing", "monotonic_timestamp_s"),
            ("timing", "frame_age_ms"),
            ("provenance", "confidence"),
        )
        for path in paths:
            for invalid in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(path=path, invalid=invalid):
                    manifest = capture_manifest()
                    manifest[path[0]][path[1]] = invalid
                    with self.assertRaisesRegex(
                        ContractValidationError,
                        "non-finite numbers",
                    ):
                        self.detector.detect(
                            manifest,
                            frame,
                            observation_id="hud:non-finite",
                        )

    def test_detector_actor_binding_is_deeply_owned(self) -> None:
        manifest = capture_manifest()
        observation = self.detector.detect(
            manifest,
            synthetic_hud(self.packet()),
            observation_id="hud:actor-copy",
        )
        original_ref = "authorization:fixture:actor-expected"
        manifest["actor_binding"]["binding_assurance"]["evidence_refs"].append(
            "authorization:source-mutated"
        )
        self.assertEqual(
            observation["actor_binding"]["binding_assurance"]["evidence_refs"],
            [original_ref],
        )

        observation["actor_binding"]["binding_assurance"]["evidence_refs"].append(
            "authorization:observation-mutated"
        )
        self.assertNotIn(
            "authorization:observation-mutated",
            manifest["actor_binding"]["binding_assurance"]["evidence_refs"],
        )

    def test_detector_owns_profile_snapshot_bound_to_hash(self) -> None:
        caller_profile = detector_module.load_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        detector = detector_module.CoordinateHudDetector(
            caller_profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
        )
        pinned_hash = detector.profile_sha256
        pinned_freshness = detector.profile["freshness_limit_ms"]
        caller_profile["freshness_limit_ms"] = 1
        caller_profile["calibration_state"] = "controlled_live_verified"

        observation = detector.detect(
            capture_manifest(),
            synthetic_hud(self.packet()),
            observation_id="hud:owned-profile",
        )
        self.assertEqual(detector.profile_sha256, pinned_hash)
        self.assertEqual(detector.profile["freshness_limit_ms"], pinned_freshness)
        self.assertEqual(
            observation["provenance"]["profile_sha256"],
            pinned_hash,
        )
        self.assertEqual(
            observation["provenance"]["profile_calibration_state"],
            "synthetic_verified",
        )

    def test_provenance_cannot_launder_replay_or_unpromoted_live_input(self) -> None:
        frame = synthetic_hud(self.packet())
        replay = self.detect(frame)
        contaminated = copy.deepcopy(replay)
        contaminated["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            ContractValidator(
                ROOT / "contracts" / "coordinate-hud.schema.json"
            ).validate(contaminated)

        live_manifest = capture_manifest()
        live_manifest["backend"] = "dxgi_desktop_duplication"
        live_manifest["source"] = {
            "source_kind": "window_region",
            "device_index": 0,
            "output_index": 0,
            "coordinate_space": "output_physical_pixels",
            "region": {"left": 0, "top": 0, "width": 800, "height": 600},
            "window_ref": "hwnd:0x1234:pid:42",
        }
        live_manifest["provenance"]["origin"] = "window_capture"
        live_manifest["provenance"]["scope"] = "unpromoted_evaluation_only"
        unpromoted = self.detector.detect(
            live_manifest,
            frame,
            observation_id="hud:unpromoted-live",
        )
        self.assertEqual(
            unpromoted["provenance"]["scope"],
            "unpromoted_evaluation_only",
        )

        lab_manifest = copy.deepcopy(live_manifest)
        lab_manifest["decision_context"] = "lab_clone"
        lab_manifest["actor_binding"].update(
            {
                "instance_id": "instance:fixture:lab-clone",
                "actor_role": "lab_clone",
                "actor_id": "actor:predator:fixture-lab-clone",
                "decision_context": "lab_clone",
                "memory_namespace": "memory:lab:fixture-clone",
                "credential_alias": "credential:fixture:lab-clone",
            }
        )
        lab_manifest["provenance"]["scope"] = "lab_evaluation_only"
        lab = self.detector.detect(
            lab_manifest,
            frame,
            observation_id="hud:lab-live",
        )
        self.assertEqual(lab["provenance"]["scope"], "lab_evaluation_only")

        controlled_profile = copy.deepcopy(self.detector.profile)
        controlled_profile["calibration_state"] = "controlled_live_verified"
        controlled_detector = detector_module.CoordinateHudDetector(
            controlled_profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
        )
        still_unpromoted = controlled_detector.detect(
            live_manifest,
            frame,
            observation_id="hud:raw-controlled-live",
        )
        self.assertEqual(
            still_unpromoted["provenance"]["scope"],
            "unpromoted_evaluation_only",
        )
        self.assertNotEqual(
            still_unpromoted["provenance"]["profile_sha256"],
            unpromoted["provenance"]["profile_sha256"],
        )

    def test_stale_capture_is_degraded_without_position(self) -> None:
        manifest = capture_manifest()
        manifest["timing"]["frame_age_ms"] = 600.001
        observation = self.detector.detect(
            manifest,
            synthetic_hud(self.packet()),
            observation_id="hud:stale-frame",
        )
        self.assertEqual(observation["tracking_state"], "DEGRADED")
        self.assertEqual(observation["reason"], "capture_frame_stale")
        self.assertIsNone(observation["position"])
        self.assertFalse(observation["map_position_available"])

    def test_valid_unavailable_packet_is_degraded_not_invented(self) -> None:
        observation = self.detect(synthetic_hud(self.packet(available=False)))
        self.assertEqual(observation["tracking_state"], "DEGRADED")
        self.assertIsNone(observation["position"])
        self.assertFalse(observation["map_position_available"])

        contaminated = dict(observation)
        contaminated["map_position_available"] = True
        contaminated["position"] = {
            "coordinate_space": "normalized_current_zone_map",
            "x": 0.5,
            "y": 0.5,
            "continent_index": 1,
            "zone_index": 1,
        }
        with self.assertRaises(ContractValidationError):
            ContractValidator(
                ROOT / "contracts" / "coordinate-hud.schema.json"
            ).validate(contaminated)

    def test_corrupted_payload_and_missing_fiducials_fail_closed(self) -> None:
        corrupt = bytearray(self.packet())
        corrupt[4] ^= 0x80
        invalid = self.detect(synthetic_hud(bytes(corrupt)))
        self.assertEqual(invalid["tracking_state"], "INVALID")
        self.assertIsNone(invalid["position"])

        empty = np.zeros((600, 800, 4), dtype=np.uint8)
        empty[:, :, 3] = 255
        missing = self.detect(empty)
        self.assertEqual(missing["tracking_state"], "NOT_FOUND")
        self.assertIsNone(missing["position"])

    def test_large_solid_fiducials_win_over_earlier_ui_color_distractors(self) -> None:
        frame = synthetic_hud(self.packet(), scale=1.5, origin=(120, 90))
        colors = ((255, 255, 0), (0, 255, 0))
        for color_index, color in enumerate(colors):
            for index in range(20):
                x = 10 + (index * 12)
                y = 5 + (color_index * 10)
                frame[y : y + 2, x : x + 2, :3] = color
        observation = self.detect(frame)
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)

    def test_isolated_world_color_speckles_do_not_exhaust_component_budget(self) -> None:
        frame = synthetic_hud(self.packet(), origin=(16, 100))
        for index in range(180):
            x = 180 + (index % 30) * 7
            y = 4 + (index // 30) * 7
            frame[y, x, :3] = (0, 255, 255)

        observation = self.detect(frame)

        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)

    def test_oversized_world_color_component_is_discarded_not_treated_as_marker(self) -> None:
        frame = synthetic_hud(self.packet(), origin=(16, 16))
        frame[100:170, 220:300, :3] = (0, 255, 255)

        observation = self.detect(frame)

        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)

    def test_dense_adversarial_marker_fragments_still_exhaust_component_budget(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        component_budget = int(self.detector.profile["maximum_marker_components_per_color"])
        for index in range(component_budget + 1):
            x = 4 + (index % 64) * 6
            y = 4 + (index // 64) * 6
            frame[y : y + 2, x : x + 2, :3] = (0, 255, 255)

        with self.assertRaisesRegex(
            detector_module.CoordinateHudDetectionError,
            "component count budget",
        ):
            self.detect(frame)

    def test_isolated_adversarial_checkerboard_fails_closed_without_budget_error(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        frame[:210:2, :400:2, :3] = (0, 255, 255)
        started = time.perf_counter()

        observation = self.detect(frame)

        self.assertEqual(observation["tracking_state"], "NOT_FOUND")
        self.assertIsNone(observation["position"])
        self.assertLess(time.perf_counter() - started, 0.5)

    def test_adversarial_solid_color_region_is_rejected_within_budget(self) -> None:
        frame = np.zeros((600, 800, 4), dtype=np.uint8)
        frame[:, :, 3] = 255
        frame[:210, :400, :3] = (255, 255, 0)
        started = time.perf_counter()
        with self.assertRaisesRegex(
            detector_module.CoordinateHudDetectionError,
            "foreground pixel budget",
        ):
            self.detect(frame)
        self.assertLess(time.perf_counter() - started, 0.5)

    def test_build_mismatch_is_rejected(self) -> None:
        manifest = capture_manifest()
        manifest["client_build"] = "2.5.6.unknown"
        with self.assertRaisesRegex(detector_module.CoordinateHudDetectionError, "client_build"):
            self.detector.detect(
                manifest,
                synthetic_hud(self.packet()),
                observation_id="hud:mismatch",
            )

    def test_direct_detector_enforces_profile_frame_pixel_budget(self) -> None:
        profile = copy.deepcopy(self.detector.profile)
        profile["maximum_frame_pixels"] = 100
        detector = detector_module.CoordinateHudDetector(
            profile,
            ContractValidator(ROOT / "contracts" / "capture-frame.schema.json"),
            ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json"),
        )
        with self.assertRaisesRegex(
            detector_module.CoordinateHudDetectionError,
            "pixel budget",
        ):
            detector.detect(
                capture_manifest(),
                synthetic_hud(self.packet()),
                observation_id="hud:oversized-direct-frame",
            )


if __name__ == "__main__":
    unittest.main()
