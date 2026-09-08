from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    verify_standalone_world_pack,
)
from scripts.build_navmesh_tile_repair_evidence import (
    CATALOG_SCHEMA,
    GEOMETRY_SCHEMA,
    PACK_SCHEMA,
    QUALITY_SCHEMA,
    _atomic_write_bytes,
    build_navmesh_tile_repair_evidence,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def build_navmesh_repair_evidence_batch(
    catalog: Mapping[str, Any],
    quality_report: Mapping[str, Any],
    *,
    map_name: str,
    source_world_pack_root: Path,
    before_results: tuple[tuple[Mapping[str, Any], bytes], ...],
    after_result: Mapping[str, Any],
    after_result_bytes: bytes,
    scenario_prefix: str,
    output_root: Path,
) -> dict[str, Any]:
    """Build exact per-tile repair evidence while verifying the source pack once."""

    ContractValidator(CATALOG_SCHEMA).validate(catalog)
    ContractValidator(QUALITY_SCHEMA).validate(quality_report)
    ContractValidator(GEOMETRY_SCHEMA).validate(after_result)
    maps = [item for item in catalog["maps"] if item["internal_name"] == map_name]
    if len(maps) != 1:
        raise ValueError("repair map is not unique in the final catalog")
    world_map = maps[0]
    final_tiles = {item["artifact"]: item for item in world_map["tiles"]}
    raw_tiles = {item["artifact"]: item for item in quality_report["nav_tiles"]}
    if (
        quality_report.get("catalog_id") != catalog["catalog_id"]
        or str(quality_report.get("client_build")) != str(catalog["client_build"])
        or int(quality_report.get("map_id", -1)) != int(world_map["map_id"])
        or quality_report.get("internal_name") != map_name
        or set(raw_tiles) != set(final_tiles)
    ):
        raise ValueError("raw bake report topology does not match the final catalog")
    replacements = {
        artifact
        for artifact, final_tile in final_tiles.items()
        if raw_tiles[artifact]["sha256"] != final_tile["sha256"]
    }
    if not replacements:
        raise ValueError("repair batch has no replaced tiles")

    failure_sources: dict[str, tuple[Mapping[str, Any], bytes, str]] = {}
    for report, report_bytes in before_results:
        ContractValidator(GEOMETRY_SCHEMA).validate(report)
        if (
            report.get("status") != "FAIL"
            or str(report.get("client_build")) != str(catalog["client_build"])
            or int(report.get("map_id", -1)) != int(world_map["map_id"])
            or report.get("internal_name") != map_name
        ):
            raise ValueError("before report identity is inconsistent")
        for failure in report["failures"]:
            artifact = str(failure["artifact"])
            if artifact in failure_sources:
                raise ValueError(f"duplicate before failure for {artifact}")
            failure_sources[artifact] = (report, report_bytes, str(failure["code"]))
    if set(failure_sources) != replacements:
        raise ValueError("before reports do not exactly cover all replaced tiles")

    source_world_pack_root = source_world_pack_root.resolve()
    source_manifest = _read_object(source_world_pack_root / "manifest.json")
    ContractValidator(PACK_SCHEMA).validate(source_manifest)
    verify_standalone_world_pack(source_world_pack_root, source_manifest)

    output_root = output_root.resolve()
    evidence_paths: list[str] = []
    for artifact in sorted(replacements):
        _, before_bytes, failure_code = failure_sources[artifact]
        evidence, artifacts = build_navmesh_tile_repair_evidence(
            catalog,
            quality_report,
            map_name=map_name,
            artifact=artifact,
            source_world_pack_root=source_world_pack_root,
            before_result_bytes=before_bytes,
            after_result_bytes=after_result_bytes,
            scenario_id=f"{scenario_prefix}-{artifact.removesuffix('.nav')}",
            failure_code=failure_code,
            verified_source_manifest=source_manifest,
        )
        evidence_path = output_root / f"{artifact.removesuffix('.nav')}.json"
        for relative_path, payload in artifacts.items():
            _atomic_write_bytes(
                evidence_path.parent.joinpath(*Path(relative_path).parts), payload,
            )
        _atomic_write_bytes(
            evidence_path,
            (json.dumps(
                evidence, indent=2, ensure_ascii=False, allow_nan=False,
            ) + "\n").encode("utf-8"),
        )
        evidence_paths.append(str(evidence_path))
    return {
        "status": "VERIFIED_REPAIR_EVIDENCE_BATCH_WRITTEN",
        "map_name": map_name,
        "replacement_count": len(replacements),
        "source_pack_id": str(source_manifest["pack_id"]),
        "source_pack_content_sha256": str(source_manifest["content_sha256"]),
        "evidence_paths": evidence_paths,
        "execution_authority": False,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create exact per-tile evidence for one repaired navmesh batch."
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--source-world-pack-root", type=Path, required=True)
    parser.add_argument("--before-result", type=Path, action="append", required=True)
    parser.add_argument("--after-result", type=Path, required=True)
    parser.add_argument("--scenario-prefix", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    before_results = tuple(
        (_read_object(path), path.read_bytes()) for path in args.before_result
    )
    result = build_navmesh_repair_evidence_batch(
        _read_object(args.catalog),
        _read_object(args.quality_report),
        map_name=args.map_name,
        source_world_pack_root=args.source_world_pack_root,
        before_results=before_results,
        after_result=_read_object(args.after_result),
        after_result_bytes=args.after_result.read_bytes(),
        scenario_prefix=args.scenario_prefix,
        output_root=args.output_root,
    )
    print(json.dumps({
        key: value for key, value in result.items() if key != "evidence_paths"
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
