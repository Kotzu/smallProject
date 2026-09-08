from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_adapter import (
    resolve_client_world_adapter,
)
from perfect_assassin.movement.client_world_inventory import (
    build_client_world_asset_inventory_record,
)


INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
COVERAGE_SCHEMA = ROOT / "contracts" / "client-world-coverage-profile.schema.json"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic, Map.dbc-bound inventory of all WDT and ADT "
            "assets present in a TBC MPQ client."
        )
    )
    parser.add_argument("--coverage-profile", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--world-catalog-asset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = _read_json(args.coverage_profile)
    ContractValidator(COVERAGE_SCHEMA).validate(profile)
    resolve_client_world_adapter(
        asset_container=str(profile["asset_container"]),
        world_catalog_parser_profile=str(profile["asset_parser_profile"]),
    )
    completed = subprocess.run(
        [str(args.extractor), "--inventory-world", str(args.data_root)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=120,
    )
    probe = json.loads(completed.stdout)
    if not isinstance(probe, dict):
        raise ValueError("native MPQ inventory did not return one JSON object")
    record = build_client_world_asset_inventory_record(
        probe,
        identity_profile=profile,
        world_catalog_asset_path=args.world_catalog_asset,
    )
    ContractValidator(INVENTORY_SCHEMA).validate(record)
    if args.check:
        if _read_json(args.output) != record:
            raise SystemExit("client world asset inventory is stale or mismatched")
        status = "VERIFIED"
    else:
        _atomic_write_json(args.output, record)
        status = "GENERATED"
    maps_with_adt = sum(item["adt_count"] > 0 for item in record["maps"])
    print(json.dumps({
        "status": status,
        "catalog_id": record["catalog_id"],
        "map_count": record["map_count"],
        "maps_with_wdt": sum(item["wdt_present"] for item in record["maps"]),
        "maps_with_adt": maps_with_adt,
        "total_adt_tiles": sum(item["adt_count"] for item in record["maps"]),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
