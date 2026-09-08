"""Validated inventory of available TBC 2.4.3 WorldPack map profiles."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidator


@dataclass(frozen=True, slots=True)
class WorldMapProfile:
    map_id: int
    internal_name: str
    runtime_profile: Path | None
    semantic_catalog: Path | None = None
    structure_index: Path | None = None
    structure_access_graph: Path | None = None


@dataclass(frozen=True, slots=True)
class WorldMapProfileReadiness:
    """Read-only capability summary for one registry profile."""

    runtime_profile_ready: bool
    semantic_catalog_ready: bool
    structure_index_ready: bool
    structure_access_graph_ready: bool

    @property
    def topographic_ready(self) -> bool:
        """Whether the immutable geometry layers are ready for observation.

        Semantic destinations are intentionally separate.  A map can therefore
        have floors, heights, walls, stairs, bridges and clearance evidence
        ready for read-only inspection while still refusing autonomous travel
        because its semantic location catalog is incomplete.
        """

        return all((
            self.runtime_profile_ready,
            self.structure_index_ready,
            self.structure_access_graph_ready,
        ))

    @property
    def autonomous_ready(self) -> bool:
        return self.topographic_ready and self.semantic_catalog_ready


@lru_cache(maxsize=128)
def _read_artifact_record(path: Path) -> dict[str, Any] | None:
    """Read one small registry artefact for identity validation.

    The registry is used by the UI as a capability boundary.  A file merely
    existing is not enough: a stale artifact from another map must not make a
    profile look autonomous-ready.  This cache keeps the read-only check cheap
    when the Control Center renders all inventory identities.
    """

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, TypeError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def _runtime_profile_matches(profile: WorldMapProfile) -> bool:
    path = profile.runtime_profile
    if path is None or not path.is_file():
        return False
    record = _read_artifact_record(path.resolve())
    if (
        record is None
        or record.get("record_type") != "world_pack_runtime_profile"
        or record.get("schema_version") != "1.0"
        or record.get("execution_authority") is not False
        or not isinstance(record.get("maps"), list)
    ):
        return False
    matches = [
        item for item in record["maps"]
        if isinstance(item, dict)
        and item.get("map_id") == profile.map_id
        and item.get("internal_name") == profile.internal_name
    ]
    return len(matches) == 1


def _map_artifact_matches(
    path: Path | None,
    *,
    record_type: str,
    profile: WorldMapProfile,
) -> bool:
    if path is None or not path.is_file():
        return False
    record = _read_artifact_record(path.resolve())
    return bool(
        record is not None
        and record.get("record_type") == record_type
        and record.get("schema_version") == "1.0"
        and record.get("map_id") == profile.map_id
        and record.get("map_name") == profile.internal_name
        and record.get("execution_authority") is False
    )


def _semantic_catalog_matches(profile: WorldMapProfile) -> bool:
    path = profile.semantic_catalog
    if path is None or not path.is_file():
        return False
    record = _read_artifact_record(path.resolve())
    return bool(
        record is not None
        and record.get("record_type") == "semantic_location_catalog"
        and record.get("schema_version") == "1.0"
        and record.get("map_name") == profile.internal_name
        and record.get("coordinate_system") == "tbc243_client_world_xy"
        and isinstance(record.get("zone_index"), int)
        and 0 <= int(record["zone_index"]) <= 65_535
        and isinstance(record.get("atlas_calibration"), str)
        and bool(record["atlas_calibration"].strip())
        and isinstance(record.get("locations"), list)
        and bool(record["locations"])
    )


def inspect_world_map_profile(profile: WorldMapProfile) -> WorldMapProfileReadiness:
    """Inspect declared artefacts without mutating runtime state.

    Readiness is identity-bound, not an existence check.  In particular, a
    shared WorldPack profile is valid for a map only when that map is explicitly
    present in its ``maps`` list, and structure/semantic artifacts must carry
    the same map identity.  This prevents Control Center from presenting stale
    cross-map evidence as autonomous capability.
    """

    return WorldMapProfileReadiness(
        runtime_profile_ready=_runtime_profile_matches(profile),
        semantic_catalog_ready=_semantic_catalog_matches(profile),
        structure_index_ready=_map_artifact_matches(
            profile.structure_index,
            record_type="world_structure_index",
            profile=profile,
        ),
        structure_access_graph_ready=_map_artifact_matches(
            profile.structure_access_graph,
            record_type="structure_access_graph",
            profile=profile,
        ),
    )


def load_world_map_registry(
    path: Path,
    *,
    schema_path: Path,
) -> tuple[WorldMapProfile, ...]:
    record = json.loads(path.read_text(encoding="utf-8"))
    ContractValidator(schema_path).validate(record)
    root = path.parent
    declared_profiles = [
        WorldMapProfile(
            map_id=int(item["map_id"]),
            internal_name=str(item["internal_name"]),
            runtime_profile=(
                None
                if item.get("runtime_profile") is None
                else (root / str(item["runtime_profile"])).resolve()
            ),
            semantic_catalog=(
                None
                if item.get("semantic_catalog") is None
                else (root / str(item["semantic_catalog"])).resolve()
            ),
            structure_index=(
                None
                if item.get("structure_index") is None
                else (root / str(item["structure_index"])).resolve()
            ),
            structure_access_graph=(
                None
                if item.get("structure_access_graph") is None
                else (root / str(item["structure_access_graph"])).resolve()
            ),
        )
        for item in record["maps"]
    ]
    if len({item.map_id for item in declared_profiles}) != len(declared_profiles):
        raise ValueError("world map registry contains duplicate map ids")
    inventory_reference = record.get("client_world_inventory")
    if inventory_reference is None:
        return tuple(declared_profiles)
    inventory_path = (root / str(inventory_reference)).resolve()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict) or not isinstance(inventory.get("maps"), list):
        raise ValueError("client world inventory has no map list")
    if (
        inventory.get("record_type") != "client_world_asset_inventory"
        or inventory.get("schema_version") != "1.0"
        or inventory.get("client_build") != "2.4.3.8606"
        or inventory.get("map_count") != len(inventory["maps"])
    ):
        raise ValueError("client world inventory identity is invalid")
    declared_ids = {item.map_id for item in declared_profiles}
    for item in inventory["maps"]:
        if not isinstance(item, dict):
            raise ValueError("client world inventory map is malformed")
        map_id = item.get("map_id")
        internal_name = item.get("internal_name")
        if type(map_id) is not int or map_id < 0:
            raise ValueError("client world inventory map id is invalid")
        if not isinstance(internal_name, str) or not internal_name.strip():
            raise ValueError("client world inventory map name is invalid")
        if map_id in declared_ids:
            declared = next(profile for profile in declared_profiles if profile.map_id == map_id)
            if declared.internal_name != internal_name:
                raise ValueError("registry and client inventory map names differ")
            continue
        declared_profiles.append(
            WorldMapProfile(
                map_id=map_id,
                internal_name=internal_name,
                runtime_profile=None,
            )
        )
        declared_ids.add(map_id)
    return tuple(sorted(declared_profiles, key=lambda item: (item.map_id, item.internal_name)))
