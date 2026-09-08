from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from pathlib import Path
from typing import Any, Mapping

from perfect_assassin.movement.world_pack_runtime import WorldPackRuntimeBinding


class SemanticLiveGateError(ValueError):
    """Raised when a semantic movement gate cannot be bound safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise SemanticLiveGateError(f"cannot hash runtime artifact: {path}") from error
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticLiveGateIdentity:
    world_pack_profile: str
    world_pack_profile_sha256: str
    world_pack_profile_id: str
    world_pack_id: str
    world_pack_content_sha256: str
    target_profile: str
    client_version: str
    client_build: str
    nav_profile_id: str
    worker: str
    worker_sha256: str


def semantic_live_gate_identity(
    binding: WorldPackRuntimeBinding,
    *,
    profile_path: Path,
    worker_path: Path,
) -> SemanticLiveGateIdentity:
    profile_path = profile_path.resolve()
    worker_path = worker_path.resolve()
    if not profile_path.is_file():
        raise SemanticLiveGateError("WorldPack runtime profile is missing")
    if not worker_path.is_file():
        raise SemanticLiveGateError("navmesh query worker is missing")
    manifest = binding.pack.manifest
    catalog = binding.pack.catalog
    return SemanticLiveGateIdentity(
        world_pack_profile=str(profile_path),
        world_pack_profile_sha256=_sha256(profile_path),
        world_pack_profile_id=binding.profile_id,
        world_pack_id=str(manifest["pack_id"]),
        world_pack_content_sha256=str(manifest["content_sha256"]),
        target_profile=catalog.target_profile,
        client_version=catalog.client_version,
        client_build=catalog.client_build,
        nav_profile_id=catalog.nav_profile_id,
        worker=str(worker_path),
        worker_sha256=_sha256(worker_path),
    )


def build_semantic_live_gate_record(
    identity: SemanticLiveGateIdentity,
    *,
    validation_result: Path,
    status: str,
    live_authority_enabled: bool,
) -> dict[str, object]:
    validation_result = validation_result.resolve()
    if status not in {"PASS", "FAIL"}:
        raise SemanticLiveGateError("semantic validation status is invalid")
    if live_authority_enabled and status != "PASS":
        raise SemanticLiveGateError("failed validation cannot enable live authority")
    return {
        "record_type": "semantic_movement_live_gate",
        "schema_version": "2.0",
        "status": status,
        "validation_result": str(validation_result),
        "validation_result_sha256": _sha256(validation_result),
        **{
            field: getattr(identity, field)
            for field in SemanticLiveGateIdentity.__dataclass_fields__
        },
        "live_authority_enabled": live_authority_enabled,
    }


def semantic_live_gate_open(
    record: Mapping[str, Any],
    *,
    expected: SemanticLiveGateIdentity,
) -> bool:
    if (
        record.get("record_type") != "semantic_movement_live_gate"
        or record.get("schema_version") != "2.0"
        or record.get("status") != "PASS"
        or record.get("live_authority_enabled") is not True
    ):
        return False
    for field in SemanticLiveGateIdentity.__dataclass_fields__:
        actual = record.get(field)
        wanted = getattr(expected, field)
        if not isinstance(actual, str) or not hmac.compare_digest(actual, wanted):
            return False
    validation_path = record.get("validation_result")
    validation_sha256 = record.get("validation_result_sha256")
    if not isinstance(validation_path, str) or not isinstance(validation_sha256, str):
        return False
    try:
        actual_validation_sha256 = _sha256(Path(validation_path).resolve())
    except (SemanticLiveGateError, OSError, RuntimeError):
        return False
    return hmac.compare_digest(actual_validation_sha256, validation_sha256)
