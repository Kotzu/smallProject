from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path, PurePosixPath
import re
import struct
from typing import Any, Iterable, Mapping

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    VerifiedStandaloneWorldPack,
)


class WorldStructureIndexError(ValueError):
    """Raised when immutable structure geometry is malformed or inconsistent."""


_MAP_MAGIC = b"1PAM"
_ADT_BITSET_BYTES = 64 * 64 // 8
_ASSET_PATH_BYTES = 128
_WMO_RECORD = struct.Struct("<IHH16f6f128s")
_DOODAD_RECORD = struct.Struct("<I16f6f128s")
_U32 = struct.Struct("<I")
_TOKEN = re.compile(r"[a-z0-9]+")
_ADT_SIZE = 533.0 + (1.0 / 3.0)


@dataclass(frozen=True, slots=True)
class Vector3:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class AxisAlignedBounds:
    minimum: Vector3
    maximum: Vector3

    def contains(self, *, x: float, y: float, z: float | None = None) -> bool:
        horizontal = (
            self.minimum.x <= x <= self.maximum.x
            and self.minimum.y <= y <= self.maximum.y
        )
        return horizontal and (
            z is None or self.minimum.z <= z <= self.maximum.z
        )

    def horizontal_distance(self, *, x: float, y: float) -> float:
        dx = max(self.minimum.x - x, 0.0, x - self.maximum.x)
        dy = max(self.minimum.y - y, 0.0, y - self.maximum.y)
        return math.hypot(dx, dy)

    def vertical_distance(self, *, z: float) -> float:
        return max(self.minimum.z - z, 0.0, z - self.maximum.z)


@dataclass(frozen=True, slots=True)
class WorldStructure:
    structure_id: str
    kind: str
    instance_id: int
    asset_path: str
    asset_tokens: tuple[str, ...]
    bounds: AxisAlignedBounds
    center: Vector3
    horizontal_radius_yards: float
    collision_role: str
    nav_coverage: str


@dataclass(frozen=True, slots=True)
class StructureAwarenessHit:
    structure: WorldStructure
    horizontal_distance_yards: float
    vertical_distance_yards: float | None
    contains_horizontal: bool
    contains_3d: bool | None


@dataclass(frozen=True, slots=True)
class ParsedMapStructures:
    terrain_present: bool
    terrain_tile_count: int
    structures: tuple[Mapping[str, Any], ...]

    @property
    def wmo_count(self) -> int:
        return sum(item["kind"] == "WMO" for item in self.structures)

    @property
    def doodad_count(self) -> int:
        return sum(item["kind"] == "DOODAD" for item in self.structures)


@dataclass(frozen=True, slots=True)
class VerifiedWorldStructureIndex:
    record: Mapping[str, Any]
    spatial: "WorldStructureSpatialIndex"


class WorldStructureSpatialIndex:
    """Deterministic uniform-grid index over immutable WMO/doodad bounds."""

    def __init__(
        self,
        structures: Iterable[WorldStructure],
        *,
        cell_size_yards: float = 128.0,
    ) -> None:
        if not math.isfinite(cell_size_yards) or not 16.0 <= cell_size_yards <= 512.0:
            raise WorldStructureIndexError("structure grid cell size is invalid")
        self.cell_size_yards = float(cell_size_yards)
        values = tuple(structures)
        if len({item.structure_id for item in values}) != len(values):
            raise WorldStructureIndexError("structure identities are not unique")
        self._structures = {item.structure_id: item for item in values}
        cells: dict[tuple[int, int], set[str]] = {}
        for item in values:
            bounds = item.bounds
            min_x = math.floor(bounds.minimum.x / self.cell_size_yards)
            max_x = math.floor(bounds.maximum.x / self.cell_size_yards)
            min_y = math.floor(bounds.minimum.y / self.cell_size_yards)
            max_y = math.floor(bounds.maximum.y / self.cell_size_yards)
            for cell_x in range(min_x, max_x + 1):
                for cell_y in range(min_y, max_y + 1):
                    cells.setdefault((cell_x, cell_y), set()).add(item.structure_id)
        self._cells = {
            key: tuple(sorted(value)) for key, value in cells.items()
        }

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, Any],
        *,
        cell_size_yards: float = 128.0,
    ) -> "WorldStructureSpatialIndex":
        structures = []
        for item in record.get("structures", []):
            bounds = item["bounds"]
            center = item["center"]
            structures.append(WorldStructure(
                structure_id=str(item["structure_id"]),
                kind=str(item["kind"]),
                instance_id=int(item["instance_id"]),
                asset_path=str(item["asset_path"]),
                asset_tokens=tuple(str(value) for value in item["asset_tokens"]),
                bounds=AxisAlignedBounds(
                    minimum=Vector3(**bounds["min"]),
                    maximum=Vector3(**bounds["max"]),
                ),
                center=Vector3(**center),
                horizontal_radius_yards=float(item["horizontal_radius_yards"]),
                collision_role=str(item["collision_role"]),
                nav_coverage=str(item["nav_coverage"]),
            ))
        if len(structures) != int(record.get("structure_count", -1)):
            raise WorldStructureIndexError("structure record count is inconsistent")
        return cls(structures, cell_size_yards=cell_size_yards)

    def nearby(
        self,
        *,
        x: float,
        y: float,
        radius_yards: float,
        z: float | None = None,
        kinds: Iterable[str] | None = None,
    ) -> tuple[StructureAwarenessHit, ...]:
        values = (x, y, radius_yards) if z is None else (x, y, z, radius_yards)
        if any(not math.isfinite(value) for value in values):
            raise WorldStructureIndexError("structure awareness query is invalid")
        if not 0.0 <= radius_yards <= 1_000.0:
            raise WorldStructureIndexError("structure awareness radius is invalid")
        accepted = None if kinds is None else frozenset(kinds)
        if accepted is not None and not accepted.issubset({"WMO", "DOODAD"}):
            raise WorldStructureIndexError("structure kind filter is invalid")
        min_x = math.floor((x - radius_yards) / self.cell_size_yards)
        max_x = math.floor((x + radius_yards) / self.cell_size_yards)
        min_y = math.floor((y - radius_yards) / self.cell_size_yards)
        max_y = math.floor((y + radius_yards) / self.cell_size_yards)
        candidates: set[str] = set()
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                candidates.update(self._cells.get((cell_x, cell_y), ()))
        hits = []
        for structure_id in candidates:
            item = self._structures[structure_id]
            if accepted is not None and item.kind not in accepted:
                continue
            horizontal = item.bounds.horizontal_distance(x=x, y=y)
            if horizontal > radius_yards:
                continue
            contains_horizontal = item.bounds.contains(x=x, y=y)
            hits.append(StructureAwarenessHit(
                structure=item,
                horizontal_distance_yards=horizontal,
                vertical_distance_yards=(
                    None if z is None else item.bounds.vertical_distance(z=z)
                ),
                contains_horizontal=contains_horizontal,
                contains_3d=(
                    None if z is None else item.bounds.contains(x=x, y=y, z=z)
                ),
            ))
        return tuple(sorted(
            hits,
            key=lambda hit: (
                hit.horizontal_distance_yards,
                float("inf") if hit.vertical_distance_yards is None else hit.vertical_distance_yards,
                hit.structure.structure_id,
            ),
        ))

    def get(self, structure_id: str) -> WorldStructure | None:
        """Return one immutable structure record by its stable identity."""

        return self._structures.get(str(structure_id))

    def containing(
        self, *, x: float, y: float, z: float | None = None,
    ) -> tuple[StructureAwarenessHit, ...]:
        return tuple(
            hit for hit in self.nearby(x=x, y=y, z=z, radius_yards=0.0)
            if hit.contains_horizontal and (z is None or hit.contains_3d)
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise WorldStructureIndexError(
            f"cannot hash map artifact {path.name!r}: {error}"
        ) from error
    return digest.hexdigest()


def _safe_asset_path(raw: bytes, *, expected_kind: str) -> str:
    terminator = raw.find(b"\0")
    if terminator <= 0:
        raise WorldStructureIndexError("structure asset path is not terminated")
    try:
        value = raw[:terminator].decode("ascii")
    except UnicodeDecodeError as error:
        raise WorldStructureIndexError("structure asset path is not ASCII") from error
    value = value.replace("\\", "/").lower()
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in value
    ):
        raise WorldStructureIndexError("structure asset path is unsafe")
    if expected_kind == "WMO" and path.suffix != ".wmo":
        raise WorldStructureIndexError("WMO instance does not reference a WMO asset")
    return path.as_posix()


def _finite_float_tuple(values: Iterable[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise WorldStructureIndexError("structure geometry contains non-finite values")
    return result


def _structure_record(
    *,
    map_id: int,
    kind: str,
    instance_id: int,
    asset_path: str,
    transform: Iterable[float],
    bounds_values: Iterable[float],
    doodad_set: int | None,
    name_set: int | None,
) -> dict[str, Any]:
    matrix = _finite_float_tuple(transform)
    bounds = _finite_float_tuple(bounds_values)
    minimum = bounds[:3]
    maximum = bounds[3:]
    if any(low > high for low, high in zip(minimum, maximum, strict=True)):
        raise WorldStructureIndexError("structure bounds are inverted")
    center = tuple((low + high) / 2.0 for low, high in zip(minimum, maximum, strict=True))
    extent = tuple(high - low for low, high in zip(minimum, maximum, strict=True))
    tokens = tuple(dict.fromkeys(_TOKEN.findall(asset_path)))[:64]
    return {
        "structure_id": f"{map_id}:{kind.lower()}:{instance_id}",
        "kind": kind,
        "instance_id": instance_id,
        "asset_path": asset_path,
        "asset_tokens": list(tokens),
        "doodad_set": doodad_set,
        "name_set": name_set,
        "transform_matrix": list(matrix),
        "bounds": {
            "min": dict(zip(("x", "y", "z"), minimum, strict=True)),
            "max": dict(zip(("x", "y", "z"), maximum, strict=True)),
        },
        "center": dict(zip(("x", "y", "z"), center, strict=True)),
        "extent": dict(zip(("x", "y", "z"), extent, strict=True)),
        "horizontal_radius_yards": math.hypot(extent[0] / 2.0, extent[1] / 2.0),
        "collision_role": (
            "ENCLOSURE_OR_LARGE_STRUCTURE"
            if kind == "WMO" else "STATIC_OBSTACLE_CANDIDATE"
        ),
        "geometry_confidence": 1.0,
        "provenance": "PINNED_CLIENT_MAP_ARTIFACT",
    }


def _terrain_tiles_for_bounds(bounds: Mapping[str, Any]) -> frozenset[tuple[int, int]]:
    minimum = bounds["min"]
    maximum = bounds["max"]

    def indices(low: float, high: float) -> range:
        first = math.floor(32.0 - high / _ADT_SIZE)
        last = math.floor(32.0 - low / _ADT_SIZE)
        return range(max(0, min(first, last)), min(63, max(first, last)) + 1)

    adt_x = indices(float(minimum["y"]), float(maximum["y"]))
    adt_y = indices(float(minimum["x"]), float(maximum["x"]))
    return frozenset((x, y) for x in adt_x for y in adt_y)


def _with_navigation_coverage(
    item: Mapping[str, Any],
    *,
    terrain_present: bool,
    covered_tiles: frozenset[tuple[int, int]],
) -> dict[str, Any]:
    result = dict(item)
    if not terrain_present:
        intersecting = frozenset()
        nav_coverage = "GLOBAL_WMO"
        covered_count = 1
    else:
        intersecting = _terrain_tiles_for_bounds(item["bounds"])
        covered_count = len(intersecting & covered_tiles)
        if intersecting and covered_count == len(intersecting):
            nav_coverage = "FULL"
        elif covered_count:
            nav_coverage = "PARTIAL"
        else:
            nav_coverage = "NONE"
    result["intersecting_terrain_tile_count"] = len(intersecting)
    result["covered_nav_tile_count"] = covered_count
    result["nav_coverage"] = nav_coverage
    return result


def parse_namigator_map_structures(
    map_path: Path, *, map_id: int,
) -> ParsedMapStructures:
    """Decode only the documented MAP1 instance table; never infer live state."""
    try:
        payload = map_path.read_bytes()
    except OSError as error:
        raise WorldStructureIndexError(
            f"cannot read map artifact {map_path.name!r}: {error}"
        ) from error
    if len(payload) < 5 or payload[:4] != _MAP_MAGIC:
        raise WorldStructureIndexError("map artifact signature is invalid")
    has_terrain = payload[4]
    if has_terrain not in (0, 1):
        raise WorldStructureIndexError("map terrain flag is invalid")
    offset = 5
    structures: list[Mapping[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def read_record(kind: str, record: struct.Struct) -> tuple[Any, ...]:
        nonlocal offset
        if offset + record.size > len(payload):
            raise WorldStructureIndexError(f"{kind} instance table is truncated")
        values = record.unpack_from(payload, offset)
        offset += record.size
        return values

    def append_wmo(values: tuple[Any, ...]) -> None:
        instance_id, doodad_set, name_set = values[:3]
        key = ("WMO", int(instance_id))
        if key in seen:
            raise WorldStructureIndexError("WMO instance identities are not unique")
        seen.add(key)
        structures.append(_structure_record(
            map_id=map_id,
            kind="WMO",
            instance_id=int(instance_id),
            doodad_set=int(doodad_set),
            name_set=int(name_set),
            transform=values[3:19],
            bounds_values=values[19:25],
            asset_path=_safe_asset_path(values[25], expected_kind="WMO"),
        ))

    terrain_tile_count = 0
    if has_terrain:
        if offset + _ADT_BITSET_BYTES + _U32.size > len(payload):
            raise WorldStructureIndexError("map terrain table is truncated")
        terrain_bits = payload[offset:offset + _ADT_BITSET_BYTES]
        offset += _ADT_BITSET_BYTES
        terrain_tile_count = sum(byte.bit_count() for byte in terrain_bits)
        (wmo_count,) = _U32.unpack_from(payload, offset)
        offset += _U32.size
        minimum_tail = _U32.size
        if wmo_count > (len(payload) - offset - minimum_tail) // _WMO_RECORD.size:
            raise WorldStructureIndexError("WMO instance count exceeds the artifact")
        for _ in range(wmo_count):
            append_wmo(read_record("WMO", _WMO_RECORD))
        if offset + _U32.size > len(payload):
            raise WorldStructureIndexError("doodad instance count is missing")
        (doodad_count,) = _U32.unpack_from(payload, offset)
        offset += _U32.size
        if doodad_count > (len(payload) - offset) // _DOODAD_RECORD.size:
            raise WorldStructureIndexError("doodad instance count exceeds the artifact")
        for _ in range(doodad_count):
            values = read_record("doodad", _DOODAD_RECORD)
            instance_id = int(values[0])
            key = ("DOODAD", instance_id)
            if key in seen:
                raise WorldStructureIndexError("doodad instance identities are not unique")
            seen.add(key)
            structures.append(_structure_record(
                map_id=map_id,
                kind="DOODAD",
                instance_id=instance_id,
                doodad_set=None,
                name_set=None,
                transform=values[1:17],
                bounds_values=values[17:23],
                asset_path=_safe_asset_path(values[23], expected_kind="DOODAD"),
            ))
    else:
        append_wmo(read_record("global WMO", _WMO_RECORD))
    if offset != len(payload):
        raise WorldStructureIndexError("map artifact has unexpected trailing bytes")
    if not structures:
        raise WorldStructureIndexError("map artifact has no indexed structures")
    return ParsedMapStructures(
        terrain_present=bool(has_terrain),
        terrain_tile_count=terrain_tile_count,
        structures=tuple(sorted(
            structures, key=lambda item: (item["kind"], item["instance_id"]),
        )),
    )


def build_world_structure_index_record(
    pack: VerifiedStandaloneWorldPack,
    *,
    map_name: str,
) -> dict[str, Any]:
    manifest = pack.manifest
    map_records = {
        str(item["internal_name"]): item for item in manifest["maps"]
    }
    selected = map_records.get(map_name)
    if selected is None:
        raise WorldStructureIndexError("map is not declared by the WorldPack")
    map_id = int(selected["map_id"])
    map_path = pack.pack_root / f"{map_name}.map"
    map_sha256 = _sha256(map_path)
    declared = [
        item for item in manifest["files"]
        if item["role"] == "NAV_MAP" and item["relative_path"] == f"{map_name}.map"
    ]
    if len(declared) != 1 or declared[0]["sha256"] != map_sha256:
        raise WorldStructureIndexError("map artifact is not pinned by the WorldPack")
    parsed = parse_namigator_map_structures(map_path, map_id=map_id)
    catalog_map = pack.catalog.map_by_id(map_id)
    covered_tiles = frozenset(
        (item.grid_x, item.grid_y) for item in catalog_map.tiles
    )
    structures = [
        _with_navigation_coverage(
            item,
            terrain_present=parsed.terrain_present,
            covered_tiles=covered_tiles,
        )
        for item in parsed.structures
    ]
    return {
        "record_type": "world_structure_index",
        "schema_version": "1.0",
        "index_id": f"{manifest['pack_id']}:{map_name}:structures-v1",
        "pack_id": str(manifest["pack_id"]),
        "catalog_id": str(manifest["catalog_id"]),
        "source_pack_content_sha256": str(manifest["content_sha256"]),
        "client_version": str(manifest["client_version"]),
        "client_build": str(manifest["client_build"]),
        "map_id": map_id,
        "map_name": map_name,
        "map_artifact": f"{map_name}.map",
        "map_artifact_sha256": map_sha256,
        "parser_profile": "namigator-map1-v1",
        "terrain_present": parsed.terrain_present,
        "terrain_tile_count": parsed.terrain_tile_count,
        "nav_tile_count": len(catalog_map.tiles),
        "navigation_coverage": catalog_map.coverage_state,
        "interior_navigation_coverage": catalog_map.interior_coverage,
        "structure_count": len(structures),
        "wmo_count": parsed.wmo_count,
        "doodad_count": parsed.doodad_count,
        "static_knowledge_semantics": "PINNED_CLIENT_ASSET_BOUNDS",
        "dynamic_entity_knowledge": "NONE",
        "structures": structures,
        "execution_authority": False,
    }


def verify_world_structure_index_binding(
    record: Mapping[str, Any],
    pack: VerifiedStandaloneWorldPack,
) -> None:
    manifest = pack.manifest
    identity = (
        ("pack_id", manifest["pack_id"]),
        ("catalog_id", manifest["catalog_id"]),
        ("source_pack_content_sha256", manifest["content_sha256"]),
        ("client_version", manifest["client_version"]),
        ("client_build", manifest["client_build"]),
    )
    for field, expected in identity:
        if record.get(field) != expected:
            raise WorldStructureIndexError(
                f"structure index {field} does not match its WorldPack"
            )
    rebuilt = build_world_structure_index_record(
        pack, map_name=str(record.get("map_name", "")),
    )
    if dict(record) != rebuilt:
        raise WorldStructureIndexError(
            "structure index does not match the pinned map artifact"
        )


def load_world_structure_index(
    index_path: Path,
    *,
    schema_path: Path,
    pack: VerifiedStandaloneWorldPack,
    cell_size_yards: float = 128.0,
) -> VerifiedWorldStructureIndex:
    try:
        import json

        record = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise WorldStructureIndexError(
            f"cannot read world structure index: {error}"
        ) from error
    if not isinstance(record, dict):
        raise WorldStructureIndexError("world structure index is not one object")
    ContractValidator(schema_path).validate(record)
    verify_world_structure_index_binding(record, pack)
    return VerifiedWorldStructureIndex(
        record=record,
        spatial=WorldStructureSpatialIndex.from_record(
            record, cell_size_yards=cell_size_yards,
        ),
    )
