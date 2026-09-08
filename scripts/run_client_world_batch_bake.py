from __future__ import annotations

import argparse
import hashlib
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


INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
BATCH_SCHEMA = ROOT / "contracts" / "client-world-batch-bake-result.schema.json"
MAP_RUNNER = ROOT / "scripts" / "run_client_world_map_bake.py"


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_maps(
    inventory: Mapping[str, Any], requested: tuple[str, ...],
) -> tuple[str, ...]:
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("batch map names must be non-empty and unique")
    eligible = {
        str(item["internal_name"])
        for item in inventory["maps"]
        if bool(item["wdt_present"]) and int(item["adt_count"]) > 0
    }
    if any(name not in eligible for name in requested):
        raise ValueError("batch contains a map without pinned WDT/ADT coverage")
    return requested


def _map_command(
    *,
    inventory: Path,
    map_name: str,
    extractor: Path,
    map_builder: Path,
    data_root: Path,
    asset_root: Path,
    nav_root: Path,
    queue_output: Path,
    result: Path,
    threads: int,
    timeout_seconds: int,
) -> tuple[str, ...]:
    return (
        sys.executable,
        str(MAP_RUNNER),
        "--inventory", str(inventory),
        "--map-name", map_name,
        "--extractor", str(extractor),
        "--map-builder", str(map_builder),
        "--data-root", str(data_root),
        "--asset-root", str(asset_root),
        "--nav-root", str(nav_root),
        "--queue-output", str(queue_output),
        "--result", str(result),
        "--threads", str(threads),
        "--timeout-seconds", str(timeout_seconds),
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run resumable client-world map bakes sequentially in one shared "
            "root so BVH writes and MPQ identity cannot race."
        )
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--map-name", action="append", required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--map-builder", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=21600)
    args = parser.parse_args(argv)
    if not 1 <= args.threads <= 64 or args.timeout_seconds <= 0:
        raise ValueError("batch threads or timeout are invalid")

    inventory_path = args.inventory.resolve()
    inventory = _read_object(inventory_path)
    ContractValidator(INVENTORY_SCHEMA).validate(inventory)
    maps = _selected_maps(inventory, tuple(args.map_name))
    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    completed_maps: list[dict[str, Any]] = []
    status = "PASS"
    for map_name in maps:
        queue_path = run_root / f"bake-queue-{map_name}.json"
        result_path = run_root / f"bake-result-{map_name}.json"
        command = _map_command(
            inventory=inventory_path,
            map_name=map_name,
            extractor=args.extractor.resolve(),
            map_builder=args.map_builder.resolve(),
            data_root=args.data_root.resolve(),
            asset_root=args.asset_root.resolve(),
            nav_root=args.nav_root.resolve(),
            queue_output=queue_path,
            result=result_path,
            threads=args.threads,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({"stage": "MAP_BAKE", "map": map_name}), flush=True)
        with (
            (run_root / f"{map_name}.stdout.log").open("wb") as stdout,
            (run_root / f"{map_name}.stderr.log").open("wb") as stderr,
        ):
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        map_result = _read_object(result_path) if result_path.is_file() else None
        item = {
            "internal_name": map_name,
            "return_code": int(completed.returncode),
            "result": str(result_path),
            "result_sha256": _sha256(result_path) if result_path.is_file() else None,
            "status": None if map_result is None else map_result.get("status"),
            "final_state": None if map_result is None else map_result.get("final_state"),
        }
        completed_maps.append(item)
        if completed.returncode != 0 or item["status"] != "PASS":
            status = "FAIL"
            break

    result = {
        "record_type": "client_world_batch_bake_result",
        "schema_version": "1.0",
        "status": status,
        "catalog_id": str(inventory["catalog_id"]),
        "client_build": str(inventory["client_build"]),
        "requested_maps": list(maps),
        "completed_maps": completed_maps,
        "map_builder": str(args.map_builder.resolve()),
        "map_builder_sha256": _sha256(args.map_builder.resolve()),
        "nav_root": str(args.nav_root.resolve()),
        "execution_authority": False,
    }
    ContractValidator(BATCH_SCHEMA).validate(result)
    _atomic_write(args.result, result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if status == "PASS" and len(completed_maps) == len(maps) else 3


if __name__ == "__main__":
    raise SystemExit(run())
