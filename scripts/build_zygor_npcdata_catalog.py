"""Build a local, read-only Knowledge Broker catalog from user-owned NPCData.

The input is read from the operator's local Zygor export and is never copied
into the repository.  Coordinates stay in the source ``zone_area`` frame and
are explicitly marked as static candidates; they are not live unit positions
and do not grant movement authority.
"""

from __future__ import annotations

import argparse
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


CATALOG_SCHEMA = ROOT / "contracts" / "knowledge-broker-catalog.schema.json"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _load_bindings(path: Path) -> dict[int, str]:
    record = _read_object(path.resolve())
    raw = record.get("map_areas")
    if not isinstance(raw, list) or not raw:
        raise ValueError("NPCData bindings must contain a non-empty map_areas array")
    bindings: dict[int, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("NPCData map binding must be an object")
        map_id = item.get("map_id")
        map_name = item.get("map_name")
        if type(map_id) is not int or map_id < 0:
            raise ValueError("NPCData map binding id is invalid")
        if map_id in bindings:
            raise ValueError(f"duplicate NPCData map binding: m{map_id}")
        if not isinstance(map_name, str) or not map_name.strip():
            raise ValueError(f"NPCData map binding m{map_id} has no name")
        bindings[map_id] = map_name.strip()
    return bindings


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


def build_catalog(
    source_path: Path,
    *,
    map_bindings_path: Path,
    target_profile: str,
    client_version: str,
    client_build: str,
    provider_version: str,
    retrieved_at: str,
    catalog_id: str | None = None,
    source_uri: str | None = None,
):
    source_path = source_path.resolve()
    payload = source_path.read_bytes()
    bindings = _load_bindings(map_bindings_path)
    source_reference = source_uri or "local://user-owned-zygor/npc/NPCData.lua"
    selected_catalog_id = catalog_id or (
        f"zygor.npcdata.{hashlib.sha256(payload).hexdigest()[:16]}"
    )
    return import_zygor_npc_data(
        payload.decode("utf-8"),
        config=NpcDataImportConfig(
            catalog_id=selected_catalog_id,
            target_profile=target_profile,
            client_version=client_version,
            client_build=client_build,
            provider_version=provider_version,
            retrieved_at=retrieved_at,
            source_uri=source_reference,
            zone_area_bindings=bindings,
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--map-bindings", type=Path, required=True)
    parser.add_argument("--target-profile", default="tbc243_lab")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--catalog-id")
    parser.add_argument("--source-uri")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    catalog = build_catalog(
        arguments.source,
        map_bindings_path=arguments.map_bindings,
        target_profile=arguments.target_profile,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
        provider_version=arguments.provider_version,
        retrieved_at=arguments.retrieved_at,
        catalog_id=arguments.catalog_id,
        source_uri=arguments.source_uri,
    )
    record = catalog.to_record()
    ContractValidator(CATALOG_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"catalog output is missing: {arguments.output}")
        if _read_object(arguments.output) != record:
            raise SystemExit("catalog output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps({
        "catalog_id": catalog.catalog_id,
        "entry_count": len(catalog.entries),
        "execution_authority": False,
        "output": str(arguments.output.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
