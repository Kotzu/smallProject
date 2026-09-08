from __future__ import annotations

import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_world_map_area import (
    AUDIT_SCHEMA,
    build_world_map_area_audit,
)


ROOT = Path(__file__).parents[1]
ASSET = Path(r"E:\WoWserver\TBC-LAB\client-data\dbc\WorldMapArea.dbc")


class WorldMapAreaAuditTests(unittest.TestCase):
    def test_client_asset_audit_reports_contexts_without_runtime_authority(self) -> None:
        record = build_world_map_area_audit(ASSET)
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["record_count"], 68)
        self.assertEqual(record["map_count"], 7)
        self.assertEqual(record["map_ids"], [0, 1, 30, 489, 529, 530, 566])
        self.assertEqual(record["provenance_scope"], "lab_evaluation_only")
        self.assertFalse(record["execution_authority"])
        tirisfal = next(
            area
            for map_record in record["maps"]
            if map_record["map_id"] == 0
            for area in map_record["areas"]
            if area["internal_name"] == "Tirisfal"
        )
        self.assertEqual(tirisfal["area_id"], 85)
        self.assertAlmostEqual(tirisfal["bounds"][0], 3033.333251953125)


if __name__ == "__main__":
    unittest.main()
