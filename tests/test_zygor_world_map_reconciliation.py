from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_zygor_world_map_reconciliation import (
    AUDIT_SCHEMA,
    build_zygor_world_map_reconciliation,
)


class ZygorWorldMapReconciliationTests(unittest.TestCase):
    def test_reconciliation_is_content_minimal_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            discovery = root / "discovery.json"
            librover = root / "data.lua"
            world = root / "world.json"
            discovery.write_text(json.dumps({
                "record_type": "zygor_npcdata_map_discovery",
                "map_areas": [
                    {"map_id": 1420, "row_count": 2},
                    {"map_id": 1421, "row_count": 1},
                    {"map_id": 9999, "row_count": 1},
                ],
                "source_sha256": "a" * 64,
            }), encoding="utf-8")
            librover.write_text('''
data.MapIDsByName = {
  ["Tirisfal Glades"] = {[0]=1420},
  ["Silverpine Forest"] = {[0]=1421},
  ["Unknown"] = {[0]=9999},
}
data.MapNamesByID = {}
''', encoding="utf-8")
            world.write_text(json.dumps({
                "record_type": "client_world_map_area_audit",
                "asset_sha256": "b" * 64,
                "maps": [{"map_id": 0, "areas": [
                    {"internal_name": "TirisfalGlades"},
                    {"internal_name": "SilverpineForest"},
                ]}],
            }), encoding="utf-8")
            record = build_zygor_world_map_reconciliation(
                discovery, librover, world,
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                npcdata_discovery_reference="local://fixture/discovery.json",
                map_source_reference="local://fixture/data.lua",
                world_map_area_reference="local://fixture/world.json",
            )
            ContractValidator(AUDIT_SCHEMA).validate(record)
            self.assertEqual(record["reconciliation_status"], "PARTIAL")
            self.assertEqual(record["exact_map_area_count"], 0)
            self.assertEqual(record["normalized_exact_map_area_count"], 2)
            self.assertEqual(record["unresolved_map_area_count"], 1)
            self.assertEqual(record["map_areas"][2]["world_map_ids"], [])
            self.assertNotIn("names", record)

    def test_ambiguous_world_name_does_not_bind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            discovery = root / "discovery.json"
            librover = root / "data.lua"
            world = root / "world.json"
            discovery.write_text(json.dumps({
                "record_type": "zygor_npcdata_map_discovery",
                "map_areas": [{"map_id": 7, "row_count": 1}],
                "source_sha256": "a" * 64,
            }), encoding="utf-8")
            librover.write_text('''
data.MapIDsByName = {
  ["Same"] = {[0]=7},
}
data.MapNamesByID = {}
''', encoding="utf-8")
            world.write_text(json.dumps({
                "record_type": "client_world_map_area_audit",
                "asset_sha256": "b" * 64,
                "maps": [
                    {"map_id": 0, "areas": [{"internal_name": "Same"}]},
                    {"map_id": 1, "areas": [{"internal_name": "Same"}]},
                ],
            }), encoding="utf-8")
            record = build_zygor_world_map_reconciliation(
                discovery, librover, world,
                provider_version="fixture",
                client_version="2.4.3",
                client_build="2.4.3.8606",
            )
            self.assertEqual(record["reconciliation_status"], "UNRESOLVED")
            self.assertEqual(record["ambiguous_map_area_count"], 1)
            self.assertEqual(record["map_areas"][0]["binding_status"], "AMBIGUOUS")

    def test_explicit_client_name_alias_binds_without_retaining_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            discovery = root / "discovery.json"
            librover = root / "data.lua"
            world = root / "world.json"
            discovery.write_text(json.dumps({
                "record_type": "zygor_npcdata_map_discovery",
                "map_areas": [{"map_id": 1420, "row_count": 2}],
                "source_sha256": "a" * 64,
            }), encoding="utf-8")
            librover.write_text('''
data.MapIDsByName = {
  ["Tirisfal Glades"] = {[0]=1420},
}
data.MapNamesByID = {}
''', encoding="utf-8")
            world.write_text(json.dumps({
                "record_type": "client_world_map_area_audit",
                "asset_sha256": "b" * 64,
                "maps": [{"map_id": 0, "areas": [
                    {"internal_name": "Tirisfal"},
                ]}],
            }), encoding="utf-8")
            record = build_zygor_world_map_reconciliation(
                discovery, librover, world,
                provider_version="fixture",
                client_version="2.4.3",
                client_build="2.4.3.8606",
            )
            self.assertEqual(record["reconciliation_status"], "COMPLETE")
            self.assertEqual(record["normalized_exact_map_area_count"], 1)
            self.assertEqual(record["resolved_map_area_count"], 1)
            self.assertNotIn("Tirisfal", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
