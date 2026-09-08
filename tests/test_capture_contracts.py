from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from perfect_assassin.capture import (
    CaptureRegion,
    CaptureReplayProvider,
    CaptureReplayReader,
    InMemoryCaptureFrame,
)
from perfect_assassin.contract_validation import ContractValidationError, ContractValidator


ROOT = Path(__file__).resolve().parents[1]


def capture_manifest(*, persisted: bool = False, backend: str = "replay_fixture") -> dict:
    replay = backend == "replay_fixture"
    return {
        "record_type": "capture_frame_manifest",
        "schema_version": "2.0",
        "frame_id": "frame:fixture:0001",
        "session_id": "session:fixture",
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
        "backend": backend,
        "source": {
            "source_kind": "replay_fixture" if replay else "window_region",
            "device_index": None if replay else 0,
            "output_index": None if replay else 0,
            "coordinate_space": (
                "replay_fixture_pixels" if replay else "output_physical_pixels"
            ),
            "region": {"left": 100, "top": 50, "width": 1280, "height": 720},
            "window_ref": None if replay else "target:tbc_243_lab",
        },
        "image": {
            "width": 1280,
            "height": 720,
            "row_stride_bytes": 5120,
            "pixel_format": "BGRA8",
            "orientation": "top_down",
        },
        "timing": {
            "captured_at": "2026-08-22T19:00:00Z",
            "source_timestamp_s": 120.125,
            "monotonic_timestamp_s": 991.25,
            "frame_age_ms": 4.5,
        },
        "provenance": {
            "origin": "replay_fixture" if replay else "window_capture",
            "capability": "screen_capture",
            "scope": (
                "synthetic_fixture" if replay else "unpromoted_evaluation_only"
            ),
            "confidence": 1.0,
            "evidence_refs": ["fixture:capture:0001"],
        },
        "artifact": {
            "persisted": persisted,
            "media_type": "application/x-perfect-assassin-bgra8",
            "path": "data/replays/capture/frame-0001.bgra" if persisted else None,
            "sha256": "a" * 64 if persisted else None,
        },
        "privacy": {
            "content_class": "game_client_pixels",
            "redaction_state": "redacted" if persisted else "in_memory_only",
            "retention": "replay_fixture" if persisted else "none",
        },
        "execution_authority": False,
    }


class CaptureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ContractValidator(ROOT / "contracts" / "capture-frame.schema.json")

    def test_non_persisted_manifest_has_no_pixel_artifact(self) -> None:
        value = capture_manifest()
        self.validator.validate(value)
        self.assertIsNone(value["artifact"]["path"])
        self.assertFalse(value["execution_authority"])

    def test_persisted_frame_requires_path_hash_and_redaction_state(self) -> None:
        value = capture_manifest(persisted=True)
        self.validator.validate(value)

        without_hash = copy.deepcopy(value)
        without_hash["artifact"]["sha256"] = None
        with self.assertRaises(ContractValidationError):
            self.validator.validate(without_hash)

        unclassified = copy.deepcopy(value)
        unclassified["privacy"]["redaction_state"] = "in_memory_only"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(unclassified)

    def test_live_backend_requires_window_capture_provenance(self) -> None:
        value = capture_manifest(backend="dxgi_desktop_duplication")
        self.validator.validate(value)
        self.assertEqual(
            value["provenance"]["scope"],
            "unpromoted_evaluation_only",
        )
        self.assertEqual(
            value["actor_binding"]["binding_assurance"]["state"],
            "configured_expected_only",
        )
        self.assertNotIn("character_name", value["actor_binding"])

        wrong_origin = copy.deepcopy(value)
        wrong_origin["provenance"]["origin"] = "replay_fixture"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(wrong_origin)

        falsely_promoted = capture_manifest(backend="dxgi_desktop_duplication")
        falsely_promoted["provenance"]["scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(falsely_promoted)

    def test_window_only_background_backend_remains_read_only(self) -> None:
        value = capture_manifest(backend="win32_print_window")
        self.validator.validate(value)
        self.assertEqual(value["source"]["source_kind"], "window_region")
        self.assertEqual(value["provenance"]["origin"], "window_capture")
        self.assertFalse(value["execution_authority"])

    def test_capture_manifest_cannot_grant_execution(self) -> None:
        value = capture_manifest()
        value["execution_authority"] = True
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_capture_manifest_requires_exact_authorization_snapshot_hash(self) -> None:
        missing = capture_manifest()
        del missing["authorization_sha256"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(missing)

        malformed = capture_manifest()
        malformed["authorization_sha256"] = "a" * 64
        with self.assertRaises(ContractValidationError):
            self.validator.validate(malformed)

    def test_contract_rejects_non_finite_capture_numbers(self) -> None:
        paths = (
            ("timing", "source_timestamp_s"),
            ("timing", "monotonic_timestamp_s"),
            ("timing", "frame_age_ms"),
            ("provenance", "confidence"),
        )
        for path in paths:
            for invalid in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(path=path, invalid=invalid):
                    value = capture_manifest()
                    value[path[0]][path[1]] = invalid
                    with self.assertRaisesRegex(
                        ContractValidationError,
                        "non-finite numbers",
                    ):
                        self.validator.validate(value)

    def test_capture_manifest_cannot_relabel_lab_actor_as_champion(self) -> None:
        value = capture_manifest(backend="dxgi_desktop_duplication")
        value["actor_binding"].update(
            {
                "actor_role": "lab_clone",
                "decision_context": "lab_clone",
                "memory_namespace": "memory:lab:fixture-clone",
            }
        )
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

        missing_binding = capture_manifest()
        del missing_binding["actor_binding"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(missing_binding)

    def test_capture_region_requires_an_explicit_coordinate_space(self) -> None:
        value = capture_manifest()
        del value["source"]["coordinate_space"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(value)

    def test_replay_reader_and_provider_are_deterministic(self) -> None:
        records = [capture_manifest(), capture_manifest()]
        records[1]["frame_id"] = "frame:fixture:0002"
        records[1]["timing"]["monotonic_timestamp_s"] = 991.30
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            reader = CaptureReplayReader(path, self.validator)
            self.assertEqual(reader.deterministic_hash(), reader.deterministic_hash())

            provider = CaptureReplayProvider(reader.records(), self.validator)
            first = provider.next_frame()
            second = provider.next_frame()
            self.assertEqual(first.manifest["frame_id"], "frame:fixture:0001")
            self.assertEqual(second.manifest["frame_id"], "frame:fixture:0002")
            self.assertIsNone(first.pixels)
            self.assertIsNone(provider.next_frame())

            provider.reset()
            self.assertEqual(provider.next_frame().manifest["frame_id"], "frame:fixture:0001")

    def test_replay_provider_rejects_unvalidated_execution_authority(self) -> None:
        value = capture_manifest()
        value["execution_authority"] = True
        with self.assertRaises(ContractValidationError):
            CaptureReplayProvider([value], self.validator)

    def test_capture_region_translates_to_dxcam_edges(self) -> None:
        region = CaptureRegion(left=100, top=50, width=1280, height=720)
        self.assertEqual(region.dxcam_region, (100, 50, 1380, 770))
        with self.assertRaises(ValueError):
            CaptureRegion(left=0, top=0, width=0, height=720)

    def test_live_in_memory_factory_emits_a_valid_manifest(self) -> None:
        frame = InMemoryCaptureFrame(
            frame_id="capture:live:0001",
            session_id="session:live",
            target_profile="tbc_243_lab",
            instance_id="instance:fixture:champion",
            actor_role="champion_journey",
            actor_id="actor:predator:fixture-champion",
            decision_context="champion",
            memory_namespace="memory:champion:fixture",
            expected_character_name="Predator",
            credential_alias="credential:fixture:champion",
            binding_assurance_state="configured_expected_only",
            binding_assurance_evidence_refs=(
                "authorization:fixture:actor-expected",
            ),
            authorization_sha256="A" * 64,
            client_build="2.4.3.8606",
            build_signature="wow-tbc-2.4.3.8606-enGB:sha256:fixture",
            provider_id="dxcam_windows_capture",
            provider_version="0.1.0",
            backend="dxgi_desktop_duplication",
            device_index=0,
            output_index=0,
            region=CaptureRegion(100, 50, 1280, 720),
            window_ref="hwnd:0x1234:pid:42",
            width=1280,
            height=720,
            row_stride_bytes=5120,
            captured_at="2026-08-22T19:00:00Z",
            monotonic_timestamp_s=10.0,
            source_timestamp_s=None,
            frame_age_ms=1.0,
            evidence_refs=("hwnd:0x1234:pid:42",),
        )
        value = frame.to_manifest()
        self.validator.validate(value)
        self.assertEqual(value["authorization_sha256"], "A" * 64)
        self.assertFalse(value["artifact"]["persisted"])
        self.assertFalse(value["execution_authority"])

        for authorization_sha256 in (None, "A" * 63, "a" * 64):
            with (
                self.subTest(authorization_sha256=authorization_sha256),
                self.assertRaises(ValueError),
            ):
                replace(frame, authorization_sha256=authorization_sha256)

        for field in (
            "monotonic_timestamp_s",
            "source_timestamp_s",
            "frame_age_ms",
            "confidence",
        ):
            for invalid in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(
                    ValueError,
                    "finite",
                ):
                    replace(frame, **{field: invalid})


if __name__ == "__main__":
    unittest.main()
