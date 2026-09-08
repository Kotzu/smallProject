from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_adapter import (
    resolve_client_world_adapter,
)
from perfect_assassin.movement.client_world_bake import (
    build_client_world_bake_queue_record,
)


INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
QUEUE_SCHEMA = ROOT / "contracts" / "client-world-bake-queue.schema.json"
RESULT_SCHEMA = ROOT / "contracts" / "client-world-map-bake-result.schema.json"
ROAD_SCRIPT = ROOT / "scripts" / "build_adt_road_semantics.py"


@dataclass(frozen=True, slots=True)
class MapBakeCommands:
    bvh: tuple[str, ...]
    extraction: tuple[str, ...]
    semantics: tuple[str, ...]
    navmesh: tuple[str, ...]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _atomic_write(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _inventory_map(inventory: Mapping[str, Any], map_name: str) -> Mapping[str, Any]:
    maps = inventory.get("maps")
    if not isinstance(maps, list):
        raise ValueError("inventory maps are invalid")
    matches = [
        item for item in maps
        if isinstance(item, Mapping) and item.get("internal_name") == map_name
    ]
    if len(matches) != 1:
        raise ValueError("map name is not unique in the pinned inventory")
    item = matches[0]
    if not item.get("wdt_present") or int(item.get("adt_count", 0)) <= 0:
        raise ValueError("map has no standalone client terrain to bake")
    return item


def build_map_bake_commands(
    *,
    python_executable: Path,
    road_script: Path,
    extractor: Path,
    map_builder: Path,
    data_root: Path,
    asset_root: Path,
    nav_root: Path,
    map_name: str,
    threads: int,
) -> MapBakeCommands:
    if not 1 <= threads <= 32:
        raise ValueError("map bake thread count is invalid")
    asset_directory = (asset_root / map_name).resolve()
    if asset_directory.parent != asset_root.resolve():
        raise ValueError("map asset destination escaped its root")
    return MapBakeCommands(
        bvh=(
            str(map_builder), "-d", str(data_root), "-b", "-o", str(nav_root),
            "-t", str(threads), "-l", "2",
        ),
        extraction=(
            str(extractor), "--extract-map", str(data_root), map_name,
            str(asset_directory),
        ),
        semantics=(
            str(python_executable), str(road_script), str(asset_directory),
            str((nav_root / "semantics").resolve()), "--map-name", map_name,
        ),
        navmesh=(
            str(map_builder), "-d", str(data_root), "-m", map_name,
            "-o", str(nav_root), "-t", str(threads), "-l", "2",
        ),
    )


def _queue(
    inventory: Mapping[str, Any], *, asset_root: Path, nav_root: Path,
) -> dict[str, Any]:
    record = build_client_world_bake_queue_record(
        inventory, asset_root=asset_root, nav_root=nav_root,
    )
    ContractValidator(QUEUE_SCHEMA).validate(record)
    return record


def _result_provenance(inventory: Mapping[str, Any]) -> dict[str, Any]:
    adapter = resolve_client_world_adapter(
        asset_container=str(inventory["asset_container"]),
        world_catalog_parser_profile=str(inventory["asset_parser_profile"]),
    )
    return {
        "product": inventory["product"],
        "expansion": inventory["expansion"],
        "client_version": inventory["client_version"],
        "client_build": inventory["client_build"],
        "asset_container": inventory["asset_container"],
        "asset_adapter_id": adapter.adapter_id,
        "world_source": "PINNED_CLIENT_ASSETS_ONLY",
        "server_dependency": False,
        "emulator_dependency": False,
    }


def _write_result(path: Path, result: Mapping[str, Any]) -> None:
    ContractValidator(RESULT_SCHEMA).validate(result)
    _atomic_write(path, result)


def _map_state(queue: Mapping[str, Any], map_name: str) -> Mapping[str, Any]:
    matches = [item for item in queue["maps"] if item["internal_name"] == map_name]
    if len(matches) != 1:
        raise RuntimeError("map disappeared from standalone bake queue")
    return matches[0]


def _run_logged(
    command: tuple[str, ...], *, log_path: Path, timeout_seconds: int,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f"\n[{datetime.now(timezone.utc).isoformat()}] START "
            + json.dumps(command, ensure_ascii=False) + "\n"
        )
        stream.flush()
        completed = subprocess.run(
            list(command), stdout=stream, stderr=subprocess.STDOUT,
            check=False, text=True, timeout=timeout_seconds,
        )
        stream.write(f"RETURN_CODE {completed.returncode}\n")
        stream.flush()
        os.fsync(stream.fileno())
    if completed.returncode != 0:
        raise RuntimeError(f"standalone bake stage failed; inspect {log_path}")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resume one exact client map through the standalone nav bake pipeline."
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--map-builder", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--queue-output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not 60 <= args.timeout_seconds <= 21600:
        parser.error("--timeout-seconds must be in [60, 21600]")
    inventory = _read_object(args.inventory)
    ContractValidator(INVENTORY_SCHEMA).validate(inventory)
    resolve_client_world_adapter(
        asset_container=str(inventory["asset_container"]),
        world_catalog_parser_profile=str(inventory["asset_parser_profile"]),
    )
    item = _inventory_map(inventory, args.map_name)
    for path, label in (
        (args.extractor, "extractor"),
        (args.map_builder, "MapBuilder"),
        (ROAD_SCRIPT, "road semantics script"),
    ):
        if not path.is_file():
            raise SystemExit(f"{label} is unavailable: {path}")
    if not args.data_root.is_dir():
        raise SystemExit("client data root is unavailable")
    commands = build_map_bake_commands(
        python_executable=Path(sys.executable), road_script=ROAD_SCRIPT,
        extractor=args.extractor.resolve(), map_builder=args.map_builder.resolve(),
        data_root=args.data_root.resolve(), asset_root=args.asset_root.resolve(),
        nav_root=args.nav_root.resolve(), map_name=args.map_name,
        threads=args.threads,
    )
    queue = _queue(inventory, asset_root=args.asset_root, nav_root=args.nav_root)
    _atomic_write(args.queue_output, queue)
    initial_state = str(_map_state(queue, args.map_name)["state"])
    if args.dry_run:
        result = {
            "record_type": "client_world_map_bake_result",
            "schema_version": "1.0",
            "status": "DRY_RUN",
            "catalog_id": inventory["catalog_id"],
            "map_id": item["map_id"],
            "internal_name": args.map_name,
            "initial_state": initial_state,
            "bvh_ready": queue["bvh_ready"],
            **_result_provenance(inventory),
            "commands": {
                name: list(getattr(commands, name))
                for name in ("bvh", "extraction", "semantics", "navmesh")
            },
            "execution_authority": False,
        }
        _write_result(args.result, result)
        print(json.dumps(result, sort_keys=True))
        return 0

    log_root = args.nav_root / "build-logs"
    if not queue["bvh_ready"]:
        print(json.dumps({"stage": "BVH", "map": args.map_name}), flush=True)
        _run_logged(
            commands.bvh, log_path=log_root / "bvh.log",
            timeout_seconds=args.timeout_seconds,
        )
        queue = _queue(inventory, asset_root=args.asset_root, nav_root=args.nav_root)
        _atomic_write(args.queue_output, queue)
        if not queue["bvh_ready"]:
            raise RuntimeError("BVH stage did not produce structural readiness")

    performed: list[str] = []
    for _stage in range(4):
        state = str(_map_state(queue, args.map_name)["state"])
        if state == "COMPLETE":
            break
        if state == "READY_FOR_EXTRACTION":
            command, action = commands.extraction, "EXTRACT_MAP_ASSETS"
        elif state in {"READY_FOR_SEMANTICS", "SEMANTICS_PARTIAL"}:
            command, action = commands.semantics, "BUILD_ROAD_SEMANTICS"
        elif state in {"READY_FOR_NAVMESH", "NAVMESH_PARTIAL"}:
            command, action = commands.navmesh, "BUILD_NAVMESH"
        else:
            raise RuntimeError(f"map bake state requires audit: {state}")
        print(json.dumps({"stage": action, "map": args.map_name}), flush=True)
        _run_logged(
            command,
            log_path=log_root / f"{args.map_name}.{action.lower()}.log",
            timeout_seconds=args.timeout_seconds,
        )
        performed.append(action)
        previous_state = state
        queue = _queue(inventory, asset_root=args.asset_root, nav_root=args.nav_root)
        state = str(_map_state(queue, args.map_name)["state"])
        if state == previous_state:
            raise RuntimeError(f"standalone bake stage made no progress: {state}")
        _atomic_write(args.queue_output, queue)
    final_state = str(_map_state(queue, args.map_name)["state"])
    result = {
        "record_type": "client_world_map_bake_result",
        "schema_version": "1.0",
        "status": "PASS" if final_state == "COMPLETE" else "FAIL",
        "catalog_id": inventory["catalog_id"],
        "map_id": item["map_id"],
        "internal_name": args.map_name,
        "initial_state": initial_state,
        "final_state": final_state,
        "bvh_ready": queue["bvh_ready"],
        **_result_provenance(inventory),
        "performed_actions": performed,
        "execution_authority": False,
    }
    _atomic_write(args.queue_output, queue)
    _write_result(args.result, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(run())
