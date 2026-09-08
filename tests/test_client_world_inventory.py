from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_inventory import (
    ClientWorldInventoryError,
    build_client_world_asset_inventory_record,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "client-world-asset-inventory.schema.json"


def _map_dbc(*records: tuple[int, str]) -> bytes:
    strings = bytearray(b"\0")
    rows: list[bytes] = []
    for map_id, internal_name in records:
        offset = len(strings)
        strings.extend(internal_name.encode("utf-8") + b"\0")
        rows.append(struct.pack("<2I", map_id, offset))
    return b"".join((
        b"WDBC",
        struct.pack("<4I", len(records), 2, 8, len(strings)),
        *rows,
        bytes(strings),
    ))


def _profile() -> dict[str, object]:
    return {
        "catalog_id": "fixture.tbc.8606",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "the_burning_crusade",
        "client_version": "2.4.3",
        "client_build": "2.4.3.8606",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
    }


def _probe() -> dict[str, object]:
    return {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "asset_container": "mpq",
        "map_count": 2,
        "maps": [
            {
                "map_id": 0,
                "internal_name": "Azeroth",
                "wdt_present": True,
                "adt_count": 2,
                "adt_bounds": [28, 27, 28, 28],
                "tiles": [
                    {"grid_x": 28, "grid_y": 27},
                    {"grid_x": 28, "grid_y": 28},
                ],
            },
            {
                "map_id": 1,
                "internal_name": "Kalimdor",
                "wdt_present": True,
                "adt_count": 0,
                "adt_bounds": None,
                "tiles": [],
            },
        ],
        "execution_authority": False,
    }


class ClientWorldInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.map_dbc_path = Path(self.temporary.name) / "Map.dbc"
        self.map_dbc = _map_dbc((0, "Azeroth"), (1, "Kalimdor"))
        self.map_dbc_path.write_bytes(self.map_dbc)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_inventory_is_bound_to_exact_map_catalog_and_contract(self) -> None:
        record = build_client_world_asset_inventory_record(
            _probe(),
            identity_profile=_profile(),
            world_catalog_asset_path=self.map_dbc_path,
        )

        ContractValidator(SCHEMA).validate(record)
        self.assertEqual(record["map_count"], 2)
        self.assertEqual(record["maps"][0]["adt_count"], 2)
        self.assertEqual(
            record["world_catalog_asset_sha256"],
            hashlib.sha256(self.map_dbc).hexdigest(),
        )
        self.assertFalse(record["execution_authority"])

    def test_inventory_map_ids_and_names_must_exactly_match_map_dbc(self) -> None:
        changed = copy.deepcopy(_probe())
        changed["maps"][0]["internal_name"] = "Kalimdor"

        with self.assertRaisesRegex(ClientWorldInventoryError, "does not match"):
            build_client_world_asset_inventory_record(
                changed,
                identity_profile=_profile(),
                world_catalog_asset_path=self.map_dbc_path,
            )

    def test_inventory_rejects_duplicate_or_inconsistent_tiles(self) -> None:
        changed = copy.deepcopy(_probe())
        changed["maps"][0]["tiles"][1] = {"grid_x": 28, "grid_y": 27}

        with self.assertRaisesRegex(ClientWorldInventoryError, "duplicate"):
            build_client_world_asset_inventory_record(
                changed,
                identity_profile=_profile(),
                world_catalog_asset_path=self.map_dbc_path,
            )

    def test_inventory_is_json_serializable_without_execution_authority(self) -> None:
        record = build_client_world_asset_inventory_record(
            _probe(),
            identity_profile=_profile(),
            world_catalog_asset_path=self.map_dbc_path,
        )

        serialized = json.loads(json.dumps(record))
        self.assertIs(serialized["execution_authority"], False)


if __name__ == "__main__":
    unittest.main()
