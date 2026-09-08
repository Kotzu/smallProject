from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    build_standalone_world_pack,
    build_standalone_world_pack_from_catalog,
    open_standalone_world_pack,
    verify_standalone_world_pack,
)


INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
QUEUE_SCHEMA = ROOT / "contracts" / "client-world-bake-queue.schema.json"
CATALOG_SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
PACK_SCHEMA = ROOT / "contracts" / "standalone-world-pack.schema.json"
QUALITY_SCHEMA = ROOT / "contracts" / "navmesh-bake-quality-report.schema.json"
GEOMETRY_SCHEMA = ROOT / "contracts" / "navmesh-geometry-validation-report.schema.json"
REPAIR_SCHEMA = ROOT / "contracts" / "navmesh-tile-repair-evidence.schema.json"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _write_manifest(path: Path, value: object) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".manifest.", suffix=".tmp", dir=path.parent,
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
        description="Seal or verify a self-contained, process-independent WorldPack."
    )
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument(
        "--bake-quality-report", type=Path, action="append", default=[],
        help="repeat once for every catalog map declaring complete terrain coverage",
    )
    parser.add_argument(
        "--navmesh-geometry-validation", type=Path, action="append", default=[],
        help="repeat once for every catalog map declaring complete terrain coverage",
    )
    parser.add_argument(
        "--tile-repair-evidence", type=Path, action="append", default=[],
        help="repeat once for every catalog tile replacing raw bake output",
    )
    parser.add_argument(
        "--tile-repair-evidence-directory",
        type=Path,
        action="append",
        default=[],
        help="load every top-level JSON repair evidence file from this directory",
    )
    parser.add_argument("--nav-root", type=Path)
    parser.add_argument("--world-catalog-asset", type=Path)
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--pack-id")
    parser.add_argument("--map-name", action="append", default=[])
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    pack_root = args.pack_root.resolve()
    manifest_path = pack_root / "manifest.json"
    if args.verify_only:
        manifest = _read_object(manifest_path)
        ContractValidator(PACK_SCHEMA).validate(manifest)
        verify_standalone_world_pack(pack_root, manifest)
        runtime_ready = False
        nav_profile_id = None
        if (pack_root / "identity" / "client-world-catalog.json").is_file():
            opened = open_standalone_world_pack(
                pack_root,
                pack_schema_path=PACK_SCHEMA,
                catalog_schema_path=CATALOG_SCHEMA,
                expected_pack_id=str(manifest["pack_id"]),
                expected_content_sha256=str(manifest["content_sha256"]),
            )
            runtime_ready = True
            nav_profile_id = opened.catalog.nav_profile_id
        print(json.dumps({
            "status": "VERIFIED",
            "pack_id": manifest["pack_id"],
            "packed_map_count": manifest["packed_map_count"],
            "artifact_count": len(manifest["files"]),
            "content_sha256": manifest["content_sha256"],
            "runtime_ready": runtime_ready,
            "nav_profile_id": nav_profile_id,
            "runtime_dependencies": manifest["runtime_dependencies"],
            "execution_authority": False,
        }, sort_keys=True))
        return 0
    required = {
        "--nav-root": args.nav_root,
        "--world-catalog-asset": args.world_catalog_asset,
        "--pack-id": args.pack_id,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("required for sealing: " + ", ".join(missing))
    if args.catalog is None and (args.inventory is None or args.queue is None):
        parser.error("sealing requires --catalog or both --inventory and --queue")
    if args.catalog is not None and (
        args.inventory is not None or args.queue is not None or args.map_name
    ):
        parser.error("--catalog cannot be combined with queue inputs or --map-name")
    if args.catalog is None and (
        args.bake_quality_report
        or args.navmesh_geometry_validation
        or args.tile_repair_evidence
        or args.tile_repair_evidence_directory
    ):
        parser.error("quality and repair evidence require --catalog")
    if pack_root.exists():
        raise SystemExit("WorldPack destination already exists")
    inventory = queue = catalog = None
    if args.catalog is not None:
        catalog = _read_object(args.catalog)
        ContractValidator(CATALOG_SCHEMA).validate(catalog)
        quality_reports = [
            _read_object(path) for path in args.bake_quality_report
        ]
        for report in quality_reports:
            ContractValidator(QUALITY_SCHEMA).validate(report)
        geometry_reports = [
            _read_object(path) for path in args.navmesh_geometry_validation
        ]
        for report in geometry_reports:
            ContractValidator(GEOMETRY_SCHEMA).validate(report)
        repair_evidence_paths = list(args.tile_repair_evidence)
        for directory in args.tile_repair_evidence_directory:
            resolved_directory = directory.resolve()
            if not resolved_directory.is_dir():
                raise ValueError(
                    f"repair evidence directory is unavailable: {resolved_directory}"
                )
            repair_evidence_paths.extend(sorted(
                path for path in resolved_directory.glob("*.json") if path.is_file()
            ))
        resolved_evidence_paths = [path.resolve() for path in repair_evidence_paths]
        if len(set(resolved_evidence_paths)) != len(resolved_evidence_paths):
            raise ValueError("repair evidence paths are not unique")
        repair_evidence = []
        repair_artifacts: dict[str, bytes] = {}
        for evidence_path in resolved_evidence_paths:
            evidence = _read_object(evidence_path)
            ContractValidator(REPAIR_SCHEMA).validate(evidence)
            repair_evidence.append(evidence)
            defect = evidence["defect"]
            regression = evidence["regression"]
            for relative_name in {
                str(defect["evidence_artifact"]),
                str(regression["before"]["result_artifact"]),
                str(regression["after"]["result_artifact"]),
            }:
                source = evidence_path.resolve().parent.joinpath(
                    *Path(relative_name).parts
                )
                payload = source.read_bytes()
                previous = repair_artifacts.get(relative_name)
                if previous not in (None, payload):
                    raise ValueError(
                        f"repair artifact path has conflicting bytes: {relative_name}"
                    )
                repair_artifacts[relative_name] = payload
    else:
        quality_reports = []
        geometry_reports = []
        repair_evidence = []
        repair_artifacts = {}
        inventory = _read_object(args.inventory)
        queue = _read_object(args.queue)
        ContractValidator(INVENTORY_SCHEMA).validate(inventory)
        ContractValidator(QUEUE_SCHEMA).validate(queue)
    staging_root = pack_root.with_name(f".{pack_root.name}.staging")
    if staging_root.exists():
        raise SystemExit("WorldPack staging destination already exists")
    try:
        if catalog is not None:
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=args.nav_root,
                world_catalog_asset_path=args.world_catalog_asset,
                staging_root=staging_root,
                pack_id=args.pack_id,
                bake_quality_reports=quality_reports,
                navmesh_geometry_reports=geometry_reports,
                tile_repair_evidence=repair_evidence,
                tile_repair_artifacts=repair_artifacts,
            )
        else:
            manifest = build_standalone_world_pack(
                inventory,
                queue,
                nav_root=args.nav_root,
                world_catalog_asset_path=args.world_catalog_asset,
                staging_root=staging_root,
                pack_id=args.pack_id,
                selected_map_names=args.map_name,
            )
        ContractValidator(PACK_SCHEMA).validate(manifest)
        _write_manifest(staging_root / "manifest.json", manifest)
        verify_standalone_world_pack(staging_root, manifest)
        runtime_ready = False
        nav_profile_id = None
        if (staging_root / "identity" / "client-world-catalog.json").is_file():
            opened = open_standalone_world_pack(
                staging_root,
                pack_schema_path=PACK_SCHEMA,
                catalog_schema_path=CATALOG_SCHEMA,
                expected_pack_id=str(manifest["pack_id"]),
                expected_content_sha256=str(manifest["content_sha256"]),
            )
            runtime_ready = True
            nav_profile_id = opened.catalog.nav_profile_id
        os.replace(staging_root, pack_root)
    except BaseException:
        if (
            staging_root.parent == pack_root.parent
            and staging_root.name == f".{pack_root.name}.staging"
        ):
            shutil.rmtree(staging_root, ignore_errors=True)
        raise
    print(json.dumps({
        "status": "SEALED",
        "pack_id": manifest["pack_id"],
        "coverage_state": manifest["coverage_state"],
        "packed_map_count": manifest["packed_map_count"],
        "artifact_count": len(manifest["files"]),
        "content_sha256": manifest["content_sha256"],
        "runtime_ready": runtime_ready,
        "nav_profile_id": nav_profile_id,
        "runtime_dependencies": manifest["runtime_dependencies"],
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
