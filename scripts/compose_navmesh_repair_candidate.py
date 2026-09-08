from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
import uuid


_NAV_NAME = re.compile(r"^\d{2}_\d{2}\.nav$")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
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


def _failure_artifacts(report: Mapping[str, Any], *, map_name: str) -> set[str]:
    if report.get("status") != "FAIL":
        raise ValueError("source geometry report must be FAIL")
    if report.get("internal_name") != map_name:
        raise ValueError("source geometry report map does not match")
    failures = report.get("failures")
    if not isinstance(failures, list) or not failures:
        raise ValueError("source geometry report has no failed artifacts")
    names: list[str] = []
    for item in failures:
        if not isinstance(item, dict) or not isinstance(item.get("artifact"), str):
            raise ValueError("source geometry report has malformed failures")
        name = item["artifact"]
        if _NAV_NAME.fullmatch(name) is None:
            raise ValueError("source geometry report has a non-canonical artifact")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("source geometry report repeats a failed artifact")
    return set(names)


def compose_navmesh_repair_candidate(
    *,
    source_root: Path,
    repair_root: Path,
    source_geometry_report: Mapping[str, Any],
    output_root: Path,
    map_name: str,
) -> dict[str, Any]:
    """Build a new candidate without mutating either the raw bake or repairs."""

    source_root = source_root.resolve()
    repair_root = repair_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError("candidate destination already exists")

    failed = _failure_artifacts(source_geometry_report, map_name=map_name)
    source_nav = source_root / "Nav" / map_name
    repair_nav = repair_root / "Nav" / map_name
    source_paths = {
        item.name: item for item in source_nav.glob("*.nav")
        if item.is_file() and _NAV_NAME.fullmatch(item.name)
    }
    repair_paths = {
        item.name: item for item in repair_nav.glob("*.nav")
        if item.is_file() and _NAV_NAME.fullmatch(item.name)
    }
    expected_count = int(source_geometry_report.get("expected_tile_count", -1))
    if len(source_paths) != expected_count:
        raise ValueError("raw bake tile set does not match the geometry report")
    if set(repair_paths) != failed:
        missing = sorted(failed - set(repair_paths))
        extra = sorted(set(repair_paths) - failed)
        raise ValueError(
            f"repair set is not exact (missing={missing}, extra={extra})"
        )

    required_map = source_root / f"{map_name}.map"
    required_bvh = source_root / "BVH"
    required_semantics = source_root / "semantics"
    if not required_map.is_file() or not required_bvh.is_dir():
        raise ValueError("raw bake is missing map or BVH artifacts")
    semantic_paths = sorted(required_semantics.glob(f"{map_name}_*.road"))
    if len(semantic_paths) != expected_count:
        raise ValueError("raw bake road semantics are not complete for the map")

    temporary_root = output_root.with_name(
        f".{output_root.name}.building-{uuid.uuid4().hex}"
    )
    temporary_root.mkdir(parents=True)
    replacements: list[dict[str, Any]] = []
    try:
        shutil.copy2(required_map, temporary_root / required_map.name)
        shutil.copytree(required_bvh, temporary_root / "BVH")
        semantic_destination = temporary_root / "semantics"
        semantic_destination.mkdir()
        for source in semantic_paths:
            shutil.copy2(source, semantic_destination / source.name)

        nav_destination = temporary_root / "Nav" / map_name
        nav_destination.mkdir(parents=True)
        for name in sorted(source_paths):
            raw_path = source_paths[name]
            selected_path = repair_paths.get(name, raw_path)
            destination = nav_destination / name
            shutil.copy2(selected_path, destination)
            selected_sha256 = _sha256(selected_path)
            if _sha256(destination) != selected_sha256:
                raise OSError(f"candidate copy verification failed for {name}")
            if name in failed:
                replacements.append({
                    "artifact": name,
                    "raw_sha256": _sha256(raw_path),
                    "replacement_sha256": selected_sha256,
                })

        evidence = {
            "record_type": "navmesh_repair_candidate_composition",
            "schema_version": "1.0",
            "status": "COMPOSED_UNVALIDATED",
            "internal_name": map_name,
            "source_geometry_validator_id": source_geometry_report.get("validator_id"),
            "source_catalog_sha256": source_geometry_report.get("catalog_sha256"),
            "tile_count": len(source_paths),
            "replacement_count": len(replacements),
            "replacements": replacements,
            "execution_authority": False,
        }
        _atomic_json(
            temporary_root / "evidence" / "navmesh-repair-composition.json",
            evidence,
        )
        os.replace(temporary_root, output_root)
        return evidence
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compose an immutable navmesh candidate from an exact repair set."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--source-geometry-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    args = parser.parse_args(argv)
    evidence = compose_navmesh_repair_candidate(
        source_root=args.source_root,
        repair_root=args.repair_root,
        source_geometry_report=_read_object(args.source_geometry_report),
        output_root=args.output_root,
        map_name=args.map_name,
    )
    print(json.dumps({
        "status": evidence["status"],
        "internal_name": evidence["internal_name"],
        "tile_count": evidence["tile_count"],
        "replacement_count": evidence["replacement_count"],
        "output_root": str(args.output_root.resolve()),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
