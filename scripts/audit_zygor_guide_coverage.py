"""Audit selected Zygor TBC guide files without retaining licensed content."""

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
    _entry_kind,
    _legacy_step_blocks,
    _legacy_tags,
    _modern_coordinates,
    _modern_step_blocks,
    _source_coordinates,
)


AUDIT_SCHEMA = ROOT / "contracts" / "zygor-guide-coverage.schema.json"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


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


def _file_counts(path: Path, archive_path: str) -> dict[str, object]:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    modern = _modern_step_blocks(text)
    legacy = _legacy_step_blocks(text)
    if modern:
        blocks = [block for _line, _guide, block in modern]
        coordinate_count = sum(_modern_coordinates(block) is not None for block in blocks)
    else:
        blocks = [block for _line, block in legacy]
        coordinate_count = sum(_source_coordinates(block) is not None for block in blocks)
    kinds = Counter(_entry_kind(block) for block in blocks)
    tags = Counter(tag for block in blocks for tag in _legacy_tags(block))
    return {
        "archive_path": archive_path,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_size_bytes": len(payload),
        "step_count": len(blocks),
        "coordinate_candidate_count": coordinate_count,
        "kind_counts": {key: int(kinds.get(key, 0)) for key in KIND_KEYS},
        "tag_counts": {key: int(tags.get(key, 0)) for key in TAG_KEYS},
        "execution_authority": False,
    }


def build_zygor_guide_coverage(
    source_root: Path,
    archive_path: Path,
    *,
    archive_reference: str,
    provider_version: str,
    client_version: str,
    client_build: str,
) -> dict[str, object]:
    source_root = source_root.resolve()
    archive_path = archive_path.resolve()
    archive_payload = archive_path.read_bytes()
    files = [
        _file_counts(source_root / relative, relative)
        for relative in SELECTED_FILES
    ]
    if any(not (source_root / relative).is_file() for relative in SELECTED_FILES):
        missing = [relative for relative in SELECTED_FILES if not (source_root / relative).is_file()]
        raise FileNotFoundError("selected guide file is missing: " + ", ".join(missing))
    kind_counts = Counter()
    tag_counts = Counter()
    for item in files:
        kind_counts.update(item["kind_counts"])
        tag_counts.update(item["tag_counts"])
    return {
        "record_type": "zygor_guide_coverage",
        "schema_version": "1.0",
        "source_archive_reference": archive_reference,
        "source_archive_sha256": hashlib.sha256(archive_payload).hexdigest(),
        "source_archive_size_bytes": len(archive_payload),
        "provider_version": provider_version,
        "client_version": client_version,
        "client_build": client_build,
        "selected_file_count": len(files),
        "files": files,
        "step_count": sum(int(item["step_count"]) for item in files),
        "coordinate_candidate_count": sum(
            int(item["coordinate_candidate_count"]) for item in files
        ),
        "kind_counts": {key: int(kind_counts.get(key, 0)) for key in KIND_KEYS},
        "tag_counts": {key: int(tag_counts.get(key, 0)) for key in TAG_KEYS},
        "coverage_state": "SELECTED_NON_TRIAL_FILES",
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-reference", required=True)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_zygor_guide_coverage(
        arguments.source_root,
        arguments.archive,
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
            raise SystemExit("audit output is stale")
    else:
        _atomic_write_json(arguments.output, record)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
