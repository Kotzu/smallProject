"""Audit static Zygor NPCData IDs against the bundled LibRover map table."""

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
from perfect_assassin.knowledge.zygor_map_bindings import (
    parse_zygor_map_name_candidates,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-npcdata-map-binding-audit.schema.json"


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


def build_npcdata_map_binding_audit(
    npcdata_source: Path,
    map_source: Path,
    *,
    provider_version: str,
    client_version: str,
    client_build: str,
    npcdata_source_uri: str | None = None,
    map_source_uri: str | None = None,
) -> dict[str, object]:
    npcdata_source = npcdata_source.resolve()
    map_source = map_source.resolve()
    npcdata_payload = npcdata_source.read_bytes()
    map_payload = map_source.read_bytes()
    npcdata_text = npcdata_payload.decode("utf-8")
    map_text = map_payload.decode("utf-8")
    map_areas = discover_zygor_npc_map_areas(npcdata_text)
    candidates = parse_zygor_map_name_candidates(map_text)
    statuses: list[dict[str, object]] = []
    for map_id, row_count in map_areas:
        names = candidates.get(map_id, ())
        binding_status = (
            "BOUND" if len(names) == 1 else "AMBIGUOUS" if len(names) > 1 else "UNRESOLVED"
        )
        statuses.append(
            {"map_id": map_id, "row_count": row_count, "binding_status": binding_status}
        )
    bound = sum(item["binding_status"] == "BOUND" for item in statuses)
    ambiguous = sum(item["binding_status"] == "AMBIGUOUS" for item in statuses)
    unresolved = sum(item["binding_status"] == "UNRESOLVED" for item in statuses)
    overall = "COMPLETE" if unresolved == 0 and ambiguous == 0 else "PARTIAL" if bound else "UNRESOLVED"
    return {
        "record_type": "zygor_npcdata_map_binding_audit",
        "schema_version": "1.0",
        "npcdata_source_reference": npcdata_source_uri or f"local://{npcdata_source.as_posix()}",
        "npcdata_source_sha256": hashlib.sha256(npcdata_payload).hexdigest(),
        "npcdata_source_size_bytes": len(npcdata_payload),
        "map_source_reference": map_source_uri or f"local://{map_source.as_posix()}",
        "map_source_sha256": hashlib.sha256(map_payload).hexdigest(),
        "map_source_size_bytes": len(map_payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "map_area_count": len(statuses),
        "bound_map_area_count": bound,
        "ambiguous_map_area_count": ambiguous,
        "unresolved_map_area_count": unresolved,
        "binding_status": overall,
        # Deliberately omit map names, NPC IDs, names and coordinates.  The
        # names remain available only in-memory for an explicitly requested
        # caller-side compatibility binding.
        "map_areas": statuses,
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npcdata-source", type=Path, required=True)
    parser.add_argument("--map-source", type=Path, required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--npcdata-source-uri")
    parser.add_argument("--map-source-uri")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_npcdata_map_binding_audit(
        arguments.npcdata_source,
        arguments.map_source,
        provider_version=arguments.provider_version,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
        npcdata_source_uri=arguments.npcdata_source_uri,
        map_source_uri=arguments.map_source_uri,
    )
    ContractValidator(AUDIT_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"audit output is missing: {arguments.output}")
        if _read_record(arguments.output) != record:
            raise SystemExit("audit output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
