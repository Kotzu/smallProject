from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


class ClientWorldBakeError(ValueError):
    """Raised when a versioned client-world bake state is inconsistent."""


def _expected_coordinates(item: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    coordinates = tuple(
        (int(tile["grid_x"]), int(tile["grid_y"]))
        for tile in item["tiles"]
    )
    if (
        len(coordinates) != int(item["adt_count"])
        or len(set(coordinates)) != len(coordinates)
        or coordinates != tuple(sorted(coordinates))
    ):
        raise ClientWorldBakeError("inventory ADT coordinates are inconsistent")
    return coordinates


def _map_bake_state(
    item: Mapping[str, Any], *, asset_root: Path, nav_root: Path,
) -> dict[str, Any]:
    map_id = int(item["map_id"])
    map_name = str(item["internal_name"])
    if (
        map_id < 0
        or not map_name
        or len(map_name) > 96
        or any(character in map_name for character in "\\/:*?\"<>|")
    ):
        raise ClientWorldBakeError("inventory map identity is invalid")
    coordinates = _expected_coordinates(item)
    if not coordinates or not bool(item["wdt_present"]):
        raise ClientWorldBakeError("bake queue accepts only maps with WDT and ADT")

    asset_directory = asset_root / map_name
    nav_directory = nav_root / "Nav" / map_name
    semantics_directory = nav_root / "semantics"
    expected_assets = {
        asset_directory / f"{map_name}_{grid_x}_{grid_y}.adt"
        for grid_x, grid_y in coordinates
    } | {asset_directory / f"{map_name}.wdt"}
    expected_nav = {
        nav_directory / f"{grid_x:02}_{grid_y:02}.nav"
        for grid_x, grid_y in coordinates
    }
    expected_semantics = {
        semantics_directory / f"{map_name}_{grid_x:02}_{grid_y:02}.road"
        for grid_x, grid_y in coordinates
    }

    existing_assets = (
        set(asset_directory.glob(f"{map_name}*.adt"))
        | set(asset_directory.glob(f"{map_name}.wdt"))
        if asset_directory.is_dir() else set()
    )
    existing_nav = set(nav_directory.glob("*.nav")) if nav_directory.is_dir() else set()
    existing_semantics = (
        set(semantics_directory.glob(f"{map_name}_*.road"))
        if semantics_directory.is_dir() else set()
    )
    asset_complete = existing_assets == expected_assets and all(
        path.stat().st_size > 0 for path in existing_assets
    )
    semantics_complete = existing_semantics == expected_semantics and all(
        path.stat().st_size > 0 for path in existing_semantics
    )
    nav_tiles_complete = existing_nav == expected_nav and all(
        path.stat().st_size > 0 for path in existing_nav
    )
    map_file = nav_root / f"{map_name}.map"
    nav_complete = (
        nav_tiles_complete and map_file.is_file() and map_file.stat().st_size > 0
    )

    partial_assets = bool(existing_assets) and not asset_complete
    partial_semantics = bool(existing_semantics) and not semantics_complete
    partial_nav = bool(existing_nav) or map_file.exists()
    if (nav_complete and not semantics_complete) or (
        semantics_complete and not asset_complete
    ):
        state, next_action = (
            "INCONSISTENT_DOWNSTREAM_ARTIFACTS",
            "AUDIT_VERSIONED_MAP_ARTIFACTS",
        )
    elif nav_complete and semantics_complete and asset_complete:
        state, next_action = "COMPLETE", "VALIDATE_CATALOG"
    elif partial_nav and not nav_complete:
        state, next_action = "NAVMESH_PARTIAL", "RESUME_NAVMESH"
    elif asset_complete and semantics_complete:
        state, next_action = "READY_FOR_NAVMESH", "BUILD_NAVMESH"
    elif partial_semantics:
        state, next_action = "SEMANTICS_PARTIAL", "RESUME_ROAD_SEMANTICS"
    elif asset_complete:
        state, next_action = "READY_FOR_SEMANTICS", "BUILD_ROAD_SEMANTICS"
    elif partial_assets:
        state, next_action = "EXTRACTION_PARTIAL", "RESTART_MAP_EXTRACTION"
    else:
        state, next_action = "READY_FOR_EXTRACTION", "EXTRACT_MAP_ASSETS"

    return {
        "map_id": map_id,
        "internal_name": map_name,
        "adt_count": len(coordinates),
        "adt_bounds": item["adt_bounds"],
        "asset_complete": asset_complete,
        "road_semantics_complete": semantics_complete,
        "navmesh_complete": nav_complete,
        "state": state,
        "next_action": next_action,
        "asset_directory": str(asset_directory.resolve()),
        "nav_directory": str(nav_directory.resolve()),
        "map_file": str(map_file.resolve()),
        "execution_authority": False,
    }


def build_client_world_bake_queue_record(
    inventory: Mapping[str, Any], *, asset_root: Path, nav_root: Path,
) -> dict[str, Any]:
    if (
        inventory.get("record_type") != "client_world_asset_inventory"
        or inventory.get("schema_version") != "1.0"
        or inventory.get("execution_authority") is not False
    ):
        raise ClientWorldBakeError("client world inventory identity is invalid")
    maps_value = inventory.get("maps")
    if not isinstance(maps_value, list):
        raise ClientWorldBakeError("client world inventory maps are invalid")
    eligible = [
        item for item in maps_value
        if isinstance(item, Mapping)
        and bool(item.get("wdt_present"))
        and int(item.get("adt_count", 0)) > 0
    ]
    maps = [
        _map_bake_state(item, asset_root=asset_root, nav_root=nav_root)
        for item in eligible
    ]
    if maps != sorted(maps, key=lambda item: (item["map_id"], item["internal_name"])):
        raise ClientWorldBakeError("client world inventory maps are not ordered")
    bvh_directory = nav_root / "BVH"
    bvh_index = bvh_directory / "bvh.idx"
    bvh_artifacts = (
        tuple(sorted(bvh_directory.glob("*.bvh")))
        if bvh_directory.is_dir() else ()
    )
    bvh_ready = (
        bvh_index.is_file()
        and bvh_index.stat().st_size > 0
        and bool(bvh_artifacts)
        and all(path.stat().st_size > 0 for path in bvh_artifacts)
    )
    return {
        "record_type": "client_world_bake_queue",
        "schema_version": "1.0",
        "catalog_id": str(inventory["catalog_id"]),
        "product": str(inventory["product"]),
        "expansion": str(inventory["expansion"]),
        "client_version": str(inventory["client_version"]),
        "client_build": str(inventory["client_build"]),
        "asset_container": str(inventory["asset_container"]),
        "asset_parser_profile": str(inventory["asset_parser_profile"]),
        "asset_root": str(asset_root.resolve()),
        "nav_root": str(nav_root.resolve()),
        "bvh_directory": str(bvh_directory.resolve()),
        "bvh_index": str(bvh_index.resolve()),
        "bvh_artifact_count": len(bvh_artifacts),
        "bvh_ready": bvh_ready,
        "eligible_map_count": len(maps),
        "eligible_adt_count": sum(item["adt_count"] for item in maps),
        "complete_map_count": sum(item["state"] == "COMPLETE" for item in maps),
        "maps": maps,
        "execution_authority": False,
    }
