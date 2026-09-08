"""Audit Zygor knowledge catalogs without producing execution authority."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.broker import load_knowledge_broker_catalog


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-knowledge-catalog-audit.schema.json"


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


def build_knowledge_catalog_audit(
    catalog_paths: Iterable[Path],
    *,
    client_version: str = "2.4.3",
    client_build: str = "2.4.3.8606",
) -> dict[str, Any]:
    """Load and summarize catalogs, keeping static positions advisory only."""

    paths = [Path(path).resolve() for path in catalog_paths]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("catalog paths must be non-empty and unique")
    summaries: list[dict[str, Any]] = []
    for path in paths:
        catalog = load_knowledge_broker_catalog(path)
        if catalog.client_version != client_version or catalog.client_build != client_build:
            raise ValueError(f"catalog client identity does not match: {path}")
        kinds = Counter(entry.kind for entry in catalog.entries)
        confidences = Counter(f"{float(entry.confidence):.6f}" for entry in catalog.entries)
        providers = Counter(entry.source.provider for entry in catalog.entries)
        origins = Counter(entry.source.origin for entry in catalog.entries)
        position_semantics = Counter(
            entry.position.position_semantics
            for entry in catalog.entries
            if entry.position is not None
        )
        position_count = sum(entry.position is not None for entry in catalog.entries)
        summaries.append(
            {
                "catalog_path": path.as_posix(),
                "catalog_id": catalog.catalog_id,
                "target_profile": catalog.target_profile,
                "entry_count": len(catalog.entries),
                "position_count": position_count,
                "missing_position_count": len(catalog.entries) - position_count,
                "kind_counts": dict(sorted(kinds.items())),
                "confidence_counts": dict(sorted(confidences.items())),
                "provider_counts": dict(sorted(providers.items())),
                "origin_counts": dict(sorted(origins.items())),
                "position_semantics_counts": dict(sorted(position_semantics.items())),
                "execution_authority": False,
            }
        )
    return {
        "record_type": "zygor_knowledge_catalog_audit",
        "schema_version": "1.0",
        "client_version": client_version,
        "client_build": client_build,
        "catalog_count": len(summaries),
        "catalogs": summaries,
        "dynamic_position_policy": "CLIENT_OBSERVED_CONFIRMATION_REQUIRED",
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="append", dest="catalogs", type=Path, required=True)
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_knowledge_catalog_audit(
        arguments.catalogs,
        client_version=arguments.client_version,
        client_build=arguments.client_build,
    )
    ContractValidator(AUDIT_SCHEMA).validate(record)
    if arguments.check:
        if not arguments.output.is_file():
            raise SystemExit(f"audit output is missing: {arguments.output}")
        existing = json.loads(arguments.output.read_text(encoding="utf-8"))
        if existing != record:
            raise SystemExit("audit output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
