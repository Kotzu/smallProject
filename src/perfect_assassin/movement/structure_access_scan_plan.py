from __future__ import annotations

import hashlib
import hmac
import json
from math import floor, isfinite
from pathlib import Path
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    VerifiedStandaloneWorldPack,
)


class StructureAccessScanPlanError(ValueError):
    """Raised when a generic structure scan plan is malformed or misbound."""


_ADT_SIZE_YARDS = 533.0 + (1.0 / 3.0)
_INITIAL_AXIS_FRACTIONS = (0.08, 0.50, 0.92)
_MAX_INITIAL_SEEDS_PER_STRUCTURE = 128


def _canonical_bytes(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _axis_samples(low: float, high: float) -> tuple[float, ...]:
    low = float(low)
    high = float(high)
    if not isfinite(low) or not isfinite(high) or low > high:
        raise StructureAccessScanPlanError("structure scan bounds are invalid")
    extent = high - low
    if extent <= 0.20:
        return ((low + high) / 2.0,)
    return tuple(low + extent * fraction for fraction in _INITIAL_AXIS_FRACTIONS)


def _adt_coordinate(*, x: float, y: float) -> tuple[int, int] | None:
    grid_x = floor(32.0 - y / _ADT_SIZE_YARDS)
    grid_y = floor(32.0 - x / _ADT_SIZE_YARDS)
    if not 0 <= grid_x <= 63 or not 0 <= grid_y <= 63:
        return None
    return grid_x, grid_y


def _tile_world_bounds(grid_x: int, grid_y: int) -> tuple[float, float, float, float]:
    x_low = (31.0 - grid_y) * _ADT_SIZE_YARDS
    x_high = (32.0 - grid_y) * _ADT_SIZE_YARDS
    y_low = (31.0 - grid_x) * _ADT_SIZE_YARDS
    y_high = (32.0 - grid_x) * _ADT_SIZE_YARDS
    return x_low, x_high, y_low, y_high


def _initial_seed_points(
    structure: Mapping[str, Any],
    *,
    terrain_present: bool,
    covered_tiles: frozenset[tuple[int, int]],
) -> tuple[tuple[float, float, float], ...]:
    bounds = structure["bounds"]
    minimum = bounds["min"]
    maximum = bounds["max"]
    xs = _axis_samples(minimum["x"], maximum["x"])
    ys = _axis_samples(minimum["y"], maximum["y"])
    zs = _axis_samples(minimum["z"], maximum["z"])
    candidates = [
        (x, y, z)
        for z in zs
        for y in ys
        for x in xs
        if not terrain_present or _adt_coordinate(x=x, y=y) in covered_tiles
    ]

    # A partial WMO can intersect only a thin edge of a covered ADT, so a
    # three-point AABB lattice may miss it.  Add the center of every exact
    # WMO/covered-tile intersection as a deterministic bootstrap seed.
    if terrain_present:
        for grid_x, grid_y in sorted(covered_tiles):
            tile_x_low, tile_x_high, tile_y_low, tile_y_high = _tile_world_bounds(
                grid_x, grid_y,
            )
            x_low = max(float(minimum["x"]), tile_x_low)
            x_high = min(float(maximum["x"]), tile_x_high)
            y_low = max(float(minimum["y"]), tile_y_low)
            y_high = min(float(maximum["y"]), tile_y_high)
            if x_low <= x_high and y_low <= y_high:
                x = (x_low + x_high) / 2.0
                y = (y_low + y_high) / 2.0
                candidates.extend((x, y, z) for z in zs)

    unique = sorted({
        (round(float(x), 6), round(float(y), 6), round(float(z), 6))
        for x, y, z in candidates
    })
    if not unique:
        raise StructureAccessScanPlanError(
            "covered WMO produced no data-derived scan seeds"
        )
    if len(unique) > _MAX_INITIAL_SEEDS_PER_STRUCTURE:
        # Keep a deterministic, evenly distributed subset.  The adaptive
        # refinement policy remains responsible for unobserved cells.
        last = len(unique) - 1
        indices = {
            round(index * last / (_MAX_INITIAL_SEEDS_PER_STRUCTURE - 1))
            for index in range(_MAX_INITIAL_SEEDS_PER_STRUCTURE)
        }
        unique = [unique[index] for index in sorted(indices)]
    return tuple(unique)


def _seed_record(structure_id: str, point: tuple[float, float, float]) -> dict[str, Any]:
    digest = _canonical_sha256({"structure_id": structure_id, "point": point})
    return {
        "seed_id": f"seed:{digest[:24]}",
        "position": list(point),
        "source": "AABB_NAV_TILE_INTERSECTION_LATTICE",
        "resolution_state": "UNVERIFIED",
        "execution_authority": False,
    }


def _identity(
    pack: VerifiedStandaloneWorldPack,
    structure_index_record: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = pack.manifest
    catalog = pack.catalog
    for field, expected in (
        ("pack_id", manifest["pack_id"]),
        ("catalog_id", catalog.catalog_id),
        ("source_pack_content_sha256", manifest["content_sha256"]),
        ("client_version", catalog.client_version),
        ("client_build", catalog.client_build),
    ):
        if structure_index_record.get(field) != expected:
            raise StructureAccessScanPlanError(
                f"structure index {field} does not match the WorldPack"
            )
    map_id = int(structure_index_record["map_id"])
    map_name = str(structure_index_record["map_name"])
    if pack.catalog.map_by_id(map_id).internal_name != map_name:
        raise StructureAccessScanPlanError("structure index map is inconsistent")
    return {
        "plan_id": f"{manifest['pack_id']}:{map_name}:structure-access-scan-v1",
        "world_pack_id": str(manifest["pack_id"]),
        "world_pack_content_sha256": str(manifest["content_sha256"]),
        "catalog_id": catalog.catalog_id,
        "target_profile": catalog.target_profile,
        "client_version": catalog.client_version,
        "client_build": catalog.client_build,
        "nav_profile_id": catalog.nav_profile_id,
        "map_id": map_id,
        "map_name": map_name,
        "structure_index_id": str(structure_index_record["index_id"]),
        "structure_index_sha256": _canonical_sha256(structure_index_record),
        "map_artifact_sha256": str(structure_index_record["map_artifact_sha256"]),
    }


def build_structure_access_scan_plan_record(
    pack: VerifiedStandaloneWorldPack,
    *,
    structure_index_record: Mapping[str, Any],
    probe_worker_sha256: str,
) -> dict[str, Any]:
    """Plan map-generic, non-authoritative probes for every covered WMO."""
    if not _valid_sha256(probe_worker_sha256):
        raise StructureAccessScanPlanError("probe worker hash is invalid")
    identity = _identity(pack, structure_index_record)
    world_map = pack.catalog.map_by_id(identity["map_id"])
    covered_tiles = frozenset((tile.grid_x, tile.grid_y) for tile in world_map.tiles)
    terrain_present = bool(structure_index_record["terrain_present"])
    tasks: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    structures = sorted(
        (
            item for item in structure_index_record["structures"]
            if item["kind"] == "WMO"
        ),
        key=lambda item: item["structure_id"],
    )
    if len(structures) != int(structure_index_record["wmo_count"]):
        raise StructureAccessScanPlanError("structure index WMO count is inconsistent")
    for item in structures:
        structure_id = str(item["structure_id"])
        nav_coverage = str(item["nav_coverage"])
        if nav_coverage == "NONE":
            deferred.append({
                "structure_id": structure_id,
                "nav_coverage": nav_coverage,
                "reason": "NAV_COVERAGE_ABSENT",
                "execution_authority": False,
            })
            continue
        points = _initial_seed_points(
            item,
            terrain_present=terrain_present,
            covered_tiles=covered_tiles,
        )
        seeds = [_seed_record(structure_id, point) for point in points]
        tasks.append({
            "task_id": f"{structure_id}:access-scan-v1",
            "structure_id": structure_id,
            "asset_path": str(item["asset_path"]),
            "nav_coverage": nav_coverage,
            "bounds": item["bounds"],
            "initial_seed_count": len(seeds),
            "initial_seeds": seeds,
            "refinement_policy": {
                "strategy": "DETOUR_RESOLVE_THEN_SUBDIVIDE_UNOBSERVED_CELLS",
                "maximum_depth": 6,
                "minimum_cell_extent_yards": 2.0,
                "maximum_probe_count": 4096,
                "requires_structure_containment": True,
            },
            "state": "PLANNED_UNVERIFIED",
            "requires_detour_resolution": True,
            "execution_authority": False,
        })
    record: dict[str, Any] = {
        "record_type": "structure_access_scan_plan",
        "schema_version": "1.0",
        **identity,
        "planner_profile": "adaptive-wmo-aabb-nav-intersection-v1",
        "probe_contract_id": "detour-bvh-local-structure-access-v1",
        "probe_worker_sha256": probe_worker_sha256,
        "structure_kind_scope": "WMO_ONLY",
        "coverage_semantics": "DATA_DERIVED_CANDIDATES_REQUIRE_NAV_RESOLUTION",
        "plan_state": "PLANNED_UNVERIFIED",
        "wmo_count": len(structures),
        "eligible_structure_count": len(tasks),
        "deferred_structure_count": len(deferred),
        "initial_seed_count": sum(item["initial_seed_count"] for item in tasks),
        "tasks": tasks,
        "deferred_structures": deferred,
        "dynamic_entity_knowledge": "NONE",
        "execution_authority": False,
    }
    record["content_sha256"] = _canonical_sha256(record)
    return record


def verify_structure_access_scan_plan_binding(
    record: Mapping[str, Any],
    *,
    pack: VerifiedStandaloneWorldPack,
    structure_index_record: Mapping[str, Any],
    expected_probe_worker_sha256: str | None = None,
) -> None:
    expected_identity = _identity(pack, structure_index_record)
    for field, expected in expected_identity.items():
        if record.get(field) != expected:
            raise StructureAccessScanPlanError(
                f"structure access scan plan {field} does not match its WorldPack"
            )
    content_sha256 = record.get("content_sha256")
    if not isinstance(content_sha256, str):
        raise StructureAccessScanPlanError("structure access scan plan hash is missing")
    unsigned = dict(record)
    del unsigned["content_sha256"]
    if not hmac.compare_digest(_canonical_sha256(unsigned), content_sha256):
        raise StructureAccessScanPlanError(
            "structure access scan plan content hash mismatch"
        )
    if expected_probe_worker_sha256 is not None and not hmac.compare_digest(
        str(record.get("probe_worker_sha256", "")), expected_probe_worker_sha256,
    ):
        raise StructureAccessScanPlanError(
            "structure access scan plan probe worker does not match runtime"
        )
    tasks = record.get("tasks")
    deferred = record.get("deferred_structures")
    if not isinstance(tasks, list) or not isinstance(deferred, list):
        raise StructureAccessScanPlanError("structure access scan plan queues are invalid")
    if (
        len(tasks) != int(record.get("eligible_structure_count", -1))
        or len(deferred) != int(record.get("deferred_structure_count", -1))
        or len(tasks) + len(deferred) != int(record.get("wmo_count", -1))
        or sum(int(item.get("initial_seed_count", -1)) for item in tasks)
        != int(record.get("initial_seed_count", -1))
    ):
        raise StructureAccessScanPlanError("structure access scan plan counts are inconsistent")


def load_structure_access_scan_plan(
    path: Path,
    *,
    schema_path: Path,
    pack: VerifiedStandaloneWorldPack,
    structure_index_record: Mapping[str, Any],
    expected_probe_worker_sha256: str | None = None,
) -> Mapping[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StructureAccessScanPlanError(
            f"cannot read structure access scan plan: {error}"
        ) from error
    if not isinstance(record, dict):
        raise StructureAccessScanPlanError("structure access scan plan is not one object")
    ContractValidator(schema_path).validate(record)
    verify_structure_access_scan_plan_binding(
        record,
        pack=pack,
        structure_index_record=structure_index_record,
        expected_probe_worker_sha256=expected_probe_worker_sha256,
    )
    return record
