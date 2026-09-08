from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.client_world_bake import (
    build_client_world_bake_queue_record,
)
from perfect_assassin.contract_validation import ContractValidator


BAKE_QUEUE_SCHEMA = ROOT / "contracts" / "client-world-bake-queue.schema.json"


def _read_object(path: Path) -> dict[str, object]:
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


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic, resumable map-by-map client nav bake queue."
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    record = build_client_world_bake_queue_record(
        _read_object(args.inventory),
        asset_root=args.asset_root,
        nav_root=args.nav_root,
    )
    ContractValidator(BAKE_QUEUE_SCHEMA).validate(record)
    if args.check:
        if _read_object(args.output) != record:
            raise SystemExit("client world bake queue is stale or mismatched")
        status = "VERIFIED"
    else:
        _atomic_write(args.output, record)
        status = "GENERATED"
    print(json.dumps({
        "status": status,
        "catalog_id": record["catalog_id"],
        "eligible_map_count": record["eligible_map_count"],
        "eligible_adt_count": record["eligible_adt_count"],
        "complete_map_count": record["complete_map_count"],
        "bvh_ready": record["bvh_ready"],
        "bvh_artifact_count": record["bvh_artifact_count"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
