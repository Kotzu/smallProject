from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from scripts.discover_zygor_npcdata_maps import (
    DISCOVERY_SCHEMA,
    build_npcdata_map_discovery,
)


class ZygorNpcDataMapDiscoveryTests(unittest.TestCase):
    def test_discovery_is_content_minimal_and_deterministic(self) -> None:
        source = '''
ZGV._NPCData={
  ["TrainerAlchemy"] = [[
    4160=sA|m1453|x64.07|y68.36|wInside, Ainsha Bloodhorn
    4161=sA|m1453|x64.10|y68.40|Second row
  ]],
  ["ClassRogue"] = [[
    4583=sH|m1458|x31.20|y48.50|Rogue trainer, Vol'jin
  ]],
}
'''.encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "NPCData.lua"
            source_path.write_bytes(source)
            record = build_npcdata_map_discovery(
                source_path,
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                retrieved_at="2026-08-31T20:00:00Z",
                source_uri="local://fixture/NPCData.lua",
            )
            ContractValidator(DISCOVERY_SCHEMA).validate(record)
            self.assertEqual(record["map_area_count"], 2)
            self.assertEqual(record["map_areas"], [
                {"map_id": 1453, "row_count": 2},
                {"map_id": 1458, "row_count": 1},
            ])
            self.assertNotIn("entries", record)
            self.assertNotIn("name", record)
            self.assertEqual(
                record,
                build_npcdata_map_discovery(
                    source_path,
                    provider_version="8.1.37070",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                    retrieved_at="2026-08-31T20:00:00Z",
                    source_uri="local://fixture/NPCData.lua",
                ),
            )

    def test_unsupported_numeric_row_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "NPCData.lua"
            source_path.write_text(
                'ZGV._NPCData={ ["x"] = [[ 1=sA|m1453|x1 ]] }',
                encoding="utf-8",
            )
            # The bounded parser must reject a row that is not fully formed.
            with self.assertRaises(ValueError):
                build_npcdata_map_discovery(
                    source_path,
                    provider_version="8.1.37070",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                    source_uri="local://fixture/NPCData.lua",
                )


if __name__ == "__main__":
    unittest.main()
