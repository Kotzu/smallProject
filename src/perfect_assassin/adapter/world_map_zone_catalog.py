"""Hash-pinned, read-only WorldMapArea zone transforms for TBC 2.4.3."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
from typing import Any

from perfect_assassin.contract_validation import ContractValidator


class WorldMapZoneTransformCatalogError(ValueError):
    """Raised when a client-asset transform catalog cannot be trusted."""


@dataclass(frozen=True, slots=True)
class WorldMapZoneTransform:
    """One map-area bounds transform; it has no height or execution authority."""

    map_id: int
    area_id: int
    internal_name: str
    loc_left: float
    loc_right: float
    loc_top: float
    loc_bottom: float

    def __post_init__(self) -> None:
        if type(self.map_id) is not int or self.map_id < 0:
            raise WorldMapZoneTransformCatalogError("map_id is invalid")
        if type(self.area_id) is not int or self.area_id < 0:
            raise WorldMapZoneTransformCatalogError("area_id is invalid")
        if not isinstance(self.internal_name, str) or not self.internal_name.strip():
            raise WorldMapZoneTransformCatalogError("internal_name is invalid")
        bounds = (
            self.loc_left, self.loc_right, self.loc_top, self.loc_bottom,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(float(value))
            for value in bounds
        ):
            raise WorldMapZoneTransformCatalogError("zone bounds are not finite")
        if self.loc_left == self.loc_right or self.loc_top == self.loc_bottom:
            raise WorldMapZoneTransformCatalogError("zone bounds are degenerate")

    def world_from_normalized(self, x: float, y: float) -> tuple[float, float]:
        if (
            isinstance(x, bool) or not isinstance(x, (int, float))
            or isinstance(y, bool) or not isinstance(y, (int, float))
            or not isfinite(float(x)) or not isfinite(float(y))
            or not 0.0 <= float(x) <= 1.0
            or not 0.0 <= float(y) <= 1.0
        ):
            raise WorldMapZoneTransformCatalogError(
                "normalized map position is invalid"
            )
        return (
            self.loc_top + float(y) * (self.loc_bottom - self.loc_top),
            self.loc_left + float(x) * (self.loc_right - self.loc_left),
        )

    def normalized_from_world(self, world_x: float, world_y: float) -> tuple[float, float]:
        if (
            isinstance(world_x, bool) or not isinstance(world_x, (int, float))
            or isinstance(world_y, bool) or not isinstance(world_y, (int, float))
            or not isfinite(float(world_x)) or not isfinite(float(world_y))
        ):
            raise WorldMapZoneTransformCatalogError("world position is invalid")
        x = (float(world_y) - self.loc_left) / (self.loc_right - self.loc_left)
        y = (float(world_x) - self.loc_top) / (self.loc_bottom - self.loc_top)
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise WorldMapZoneTransformCatalogError(
                "world position is outside the current zone map"
            )
        return x, y


@dataclass(frozen=True, slots=True)
class WorldMapZoneTransformCatalog:
    """Immutable transform catalog keyed by client map and area IDs."""

    target_profile: str
    client_build: str
    asset_sha256: str
    record_fingerprint_sha256: str
    source_reference: str
    retrieved_at: str
    zones: tuple[WorldMapZoneTransform, ...]
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if self.target_profile != "tbc_243_lab":
            raise WorldMapZoneTransformCatalogError("target profile is invalid")
        if self.client_build != "2.4.3.8606":
            raise WorldMapZoneTransformCatalogError("client build is invalid")
        if (
            not isinstance(self.source_reference, str)
            or not self.source_reference.strip()
            or len(self.source_reference) > 512
            or not isinstance(self.retrieved_at, str)
            or not self.retrieved_at.strip()
            or len(self.retrieved_at) > 64
        ):
            raise WorldMapZoneTransformCatalogError("transform provenance is invalid")
        for label, value in (
            ("asset_sha256", self.asset_sha256),
            ("record_fingerprint_sha256", self.record_fingerprint_sha256),
        ):
            if (
                not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdefABCDEF" for character in value)
            ):
                raise WorldMapZoneTransformCatalogError(f"{label} is invalid")
        if self.execution_authority is not False or not self.zones:
            raise WorldMapZoneTransformCatalogError(
                "transform catalog must remain read-only and non-empty"
            )
        keys = {(zone.map_id, zone.area_id) for zone in self.zones}
        if len(keys) != len(self.zones):
            raise WorldMapZoneTransformCatalogError("duplicate map-area transform")

    def resolve(self, *, map_id: int, area_id: int) -> WorldMapZoneTransform:
        matches = tuple(
            zone for zone in self.zones
            if zone.map_id == map_id and zone.area_id == area_id
        )
        if len(matches) != 1:
            raise WorldMapZoneTransformCatalogError(
                f"map-area transform is not unique: map_id={map_id}, area_id={area_id}"
            )
        return matches[0]


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorldMapZoneTransformCatalogError(
            f"cannot read transform catalog: {path}"
        ) from error
    if not isinstance(value, dict):
        raise WorldMapZoneTransformCatalogError("transform catalog must be an object")
    return value


def load_world_map_zone_transform_catalog(
    path: Path, *, schema_path: Path,
) -> WorldMapZoneTransformCatalog:
    """Load a client-asset catalog; no server or runtime state is consulted."""

    record = _read_object(path.resolve())
    try:
        ContractValidator(schema_path.resolve()).validate(record)
    except Exception as error:  # validator implementations expose varied errors
        raise WorldMapZoneTransformCatalogError(
            "transform catalog contract validation failed"
        ) from error
    zones: list[WorldMapZoneTransform] = []
    for item in record["zones"]:
        try:
            bounds = item["bounds"]
            zones.append(WorldMapZoneTransform(
                map_id=int(item["map_id"]), area_id=int(item["area_id"]),
                internal_name=str(item["internal_name"]),
                loc_left=float(bounds[0]), loc_right=float(bounds[1]),
                loc_top=float(bounds[2]), loc_bottom=float(bounds[3]),
            ))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise WorldMapZoneTransformCatalogError(
                "transform catalog zone is malformed"
            ) from error
    try:
        return WorldMapZoneTransformCatalog(
            target_profile=str(record["target_profile"]),
            client_build=str(record["client_build"]),
            asset_sha256=str(record["asset_sha256"]),
            record_fingerprint_sha256=str(record["record_fingerprint_sha256"]),
            source_reference=str(record["source_reference"]),
            retrieved_at=str(record["retrieved_at"]),
            zones=tuple(zones),
            execution_authority=bool(record["execution_authority"]),
        )
    except WorldMapZoneTransformCatalogError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise WorldMapZoneTransformCatalogError(
            "transform catalog metadata is malformed"
        ) from error
