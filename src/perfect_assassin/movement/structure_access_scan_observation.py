from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.local_environment_awareness import (
    EnvironmentBoundary,
    LocalEnvironmentAwareness,
    StructureContainmentEvidence,
    VerifiedEnvironmentEgress,
)


class StructureAccessScanObservationError(ValueError):
    """Raised when a resumable structure scan observation is invalid."""


def canonical_sha256(record: Mapping[str, Any]) -> str:
    wire = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(wire).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise StructureAccessScanObservationError(
            f"cannot hash scan artifact: {error}"
        ) from error
    return digest.hexdigest()


def collision_probe_record(awareness: LocalStaticAwareness) -> dict[str, Any]:
    return {
        "physical_surfaces": sorted(awareness.physical_surfaces),
        "probe_radius_yards": awareness.probe_radius_yards,
        "radial_probes": [{
            "bearing_rad": item.bearing_rad,
            "clearance_yards": item.clearance_yards,
            "navmesh_reachable": item.navmesh_reachable,
        } for item in awareness.radial_probes],
    }


def collision_probe_from_record(record: Mapping[str, Any]) -> LocalStaticAwareness:
    return LocalStaticAwareness(
        physical_surfaces=frozenset(str(item) for item in record["physical_surfaces"]),
        probe_radius_yards=float(record["probe_radius_yards"]),
        overhead_clear=False,
        radial_probes=tuple(RadialClearanceProbe(
            bearing_rad=float(item["bearing_rad"]),
            clearance_yards=float(item["clearance_yards"]),
            navmesh_reachable=bool(item["navmesh_reachable"]),
        ) for item in record["radial_probes"]),
    )


def _point(value: Any) -> NavPoint:
    if not isinstance(value, list) or len(value) != 3:
        raise StructureAccessScanObservationError("scan awareness point is invalid")
    return NavPoint(float(value[0]), float(value[1]), float(value[2]))


def local_environment_from_record(record: Mapping[str, Any]) -> LocalEnvironmentAwareness:
    return LocalEnvironmentAwareness(
        map_name=str(record["map_name"]),
        observed_monotonic_s=float(record["observed_monotonic_s"]),
        position=_point(record["position"]),
        environment_state=str(record["environment_state"]),
        environment_confidence=float(record["environment_confidence"]),
        physical_surfaces=frozenset(str(item) for item in record["physical_surfaces"]),
        topology_complete=bool(record["topology_complete"]),
        containing_structures=tuple(StructureContainmentEvidence(
            structure_id=str(item["structure_id"]),
            asset_path=str(item["asset_path"]),
            nav_coverage=str(item["nav_coverage"]),
            evidence=str(item["evidence"]),
            confidence=float(item["confidence"]),
        ) for item in record["containing_structures"]),
        boundaries=tuple(EnvironmentBoundary(
            left=_point(item["left"]),
            right=_point(item["right"]),
            midpoint=_point(item["midpoint"]),
            bearing_rad=float(item["bearing_rad"]),
            distance_yards=float(item["distance_yards"]),
            length_yards=float(item["length_yards"]),
            kind=str(item["kind"]),
            physical_wall_semantics=str(item["physical_wall_semantics"]),
            topology_confidence=float(item["topology_confidence"]),
        ) for item in record["boundaries"]),
        verified_egresses=tuple(VerifiedEnvironmentEgress(
            left=_point(item["left"]),
            right=_point(item["right"]),
            midpoint=_point(item["midpoint"]),
            bearing_rad=float(item["bearing_rad"]),
            width_yards=float(item["width_yards"]),
            distance_yards=float(item["distance_yards"]),
            route_distance_yards=float(item["route_distance_yards"]),
            from_surfaces=frozenset(str(value) for value in item["from_surfaces"]),
            to_surfaces=frozenset(str(value) for value in item["to_surfaces"]),
            kind=str(item["kind"]),
            route_verified=bool(item["route_verified"]),
            topology_confidence=float(item["topology_confidence"]),
        ) for item in record["verified_egresses"]),
        candidate_opening_bearings_rad=tuple(
            float(item) for item in record["candidate_opening_bearings_rad"]
        ),
        nearby_wmo_count=int(record["nearby_wmo_count"]),
        nearby_static_obstacle_count=int(record["nearby_static_obstacle_count"]),
        source=str(record["source"]),
        execution_authority=bool(record["execution_authority"]),
    )


def build_scan_observation_record(
    *,
    plan: Mapping[str, Any],
    task: Mapping[str, Any],
    seed: Mapping[str, Any],
    status: str,
    resolved_position: list[float] | None,
    actual_structure_ids: list[str],
    awareness_artifact: str | None,
    awareness_sha256: str | None,
    collision_probe: Mapping[str, Any] | None,
    failure_reason: str | None,
) -> dict[str, Any]:
    if status not in {
        "ACCEPTED_CONTAINED_WMO",
        "REJECTED_EXPECTED_STRUCTURE_NOT_CONFIRMED",
        "REJECTED_NO_NAV_POLYGON",
        "REJECTED_INCOMPLETE_STATIC_AWARENESS",
        "PROBE_ERROR",
    }:
        raise StructureAccessScanObservationError("scan observation status is invalid")
    accepted = status == "ACCEPTED_CONTAINED_WMO"
    probed = status not in {
        "REJECTED_NO_NAV_POLYGON",
        "REJECTED_INCOMPLETE_STATIC_AWARENESS",
        "PROBE_ERROR",
    }
    if (
        (resolved_position is not None) != probed
        or (awareness_artifact is not None) != probed
        or (awareness_sha256 is not None) != probed
        or (collision_probe is not None) != probed
        or (failure_reason is None) != accepted
    ):
        raise StructureAccessScanObservationError(
            "scan observation evidence does not match its status"
        )
    if awareness_artifact is not None:
        path = PurePosixPath(awareness_artifact)
        if path.name != awareness_artifact or path.suffix != ".json":
            raise StructureAccessScanObservationError(
                "scan awareness artifact path is unsafe"
            )
    record: dict[str, Any] = {
        "record_type": "structure_access_scan_observation",
        "schema_version": "1.0",
        "fragment_id": f"{seed['seed_id']}:observation-v1",
        "plan_id": str(plan["plan_id"]),
        "plan_content_sha256": str(plan["content_sha256"]),
        "world_pack_id": str(plan["world_pack_id"]),
        "world_pack_content_sha256": str(plan["world_pack_content_sha256"]),
        "client_build": str(plan["client_build"]),
        "map_id": int(plan["map_id"]),
        "map_name": str(plan["map_name"]),
        "probe_worker_sha256": str(plan["probe_worker_sha256"]),
        "task_id": str(task["task_id"]),
        "seed_id": str(seed["seed_id"]),
        "expected_structure_id": str(task["structure_id"]),
        "requested_position": list(seed["position"]),
        "status": status,
        "resolved_position": resolved_position,
        "actual_structure_ids": sorted(actual_structure_ids),
        "awareness_artifact": awareness_artifact,
        "awareness_sha256": awareness_sha256,
        "collision_probe": collision_probe,
        "failure_reason": failure_reason,
        "execution_authority": False,
    }
    record["content_sha256"] = canonical_sha256(record)
    return record


def verify_scan_observation_binding(
    record: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
) -> None:
    for field, expected in (
        ("plan_id", plan["plan_id"]),
        ("plan_content_sha256", plan["content_sha256"]),
        ("world_pack_id", plan["world_pack_id"]),
        ("world_pack_content_sha256", plan["world_pack_content_sha256"]),
        ("client_build", plan["client_build"]),
        ("map_id", plan["map_id"]),
        ("map_name", plan["map_name"]),
        ("probe_worker_sha256", plan["probe_worker_sha256"]),
    ):
        if record.get(field) != expected:
            raise StructureAccessScanObservationError(
                f"scan observation {field} does not match its plan"
            )
    unsigned = dict(record)
    content_sha256 = unsigned.pop("content_sha256", None)
    if not isinstance(content_sha256, str) or not hmac.compare_digest(
        canonical_sha256(unsigned), content_sha256,
    ):
        raise StructureAccessScanObservationError(
            "scan observation content hash mismatch"
        )


def load_scan_observation(
    path: Path,
    *,
    schema_path: Path,
    plan: Mapping[str, Any],
    validator: ContractValidator | None = None,
) -> Mapping[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StructureAccessScanObservationError(
            f"cannot read scan observation: {error}"
        ) from error
    if not isinstance(record, dict):
        raise StructureAccessScanObservationError("scan observation is not one object")
    (validator or ContractValidator(schema_path)).validate(record)
    verify_scan_observation_binding(record, plan=plan)
    return record
