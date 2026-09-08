"""Audit Zygor route coverage by explicit TBC WorldPack map binding.

Only hashes, bounded counts, and map identities are retained.  The guide is
parsed as data; no Lua is evaluated and no route entry becomes executable.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.route_teacher import (
    RouteTeacherImportConfig,
    import_zygor_lua,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-route-coverage.schema.json"
BINDING_SCHEMA = ROOT / "contracts" / "zygor-zone-map-bindings.schema.json"
SELECTED_FILES = (
    "leveling/ZygorLevelingAllianceCLASSIC.lua",
    "leveling/ZygorLevelingCommonCLASSIC.lua",
    "leveling/ZygorLevelingHordeCLASSIC.lua",
    "professions/ZygorProfessionsAllianceCLASSIC.lua",
    "professions/ZygorProfessionsCommonCLASSIC.lua",
    "professions/ZygorProfessionsHordeCLASSIC.lua",
)
KIND_KEYS = (
    "class_quest", "class_trainer", "profession_quest",
    "profession_trainer", "route_step",
)
TAG_KEYS = ("accept", "combat", "profession", "talk", "trainer", "turnin")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


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
    ContractValidator(BINDING_SCHEMA).validate(record)
    bindings: dict[str, tuple[int, str]] = {}
    for item in record["bindings"]:
        zone = str(item["zone"]).strip()
        if zone in bindings:
            raise ValueError(f"duplicate Zygor zone binding: {zone!r}")
        bindings[zone] = (int(item["map_id"]), str(item["map_name"]).strip())
    return _reference(path), bindings


def _empty_kind_counts() -> dict[str, int]:
    return {key: 0 for key in KIND_KEYS}


def _empty_tag_counts() -> dict[str, int]:
    return {key: 0 for key in TAG_KEYS}


def _count_entries(entries: tuple[Any, ...]) -> dict[str, Any]:
    kinds = Counter(str(entry.kind) for entry in entries)
    tags = Counter(str(tag) for entry in entries for tag in entry.tags)
    map_entries: dict[tuple[int, str], list[Any]] = {}
    for entry in entries:
        map_entries.setdefault((int(entry.map_id), str(entry.map_name)), []).append(entry)

    def map_record(map_id: int, map_name: str, selected: list[Any]) -> dict[str, Any]:
        map_kinds = Counter(str(entry.kind) for entry in selected)
        map_tags = Counter(str(tag) for entry in selected for tag in entry.tags)
        return {
            "map_id": map_id,
            "map_name": map_name,
            "step_count": len(selected),
            "coordinate_candidate_count": sum(entry.position is not None for entry in selected),
            "kind_counts": {key: int(map_kinds.get(key, 0)) for key in KIND_KEYS},
            "tag_counts": {key: int(map_tags.get(key, 0)) for key in TAG_KEYS},
        }

    return {
        "step_count": len(entries),
        "coordinate_candidate_count": sum(entry.position is not None for entry in entries),
        "kind_counts": {key: int(kinds.get(key, 0)) for key in KIND_KEYS},
        "tag_counts": {key: int(tags.get(key, 0)) for key in TAG_KEYS},
        "map_counts": [
            map_record(map_id, map_name, selected)
            for (map_id, map_name), selected in sorted(map_entries.items())
        ],
    }


def _parse_file(
    path: Path,
    *,
    archive_path: str,
    archive_reference: str,
    zone_map_bindings: dict[str, tuple[int, str]],
    provider_version: str,
    client_version: str,
    client_build: str,
) -> dict[str, Any]:
    payload = path.read_bytes()
    catalog = import_zygor_lua(
        payload.decode("utf-8"),
        config=RouteTeacherImportConfig(
            catalog_id=f"zygor.route.coverage.{hashlib.sha256(payload).hexdigest()[:16]}",
            target_profile="tbc243_lab",
            client_version=client_version,
            client_build=client_build,
            provider_version=provider_version,
            retrieved_at="1970-01-01T00:00:00Z",
            source_uri=f"{archive_reference}#{archive_path}",
            default_map_id=0,
            default_map_name="Azeroth",
            zone_map_bindings=zone_map_bindings,
        ),
    )
    counts = _count_entries(catalog.entries)
    return {
        "archive_path": archive_path,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_size_bytes": len(payload),
        **counts,
        "execution_authority": False,
    }


def build_zygor_route_coverage(
    source_root: Path,
    archive_path: Path,
    *,
    bindings_path: Path,
    archive_reference: str,
    provider_version: str,
    client_version: str,
    client_build: str,
) -> dict[str, object]:
    source_root = source_root.resolve()
    archive_path = archive_path.resolve()
    archive_payload = archive_path.read_bytes()
    binding_reference, bindings = _load_bindings(bindings_path)
    missing = [relative for relative in SELECTED_FILES if not (source_root / relative).is_file()]
    if missing:
        raise FileNotFoundError("selected guide file is missing: " + ", ".join(missing))
    files = [
        _parse_file(
            source_root / relative,
            archive_path=relative,
            archive_reference=archive_reference,
            zone_map_bindings=bindings,
            provider_version=provider_version,
            client_version=client_version,
            client_build=client_build,
        )
        for relative in SELECTED_FILES
    ]
    kind_counts = Counter()
    tag_counts = Counter()
    map_entries: dict[tuple[int, str], list[Any]] = {}
    for item in files:
        kind_counts.update(item["kind_counts"])
        tag_counts.update(item["tag_counts"])
        for map_item in item["map_counts"]:
            key = (int(map_item["map_id"]), str(map_item["map_name"]))
            map_entries.setdefault(key, []).append(map_item)

    def aggregate_map(key: tuple[int, str], values: list[dict[str, Any]]) -> dict[str, Any]:
        map_kinds = Counter()
        map_tags = Counter()
        for value in values:
            map_kinds.update(value["kind_counts"])
            map_tags.update(value["tag_counts"])
        return {
            "map_id": key[0],
            "map_name": key[1],
            "step_count": sum(int(value["step_count"]) for value in values),
            "coordinate_candidate_count": sum(int(value["coordinate_candidate_count"]) for value in values),
            "kind_counts": {name: int(map_kinds.get(name, 0)) for name in KIND_KEYS},
            "tag_counts": {name: int(map_tags.get(name, 0)) for name in TAG_KEYS},
        }

    return {
        "record_type": "zygor_route_coverage",
        "schema_version": "1.0",
        "source_archive_reference": archive_reference,
        "source_archive_sha256": hashlib.sha256(archive_payload).hexdigest(),
        "source_archive_size_bytes": len(archive_payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "binding_reference": binding_reference,
        "selected_file_count": len(files),
        "files": files,
        "step_count": sum(int(item["step_count"]) for item in files),
        "coordinate_candidate_count": sum(int(item["coordinate_candidate_count"]) for item in files),
        "kind_counts": {key: int(kind_counts.get(key, 0)) for key in KIND_KEYS},
        "tag_counts": {key: int(tag_counts.get(key, 0)) for key in TAG_KEYS},
        "map_coverage": [
            aggregate_map(key, values)
            for key, values in sorted(map_entries.items())
        ],
        "coverage_state": "BOUND_EXPLICIT_ZONE_MAPS",
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--archive-reference", required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_zygor_route_coverage(
        arguments.source_root,
        arguments.archive,
        bindings_path=arguments.bindings,
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
            raise SystemExit("route coverage audit is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
