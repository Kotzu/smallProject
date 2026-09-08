"""Reconcile bounded Zygor map-area IDs with client WorldMapArea names."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.zygor_map_bindings import (
    parse_zygor_map_name_candidates,
    normalize_zygor_world_map_name,
    zygor_world_map_internal_key,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-world-map-reconciliation.schema.json"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
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


def _normalize_name(value: str) -> str:
    return normalize_zygor_world_map_name(value)


def _discovery_map_areas(record: dict[str, Any]) -> list[dict[str, int]]:
    if record.get("record_type") != "zygor_npcdata_map_discovery":
        raise ValueError("NPCData input is not a discovery record")
    areas = record.get("map_areas")
    if not isinstance(areas, list) or not areas:
        raise ValueError("NPCData discovery has no map_areas")
    result: list[dict[str, int]] = []
    seen: set[int] = set()
    for item in areas:
        if not isinstance(item, dict):
            raise ValueError("NPCData discovery map_areas must contain objects")
        map_id, row_count = item.get("map_id"), item.get("row_count")
        if not isinstance(map_id, int) or map_id < 0:
            raise ValueError("NPCData discovery map_id must be a non-negative integer")
        if not isinstance(row_count, int) or row_count < 1:
            raise ValueError("NPCData discovery row_count must be positive")
        if map_id in seen:
            raise ValueError(f"duplicate NPCData discovery map ID: m{map_id}")
        seen.add(map_id)
        result.append({"map_id": map_id, "row_count": row_count})
    return result


def _world_map_names(record: dict[str, Any]) -> tuple[dict[str, list[dict[str, int]]], int, str]:
    if record.get("record_type") != "client_world_map_area_audit":
        raise ValueError("WorldMapArea input is not a client audit record")
    maps = record.get("maps")
    if not isinstance(maps, list) or not maps:
        raise ValueError("WorldMapArea audit has no maps")
    by_exact: dict[str, list[dict[str, int]]] = {}
    record_count = 0
    for world_map in maps:
        if not isinstance(world_map, dict) or not isinstance(world_map.get("map_id"), int):
            raise ValueError("WorldMapArea maps are malformed")
        map_id = world_map["map_id"]
        areas = world_map.get("areas")
        if not isinstance(areas, list):
            raise ValueError("WorldMapArea map has no areas")
        for area in areas:
            if not isinstance(area, dict) or not isinstance(area.get("internal_name"), str):
                raise ValueError("WorldMapArea area is malformed")
            name = area["internal_name"].strip()
            if not name:
                raise ValueError("WorldMapArea area has an empty internal name")
            record_count += 1
            by_exact.setdefault(name, []).append({"map_id": map_id})
    asset_sha256 = record.get("asset_sha256")
    if not isinstance(asset_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", asset_sha256):
        raise ValueError("WorldMapArea audit has no valid asset_sha256")
    return by_exact, record_count, asset_sha256


def build_zygor_world_map_reconciliation(
    npcdata_discovery_path: Path,
    map_source_path: Path,
    world_map_area_audit_path: Path,
    *,
    provider_version: str,
    client_version: str,
    client_build: str,
    npcdata_discovery_reference: str | None = None,
    map_source_reference: str | None = None,
    world_map_area_reference: str | None = None,
) -> dict[str, object]:
    discovery_path = npcdata_discovery_path.resolve()
    map_path = map_source_path.resolve()
    world_path = world_map_area_audit_path.resolve()
    discovery = _read_object(discovery_path)
    discovery_areas = _discovery_map_areas(discovery)
    map_payload = map_path.read_bytes()
    candidates = parse_zygor_map_name_candidates(map_payload.decode("utf-8"))
    world_exact, world_record_count, world_asset_sha256 = _world_map_names(
        _read_object(world_path)
    )
    world_normalized: dict[str, list[dict[str, int]]] = {}
    for name, records in world_exact.items():
        world_normalized.setdefault(_normalize_name(name), []).extend(records)

    statuses: list[dict[str, object]] = []
    exact_count = normalized_count = ambiguous_count = unresolved_count = 0
    for item in discovery_areas:
        map_id = item["map_id"]
        names = candidates.get(map_id, ())
        exact_records = [
            record for name in names for record in world_exact.get(name, ())
        ]
        exact_map_ids = sorted({record["map_id"] for record in exact_records})
        if len(exact_records) == 1 and len(exact_map_ids) == 1:
            status = "EXACT"
            world_ids = exact_map_ids
            exact_count += 1
        else:
            normalized_records = [
                record
                for name in names
                for record in world_normalized.get(_normalize_name(name), ())
            ]
            normalized_map_ids = sorted({record["map_id"] for record in normalized_records})
            if len(normalized_records) == 1 and len(normalized_map_ids) == 1:
                status = "NORMALIZED_EXACT"
                world_ids = normalized_map_ids
                normalized_count += 1
            else:
                # A small, explicit compatibility layer handles names such as
                # ``Tirisfal Glades`` -> ``Tirisfal``.  It is identity-only
                # metadata from the same client assets, never a route point.
                alias_records = [
                    record
                    for name in names
                    for record in world_normalized.get(
                        zygor_world_map_internal_key(name), ()
                    )
                ]
                alias_map_ids = sorted({record["map_id"] for record in alias_records})
                if len(alias_records) == 1 and len(alias_map_ids) == 1:
                    status = "NORMALIZED_EXACT"
                    world_ids = alias_map_ids
                    normalized_count += 1
                elif exact_records or normalized_records or alias_records or len(names) > 1:
                    status = "AMBIGUOUS"
                    world_ids = sorted(set(exact_map_ids or normalized_map_ids or alias_map_ids))
                    ambiguous_count += 1
                else:
                    status = "UNRESOLVED"
                    world_ids = []
                    unresolved_count += 1
        statuses.append({
            "map_id": map_id,
            "row_count": item["row_count"],
            "binding_status": status,
            "world_map_ids": world_ids,
        })

    resolved_count = exact_count + normalized_count
    reconciliation_status = (
        "COMPLETE"
        if ambiguous_count == 0 and unresolved_count == 0
        else "PARTIAL"
        if resolved_count
        else "UNRESOLVED"
    )
    discovery_sha256 = discovery.get("source_sha256")
    if not isinstance(discovery_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", discovery_sha256):
        raise ValueError("NPCData discovery has no valid source_sha256")
    return {
        "record_type": "zygor_world_map_reconciliation",
        "schema_version": "1.0",
        "npcdata_discovery_reference": npcdata_discovery_reference or str(discovery_path).replace("\\", "/"),
        "npcdata_source_sha256": discovery_sha256,
        "map_source_reference": map_source_reference or str(map_path).replace("\\", "/"),
        "map_source_sha256": hashlib.sha256(map_payload).hexdigest(),
        "map_source_size_bytes": len(map_payload),
        "world_map_area_reference": world_map_area_reference or str(world_path).replace("\\", "/"),
        "world_map_area_asset_sha256": world_asset_sha256,
        "world_map_area_record_count": world_record_count,
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "map_area_count": len(statuses),
        "exact_map_area_count": exact_count,
        "normalized_exact_map_area_count": normalized_count,
        "resolved_map_area_count": resolved_count,
        "ambiguous_map_area_count": ambiguous_count,
        "unresolved_map_area_count": unresolved_count,
        "reconciliation_status": reconciliation_status,
        "map_areas": statuses,
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npcdata-discovery", type=Path, required=True)
    parser.add_argument("--map-source", type=Path, required=True)
    parser.add_argument("--world-map-area-audit", type=Path, required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--npcdata-discovery-reference")
    parser.add_argument("--map-source-reference")
    parser.add_argument("--world-map-area-reference")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_zygor_world_map_reconciliation(
        arguments.npcdata_discovery,
        arguments.map_source,
        arguments.world_map_area_audit,
        provider_version=arguments.provider_version,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
        npcdata_discovery_reference=arguments.npcdata_discovery_reference,
        map_source_reference=arguments.map_source_reference,
        world_map_area_reference=arguments.world_map_area_reference,
    )
    ContractValidator(AUDIT_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"audit output is missing: {arguments.output}")
        if _read_object(arguments.output) != record:
            raise SystemExit("audit output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
