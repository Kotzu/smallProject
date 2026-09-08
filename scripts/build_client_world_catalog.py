from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_catalog import (
    build_client_world_catalog_record,
    decode_client_world_catalog,
    parse_client_map_catalog,
)
from perfect_assassin.movement.client_world_bake import (
    build_client_world_bake_queue_record,
)


COVERAGE_SCHEMA = ROOT / "contracts" / "client-world-coverage-profile.schema.json"
CATALOG_SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
QUEUE_SCHEMA = ROOT / "contracts" / "client-world-bake-queue.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic client/build-bound world catalog from "
            "reviewed coverage metadata and actual navigation artifacts."
        )
    )
    parser.add_argument("--coverage-profile", type=Path, required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--world-catalog-asset", type=Path, required=True)
    parser.add_argument(
        "--inventory",
        type=Path,
        help=(
            "pinned client asset inventory; required with --queue whenever "
            "the coverage profile declares a complete map"
        ),
    )
    parser.add_argument(
        "--queue",
        type=Path,
        help=(
            "current bake queue; required with --inventory whenever the "
            "coverage profile declares a complete map"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that --output already equals the generated catalog",
    )
    parser.add_argument(
        "--shared-nav-root",
        action="store_true",
        help=(
            "select only profile-declared maps from a shared bake root; "
            "selected map artifacts remain exact and hash-verified"
        ),
    )
    return parser


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _validate_complete_coverage_evidence(
    *,
    coverage_profile: dict[str, Any],
    inventory: dict[str, Any] | None,
    queue: dict[str, Any] | None,
    nav_root: Path,
) -> None:
    complete_maps = [
        item for item in coverage_profile["maps"]
        if item["coverage_state"] == "complete"
    ]
    if not complete_maps:
        return
    if inventory is None or queue is None:
        raise ValueError(
            "complete coverage requires exact --inventory and --queue evidence"
        )
    ContractValidator(INVENTORY_SCHEMA).validate(inventory)
    ContractValidator(QUEUE_SCHEMA).validate(queue)
    identity_keys = (
        "product", "expansion", "client_version", "client_build",
        "asset_container", "asset_parser_profile",
    )
    if any(
        coverage_profile[key] != inventory[key]
        or inventory[key] != queue[key]
        for key in identity_keys
    ):
        raise ValueError("complete coverage evidence has a client identity mismatch")
    if inventory["catalog_id"] != queue["catalog_id"]:
        raise ValueError("complete coverage evidence has an inventory/queue mismatch")
    if Path(str(queue["nav_root"])).resolve() != nav_root.resolve():
        raise ValueError("complete coverage evidence has a navigation root mismatch")

    rebuilt_queue = build_client_world_bake_queue_record(
        inventory,
        asset_root=Path(str(queue["asset_root"])),
        nav_root=nav_root,
    )
    if rebuilt_queue != queue:
        raise ValueError("complete coverage queue is stale or does not match its files")
    inventory_maps = {
        (int(item["map_id"]), str(item["internal_name"])): item
        for item in inventory["maps"]
    }
    queue_maps = {
        (int(item["map_id"]), str(item["internal_name"])): item
        for item in queue["maps"]
    }
    if (
        len(inventory_maps) != len(inventory["maps"])
        or len(queue_maps) != len(queue["maps"])
    ):
        raise ValueError("complete coverage evidence map identities are not unique")
    for profile_map in complete_maps:
        key = (int(profile_map["map_id"]), str(profile_map["internal_name"]))
        inventory_map = inventory_maps.get(key)
        queue_map = queue_maps.get(key)
        if inventory_map is None or queue_map is None:
            raise ValueError("complete map is absent from pinned client bake evidence")
        if (
            not bool(inventory_map["wdt_present"])
            or int(inventory_map["adt_count"]) <= 0
            or int(queue_map["adt_count"]) != int(inventory_map["adt_count"])
            or queue_map["state"] != "COMPLETE"
            or queue_map["asset_complete"] is not True
            or queue_map["road_semantics_complete"] is not True
            or queue_map["navmesh_complete"] is not True
        ):
            raise ValueError(
                "complete map does not exactly match pinned ADT, semantic, and nav assets"
            )


def _coverage_report(
    *,
    catalog_record: dict[str, Any],
    world_catalog_asset_path: Path,
) -> dict[str, Any]:
    catalog = decode_client_world_catalog(catalog_record)
    client_maps = parse_client_map_catalog(
        world_catalog_asset_path,
        parser_profile=catalog.asset_parser_profile,
    )
    baked_by_id = {item.map_id: item for item in catalog.maps}
    maps: list[dict[str, Any]] = []
    for map_id, internal_name in sorted(client_maps.items()):
        baked = baked_by_id.get(map_id)
        maps.append(
            {
                "map_id": map_id,
                "internal_name": internal_name,
                "navigation_state": (
                    "missing"
                    if baked is None
                    else f"baked_{baked.coverage_state}"
                ),
                "interior_coverage": (
                    "none" if baked is None else baked.interior_coverage
                ),
                "road_semantic_coverage": (
                    "none" if baked is None else baked.road_semantic_coverage
                ),
                "tile_count": 0 if baked is None else len(baked.tiles),
                "road_semantic_count": (
                    0 if baked is None else len(baked.road_semantics)
                ),
            }
        )
    baked_maps = sum(item["navigation_state"] != "missing" for item in maps)
    complete_maps = sum(item["navigation_state"] == "baked_complete" for item in maps)
    return {
        "record_type": "client_world_coverage_report",
        "schema_version": "1.0",
        "catalog_id": catalog.catalog_id,
        "client_build": catalog.client_build,
        "client_map_count": len(maps),
        "baked_map_count": baked_maps,
        "complete_map_count": complete_maps,
        "missing_map_count": len(maps) - baked_maps,
        "maps": maps,
        "execution_authority": False,
    }


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    coverage_profile = _read_json(args.coverage_profile)
    ContractValidator(COVERAGE_SCHEMA).validate(coverage_profile)
    if (args.inventory is None) != (args.queue is None):
        raise ValueError("--inventory and --queue must be provided together")
    inventory = None if args.inventory is None else _read_json(args.inventory)
    queue = None if args.queue is None else _read_json(args.queue)
    _validate_complete_coverage_evidence(
        coverage_profile=coverage_profile,
        inventory=inventory,
        queue=queue,
        nav_root=args.nav_root,
    )
    catalog_record = build_client_world_catalog_record(
        coverage_profile,
        nav_root=args.nav_root,
        world_catalog_asset_path=args.world_catalog_asset,
        strict_root_artifacts=not args.shared_nav_root,
    )
    ContractValidator(CATALOG_SCHEMA).validate(catalog_record)

    if args.check:
        existing = _read_json(args.output)
        if existing != catalog_record:
            raise SystemExit("client world catalog is stale or does not match its assets")
        status = "VERIFIED"
    else:
        _atomic_write_json(args.output, catalog_record)
        status = "GENERATED"

    report = _coverage_report(
        catalog_record=catalog_record,
        world_catalog_asset_path=args.world_catalog_asset,
    )
    if args.coverage_report is not None:
        _atomic_write_json(args.coverage_report, report)
    print(
        json.dumps(
            {
                "status": status,
                "catalog_id": catalog_record["catalog_id"],
                "client_maps": report["client_map_count"],
                "baked_maps": report["baked_map_count"],
                "complete_maps": report["complete_map_count"],
                "missing_maps": report["missing_map_count"],
                "shared_nav_root": args.shared_nav_root,
                "execution_authority": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
