from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    verify_standalone_world_pack,
)


CATALOG_SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
QUALITY_SCHEMA = ROOT / "contracts" / "navmesh-bake-quality-report.schema.json"
GEOMETRY_SCHEMA = ROOT / "contracts" / "navmesh-geometry-validation-report.schema.json"
PACK_SCHEMA = ROOT / "contracts" / "standalone-world-pack.schema.json"
REPAIR_SCHEMA = ROOT / "contracts" / "navmesh-tile-repair-evidence.schema.json"
_NAV_NAME = re.compile(r"^(\d{2})_(\d{2})\.nav$")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _json_object_from_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be one UTF-8 JSON object") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one JSON object")
    return value


def _record_sha256(value: Mapping[str, Any]) -> str:
    wire = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(wire).hexdigest()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def build_navmesh_tile_repair_evidence(
    catalog: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    *,
    map_name: str,
    artifact: str,
    source_world_pack_root: Path,
    before_result_bytes: bytes,
    after_result_bytes: bytes,
    scenario_id: str,
    failure_code: str,
    verified_source_manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Verify and bind one raw-bake replacement to its source and regressions."""
    ContractValidator(CATALOG_SCHEMA).validate(catalog)
    ContractValidator(QUALITY_SCHEMA).validate(quality_report)
    match = _NAV_NAME.fullmatch(artifact)
    if match is None:
        raise ValueError("repair artifact must be a canonical NN_NN.nav tile")
    grid_x, grid_y = int(match.group(1)), int(match.group(2))
    maps = [item for item in catalog["maps"] if item["internal_name"] == map_name]
    if len(maps) != 1:
        raise ValueError("repair map is not unique in the final catalog")
    world_map = maps[0]
    final_tiles = [
        item for item in world_map["tiles"]
        if item["artifact"] == artifact
        and int(item["grid_x"]) == grid_x
        and int(item["grid_y"]) == grid_y
    ]
    reported_tiles = [
        item for item in quality_report["nav_tiles"]
        if item["artifact"] == artifact
        and int(item["grid_x"]) == grid_x
        and int(item["grid_y"]) == grid_y
    ]
    if len(final_tiles) != 1 or len(reported_tiles) != 1:
        raise ValueError("repair tile is not unique in catalog and raw bake report")
    if (
        quality_report["status"]
        not in {"COMPLETE_CLEAN", "COMPLETE_WITH_RECAST_DIAGNOSTICS"}
        or quality_report["catalog_id"] != catalog["catalog_id"]
        or str(quality_report["client_build"]) != str(catalog["client_build"])
        or int(quality_report["map_id"]) != int(world_map["map_id"])
        or quality_report["internal_name"] != map_name
    ):
        raise ValueError("raw bake report does not describe the final catalog map")
    raw_sha256 = str(reported_tiles[0]["sha256"]).lower()
    replacement_sha256 = str(final_tiles[0]["sha256"]).lower()
    if raw_sha256 == replacement_sha256:
        raise ValueError("repair evidence is forbidden when raw and final tiles match")

    source_world_pack_root = source_world_pack_root.resolve()
    if verified_source_manifest is None:
        source_manifest = _read_object(source_world_pack_root / "manifest.json")
        ContractValidator(PACK_SCHEMA).validate(source_manifest)
        verify_standalone_world_pack(source_world_pack_root, source_manifest)
    else:
        source_manifest = dict(verified_source_manifest)
    source_relative_path = f"Nav/{map_name}/{artifact}"
    source_records = [
        item for item in source_manifest["files"]
        if item["role"] == "NAV_TILE"
        and item["relative_path"] == source_relative_path
    ]
    if (
        len(source_records) != 1
        or str(source_manifest["client_build"]) != str(catalog["client_build"])
        or not any(
            item["internal_name"] == map_name for item in source_manifest["maps"]
        )
        or str(source_records[0]["sha256"]).lower() != replacement_sha256
    ):
        raise ValueError("source WorldPack does not contain the final replacement tile")

    before_result = _json_object_from_bytes(
        before_result_bytes, label="before regression result",
    )
    after_result = _json_object_from_bytes(
        after_result_bytes, label="after regression result",
    )
    ContractValidator(GEOMETRY_SCHEMA).validate(before_result)
    ContractValidator(GEOMETRY_SCHEMA).validate(after_result)
    before_failures = [
        item for item in before_result["failures"]
        if item["artifact"] == artifact
    ]
    if (
        before_result.get("status") != "FAIL"
        or str(before_result.get("client_build")) != str(catalog["client_build"])
        or int(before_result.get("map_id", -1)) != int(world_map["map_id"])
        or before_result.get("internal_name") != map_name
        or len(before_failures) != 1
        or before_failures[0]["code"] != failure_code
    ):
        raise ValueError(
            "before regression result must identify this exact failed tile"
        )
    if (
        after_result.get("status") != "PASS"
        or after_result.get("catalog_id") != catalog["catalog_id"]
        or str(after_result.get("client_build")) != str(catalog["client_build"])
        or int(after_result.get("map_id", -1)) != int(world_map["map_id"])
        or after_result.get("internal_name") != map_name
        or int(after_result.get("expected_tile_count", -1)) != len(world_map["tiles"])
        or int(after_result.get("validated_tile_count", -1)) != len(world_map["tiles"])
        or after_result.get("nav_tiles_sha256") != world_map["nav_tiles_sha256"]
    ):
        raise ValueError(
            "after regression result must prove the exact final catalog map"
        )
    if not scenario_id or not failure_code:
        raise ValueError("scenario and failure code are required")

    prefix = f"evidence/navmesh-repair-regression/{map_name}-{grid_x:02d}-{grid_y:02d}"
    before_relative = f"{prefix}-before.json"
    after_relative = f"{prefix}-after.json"
    before_sha256 = hashlib.sha256(before_result_bytes).hexdigest()
    after_sha256 = hashlib.sha256(after_result_bytes).hexdigest()
    evidence = {
        "record_type": "navmesh_tile_repair_evidence",
        "schema_version": "1.0",
        "catalog_id": str(catalog["catalog_id"]),
        "client_build": str(catalog["client_build"]),
        "map_id": int(world_map["map_id"]),
        "internal_name": map_name,
        "tile": {
            "grid_x": grid_x,
            "grid_y": grid_y,
            "artifact": artifact,
            "raw_bake_sha256": raw_sha256,
            "replacement_sha256": replacement_sha256,
        },
        "raw_bake_report_sha256": _record_sha256(quality_report),
        "defect": {
            "failure_code": failure_code,
            "evidence_artifact": before_relative,
            "evidence_sha256": before_sha256,
        },
        "replacement_source": {
            "pack_id": str(source_manifest["pack_id"]),
            "pack_content_sha256": str(source_manifest["content_sha256"]),
            "relative_path": source_relative_path,
            "artifact_sha256": replacement_sha256,
        },
        "regression": {
            "scenario_id": scenario_id,
            "before": {
                "status": "FAILED",
                "result_artifact": before_relative,
                "result_sha256": before_sha256,
            },
            "after": {
                "status": "PASSED",
                "result_artifact": after_relative,
                "result_sha256": after_sha256,
            },
        },
        "execution_authority": False,
    }
    ContractValidator(REPAIR_SCHEMA).validate(evidence)
    return evidence, {
        before_relative: before_result_bytes,
        after_relative: after_result_bytes,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create self-contained evidence for one navmesh tile replacement."
        )
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--source-world-pack-root", type=Path, required=True)
    parser.add_argument("--before-result", type=Path, required=True)
    parser.add_argument("--after-result", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--failure-code", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence, artifacts = build_navmesh_tile_repair_evidence(
        _read_object(args.catalog),
        _read_object(args.quality_report),
        map_name=args.map_name,
        artifact=args.artifact,
        source_world_pack_root=args.source_world_pack_root,
        before_result_bytes=args.before_result.read_bytes(),
        after_result_bytes=args.after_result.read_bytes(),
        scenario_id=args.scenario_id,
        failure_code=args.failure_code,
    )
    output = args.output.resolve()
    for relative_path, payload in artifacts.items():
        _atomic_write_bytes(output.parent.joinpath(*Path(relative_path).parts), payload)
    _atomic_write_bytes(
        output,
        (json.dumps(
            evidence, indent=2, ensure_ascii=False, allow_nan=False,
        ) + "\n").encode("utf-8"),
    )
    print(json.dumps({
        "status": "VERIFIED_REPAIR_EVIDENCE_WRITTEN",
        "map_name": args.map_name,
        "artifact": args.artifact,
        "source_pack_id": evidence["replacement_source"]["pack_id"],
        "regression_scenario_id": args.scenario_id,
        "output": str(output),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
