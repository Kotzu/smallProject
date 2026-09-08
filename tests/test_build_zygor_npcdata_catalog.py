from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_zygor_npcdata_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("zygor_npcdata_catalog_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildZygorNpcDataCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_catalog_keeps_zone_area_candidates_and_provenance(self) -> None:
        source = '''ZGV._NPCData={
  ["TrainerAlchemy"] = [[
    4160=sA|m1453|x64.07|y68.36|wInside, Ainsha Bloodhorn
  ]],
  ["ClassRogue"] = [[
    4583=sH|m1458|x31.20|y48.50|Rogue trainer, Vol'jin
  ]],
}'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "NPCData.lua"
            bindings_path = root / "bindings.json"
            source_path.write_text(source, encoding="utf-8")
            bindings_path.write_text(json.dumps({
                "map_areas": [
                    {"map_id": 1453, "map_name": "Stormwind City"},
                    {"map_id": 1458, "map_name": "Undercity"},
                ]
            }), encoding="utf-8")
            catalog = self.module.build_catalog(
                source_path,
                map_bindings_path=bindings_path,
                target_profile="tbc243_lab",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                provider_version="8.1.37070",
                retrieved_at="2026-09-02T00:00:00Z",
                source_uri="local://fixture/NPCData.lua",
            )

        record = catalog.to_record()
        ContractValidator(
            ROOT / "contracts" / "knowledge-broker-catalog.schema.json"
        ).validate(record)
        self.assertEqual(len(catalog.entries), 2)
        self.assertEqual({entry.map_scope for entry in catalog.entries}, {"zone_area"})
        self.assertTrue(all(entry.position is not None for entry in catalog.entries))
        self.assertTrue(all(entry.confidence == 0.70 for entry in catalog.entries))
        self.assertTrue(all(
            entry.position is not None
            and entry.position.position_semantics == "STATIC_SOURCE_CANDIDATE"
            for entry in catalog.entries
        ))
        self.assertFalse(catalog.execution_authority)

    def test_missing_zone_area_binding_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "NPCData.lua"
            bindings_path = root / "bindings.json"
            source_path.write_text(
                'ZGV._NPCData={["ClassRogue"]=[[\n'
                '  4583=sH|m1458|x31.20|y48.50|Rogue trainer, Vol\'jin\n'
                ']]}',
                encoding="utf-8",
            )
            bindings_path.write_text(json.dumps({
                "map_areas": [{"map_id": 1453, "map_name": "Stormwind City"}]
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module.build_catalog(
                    source_path,
                    map_bindings_path=bindings_path,
                    target_profile="tbc243_lab",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                    provider_version="8.1.37070",
                    retrieved_at="2026-09-02T00:00:00Z",
                )


if __name__ == "__main__":
    unittest.main()
