from __future__ import annotations

import copy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from perfect_assassin.adapter.coordinate_hud import (
    CoordinateHudProtocolError,
    encode_packet,
    packet_to_bits,
    validate_sequence_summary_semantics,
)
from perfect_assassin.capture import CapturePacket
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-capture"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

detector_module = importlib.import_module("coordinate_hud_detector")
probe_module = importlib.import_module("probe_coordinate_hud")


def capture_manifest(
    width: int = 800,
    height: int = 600,
    *,
    frame_id: str = "frame:hud-probe:fixture:0001",
    monotonic_timestamp_s: float = 20.0,
    session_id: str = "session:hud-probe-fixture",
    build_signature: str = "wow-tbc-2.4.3.8606-enGB",
) -> dict:
    return {
        "record_type": "capture_frame_manifest",
        "schema_version": "2.0",
        "frame_id": frame_id,
        "session_id": session_id,
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
        "build_signature": build_signature,
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
            "monotonic_timestamp_s": monotonic_timestamp_s,
            "frame_age_ms": 2.0,
        },
        "provenance": {
            "origin": "replay_fixture",
            "capability": "screen_capture",
            "scope": "synthetic_fixture",
            "confidence": 1.0,
            "evidence_refs": ["fixture:hud-probe:synthetic:0001"],
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


def synthetic_hud(packet: bytes) -> np.ndarray:
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
            base_x + 14 + column * 5,
            base_y + 34 + row * 5,
            4,
            4,
            (value, value, value),
        )
    return frame


def position_packet(
    *,
    sequence: int = 23,
    available: bool = True,
    zone_index: int = 14,
) -> bytes:
    return encode_packet(
        sequence=sequence,
        position_available=available,
        map_context_ready=available,
        world_map_visible=False,
        x=0.42125 if available else None,
        y=0.61875 if available else None,
        continent_index=1,
        zone_index=zone_index,
    )


class OnePacketProvider:
    def __init__(self, packet: CapturePacket | None) -> None:
        self.packet = packet
        self.calls = 0

    def next_frame(self) -> CapturePacket | None:
        self.calls += 1
        packet, self.packet = self.packet, None
        return packet

    def reset(self) -> None:
        self.calls = 0


class PacketSequenceProvider:
    def __init__(self, packets: list[CapturePacket]) -> None:
        self.packets = iter(packets)
        self.calls = 0

    def next_frame(self) -> CapturePacket | None:
        self.calls += 1
        return next(self.packets, None)

    def reset(self) -> None:
        self.calls = 0


class SequenceClock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def make_probe(*, clock=None, process_identity_verifier=None):
    profile, profile_sha256 = probe_module.load_pinned_profile(
        ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
    )
    capture_validator = ContractValidator(ROOT / "contracts" / "capture-frame.schema.json")
    observation_validator = ContractValidator(ROOT / "contracts" / "coordinate-hud.schema.json")
    detector = detector_module.CoordinateHudDetector(
        profile,
        capture_validator,
        observation_validator,
    )
    kwargs = {}
    if clock is not None:
        kwargs["monotonic"] = clock
    if process_identity_verifier is not None:
        kwargs["process_identity_verifier"] = process_identity_verifier
    return probe_module.CoordinateHudOneShotProbe(
        profile,
        profile_sha256,
        capture_validator,
        observation_validator,
        detector,
        **kwargs,
    )


def make_sequence_probe(*, clock=None):
    return probe_module.CoordinateHudSequenceProbe(
        make_probe(),
        ContractValidator(
            ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
        ),
        monotonic=clock or (lambda: 0.0),
        sleep=lambda _seconds: None,
    )


def sequence_provider(
    sequences: list[int],
    timestamps: list[float],
    *,
    available: bool = True,
    session_ids: list[str] | None = None,
    memory_namespaces: list[str] | None = None,
    authorization_hashes: list[str] | None = None,
    zone_indices: list[int] | None = None,
) -> tuple[PacketSequenceProvider, list[memoryview]]:
    packets: list[CapturePacket] = []
    pixel_views: list[memoryview] = []
    for index, (sequence, timestamp) in enumerate(zip(sequences, timestamps, strict=True)):
        frame = synthetic_hud(
            position_packet(
                sequence=sequence,
                available=available,
                zone_index=(zone_indices or [14] * len(sequences))[index],
            )
        )
        pixel_view = memoryview(frame)
        pixel_views.append(pixel_view)
        manifest = capture_manifest(
            frame_id=f"frame:hud-sequence:{index:04d}",
            monotonic_timestamp_s=timestamp,
            session_id=(
                session_ids or ["session:hud-probe-fixture"] * len(sequences)
            )[index],
        )
        if memory_namespaces is not None:
            manifest["actor_binding"]["memory_namespace"] = memory_namespaces[index]
        if authorization_hashes is not None:
            manifest["authorization_sha256"] = authorization_hashes[index]
        packets.append(
            CapturePacket(
                manifest=manifest,
                pixels=pixel_view,
            )
        )
    return PacketSequenceProvider(packets), pixel_views


class CoordinateHudProbeTests(unittest.TestCase):
    def test_pinned_profile_is_schema_valid_and_hash_bound(self) -> None:
        profile_path = ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        profile, digest = probe_module.load_pinned_profile(profile_path)
        self.assertEqual(digest, probe_module.SUPPORTED_PROFILE_SHA256)
        self.assertEqual(profile["target_profile"], "tbc_243_lab")
        self.assertFalse(profile["execution_authority"])

        with tempfile.TemporaryDirectory() as directory:
            modified = Path(directory) / "profile.json"
            changed_profile = copy.deepcopy(profile)
            changed_profile["detector_deadline_ms"] = 501
            modified.write_text(json.dumps(changed_profile), encoding="utf-8")
            with self.assertRaisesRegex(
                probe_module.CoordinateHudProbeError, "SHA-256"
            ):
                probe_module.load_pinned_profile(modified)

    def test_one_shot_owns_profile_and_binds_detector_to_same_hash(self) -> None:
        caller_profile, digest = probe_module.load_pinned_profile(
            ROOT / "config" / "pose" / "coordinate-hud-tbc243-v1.json"
        )
        capture_validator = ContractValidator(
            ROOT / "contracts" / "capture-frame.schema.json"
        )
        observation_validator = ContractValidator(
            ROOT / "contracts" / "coordinate-hud.schema.json"
        )
        detector = detector_module.CoordinateHudDetector(
            caller_profile,
            capture_validator,
            observation_validator,
        )
        one_shot = probe_module.CoordinateHudOneShotProbe(
            caller_profile,
            digest,
            capture_validator,
            observation_validator,
            detector,
            monotonic=SequenceClock([1.0, 1.0]),
        )
        caller_profile["freshness_limit_ms"] = 1
        caller_profile["calibration_state"] = "controlled_live_verified"
        self.assertEqual(one_shot.profile["freshness_limit_ms"], 600)
        self.assertEqual(one_shot.profile_sha256, digest)
        self.assertEqual(detector.profile_sha256, digest)

        frame = synthetic_hud(position_packet())
        observation = one_shot.observe_once(
            OnePacketProvider(
                CapturePacket(
                    manifest=capture_manifest(),
                    pixels=memoryview(frame),
                )
            ),
            observation_id="hud-probe:owned-profile",
        )
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertEqual(
            observation["provenance"]["profile_sha256"],
            digest,
        )

        mismatched_profile = copy.deepcopy(one_shot.profile)
        mismatched_profile["freshness_limit_ms"] = 500
        with self.assertRaisesRegex(
            probe_module.CoordinateHudProbeError,
            "pinned SHA-256",
        ):
            probe_module.CoordinateHudOneShotProbe(
                mismatched_profile,
                digest,
                capture_validator,
                observation_validator,
                detector,
            )

    def test_one_shot_replay_packet_decodes_and_releases_pixels(self) -> None:
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        provider = OnePacketProvider(
            CapturePacket(manifest=capture_manifest(), pixels=pixel_view)
        )
        observation = make_probe().observe_once(
            provider,
            observation_id="hud-probe:fixture:0001",
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertEqual(observation["schema_version"], "2.0")
        self.assertEqual(
            observation["actor_binding"],
            capture_manifest()["actor_binding"],
        )
        self.assertEqual(observation["decision_context"], "champion")
        self.assertEqual(observation["provenance"]["scope"], "synthetic_fixture")
        self.assertEqual(observation["timing"]["monotonic_timestamp_s"], 20.0)
        self.assertAlmostEqual(observation["position"]["x"], 0.42125, delta=1 / 65535)
        self.assertTrue(
            any(
                reference.startswith("profile:coordinate_hud_tbc243_v1:sha256:")
                for reference in observation["provenance"]["evidence_refs"]
            )
        )
        self.assertFalse(observation["execution_authority"])
        with self.assertRaises(ValueError):
            _ = pixel_view.nbytes

    def test_one_shot_rejects_non_finite_replay_timing_and_releases_pixels(self) -> None:
        for field in ("source_timestamp_s", "monotonic_timestamp_s", "frame_age_ms"):
            for invalid in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, invalid=invalid):
                    manifest = capture_manifest()
                    manifest["timing"][field] = invalid
                    frame = synthetic_hud(position_packet())
                    pixel_view = memoryview(frame)
                    with self.assertRaisesRegex(
                        ContractValidationError,
                        "non-finite numbers",
                    ):
                        make_probe().observe_once(
                            OnePacketProvider(
                                CapturePacket(manifest=manifest, pixels=pixel_view)
                            ),
                            observation_id="hud-probe:non-finite-replay",
                        )
                    with self.assertRaises(ValueError):
                        _ = pixel_view.nbytes

    def test_one_shot_revalidates_valid_observation_semantics_after_detection(self) -> None:
        probe = make_probe(clock=SequenceClock([1.0, 1.0]))
        detector = probe.detector

        class CorruptingDetector:
            def detect(self, *args, **kwargs):
                observation = detector.detect(*args, **kwargs)
                observation["timing"]["expires_monotonic_s"] += 0.1
                return observation

        probe.detector = CorruptingDetector()
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        with self.assertRaisesRegex(
            CoordinateHudProtocolError,
            "expiry is inconsistent",
        ):
            probe.observe_once(
                OnePacketProvider(
                    CapturePacket(manifest=capture_manifest(), pixels=pixel_view)
                ),
                observation_id="hud-probe:semantic-recheck",
            )
        with self.assertRaises(ValueError):
            _ = pixel_view.nbytes

    def test_live_process_identity_is_rechecked_before_and_after_each_frame(self) -> None:
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        provider = OnePacketProvider(
            CapturePacket(manifest=capture_manifest(), pixels=pixel_view)
        )
        checks: list[str] = []
        observation = make_probe(
            process_identity_verifier=lambda: checks.append("verified")
        ).observe_once(provider, observation_id="hud-probe:identity:0001")
        self.assertEqual(observation["tracking_state"], "VALID")
        self.assertEqual(checks, ["verified", "verified"])

    def test_post_capture_identity_failure_releases_pixels_and_fails_closed(self) -> None:
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        provider = OnePacketProvider(
            CapturePacket(manifest=capture_manifest(), pixels=pixel_view)
        )
        checks = 0

        def verify() -> None:
            nonlocal checks
            checks += 1
            if checks == 2:
                raise RuntimeError("running process identity changed")

        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            make_probe(process_identity_verifier=verify).observe_once(
                provider,
                observation_id="hud-probe:identity-change",
            )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(checks, 2)
        with self.assertRaises(ValueError):
            _ = pixel_view.nbytes

    def test_missing_pixels_and_live_signature_without_hash_fail_closed(self) -> None:
        without_pixels = OnePacketProvider(
            CapturePacket(manifest=capture_manifest(), pixels=None)
        )
        with self.assertRaisesRegex(
            probe_module.CoordinateHudProbeError, "no in-memory BGRA"
        ):
            make_probe().observe_once(
                without_pixels,
                observation_id="hud-probe:no-pixels",
            )

        live_manifest = copy.deepcopy(capture_manifest())
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
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        with self.assertRaisesRegex(
            probe_module.CoordinateHudProbeError, "verified executable hash"
        ):
            make_probe(process_identity_verifier=lambda: None).observe_once(
                OnePacketProvider(CapturePacket(live_manifest, pixel_view)),
                observation_id="hud-probe:unbound-live",
            )
        with self.assertRaises(ValueError):
            _ = pixel_view.nbytes

    def test_live_identity_evidence_survives_observation_and_summary(self) -> None:
        manifests = []
        pixel_views = []
        for index, sequence in enumerate((10, 11)):
            manifest = capture_manifest(
                frame_id=f"frame:hud-live-evidence:{index}",
                monotonic_timestamp_s=20.0 + index * 0.1,
                build_signature=(
                    "wow-tbc-2.4.3.8606-enGB:sha256:"
                    + "A" * 64
                ),
            )
            manifest["backend"] = "dxgi_desktop_duplication"
            manifest["source"] = {
                "source_kind": "window_region",
                "device_index": 0,
                "output_index": 0,
                "coordinate_space": "output_physical_pixels",
                "region": {"left": 0, "top": 0, "width": 800, "height": 600},
                "window_ref": "hwnd:0x1234:pid:42",
            }
            manifest["provenance"] = {
                "origin": "window_capture",
                "capability": "screen_capture",
                "scope": "unpromoted_evaluation_only",
                "confidence": 1.0,
                "evidence_refs": [
                    "hwnd:0x1234:pid:42",
                    "authorization:execution:tbc243-lab:bounded-fixed-ui",
                ],
            }
            frame = synthetic_hud(position_packet(sequence=sequence))
            pixel_view = memoryview(frame)
            pixel_views.append(pixel_view)
            manifests.append(CapturePacket(manifest=manifest, pixels=pixel_view))

        one_shot = make_probe(
            process_identity_verifier=lambda: None,
            clock=SequenceClock([20.001, 20.002, 20.101, 20.102]),
        )
        sequence_probe = probe_module.CoordinateHudSequenceProbe(
            one_shot,
            ContractValidator(
                ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
            ),
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: None,
        )
        summary = sequence_probe.observe_sequence(
            PacketSequenceProvider(manifests),
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:identity-evidence",
        )
        self.assertIn(
            "hwnd:0x1234:pid:42",
            summary["provenance"]["evidence_refs"],
        )
        self.assertIn(
            "authorization:execution:tbc243-lab:bounded-fixed-ui",
            summary["provenance"]["evidence_refs"],
        )

    def test_detector_deadline_discards_an_otherwise_valid_position(self) -> None:
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        with self.assertRaisesRegex(
            probe_module.CoordinateHudProbeError, "exceeded the pinned deadline"
        ):
            make_probe(clock=SequenceClock([1.0, 1.501])).observe_once(
                OnePacketProvider(
                    CapturePacket(manifest=capture_manifest(), pixels=pixel_view)
                ),
                observation_id="hud-probe:slow-detector",
            )
        with self.assertRaises(ValueError):
            _ = pixel_view.nbytes

    def test_frame_that_expires_during_detection_is_downgraded(self) -> None:
        manifest = capture_manifest()
        manifest["timing"]["frame_age_ms"] = 599.0
        frame = synthetic_hud(position_packet())
        pixel_view = memoryview(frame)
        observation = make_probe(clock=SequenceClock([1.0, 1.4])).observe_once(
            OnePacketProvider(CapturePacket(manifest=manifest, pixels=pixel_view)),
            observation_id="hud-probe:expires-during-detection",
        )
        self.assertEqual(observation["tracking_state"], "DEGRADED")
        self.assertEqual(observation["reason"], "capture_frame_stale_at_observation")
        self.assertIsNone(observation["position"])
        self.assertAlmostEqual(
            observation["timing"]["age_at_observation_ms"],
            999.0,
        )

    def test_sequence_gate_accepts_duplicates_wrap_and_fresh_advances(self) -> None:
        provider, pixel_views = sequence_provider(
            [254, 254, 255, 0],
            [20.0, 20.1, 20.2, 20.3],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=4,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:pass",
        )
        ContractValidator(
            ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
        ).validate(summary)
        self.assertEqual(summary["gate_state"], "PASS")
        self.assertEqual(summary["schema_version"], "2.0")
        self.assertEqual(
            summary["actor_binding"],
            capture_manifest()["actor_binding"],
        )
        self.assertEqual(
            summary["actor_binding"]["binding_assurance"]["state"],
            "configured_expected_only",
        )
        self.assertEqual(summary["authorization_sha256"], "A" * 64)
        self.assertEqual(summary["decision_context"], "champion")
        self.assertEqual(summary["provenance"]["scope"], "synthetic_fixture")
        self.assertEqual(summary["timing"]["first_monotonic_timestamp_s"], 20.0)
        self.assertEqual(summary["timing"]["last_monotonic_timestamp_s"], 20.3)
        self.assertEqual(summary["timing"]["freshness_limit_ms"], 600)
        self.assertEqual(summary["reason"], "fresh_sequence_verified")
        self.assertEqual(summary["sequence"]["first"], 254)
        self.assertEqual(summary["sequence"]["last"], 0)
        self.assertEqual(summary["sequence"]["advances"], 2)
        self.assertEqual(summary["sequence"]["duplicates"], 1)
        self.assertEqual(provider.calls, 4)
        self.assertFalse(summary["artifact"]["persisted"])
        self.assertFalse(summary["privacy"]["pixels_in_output"])
        self.assertFalse(summary["execution_authority"])
        self.assertNotIn("packet_hex", json.dumps(summary))
        for pixel_view in pixel_views:
            with self.assertRaises(ValueError):
                _ = pixel_view.nbytes

    def test_sequence_summary_deeply_owns_actor_binding(self) -> None:
        delegate = make_probe()

        class RecordingOneShot:
            profile = delegate.profile
            observation_validator = delegate.observation_validator

            def __init__(self) -> None:
                self.observations = []

            def observe_sample(self, *args, **kwargs):
                sample = delegate.observe_sample(*args, **kwargs)
                self.observations.append(sample.observation)
                return sample

        one_shot = RecordingOneShot()
        sequence_probe = probe_module.CoordinateHudSequenceProbe(
            one_shot,
            ContractValidator(
                ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
            ),
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: None,
        )
        provider, _pixel_views = sequence_provider([10, 11], [20.0, 20.1])
        summary = sequence_probe.observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:actor-deep-copy",
        )
        original_refs = ["authorization:fixture:actor-expected"]
        summary["actor_binding"]["binding_assurance"]["evidence_refs"].append(
            "authorization:summary-mutated"
        )
        self.assertEqual(
            one_shot.observations[0]["actor_binding"]["binding_assurance"][
                "evidence_refs"
            ],
            original_refs,
        )

        one_shot.observations[0]["actor_binding"]["binding_assurance"][
            "evidence_refs"
        ].append("authorization:observation-mutated")
        self.assertNotIn(
            "authorization:observation-mutated",
            summary["actor_binding"]["binding_assurance"]["evidence_refs"],
        )

    def test_sequence_revalidates_valid_observation_semantics(self) -> None:
        probe = make_probe()
        manifest = capture_manifest(monotonic_timestamp_s=20.0)
        observation = probe.detector.detect(
            manifest,
            synthetic_hud(position_packet(sequence=10)),
            observation_id="hud-sequence:corrupt-semantic:01",
        )
        observation["timing"]["expires_monotonic_s"] += 0.1

        class BypassOneShot:
            profile = probe.profile
            observation_validator = probe.observation_validator

            def observe_sample(self, *_args, **_kwargs):
                return probe_module.DecodedHudSample(
                    observation=observation,
                    captured_monotonic_s=20.0,
                )

        sequence_probe = probe_module.CoordinateHudSequenceProbe(
            BypassOneShot(),
            ContractValidator(
                ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
            ),
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: None,
        )
        with self.assertRaisesRegex(
            CoordinateHudProtocolError,
            "expiry is inconsistent",
        ):
            sequence_probe.observe_sequence(
                PacketSequenceProvider([]),
                samples=2,
                target_fps=10.0,
                observation_id_prefix="hud-sequence:semantic-recheck",
            )

    def test_sequence_rejects_non_finite_clock_values(self) -> None:
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                provider, _pixel_views = sequence_provider([10, 11], [20.0, 20.1])
                with self.assertRaisesRegex(
                    probe_module.CoordinateHudProbeError,
                    "finite and non-negative",
                ):
                    make_sequence_probe(clock=lambda: invalid).observe_sequence(
                        provider,
                        samples=2,
                        target_fps=10.0,
                        observation_id_prefix="hud-sequence:non-finite-clock",
                    )

    def test_sequence_rejects_sample_that_exceeds_wall_deadline(self) -> None:
        provider, _pixel_views = sequence_provider([10, 11], [20.0, 20.1])
        with self.assertRaisesRegex(
            probe_module.CoordinateHudProbeError,
            "sample exceeded its monotonic wall deadline",
        ):
            make_sequence_probe(
                clock=SequenceClock([0.0, 1.001]),
            ).observe_sequence(
                provider,
                samples=2,
                target_fps=10.0,
                observation_id_prefix="hud-sequence:sample-wall-timeout",
            )

    def test_sequence_summary_contract_rejects_stale_or_contradictory_gate(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:contract-semantics",
        )
        validator = ContractValidator(
            ROOT / "contracts" / "coordinate-hud-sequence-summary.schema.json"
        )
        validator.validate(summary)
        validate_sequence_summary_semantics(summary)

        stale_pass = copy.deepcopy(summary)
        stale_pass["timing"]["last_observation_age_at_summary_ms"] = 999.0
        with self.assertRaises(ContractValidationError):
            validator.validate(stale_pass)

        stale_maximum = copy.deepcopy(summary)
        stale_maximum["timing"]["maximum_frame_age_ms"] = 999999.0
        with self.assertRaises(ContractValidationError):
            validator.validate(stale_maximum)
        with self.assertRaisesRegex(
            CoordinateHudProtocolError,
            "contradictory counts, flags or reason",
        ):
            validate_sequence_summary_semantics(stale_maximum)

        contradictory_failure = copy.deepcopy(summary)
        contradictory_failure["gate_state"] = "FAIL"
        with self.assertRaises(ContractValidationError):
            validator.validate(contradictory_failure)

        semantic_cases = []

        observed_over_requested = copy.deepcopy(summary)
        observed_over_requested["observed_samples"] = 3
        observed_over_requested["valid_observations"] = 3
        semantic_cases.append(("observed-over-requested", observed_over_requested))

        valid_over_observed = copy.deepcopy(summary)
        valid_over_observed["gate_state"] = "FAIL"
        valid_over_observed["reason"] = "sequence_not_advanced"
        valid_over_observed["valid_observations"] = 3
        semantic_cases.append(("valid-over-observed", valid_over_observed))

        impossible_transitions = copy.deepcopy(summary)
        impossible_transitions["sequence"]["advances"] = 2
        semantic_cases.append(("impossible-transitions", impossible_transitions))

        backwards_clock = copy.deepcopy(summary)
        backwards_clock["timing"]["first_monotonic_timestamp_s"] = 21.0
        semantic_cases.append(("backwards-clock", backwards_clock))

        wrong_duration = copy.deepcopy(summary)
        wrong_duration["timing"]["duration_ms"] += 1.0
        semantic_cases.append(("wrong-duration", wrong_duration))

        contradictory_all_valid = copy.deepcopy(summary)
        contradictory_all_valid["gate_state"] = "FAIL"
        contradictory_all_valid["reason"] = "sequence_not_advanced"
        contradictory_all_valid["valid_observations"] = 0
        semantic_cases.append(("all-valid-with-zero-valid", contradictory_all_valid))

        incomplete_pass = copy.deepcopy(summary)
        incomplete_pass["observed_samples"] = 1
        incomplete_pass["valid_observations"] = 1
        semantic_cases.append(("incomplete-pass", incomplete_pass))

        for label, candidate in semantic_cases:
            with self.subTest(case=label):
                validator.validate(candidate)
                with self.assertRaises(CoordinateHudProtocolError):
                    validate_sequence_summary_semantics(candidate)

    def test_sequence_gate_fails_on_stale_or_never_advanced_sequence(self) -> None:
        cases = (
            ([7, 7, 7], [20.0, 20.3, 20.601], "sequence_stale"),
            ([7, 7], [20.0, 20.1], "sequence_not_advanced"),
        )
        for sequences, timestamps, expected_reason in cases:
            with self.subTest(reason=expected_reason):
                provider, _pixel_views = sequence_provider(sequences, timestamps)
                summary = make_sequence_probe().observe_sequence(
                    provider,
                    samples=len(sequences),
                    target_fps=10.0,
                    observation_id_prefix=f"hud-sequence:{expected_reason}",
                )
                self.assertEqual(summary["gate_state"], "FAIL")
                self.assertEqual(summary["reason"], expected_reason)
                self.assertFalse(summary["execution_authority"])

    def test_sequence_gate_rejects_reverse_large_jump_and_source_change(self) -> None:
        cases = (
            ([10, 9], [20.0, 20.1], None, "sequence_reverse"),
            ([10, 30], [20.0, 20.1], None, "sequence_jump_too_large"),
            (
                [10, 11],
                [20.0, 20.1],
                ["session:one", "session:two"],
                "source_binding_changed",
            ),
        )
        for sequences, timestamps, session_ids, expected_reason in cases:
            with self.subTest(reason=expected_reason):
                provider, _pixel_views = sequence_provider(
                    sequences,
                    timestamps,
                    session_ids=session_ids,
                )
                summary = make_sequence_probe().observe_sequence(
                    provider,
                    samples=2,
                    target_fps=10.0,
                    observation_id_prefix=f"hud-sequence:{expected_reason}",
                )
                self.assertEqual(summary["gate_state"], "FAIL")
                self.assertEqual(summary["reason"], expected_reason)

    def test_early_sequence_failure_reports_all_observed_valid_without_claiming_pass(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 9, 11],
            [20.0, 20.1, 20.2],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=3,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:early-reverse",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "sequence_reverse")
        self.assertEqual(summary["observed_samples"], 2)
        self.assertEqual(summary["valid_observations"], 2)
        self.assertTrue(summary["all_observations_valid"])
        validate_sequence_summary_semantics(summary)

    def test_sequence_gate_rejects_map_context_change(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
            zone_indices=[14, 15],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:map-context-change",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "map_context_changed")

    def test_sequence_gate_rejects_actor_memory_namespace_change(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
            memory_namespaces=[
                "memory:champion:fixture",
                "memory:champion:other-instance",
            ],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:actor-binding-change",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "source_binding_changed")

    def test_sequence_gate_rejects_authorization_snapshot_change(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
            authorization_hashes=["A" * 64, "B" * 64],
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:authorization-change",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "source_binding_changed")

    def test_sequence_gate_requires_every_observation_to_be_valid(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
            available=False,
        )
        summary = make_sequence_probe().observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:unavailable",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "observation_not_valid")
        self.assertFalse(summary["all_observations_valid"])
        self.assertEqual(summary["valid_observations"], 0)

    def test_sequence_gate_rechecks_last_observation_at_summary_time(self) -> None:
        provider, _pixel_views = sequence_provider(
            [10, 11],
            [20.0, 20.1],
        )
        summary = make_sequence_probe(
            clock=SequenceClock([20.0, 20.1, 20.2, 20.701])
        ).observe_sequence(
            provider,
            samples=2,
            target_fps=10.0,
            observation_id_prefix="hud-sequence:expired-at-summary",
        )
        self.assertEqual(summary["gate_state"], "FAIL")
        self.assertEqual(summary["reason"], "last_observation_expired")

    def test_cli_bounds_and_default_one_shot_mode(self) -> None:
        parser = probe_module.build_parser()
        self.assertEqual(parser.get_default("samples"), 1)
        self.assertEqual(parser.get_default("target_fps"), 10.0)
        for invalid in (0, 31):
            with self.subTest(samples=invalid):
                with self.assertRaises(probe_module.CoordinateHudProbeError):
                    probe_module.validate_probe_bounds(invalid, 10.0)
        for invalid in (0.5, 31.0, float("nan")):
            with self.subTest(target_fps=invalid):
                with self.assertRaises(probe_module.CoordinateHudProbeError):
                    probe_module.validate_probe_bounds(10, invalid)

    def test_probe_source_has_no_pixel_persistence_path(self) -> None:
        source = (INTEGRATION / "probe_coordinate_hud.py").read_text(encoding="utf-8")
        for forbidden in (
            "write_bytes(",
            "write_text(",
            "np.save(",
            "imwrite(",
            "Image.save(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("buffer_capacity=1", source)
        self.assertIn("load_capture_target_identity", source)
        self.assertIn("verify_capture_process_identity", source)
        self.assertIn("DxcamWindowCaptureProvider", source)
        self.assertEqual(source.count("provider.open()"), 1)


if __name__ == "__main__":
    unittest.main()
