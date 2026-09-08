"""Build a deterministic, lab-only audit of client WorldMapArea coverage."""

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

from perfect_assassin.adapter.world_map_area import WorldMapAreaTable
from perfect_assassin.contract_validation import ContractValidator


AUDIT_SCHEMA = ROOT / "contracts" / "client-world-map-area-audit.schema.json"
DEFAULT_ASSET = Path(r"E:\WoWserver\TBC-LAB\client-data\dbc\WorldMapArea.dbc")
DEFAULT_BUILD_SIGNATURE = (
    "wow-tbc-2.4.3.8606-enGB:sha256:"
    "406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6"
)
PINNED_ASSET_SHA256 = (
    "918BF402A83BAA78B0D35F0978BC760683291EE8CF48D7CE8C90E3814AA1BC7B"
)


def _relative_reference(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def build_world_map_area_audit(
    asset_path: Path,
    *,
    expected_sha256: str = PINNED_ASSET_SHA256,
    build_signature: str = DEFAULT_BUILD_SIGNATURE,
) -> dict[str, object]:
    """Parse static client map bounds; never grants runtime authority."""

    asset_path = asset_path.resolve()
    table = WorldMapAreaTable.from_file(
        asset_path,
        expected_sha256=expected_sha256,
        client_build="2.4.3.8606",
        build_signature=build_signature,
    )
    groups: dict[int, list[dict[str, object]]] = {}
    for record in table.records:
        groups.setdefault(record.map_id, []).append({
            "record_id": record.record_id,
            "area_id": record.area_id,
            "internal_name": record.internal_name,
            "bounds": [
                record.loc_left, record.loc_right,
                record.loc_top, record.loc_bottom,
            ],
            "virtual_map_id": record.virtual_map_id,
        })
    map_ids = sorted(groups)
    maps = [
        {"map_id": map_id, "area_count": len(groups[map_id]), "areas": groups[map_id]}
        for map_id in map_ids
    ]
    actual_sha256 = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    return {
        "record_type": "client_world_map_area_audit",
        "schema_version": "1.0",
        "client_build": "2.4.3.8606",
        "asset_reference": _relative_reference(asset_path),
        "asset_sha256": actual_sha256,
        "provenance_scope": table.provenance.scope,
        "record_count": len(table.records),
        "map_count": len(map_ids),
        "map_ids": map_ids,
        "maps": maps,
        "execution_authority": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--expected-sha256", default=PINNED_ASSET_SHA256)
    parser.add_argument("--build-signature", default=DEFAULT_BUILD_SIGNATURE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    record = build_world_map_area_audit(
        arguments.asset,
        expected_sha256=arguments.expected_sha256,
        build_signature=arguments.build_signature,
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
