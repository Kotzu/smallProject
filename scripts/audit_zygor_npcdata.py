"""Produce a content-minimal, deterministic audit of a user-owned NPCData.lua."""

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
from perfect_assassin.knowledge.npc_data import (
    NpcDataImportConfig,
    import_zygor_npc_data,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-npcdata-audit.schema.json"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


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


def _load_bindings(path: Path) -> dict[int, str]:
    record = _read_object(path)
    raw = record.get("map_areas")
    if not isinstance(raw, list) or not raw:
        raise ValueError("map bindings must contain a non-empty map_areas array")
    bindings: dict[int, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("map binding entries must be objects")
        map_id = item.get("map_id")
        map_name = item.get("map_name")
        if not isinstance(map_id, int) or map_id < 0:
            raise ValueError("map binding map_id must be a non-negative integer")
        if map_id in bindings:
            raise ValueError(f"duplicate map binding: m{map_id}")
        if not isinstance(map_name, str) or not map_name.strip():
            raise ValueError(f"map binding m{map_id} has no name")
        bindings[map_id] = map_name.strip()
    return bindings


def build_npcdata_audit(
    source_path: Path,
    *,
    map_bindings_path: Path,
    catalog_id: str,
    target_profile: str,
    client_version: str,
    client_build: str,
    provider_version: str,
    retrieved_at: str,
    source_uri: str | None = None,
) -> dict[str, object]:
    source_path = source_path.resolve()
    payload = source_path.read_bytes()
    text = payload.decode("utf-8")
    bindings = _load_bindings(map_bindings_path.resolve())
    uri = source_uri or f"local://{source_path.as_posix()}"
    catalog = import_zygor_npc_data(
        text,
        config=NpcDataImportConfig(
            catalog_id=catalog_id,
            target_profile=target_profile,
            client_version=client_version,
            client_build=client_build,
            provider_version=provider_version,
            retrieved_at=retrieved_at,
            source_uri=uri,
            zone_area_bindings=bindings,
        ),
    )
    section_tags = {
        tag for entry in catalog.entries for tag in entry.tags
        if tag.startswith("section:")
    }
    kind_counts = Counter(entry.kind for entry in catalog.entries)
    faction_counts = Counter(
        tag.split(":", 1)[1]
        for entry in catalog.entries
        for tag in entry.tags
        if tag.startswith("faction:")
    )
    map_rows = Counter(entry.map_id for entry in catalog.entries)
    map_areas = [
        {
            "map_id": map_id,
            "map_name": bindings[map_id],
            "row_count": map_rows[map_id],
        }
        for map_id in sorted(map_rows)
    ]
    return {
        "record_type": "zygor_npcdata_audit",
        "schema_version": "1.0",
        "source_reference": uri,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_size_bytes": len(payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "section_count": len(section_tags),
        "row_count": len(catalog.entries),
        "map_area_count": len(map_areas),
        "map_areas": map_areas,
        "kind_counts": dict(sorted(kind_counts.items())),
        "faction_counts": dict(sorted(faction_counts.items())),
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--map-bindings", type=Path, required=True)
    parser.add_argument("--catalog-id", default="zygor.npcdata.tbc243.anniversary")
    parser.add_argument("--target-profile", default="tbc243_lab")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--source-uri")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_npcdata_audit(
        arguments.source,
        map_bindings_path=arguments.map_bindings,
        catalog_id=arguments.catalog_id,
        target_profile=arguments.target_profile,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
        provider_version=arguments.provider_version,
        retrieved_at=arguments.retrieved_at,
        source_uri=arguments.source_uri,
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
