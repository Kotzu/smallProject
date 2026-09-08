from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from perfect_assassin.movement.client_world_catalog import (
    ClientWorldCatalogError,
    parse_client_map_catalog,
)
from perfect_assassin.movement.client_world_adapter import (
    ClientWorldAdapterError,
    resolve_client_world_adapter,
)


class ClientWorldInventoryError(ValueError):
    """Raised when an asset inventory is not the exact pinned client world."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ClientWorldInventoryError(
            f"cannot hash client world catalog asset: {error}"
        ) from error
    return digest.hexdigest()


def _validated_map_record(
    item: Mapping[str, Any],
    *,
    expected_name: str,
) -> dict[str, Any]:
    map_id = int(item["map_id"])
    internal_name = str(item["internal_name"])
    if internal_name != expected_name:
        raise ClientWorldInventoryError(
            f"inventory map_id {map_id} does not match Map.dbc"
        )
    tiles = tuple(
        (int(tile["grid_x"]), int(tile["grid_y"]))
        for tile in item["tiles"]
    )
    if len(set(tiles)) != len(tiles):
        raise ClientWorldInventoryError(
            f"inventory map {internal_name!r} has duplicate ADT coordinates"
        )
    if any(not 0 <= coordinate <= 63 for tile in tiles for coordinate in tile):
        raise ClientWorldInventoryError(
            f"inventory map {internal_name!r} has invalid ADT coordinates"
        )
    ordered_tiles = tuple(sorted(tiles))
    if tiles != ordered_tiles:
        raise ClientWorldInventoryError(
            f"inventory map {internal_name!r} ADTs are not deterministically ordered"
        )
    adt_count = int(item["adt_count"])
    if adt_count != len(tiles):
        raise ClientWorldInventoryError(
            f"inventory map {internal_name!r} ADT count is inconsistent"
        )
    bounds = item["adt_bounds"]
    expected_bounds: list[int] | None
    if not tiles:
        expected_bounds = None
    else:
        expected_bounds = [
            min(grid_x for grid_x, _grid_y in tiles),
            min(grid_y for _grid_x, grid_y in tiles),
            max(grid_x for grid_x, _grid_y in tiles),
            max(grid_y for _grid_x, grid_y in tiles),
        ]
    if bounds != expected_bounds:
        raise ClientWorldInventoryError(
            f"inventory map {internal_name!r} ADT bounds are inconsistent"
        )
    return {
        "map_id": map_id,
        "internal_name": internal_name,
        "wdt_present": bool(item["wdt_present"]),
        "adt_count": adt_count,
        "adt_bounds": expected_bounds,
        "tiles": [
            {"grid_x": grid_x, "grid_y": grid_y}
            for grid_x, grid_y in tiles
        ],
    }


def build_client_world_asset_inventory_record(
    probe: Mapping[str, Any],
    *,
    identity_profile: Mapping[str, Any],
    world_catalog_asset_path: Path,
) -> dict[str, Any]:
    """Bind a read-only asset probe to one exact versioned world identity."""

    asset_container = str(identity_profile["asset_container"])
    parser_profile = str(identity_profile["asset_parser_profile"])
    try:
        adapter = resolve_client_world_adapter(
            asset_container=asset_container,
            world_catalog_parser_profile=parser_profile,
        )
    except ClientWorldAdapterError as error:
        raise ClientWorldInventoryError(str(error)) from error

    if (
        probe.get("record_type") != "client_world_asset_inventory"
        or probe.get("schema_version") != "1.0"
        or probe.get("asset_container") != adapter.asset_container
        or probe.get("execution_authority") is not False
    ):
        raise ClientWorldInventoryError("native asset inventory identity is invalid")
    try:
        client_maps = parse_client_map_catalog(
            world_catalog_asset_path,
            parser_profile=parser_profile,
        )
    except ClientWorldCatalogError as error:
        raise ClientWorldInventoryError(str(error)) from error
    probe_maps = probe.get("maps")
    if not isinstance(probe_maps, list):
        raise ClientWorldInventoryError("native MPQ inventory maps are malformed")
    if int(probe.get("map_count", -1)) != len(probe_maps):
        raise ClientWorldInventoryError("native MPQ inventory map count is inconsistent")
    probe_by_id: dict[int, Mapping[str, Any]] = {}
    for item in probe_maps:
        if not isinstance(item, Mapping):
            raise ClientWorldInventoryError("native MPQ inventory map is malformed")
        map_id = int(item["map_id"])
        if map_id in probe_by_id:
            raise ClientWorldInventoryError("native MPQ inventory map IDs are not unique")
        probe_by_id[map_id] = item
    if set(probe_by_id) != set(client_maps):
        raise ClientWorldInventoryError(
            "native MPQ inventory and Map.dbc map IDs do not exactly match"
        )
    maps = [
        _validated_map_record(
            probe_by_id[map_id],
            expected_name=internal_name,
        )
        for map_id, internal_name in sorted(client_maps.items())
    ]
    return {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": str(identity_profile["catalog_id"]),
        "target_profile": str(identity_profile["target_profile"]),
        "product": str(identity_profile["product"]),
        "expansion": str(identity_profile["expansion"]),
        "client_version": str(identity_profile["client_version"]),
        "client_build": str(identity_profile["client_build"]),
        "asset_container": adapter.asset_container,
        "asset_parser_profile": parser_profile,
        "world_catalog_asset": str(identity_profile["world_catalog_asset"]),
        "world_catalog_asset_sha256": _sha256(world_catalog_asset_path),
        "map_count": len(maps),
        "maps": maps,
        "execution_authority": False,
    }
