"""Discover Zygor NPCData map-area IDs without retaining licensed rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.npc_data import discover_zygor_npc_map_areas


DISCOVERY_SCHEMA = ROOT / "contracts" / "zygor-npcdata-map-discovery.schema.json"


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


def _read_record(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def build_npcdata_map_discovery(
    source_path: Path,
    *,
    provider_version: str,
    client_version: str,
    client_build: str,
    retrieved_at: str | None = None,
    source_uri: str | None = None,
) -> dict[str, object]:
    """Build a content-minimal map-ID inventory.

    ``retrieved_at`` is accepted for CLI symmetry and future evidence joins,
    but is intentionally not persisted: the source hash is the deterministic
    identity of this discovery record.
    """

    del retrieved_at
    source_path = source_path.resolve()
    payload = source_path.read_bytes()
    text = payload.decode("utf-8")
    map_areas = discover_zygor_npc_map_areas(text)
    uri = source_uri or f"local://{source_path.as_posix()}"
    return {
        "record_type": "zygor_npcdata_map_discovery",
        "schema_version": "1.0",
        "source_reference": uri,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_size_bytes": len(payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "map_area_count": len(map_areas),
        "map_areas": [
            {"map_id": map_id, "row_count": row_count}
            for map_id, row_count in map_areas
        ],
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--source-uri")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_npcdata_map_discovery(
        arguments.source,
        provider_version=arguments.provider_version,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
        retrieved_at=arguments.retrieved_at,
        source_uri=arguments.source_uri,
    )
    ContractValidator(DISCOVERY_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"discovery output is missing: {arguments.output}")
        if _read_record(arguments.output) != record:
            raise SystemExit("discovery output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
