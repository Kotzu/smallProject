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


INVENTORY_SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"
REPORT_SCHEMA = ROOT / "contracts" / "navmesh-bake-quality-report.schema.json"
_NAV_NAME = re.compile(r"^(\d{2})_(\d{2})\.nav$")
_RETURN_CODE = re.compile(r"^RETURN_CODE (-?\d+)$")
_AGGREGATE_FINISHED = re.compile(r"^Finished (.+) \((\d+) tiles\)(?: .*)?$")
_NAMIGATOR_TILES_PER_ADT = 256


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
    matches = [
        item for item in inventory["maps"]
        if item["internal_name"] == map_name
    ]
    if len(matches) != 1:
        raise ValueError("map name is not unique in the pinned inventory")
    return matches[0]


def _active_log_lines(log_text: str) -> tuple[str, ...]:
    lines = tuple(log_text.splitlines())
    starts = [index for index, line in enumerate(lines) if " START [" in line]
    return lines[starts[-1]:] if starts else lines


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _named_nav_tiles_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.name):
        encoded_name = path.name.encode("ascii")
        digest.update(len(encoded_name).to_bytes(2, "little"))
        digest.update(encoded_name)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def build_navmesh_bake_quality_report(
    inventory: Mapping[str, Any],
    *,
    map_name: str,
    nav_root: Path,
    log_bytes: bytes,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    report_catalog_id = str(
        inventory["catalog_id"] if catalog_id is None else catalog_id
    )
    if not report_catalog_id:
        raise ValueError("quality report catalog_id must be non-empty")
    item = _inventory_map(inventory, map_name)
    expected = {
        (int(tile["grid_x"]), int(tile["grid_y"]))
        for tile in item["tiles"]
    }
    if len(expected) != int(item["adt_count"]):
        raise ValueError("pinned inventory ADT coordinates are inconsistent")

    nav_directory = nav_root.resolve() / "Nav" / map_name
    actual: set[tuple[int, int]] = set()
    valid_nav_paths: list[Path] = []
    invalid_nav_artifact_count = 0
    if nav_directory.is_dir():
        for path in nav_directory.glob("*.nav"):
            match = _NAV_NAME.fullmatch(path.name)
            if match is None or not path.is_file() or path.stat().st_size <= 0:
                invalid_nav_artifact_count += 1
                continue
            coordinate = (int(match.group(1)), int(match.group(2)))
            if coordinate in actual:
                invalid_nav_artifact_count += 1
                continue
            actual.add(coordinate)
            valid_nav_paths.append(path)

    nav_tiles = []
    for path in sorted(valid_nav_paths, key=lambda value: value.name):
        match = _NAV_NAME.fullmatch(path.name)
        if match is None:  # guarded above; retained as a fail-closed invariant
            raise ValueError("validated nav tile name changed during audit")
        nav_tiles.append({
            "grid_x": int(match.group(1)),
            "grid_y": int(match.group(2)),
            "artifact": path.name,
            "byte_size": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    nav_tiles_sha256 = _named_nav_tiles_sha256(valid_nav_paths)

    log_text = log_bytes.decode("utf-8", errors="replace")
    lines = _active_log_lines(log_text)
    finished_pattern = re.compile(
        rf"^Finished {re.escape(map_name)} ADT \((\d+), (\d+)\)$"
    )
    finished = {
        (int(match.group(1)), int(match.group(2)))
        for line in lines
        if (match := finished_pattern.fullmatch(line)) is not None
    }
    # The pinned MapBuilder v5 emits one aggregate completion line rather than
    # one line per ADT.  Count it only when the map name and exact inner-tile
    # total agree with the pinned 256 inner tiles per ADT.  The independent
    # artifact set below still proves the actual coordinate coverage.
    aggregate_finished = [
        int(match.group(2))
        for line in lines
        if (match := _AGGREGATE_FINISHED.fullmatch(line)) is not None
        and match.group(1) == map_name
    ]
    if not finished and aggregate_finished == [
        len(expected) * _NAMIGATOR_TILES_PER_ADT
    ]:
        finished = set(expected)
    return_codes = [
        int(match.group(1))
        for line in lines
        if (match := _RETURN_CODE.fullmatch(line)) is not None
    ]
    terminal_return_code = return_codes[-1] if return_codes else None
    diagnostics = {
        "recast_error_count": sum(" ERROR: " in line for line in lines),
        "recast_warning_count": sum(" WARNING: " in line for line in lines),
        "multiple_outline_error_count": sum(
            "Multiple outlines for region" in line for line in lines
        ),
        "bad_outline_error_count": sum(
            "Bad outline for region" in line for line in lines
        ),
        "bad_triangulation_warning_count": sum(
            "Bad triangulation Contour" in line for line in lines
        ),
        "walk_center_warning_count": sum(
            "Walk towards polygon center failed" in line for line in lines
        ),
        "dangling_face_warning_count": sum(
            "Removing dangling face" in line for line in lines
        ),
        "failed_tile_count": sum(
            " ADT (" in line and ") tile (" in line and " FAILED!" in line
            for line in lines
        ),
    }
    missing = expected - actual
    extra = actual - expected
    fatal = (
        terminal_return_code not in (None, 0)
        or diagnostics["failed_tile_count"] > 0
        or invalid_nav_artifact_count > 0
    )
    exact = not missing and not extra and len(actual) == len(expected)
    recast_diagnostics = (
        diagnostics["recast_error_count"] > 0
        or diagnostics["recast_warning_count"] > 0
    )
    if terminal_return_code is None:
        status = "IN_PROGRESS"
    elif fatal or not exact:
        status = "FAILED"
    elif recast_diagnostics:
        status = "COMPLETE_WITH_RECAST_DIAGNOSTICS"
    else:
        status = "COMPLETE_CLEAN"
    return {
        "record_type": "navmesh_bake_quality_report",
        "schema_version": "1.0",
        "status": status,
        "catalog_id": report_catalog_id,
        "client_build": str(inventory["client_build"]),
        "map_id": int(item["map_id"]),
        "internal_name": map_name,
        "expected_adt_count": len(expected),
        "nav_adt_count": len(actual),
        "finished_adt_count": len(finished),
        "missing_coordinates": [list(value) for value in sorted(missing)],
        "extra_coordinates": [list(value) for value in sorted(extra)],
        "invalid_nav_artifact_count": invalid_nav_artifact_count,
        "nav_tiles": nav_tiles,
        "nav_tiles_sha256": nav_tiles_sha256,
        "diagnostics": diagnostics,
        "terminal_return_code": terminal_return_code,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "geometric_validation_required": True,
        "execution_authority": False,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit exact ADT coverage and Recast diagnostics for one map bake."
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--map-name", required=True)
    parser.add_argument("--nav-root", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--catalog-id",
        help=(
            "catalog identity for the report; defaults to the pinned inventory "
            "catalog_id when omitted"
        ),
    )
    args = parser.parse_args(argv)
    inventory = _read_object(args.inventory)
    ContractValidator(INVENTORY_SCHEMA).validate(inventory)
    report = build_navmesh_bake_quality_report(
        inventory,
        map_name=args.map_name,
        nav_root=args.nav_root,
        log_bytes=args.log.read_bytes(),
        catalog_id=args.catalog_id,
    )
    ContractValidator(REPORT_SCHEMA).validate(report)
    _atomic_write(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "internal_name": report["internal_name"],
        "expected_adt_count": report["expected_adt_count"],
        "nav_adt_count": report["nav_adt_count"],
        "finished_adt_count": report["finished_adt_count"],
        "missing_coordinate_count": len(report["missing_coordinates"]),
        "extra_coordinate_count": len(report["extra_coordinates"]),
        "diagnostics": report["diagnostics"],
        "terminal_return_code": report["terminal_return_code"],
        "geometric_validation_required": True,
        "execution_authority": False,
    }, sort_keys=True))
    return 2 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(run())
