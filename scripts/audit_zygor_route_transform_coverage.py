"""Audit bounded Zygor coordinates against client WorldMapArea transforms.

The user-owned guide is parsed as data only.  The output retains hashes,
counts, map/area identities and deterministic unresolved-key hashes; it never
retains guide names, coordinates, NPC text or an executable route.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.adapter.world_map_zone_catalog import (
    WorldMapZoneTransform,
    WorldMapZoneTransformCatalog,
    WorldMapZoneTransformCatalogError,
    load_world_map_zone_transform_catalog,
)
from perfect_assassin.knowledge.route_teacher import (
    RouteTeacherImportConfig,
    _GOTO,
    _MAPZONE,
    _legacy_step_blocks,
    _modern_coordinates,
    _modern_step_blocks,
    _source_coordinates,
    import_zygor_lua,
)
from perfect_assassin.knowledge.zygor_map_bindings import (
    normalize_zygor_world_map_name,
    zygor_world_map_internal_key,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-route-transform-coverage.schema.json"
BINDING_SCHEMA = ROOT / "contracts" / "zygor-zone-map-bindings.schema.json"
TRANSFORM_SCHEMA = ROOT / "contracts" / "world-map-zone-transform-catalog.schema.json"
SELECTED_FILES = (
    "leveling/ZygorLevelingAllianceCLASSIC.lua",
    "leveling/ZygorLevelingCommonCLASSIC.lua",
    "leveling/ZygorLevelingHordeCLASSIC.lua",
    "professions/ZygorProfessionsAllianceCLASSIC.lua",
    "professions/ZygorProfessionsCommonCLASSIC.lua",
    "professions/ZygorProfessionsHordeCLASSIC.lua",
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON object: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _atomic_write_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _load_bindings(path: Path) -> tuple[str, dict[str, tuple[int, str]]]:
    record = _read_object(path.resolve())
    ContractValidator(BINDING_SCHEMA.resolve()).validate(record)
    bindings: dict[str, tuple[int, str]] = {}
    for item in record["bindings"]:
        zone = str(item["zone"]).strip()
        if zone in bindings:
            raise ValueError(f"duplicate Zygor zone binding: {zone!r}")
        bindings[zone] = (int(item["map_id"]), str(item["map_name"]).strip())
    return _reference(path), bindings


def _normalize_name(value: str) -> str:
    return normalize_zygor_world_map_name(value)


def _internal_key(zone: str | None) -> str | None:
    if zone is None or not zone.strip():
        return None
    cleaned = re.sub(r"/\d+.*$", "", zone).strip()
    normalized = _normalize_name(cleaned)
    return zygor_world_map_internal_key(cleaned)


def _coordinate_records(text: str) -> Iterable[tuple[str | None, float, float]]:
    """Yield coordinate candidates using the same bounded shapes as importer."""

    modern = _modern_step_blocks(text)
    if modern:
        current_guide: str | None = None
        current_zone: str | None = None
        for _line, guide, block in modern:
            if guide != current_guide:
                current_guide, current_zone = guide, None
            coordinates = _modern_coordinates(block)
            if coordinates is None:
                continue
            zone, x, y = coordinates
            if zone is not None:
                current_zone = zone
            yield current_zone, x, y
        return

    legacy = _legacy_step_blocks(text)
    if legacy:
        for _line, block in legacy:
            coordinates = _source_coordinates(block)
            if coordinates is None:
                continue
            zone_match = _MAPZONE.search(block)
            yield (
                zone_match.group("value").strip() if zone_match else None,
                *coordinates,
            )
        return

    current_zone: str | None = None
    for raw_line in text.splitlines():
        match = _GOTO.match(raw_line.strip())
        if match is None:
            continue
        zone = match.group("zone")
        if zone is not None:
            current_zone = zone.strip()
        yield current_zone, float(match.group("x")), float(match.group("y"))


def _resolve_transform(
    catalog: WorldMapZoneTransformCatalog,
    *,
    map_id: int,
    zone: str | None,
) -> WorldMapZoneTransform | None:
    internal = _internal_key(zone)
    if internal is None:
        internal = _normalize_name("Azeroth")
    matches = tuple(
        item for item in catalog.zones
        if item.map_id == map_id and _normalize_name(item.internal_name) == internal
    )
    return matches[0] if len(matches) == 1 else None


def _parse_file(
    path: Path,
    *,
    archive_path: str,
    archive_reference: str,
    bindings: dict[str, tuple[int, str]],
    catalog: WorldMapZoneTransformCatalog,
    provider_version: str,
    client_version: str,
    client_build: str,
) -> dict[str, object]:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    # Validate all route semantics through the existing bounded importer first;
    # this ensures unknown zones and out-of-range source percentages fail closed.
    imported = import_zygor_lua(
        text,
        config=RouteTeacherImportConfig(
            catalog_id=f"zygor.route.transform.{_sha256(payload)[:16]}",
            target_profile="tbc243_lab",
            client_version=client_version,
            client_build=client_build,
            provider_version=provider_version,
            retrieved_at="1970-01-01T00:00:00Z",
            source_uri=f"{archive_reference}#{archive_path}",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings=bindings,
        ),
    )
    expected_coordinates = sum(entry.position is not None for entry in imported.entries)
    records = tuple(_coordinate_records(text))
    if len(records) != expected_coordinates:
        raise ValueError(
            f"coordinate parser drift in {archive_path}: "
            f"bounded importer={expected_coordinates}, transform audit={len(records)}"
        )

    map_totals: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    transform_totals: Counter[tuple[int, int]] = Counter()
    unresolved_keys: set[str] = set()
    transformed = 0
    unresolved = 0
    transform_errors = 0
    for zone, x, y in records:
        binding = bindings.get(zone.strip()) if zone is not None else None
        map_id, map_name = binding if binding is not None else (0, "Azeroth")
        counters = map_totals[(map_id, map_name)]
        counters["candidate"] += 1
        transform = _resolve_transform(catalog, map_id=map_id, zone=zone)
        if transform is None:
            unresolved += 1
            counters["unresolved"] += 1
            key = f"{map_id}:{_internal_key(zone) or _normalize_name('Azeroth')}"
            unresolved_keys.add(_sha256(key.encode("utf-8")))
            continue
        try:
            transform.world_from_normalized(x / 100.0, y / 100.0)
        except WorldMapZoneTransformCatalogError:
            transform_errors += 1
            counters["unresolved"] += 1
            continue
        transformed += 1
        counters["transformed"] += 1
        transform_totals[(transform.map_id, transform.area_id)] += 1

    map_coverage = [
        {
            "map_id": map_id,
            "map_name": map_name,
            "coordinate_candidate_count": int(values["candidate"]),
            "transformed_coordinate_count": int(values["transformed"]),
            "unresolved_coordinate_count": int(values["unresolved"]),
            "transform_area_count": sum(
                1 for (candidate_map, _area_id) in transform_totals
                if candidate_map == map_id
            ),
        }
        for (map_id, map_name), values in sorted(map_totals.items())
    ]
    transform_coverage = [
        {
            "map_id": map_id,
            "area_id": area_id,
            "coordinate_count": int(count),
        }
        for (map_id, area_id), count in sorted(transform_totals.items())
    ]
    return {
        "archive_path": archive_path,
        "source_sha256": _sha256(payload),
        "source_size_bytes": len(payload),
        "coordinate_candidate_count": expected_coordinates,
        "transformed_coordinate_count": transformed,
        "unresolved_coordinate_count": unresolved,
        "transform_error_count": transform_errors,
        "map_coverage": map_coverage,
        "transform_coverage": transform_coverage,
        "execution_authority": False,
    }, unresolved_keys


def build_zygor_route_transform_coverage(
    source_root: Path,
    archive_path: Path,
    *,
    bindings_path: Path,
    transform_catalog_path: Path,
    archive_reference: str,
    provider_version: str,
    client_version: str,
    client_build: str,
) -> dict[str, object]:
    source_root = source_root.resolve()
    archive_path = archive_path.resolve()
    archive_payload = archive_path.read_bytes()
    binding_reference, bindings = _load_bindings(bindings_path)
    catalog = load_world_map_zone_transform_catalog(
        transform_catalog_path.resolve(), schema_path=TRANSFORM_SCHEMA,
    )
    if catalog.client_build != client_build:
        raise ValueError("transform catalog client build does not match audit")
    files: list[dict[str, object]] = []
    unresolved_keys: set[str] = set()
    missing = [relative for relative in SELECTED_FILES if not (source_root / relative).is_file()]
    if missing:
        raise FileNotFoundError("selected guide file is missing: " + ", ".join(missing))
    for relative in SELECTED_FILES:
        item, item_keys = _parse_file(
            source_root / relative,
            archive_path=relative,
            archive_reference=archive_reference,
            bindings=bindings,
            catalog=catalog,
            provider_version=provider_version,
            client_version=client_version,
            client_build=client_build,
        )
        files.append(item)
        unresolved_keys.update(item_keys)

    map_totals: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    transform_totals: Counter[tuple[int, int]] = Counter()
    for item in files:
        for map_item in item["map_coverage"]:
            key = (int(map_item["map_id"]), str(map_item["map_name"]))
            target = map_totals[key]
            target["candidate"] += int(map_item["coordinate_candidate_count"])
            target["transformed"] += int(map_item["transformed_coordinate_count"])
            target["unresolved"] += int(map_item["unresolved_coordinate_count"])
        for transform_item in item["transform_coverage"]:
            transform_totals[(int(transform_item["map_id"]), int(transform_item["area_id"]))] += int(transform_item["coordinate_count"])

    map_coverage = [
        {
            "map_id": map_id,
            "map_name": map_name,
            "coordinate_candidate_count": int(values["candidate"]),
            "transformed_coordinate_count": int(values["transformed"]),
            "unresolved_coordinate_count": int(values["unresolved"]),
            "transform_area_count": sum(
                1 for candidate_map, _area_id in transform_totals
                if candidate_map == map_id
            ),
        }
        for (map_id, map_name), values in sorted(map_totals.items())
    ]
    transform_coverage = [
        {"map_id": map_id, "area_id": area_id, "coordinate_count": int(count)}
        for (map_id, area_id), count in sorted(transform_totals.items())
    ]
    total_candidates = sum(int(item["coordinate_candidate_count"]) for item in files)
    total_transformed = sum(int(item["transformed_coordinate_count"]) for item in files)
    total_unresolved = sum(int(item["unresolved_coordinate_count"]) for item in files)
    total_errors = sum(int(item["transform_error_count"]) for item in files)
    return {
        "record_type": "zygor_route_transform_coverage",
        "schema_version": "1.0",
        "source_archive_reference": archive_reference,
        "source_archive_sha256": _sha256(archive_payload),
        "source_archive_size_bytes": len(archive_payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "binding_reference": binding_reference,
        "transform_catalog_reference": _reference(transform_catalog_path),
        "transform_asset_sha256": catalog.asset_sha256.lower(),
        "transform_record_fingerprint_sha256": catalog.record_fingerprint_sha256.lower(),
        "selected_file_count": len(files),
        "files": files,
        "coordinate_candidate_count": total_candidates,
        "transformed_coordinate_count": total_transformed,
        "unresolved_coordinate_count": total_unresolved,
        "transform_error_count": total_errors,
        "map_coverage": map_coverage,
        "transform_coverage": transform_coverage,
        "unresolved_transform_key_hashes": sorted(unresolved_keys),
        "coverage_state": (
            "COMPLETE_CLIENT_2D_TRANSFORM"
            if total_unresolved == 0 and total_errors == 0
            else "PARTIAL_CLIENT_2D_TRANSFORM"
        ),
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--transform-catalog", type=Path, required=True)
    parser.add_argument("--archive-reference", required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_zygor_route_transform_coverage(
        arguments.source_root,
        arguments.archive,
        bindings_path=arguments.bindings,
        transform_catalog_path=arguments.transform_catalog,
        archive_reference=arguments.archive_reference,
        provider_version=arguments.provider_version,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
    )
    ContractValidator(AUDIT_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"audit output is missing: {arguments.output}")
        if _read_object(arguments.output) != record:
            raise SystemExit("route transform coverage audit is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
