from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.semantic_live_gate import (
    SemanticLiveGateError,
    SemanticLiveGateIdentity,
    build_semantic_live_gate_record,
    semantic_live_gate_open,
)


ROOT = Path(__file__).parents[1]


class SemanticLiveGateTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[SemanticLiveGateIdentity, Path]:
        profile = root / "profile.json"
        profile.write_text("{}", encoding="utf-8")
        worker = root / "worker.exe"
        worker.write_bytes(b"worker-v1")
        result = root / "validation.json"
        result.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        identity = SemanticLiveGateIdentity(
            world_pack_profile=str(profile.resolve()),
            world_pack_profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
            world_pack_profile_id="worldpack-runtime:test:v1",
            world_pack_id="wow.test.pack-v1",
            world_pack_content_sha256="a" * 64,
            target_profile="test_lab",
            client_version="2.5.5",
            client_build="2.5.5.12345",
            nav_profile_id="test-nav-v1",
            worker=str(worker.resolve()),
            worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
        )
        return identity, result

    def test_gate_contract_binds_complete_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity, result = self._fixture(Path(directory))
            record = build_semantic_live_gate_record(
                identity,
                validation_result=result,
                status="PASS",
                live_authority_enabled=True,
            )
            ContractValidator(
                ROOT / "contracts" / "semantic-movement-live-gate.schema.json"
            ).validate(record)
            self.assertTrue(semantic_live_gate_open(record, expected=identity))

    def test_gate_rejects_different_client_build_or_pack_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity, result = self._fixture(Path(directory))
            record = build_semantic_live_gate_record(
                identity,
                validation_result=result,
                status="PASS",
                live_authority_enabled=True,
            )
            for field, replacement in (
                ("client_build", "2.4.3.8606"),
                ("world_pack_content_sha256", "b" * 64),
            ):
                altered = {**record, field: replacement}
                self.assertFalse(semantic_live_gate_open(altered, expected=identity))

    def test_gate_rejects_modified_validation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity, result = self._fixture(Path(directory))
            record = build_semantic_live_gate_record(
                identity,
                validation_result=result,
                status="PASS",
                live_authority_enabled=True,
            )
            result.write_text(json.dumps({"status": "FAIL"}), encoding="utf-8")
            self.assertFalse(semantic_live_gate_open(record, expected=identity))

    def test_failed_validation_cannot_enable_live_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity, result = self._fixture(Path(directory))
            with self.assertRaisesRegex(SemanticLiveGateError, "failed validation"):
                build_semantic_live_gate_record(
                    identity,
                    validation_result=result,
                    status="FAIL",
                    live_authority_enabled=True,
                )


if __name__ == "__main__":
    unittest.main()
