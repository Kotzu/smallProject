from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.structure_access_scan_plan import (
    StructureAccessScanPlanError,
    build_structure_access_scan_plan_record,
    load_structure_access_scan_plan,
)
from perfect_assassin.movement.world_pack_runtime import (
    load_world_pack_runtime_profile,
)
from perfect_assassin.movement.world_structure_index import (
    load_world_structure_index,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise StructureAccessScanPlanError(
            f"cannot hash probe worker: {error}"
        ) from error
    return digest.hexdigest()


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
        description=(
            "Build or verify a deterministic, resumable access scan plan for "
            "every WMO covered by one sealed WorldPack map."
        )
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    binding = load_world_pack_runtime_profile(
        args.profile,
        store_root=args.store_root,
        profile_schema_path=ROOT / "contracts" / "world-pack-runtime-profile.schema.json",
        pack_schema_path=ROOT / "contracts" / "standalone-world-pack.schema.json",
        catalog_schema_path=ROOT / "contracts" / "client-world-catalog.schema.json",
    )
    loaded_index = load_world_structure_index(
        args.index,
        schema_path=ROOT / "contracts" / "world-structure-index.schema.json",
        pack=binding.pack,
    )
    worker_sha256 = _sha256(args.worker)
    expected = build_structure_access_scan_plan_record(
        binding.pack,
        structure_index_record=loaded_index.record,
        probe_worker_sha256=worker_sha256,
    )
    schema_path = ROOT / "contracts" / "structure-access-scan-plan.schema.json"
    ContractValidator(schema_path).validate(expected)
    if args.check:
        existing = load_structure_access_scan_plan(
            args.output,
            schema_path=schema_path,
            pack=binding.pack,
            structure_index_record=loaded_index.record,
            expected_probe_worker_sha256=worker_sha256,
        )
        if dict(existing) != expected:
            raise StructureAccessScanPlanError(
                "structure access scan plan is stale or mismatched"
            )
        status = "VERIFIED"
    else:
        if args.output.exists():
            raise StructureAccessScanPlanError(
                "structure access scan plan already exists; use --check or a new path"
            )
        _atomic_write(args.output, expected)
        status = "CREATED"
    print(json.dumps({
        "status": status,
        "plan_id": expected["plan_id"],
        "map_id": expected["map_id"],
        "map_name": expected["map_name"],
        "wmo_count": expected["wmo_count"],
        "eligible_structure_count": expected["eligible_structure_count"],
        "deferred_structure_count": expected["deferred_structure_count"],
        "initial_seed_count": expected["initial_seed_count"],
        "content_sha256": expected["content_sha256"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
