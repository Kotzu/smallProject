from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_zygor_npcdata import AUDIT_SCHEMA, build_npcdata_audit


class ZygorNpcDataAuditTests(unittest.TestCase):
    def test_audit_is_content_minimal_and_deterministic(self) -> None:
        source = '''
ZGV._NPCData={
  ["TrainerAlchemy"] = [[
    4160=sA|m1453|x64.07|y68.36|wInside, Ainsha Bloodhorn
  ]],
  ["ClassRogue"] = [[
    4583=sH|m1458|x31.20|y48.50|Rogue trainer, Vol'jin
  ]],
}
'''.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "NPCData.lua"
            bindings_path = root / "bindings.json"
            source_path.write_bytes(source)
            bindings_path.write_text(json.dumps({
                "map_areas": [
                    {"map_id": 1453, "map_name": "Stormwind City"},
                    {"map_id": 1458, "map_name": "The Barrens"},
                ]
            }), encoding="utf-8")
            record = build_npcdata_audit(
                source_path,
                map_bindings_path=bindings_path,
                catalog_id="fixture.npcdata.audit",
                target_profile="tbc243_lab",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                provider_version="8.1.37070",
                retrieved_at="2026-08-31T20:00:00Z",
                source_uri="local://fixture/NPCData.lua",
            )
            ContractValidator(AUDIT_SCHEMA).validate(record)
            self.assertEqual(record["row_count"], 2)
            self.assertEqual(record["section_count"], 2)
            self.assertEqual(record["map_area_count"], 2)
            self.assertEqual(record["kind_counts"], {
                "class_trainer": 1, "profession_trainer": 1,
            })
            self.assertEqual(record["faction_counts"], {
                "alliance": 1, "horde": 1,
            })
            self.assertNotIn("entries", record)
            self.assertEqual(
                record,
                build_npcdata_audit(
                    source_path,
                    map_bindings_path=bindings_path,
                    catalog_id="fixture.npcdata.audit",
                    target_profile="tbc243_lab",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                    provider_version="8.1.37070",
                    retrieved_at="2026-08-31T20:00:00Z",
                    source_uri="local://fixture/NPCData.lua",
                ),
            )


if __name__ == "__main__":
    unittest.main()
