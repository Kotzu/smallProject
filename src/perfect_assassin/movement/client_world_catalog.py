from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator


class ClientWorldCatalogError(ValueError):
    """Raised when client assets and navigation artifacts are not one exact world."""


@dataclass(frozen=True, slots=True)
class WorldNavTile:
    grid_x: int
    grid_y: int
    artifact: str
    sha256: str


@dataclass(frozen=True, slots=True)
class WorldRoadSemantic:
    grid_x: int
    grid_y: int
    artifact: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ClientWorldMap:
    map_id: int
    internal_name: str
    classification: str
    map_artifact: str
    map_artifact_sha256: str
    nav_tiles_sha256: str
    coverage_state: str
    interior_coverage: str
    road_semantic_coverage: str
    road_semantics_sha256: str
    tiles: tuple[WorldNavTile, ...]
    road_semantics: tuple[WorldRoadSemantic, ...]


@dataclass(frozen=True, slots=True)
class ClientWorldCatalog:
    catalog_id: str
    target_profile: str
    product: str
    expansion: str
    client_version: str
    client_build: str
    asset_container: str
    asset_parser_profile: str
    world_catalog_asset: str
    world_catalog_asset_sha256: str
    nav_profile_id: str
    maps: tuple[ClientWorldMap, ...]

    def map_by_id(self, map_id: int) -> ClientWorldMap:
        matches = tuple(item for item in self.maps if item.map_id == map_id)
        if len(matches) != 1:
            raise ClientWorldCatalogError(f"catalog has no unique map_id {map_id}")
        return matches[0]

    def map_by_internal_name(self, internal_name: str) -> ClientWorldMap:
        matches = tuple(
            item for item in self.maps if item.internal_name == internal_name
        )
        if len(matches) != 1:
            raise ClientWorldCatalogError(
                f"catalog has no unique internal map name {internal_name!r}"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class VerifiedClientWorld:
    catalog: ClientWorldCatalog
    nav_root: Path
    world_catalog_asset_path: Path


def load_client_world_catalog(
    path: Path,
    *,
    schema_path: Path,
) -> ClientWorldCatalog:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ClientWorldCatalogError(f"cannot read client world catalog: {error}") from error
    ContractValidator(schema_path).validate(record)
    return decode_client_world_catalog(record)


def decode_client_world_catalog(record: Mapping[str, Any]) -> ClientWorldCatalog:
    maps = tuple(
        ClientWorldMap(
            map_id=int(item["map_id"]),
            internal_name=str(item["internal_name"]),
            classification=str(item["classification"]),
            map_artifact=str(item["map_artifact"]),
            map_artifact_sha256=str(item["map_artifact_sha256"]).lower(),
            nav_tiles_sha256=str(item["nav_tiles_sha256"]).lower(),
            coverage_state=str(item["coverage_state"]),
            interior_coverage=str(item["interior_coverage"]),
            road_semantic_coverage=str(item["road_semantic_coverage"]),
            road_semantics_sha256=str(item["road_semantics_sha256"]).lower(),
            tiles=tuple(
                WorldNavTile(
                    grid_x=int(tile["grid_x"]),
                    grid_y=int(tile["grid_y"]),
                    artifact=str(tile["artifact"]),
                    sha256=str(tile["sha256"]).lower(),
                )
                for tile in item["tiles"]
            ),
            road_semantics=tuple(
                WorldRoadSemantic(
                    grid_x=int(semantic["grid_x"]),
                    grid_y=int(semantic["grid_y"]),
                    artifact=str(semantic["artifact"]),
                    sha256=str(semantic["sha256"]).lower(),
                )
                for semantic in item["road_semantics"]
            ),
        )
        for item in record["maps"]
    )
    catalog = ClientWorldCatalog(
        catalog_id=str(record["catalog_id"]),
        target_profile=str(record["target_profile"]),
        product=str(record["product"]),
        expansion=str(record["expansion"]),
        client_version=str(record["client_version"]),
        client_build=str(record["client_build"]),
        asset_container=str(record["asset_container"]),
        asset_parser_profile=str(record["asset_parser_profile"]),
        world_catalog_asset=str(record["world_catalog_asset"]),
        world_catalog_asset_sha256=str(record["world_catalog_asset_sha256"]).lower(),
        nav_profile_id=str(record["nav_profile_id"]),
        maps=maps,
    )
    _validate_catalog_uniqueness(catalog)
    return catalog


def verify_client_world_catalog(
    catalog: ClientWorldCatalog,
    *,
    target_profile: str,
    client_version: str,
    client_build: str,
    nav_profile_id: str,
    nav_root: Path,
    world_catalog_asset_path: Path,
    allow_extra_unselected_artifacts: bool = False,
) -> VerifiedClientWorld:
    expected_identity = (
        ("target_profile", catalog.target_profile, target_profile),
        ("client_version", catalog.client_version, client_version),
        ("client_build", catalog.client_build, client_build),
        ("nav_profile_id", catalog.nav_profile_id, nav_profile_id),
    )
    for field, catalog_value, runtime_value in expected_identity:
        if catalog_value != runtime_value:
            raise ClientWorldCatalogError(
                f"{field} does not match client world catalog"
            )

    nav_root = nav_root.resolve()
    world_catalog_asset_path = world_catalog_asset_path.resolve()
    if not nav_root.is_dir():
        raise ClientWorldCatalogError("navigation profile root does not exist")
    if not world_catalog_asset_path.is_file():
        raise ClientWorldCatalogError("client world catalog asset does not exist")
    if _file_sha256(world_catalog_asset_path) != catalog.world_catalog_asset_sha256:
        raise ClientWorldCatalogError("client world catalog asset hash mismatch")

    client_maps = _parse_client_map_catalog(
        world_catalog_asset_path,
        parser_profile=catalog.asset_parser_profile,
    )
    expected_map_artifacts = {item.map_artifact for item in catalog.maps}
    actual_map_artifacts = {item.name for item in nav_root.glob("*.map") if item.is_file()}
    map_artifacts_match = (
        expected_map_artifacts.issubset(actual_map_artifacts)
        if allow_extra_unselected_artifacts
        else actual_map_artifacts == expected_map_artifacts
    )
    if not map_artifacts_match:
        raise ClientWorldCatalogError(
            "navigation map artifacts do not exactly match the versioned catalog"
        )
    semantic_directory = nav_root / "semantics"
    expected_semantic_artifacts = {
        semantic.artifact
        for world_map in catalog.maps
        for semantic in world_map.road_semantics
    }
    actual_semantic_artifacts = {
        item.name for item in semantic_directory.glob("*.road") if item.is_file()
    }
    semantic_artifacts_match = (
        expected_semantic_artifacts.issubset(actual_semantic_artifacts)
        if allow_extra_unselected_artifacts
        else actual_semantic_artifacts == expected_semantic_artifacts
    )
    if not semantic_artifacts_match:
        raise ClientWorldCatalogError(
            "road semantics do not exactly match the versioned catalog"
        )

    for world_map in catalog.maps:
        if client_maps.get(world_map.map_id) != world_map.internal_name:
            raise ClientWorldCatalogError(
                f"map_id {world_map.map_id} is not {world_map.internal_name!r} "
                "in the pinned client asset"
            )
        map_artifact_path = nav_root / world_map.map_artifact
        if _file_sha256(map_artifact_path) != world_map.map_artifact_sha256:
            raise ClientWorldCatalogError(
                f"navigation map artifact hash mismatch: {world_map.map_artifact}"
            )
        nav_directory = nav_root / "Nav" / world_map.internal_name
        expected_tiles = {item.artifact for item in world_map.tiles}
        actual_tiles = {
            item.name for item in nav_directory.glob("*.nav") if item.is_file()
        }
        if actual_tiles != expected_tiles:
            raise ClientWorldCatalogError(
                f"navigation tiles do not exactly match catalog map "
                f"{world_map.internal_name!r}"
            )
        tile_by_name = {item.artifact: item for item in world_map.tiles}
        for tile_name in sorted(expected_tiles):
            if _file_sha256(nav_directory / tile_name) != tile_by_name[tile_name].sha256:
                raise ClientWorldCatalogError(
                    f"navigation tile hash mismatch: {world_map.internal_name}/{tile_name}"
                )
        if _named_files_sha256(nav_directory, "*.nav") != world_map.nav_tiles_sha256:
            raise ClientWorldCatalogError(
                f"navigation tile-set hash mismatch: {world_map.internal_name}"
            )
        semantic_by_name = {
            item.artifact: item for item in world_map.road_semantics
        }
        for semantic_name in sorted(semantic_by_name):
            if (
                _file_sha256(semantic_directory / semantic_name)
                != semantic_by_name[semantic_name].sha256
            ):
                raise ClientWorldCatalogError(
                    f"road semantic hash mismatch: {semantic_name}"
                )
        if (
            _named_files_sha256(
                semantic_directory,
                f"{world_map.internal_name}_*.road",
            )
            != world_map.road_semantics_sha256
        ):
            raise ClientWorldCatalogError(
                f"road semantic-set hash mismatch: {world_map.internal_name}"
            )

    return VerifiedClientWorld(
        catalog=catalog,
        nav_root=nav_root,
        world_catalog_asset_path=world_catalog_asset_path,
    )


def build_client_world_catalog_record(
    profile: Mapping[str, Any],
    *,
    nav_root: Path,
    world_catalog_asset_path: Path,
    strict_root_artifacts: bool = True,
) -> dict[str, Any]:
    """Build one deterministic catalog from client identities and baked maps."""
    nav_root = nav_root.resolve()
    world_catalog_asset_path = world_catalog_asset_path.resolve()
    if not nav_root.is_dir():
        raise ClientWorldCatalogError("navigation profile root does not exist")
    if not world_catalog_asset_path.is_file():
        raise ClientWorldCatalogError("client world catalog asset does not exist")

    parser_profile = str(profile["asset_parser_profile"])
    client_maps = parse_client_map_catalog(
        world_catalog_asset_path,
        parser_profile=parser_profile,
    )
    map_id_by_name: dict[str, int] = {}
    for map_id, internal_name in client_maps.items():
        if internal_name in map_id_by_name:
            raise ClientWorldCatalogError(
                f"client catalog map name is not unique: {internal_name!r}"
            )
        map_id_by_name[internal_name] = map_id

    metadata_items = profile["maps"]
    metadata_by_id = {int(item["map_id"]): item for item in metadata_items}
    if len(metadata_by_id) != len(metadata_items):
        raise ClientWorldCatalogError("coverage profile map_id values must be unique")

    map_artifacts = sorted(
        (path for path in nav_root.glob("*.map") if path.is_file()),
        key=lambda path: path.name,
    )
    if not map_artifacts:
        raise ClientWorldCatalogError("navigation profile contains no map artifacts")
    if not strict_root_artifacts:
        selected_names = {
            str(item["internal_name"]) for item in metadata_items
        }
        map_artifacts = [
            path for path in map_artifacts if path.stem in selected_names
        ]
        if not map_artifacts:
            raise ClientWorldCatalogError(
                "shared navigation root contains none of the reviewed maps"
            )
    discovered_ids: set[int] = set()
    maps: list[dict[str, Any]] = []
    for map_artifact_path in map_artifacts:
        internal_name = map_artifact_path.stem
        map_id = map_id_by_name.get(internal_name)
        if map_id is None:
            raise ClientWorldCatalogError(
                f"navigation map is absent from client catalog: {internal_name!r}"
            )
        metadata = metadata_by_id.get(map_id)
        if metadata is None:
            raise ClientWorldCatalogError(
                f"navigation map has no reviewed coverage metadata: {internal_name!r}"
            )
        if str(metadata["internal_name"]) != internal_name:
            raise ClientWorldCatalogError(
                f"coverage metadata does not match map_id {map_id}"
            )
        nav_directory = nav_root / "Nav" / internal_name
        tile_paths = sorted(
            (path for path in nav_directory.glob("*.nav") if path.is_file()),
            key=lambda path: path.name,
        )
        if not tile_paths:
            raise ClientWorldCatalogError(
                f"navigation map has no tiles: {internal_name!r}"
            )
        semantic_directory = nav_root / "semantics"
        tile_records: list[dict[str, Any]] = []
        semantic_records: list[dict[str, Any]] = []
        for tile_path in tile_paths:
            grid_x, grid_y = _tile_coordinates_from_name(tile_path.name)
            tile_records.append(
                {
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "artifact": tile_path.name,
                    "sha256": _file_sha256(tile_path),
                }
            )
            semantic_name = f"{internal_name}_{grid_x:02d}_{grid_y:02d}.road"
            semantic_path = semantic_directory / semantic_name
            if not semantic_path.is_file():
                raise ClientWorldCatalogError(
                    f"navigation tile has no road semantic: {internal_name}/{tile_path.name}"
                )
            semantic_records.append(
                {
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "artifact": semantic_name,
                    "sha256": _file_sha256(semantic_path),
                }
            )
        actual_semantics = {
            path.name
            for path in semantic_directory.glob(f"{internal_name}_*.road")
            if path.is_file()
        }
        expected_semantics = {item["artifact"] for item in semantic_records}
        if actual_semantics != expected_semantics:
            raise ClientWorldCatalogError(
                f"road semantics do not exactly match navigation tiles for {internal_name!r}"
            )
        maps.append(
            {
                "map_id": map_id,
                "internal_name": internal_name,
                "classification": str(metadata["classification"]),
                "map_artifact": map_artifact_path.name,
                "map_artifact_sha256": _file_sha256(map_artifact_path),
                "nav_tiles_sha256": _named_files_sha256(nav_directory, "*.nav"),
                "coverage_state": str(metadata["coverage_state"]),
                "interior_coverage": str(metadata["interior_coverage"]),
                "road_semantic_coverage": str(metadata["road_semantic_coverage"]),
                "road_semantics_sha256": _named_files_sha256(
                    semantic_directory,
                    f"{internal_name}_*.road",
                ),
                "tiles": tile_records,
                "road_semantics": semantic_records,
            }
        )
        discovered_ids.add(map_id)
    if discovered_ids != set(metadata_by_id):
        raise ClientWorldCatalogError(
            "coverage metadata and baked navigation maps do not exactly match"
        )
    expected_all_semantics = {
        str(semantic["artifact"])
        for world_map in maps
        for semantic in world_map["road_semantics"]
    }
    actual_all_semantics = {
        path.name
        for path in (nav_root / "semantics").glob("*.road")
        if path.is_file()
    }
    if strict_root_artifacts and actual_all_semantics != expected_all_semantics:
        raise ClientWorldCatalogError(
            "road semantics and baked navigation maps do not exactly match"
        )

    maps.sort(key=lambda item: (int(item["map_id"]), str(item["internal_name"])))
    return {
        "record_type": "client_world_catalog",
        "schema_version": "1.0",
        "catalog_id": str(profile["catalog_id"]),
        "target_profile": str(profile["target_profile"]),
        "product": str(profile["product"]),
        "expansion": str(profile["expansion"]),
        "client_version": str(profile["client_version"]),
        "client_build": str(profile["client_build"]),
        "asset_container": str(profile["asset_container"]),
        "asset_parser_profile": parser_profile,
        "world_catalog_asset": str(profile["world_catalog_asset"]),
        "world_catalog_asset_sha256": _file_sha256(world_catalog_asset_path),
        "nav_profile_id": str(profile["nav_profile_id"]),
        "maps": maps,
        "execution_authority": False,
    }


def _validate_catalog_uniqueness(catalog: ClientWorldCatalog) -> None:
    map_ids = [item.map_id for item in catalog.maps]
    map_names = [item.internal_name for item in catalog.maps]
    map_artifacts = [item.map_artifact for item in catalog.maps]
    if len(set(map_ids)) != len(map_ids):
        raise ClientWorldCatalogError("catalog map_id values must be unique")
    if len(set(map_names)) != len(map_names):
        raise ClientWorldCatalogError("catalog internal map names must be unique")
    if len(set(map_artifacts)) != len(map_artifacts):
        raise ClientWorldCatalogError("catalog map artifacts must be unique")
    for world_map in catalog.maps:
        tile_names = [item.artifact for item in world_map.tiles]
        tile_coordinates = [(item.grid_x, item.grid_y) for item in world_map.tiles]
        semantic_names = [item.artifact for item in world_map.road_semantics]
        semantic_coordinates = [
            (item.grid_x, item.grid_y) for item in world_map.road_semantics
        ]
        if len(set(tile_names)) != len(tile_names):
            raise ClientWorldCatalogError("catalog navigation tile names must be unique")
        if len(set(tile_coordinates)) != len(tile_coordinates):
            raise ClientWorldCatalogError(
                "catalog navigation tile coordinates must be unique"
            )
        if len(set(semantic_names)) != len(semantic_names):
            raise ClientWorldCatalogError("catalog road semantic names must be unique")
        if len(set(semantic_coordinates)) != len(semantic_coordinates):
            raise ClientWorldCatalogError(
                "catalog road semantic coordinates must be unique"
            )
        if set(tile_coordinates) != set(semantic_coordinates):
            raise ClientWorldCatalogError(
                "catalog navigation tiles and road semantics must cover identical coordinates"
            )
        for tile in world_map.tiles:
            expected_name = f"{tile.grid_x:02d}_{tile.grid_y:02d}.nav"
            if tile.artifact != expected_name:
                raise ClientWorldCatalogError(
                    f"tile coordinates do not match artifact {tile.artifact!r}"
                )
        for semantic in world_map.road_semantics:
            expected_name = (
                f"{world_map.internal_name}_{semantic.grid_x:02d}_"
                f"{semantic.grid_y:02d}.road"
            )
            if semantic.artifact != expected_name:
                raise ClientWorldCatalogError(
                    "road semantic coordinates do not match artifact "
                    f"{semantic.artifact!r}"
                )


def parse_client_map_catalog(path: Path, *, parser_profile: str) -> dict[int, str]:
    if parser_profile != "wow-wdbc-map-v1":
        raise ClientWorldCatalogError(
            f"unsupported client world catalog parser profile: {parser_profile}"
        )
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"WDBC":
        raise ClientWorldCatalogError("client Map catalog is not a WDBC table")
    record_count, field_count, record_size, string_size = struct.unpack_from(
        "<4I", data, 4
    )
    if field_count < 2 or record_size < 8:
        raise ClientWorldCatalogError("client Map catalog record layout is invalid")
    records_end = 20 + record_count * record_size
    strings_end = records_end + string_size
    if records_end < 20 or strings_end != len(data):
        raise ClientWorldCatalogError("client Map catalog byte length is invalid")
    result: dict[int, str] = {}
    for index in range(record_count):
        offset = 20 + index * record_size
        map_id, name_offset = struct.unpack_from("<2I", data, offset)
        if name_offset >= string_size:
            raise ClientWorldCatalogError("client Map catalog string offset is invalid")
        string_start = records_end + name_offset
        string_stop = data.find(b"\0", string_start, strings_end)
        if string_stop < 0:
            raise ClientWorldCatalogError("client Map catalog string is unterminated")
        try:
            internal_name = data[string_start:string_stop].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ClientWorldCatalogError(
                "client Map catalog contains an invalid map name"
            ) from error
        if not internal_name or map_id in result:
            raise ClientWorldCatalogError("client Map catalog map identity is invalid")
        result[map_id] = internal_name
    return result


def _parse_client_map_catalog(path: Path, *, parser_profile: str) -> dict[int, str]:
    """Backward-compatible private alias for the initial verifier."""
    return parse_client_map_catalog(path, parser_profile=parser_profile)


def _tile_coordinates_from_name(name: str) -> tuple[int, int]:
    if len(name) != 9 or name[2] != "_" or not name.endswith(".nav"):
        raise ClientWorldCatalogError(f"invalid navigation tile name: {name!r}")
    try:
        grid_x = int(name[:2])
        grid_y = int(name[3:5])
    except ValueError as error:
        raise ClientWorldCatalogError(
            f"invalid navigation tile coordinates: {name!r}"
        ) from error
    if not (0 <= grid_x <= 63 and 0 <= grid_y <= 63):
        raise ClientWorldCatalogError(
            f"navigation tile coordinates are outside the WoW ADT grid: {name!r}"
        )
    return grid_x, grid_y


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ClientWorldCatalogError(f"cannot hash artifact {path.name!r}") from error
    return digest.hexdigest()


def _named_files_sha256(directory: Path, pattern: str) -> str:
    files = sorted(directory.glob(pattern), key=lambda item: item.name)
    if not files:
        raise ClientWorldCatalogError(f"artifact set is empty: {pattern}")
    digest = hashlib.sha256()
    for path in files:
        encoded_name = path.name.encode("ascii", "strict")
        digest.update(len(encoded_name).to_bytes(2, "little"))
        digest.update(encoded_name)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _nav_tiles_sha256(nav_directory: Path) -> str:
    """Backward-compatible alias retained for external fixture users."""
    return _named_files_sha256(nav_directory, "*.nav")
