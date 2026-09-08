"""Build a local, read-only RouteTeacher catalog from a user-owned Zygor folder.

The source folder is never copied into the repository.  The output is meant
for ``data/runtime`` (which is ignored) and contains only bounded parsed guide
facts needed by the leveling brain.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.broker import (
    KnowledgeBrokerCatalog,
)
from perfect_assassin.knowledge.route_teacher import (
    RouteTeacherImportConfig,
    import_zygor_lua,
)


CATALOG_SCHEMA = ROOT / "contracts" / "knowledge-broker-catalog.schema.json"
BINDINGS = ROOT / "config" / "knowledge" / "zygor-zone-map-bindings-tbc243.json"
GUIDE_FILES = {
    "horde": (
        "leveling/ZygorLevelingHordeCLASSIC.lua",
        "leveling/ZygorLevelingCommonCLASSIC.lua",
    ),
    "alliance": (
        "leveling/ZygorLevelingAllianceCLASSIC.lua",
        "leveling/ZygorLevelingCommonCLASSIC.lua",
    ),
}


def _bindings(path: Path) -> dict[str, tuple[int, str]]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("bindings"), list):
        raise ValueError("Zygor map binding file is invalid")
    result: dict[str, tuple[int, str]] = {}
    for item in record["bindings"]:
        if not isinstance(item, dict):
            raise ValueError("Zygor map binding row is invalid")
        zone = str(item["zone"]).strip()
        if not zone or zone in result:
            raise ValueError(f"duplicate or empty Zygor zone binding: {zone!r}")
        result[zone] = (int(item["map_id"]), str(item["map_name"]))
    return result


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-") or "guide"


def _bounded_entry_id(value: str) -> str:
    """Keep a deterministic, unique-enough ID inside the contract limit.

    Long guide names are common in user-owned exports.  Blindly cutting the
    string at 128 characters made every step in one long guide share the same
    ID, so the catalog could not be built.  Keep a readable prefix and append
    a digest of the complete ID instead of dropping the distinguishing tail.
    """

    if len(value) <= 128:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{value[:95]}-{digest}"


def build_catalog(
    source_root: Path,
    *,
    faction: str,
    bindings_path: Path = BINDINGS,
    provider_version: str = "8.1.37070",
    client_version: str = "2.4.3",
    client_build: str = "2.4.3.8606",
    retrieved_at: str = "1970-01-01T00:00:00Z",
) -> KnowledgeBrokerCatalog:
    if faction not in GUIDE_FILES:
        raise ValueError("faction must be horde or alliance")
    source_root = source_root.resolve()
    zone_bindings = _bindings(bindings_path.resolve())
    entries = []
    global_order = 0
    payload_hash = hashlib.sha256()
    for relative in GUIDE_FILES[faction]:
        path = source_root / relative
        payload = path.read_bytes()
        payload_hash.update(payload)
        imported = import_zygor_lua(
            payload.decode("utf-8"),
            config=RouteTeacherImportConfig(
                catalog_id=f"zygor.leveling.{faction}.{hashlib.sha256(payload).hexdigest()[:16]}",
                target_profile="tbc243_lab",
                client_version=client_version,
                client_build=client_build,
                provider_version=provider_version,
                retrieved_at=retrieved_at,
                source_uri=(
                    f"local://user-owned-zygor/{relative}"
                ),
                default_map_id=0,
                default_map_name="Azeroth",
                zone_map_bindings=zone_bindings,
            ),
        )
        for entry in imported.entries:
            global_order += 1
            # Keep IDs unique when the Common guide repeats a guide name.
            entry_id = f"route.{faction}.{_slug(relative)}.{entry.entry_id}"
            entry_id = _bounded_entry_id(entry_id)
            entries.append(
                replace(
                    entry,
                    entry_id=entry_id,
                    step_order=global_order,
                )
            )
    if not entries:
        raise ValueError("selected Zygor leveling files contain no guide steps")
    return KnowledgeBrokerCatalog(
        catalog_id=f"zygor.leveling.{faction}.{payload_hash.hexdigest()[:16]}",
        target_profile="tbc243_lab",
        product="wow",
        expansion="the_burning_crusade",
        client_version=client_version,
        client_build=client_build,
        entries=tuple(entries),
        execution_authority=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--faction", choices=tuple(GUIDE_FILES), default="horde")
    parser.add_argument("--bindings", type=Path, default=BINDINGS)
    parser.add_argument("--provider-version", default="8.1.37070")
    parser.add_argument("--client-version", default="2.4.3")
    parser.add_argument("--client-build", default="2.4.3.8606")
    parser.add_argument("--retrieved-at", default="1970-01-01T00:00:00Z")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    catalog = build_catalog(
        args.source_root,
        faction=args.faction,
        bindings_path=args.bindings,
        provider_version=args.provider_version,
        client_version=args.client_version,
        client_build=args.client_build,
        retrieved_at=args.retrieved_at,
    )
    record = catalog.to_record()
    ContractValidator(CATALOG_SCHEMA).validate(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "catalog_id": catalog.catalog_id,
        "entry_count": len(catalog.entries),
        "output": str(args.output.resolve()),
        "execution_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
