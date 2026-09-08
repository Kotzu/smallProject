from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.knowledge.npc_data import NpcDataImportConfig, import_zygor_npc_data
from perfect_assassin.knowledge.zygor_map_bindings import (
    ZygorMapBindingError,
    parse_zygor_map_name_candidates,
    resolve_zygor_map_bindings,
)
from scripts.audit_zygor_npcdata_map_bindings import (
    AUDIT_SCHEMA,
    build_npcdata_map_binding_audit,
)


class ZygorMapBindingTests(unittest.TestCase):
    def test_resolves_only_requested_ids_and_preserves_floor_aliases(self) -> None:
        source = """
data.MapIDsByName = {
  [\"Tirisfal Glades\"] = {[0]=1420},
  [\"Shadowfang Keep\"] = {[0]=9017},
  [\"Auchenai Crypts\"] = {[0]=256,[1]=257},
}
data.MapNamesByID = {}
"""
        self.assertEqual(
            parse_zygor_map_name_candidates(source),
            {1420: ("Tirisfal Glades",), 256: ("Auchenai Crypts",),
             257: ("Auchenai Crypts",), 9017: ("Shadowfang Keep",)},
        )
        self.assertEqual(
            resolve_zygor_map_bindings(source, {1420, 257}),
            {1420: "Tirisfal Glades", 257: "Auchenai Crypts"},
        )

    def test_ambiguous_alias_fails_closed(self) -> None:
        source = """
data.MapIDsByName = {
  [\"First alias\"] = {[0]=9010},
  [\"Second alias\"] = {[0]=9010},
}
data.MapNamesByID = {}
"""
        with self.assertRaises(ZygorMapBindingError):
            resolve_zygor_map_bindings(source, {9010})

    def test_binding_audit_is_content_minimal_and_import_works_in_memory(self) -> None:
        npcdata = """
ZGV._NPCData={ [\"Trainer\"] = [[
  1=sH|m1420|x10|y20|Tirisfal trainer
  2=sH|m9017|x30|y40|Crypt trainer
]] }
""".encode("utf-8")
        librover = """
data.MapIDsByName = {
  [\"Tirisfal Glades\"] = {[0]=1420},
  [\"Shadowfang Keep\"] = {[0]=9017},
}
data.MapNamesByID = {}
""".encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            npc_path = root / "NPCData.lua"
            map_path = root / "data.lua"
            npc_path.write_bytes(npcdata)
            map_path.write_bytes(librover)
            record = build_npcdata_map_binding_audit(
                npc_path,
                map_path,
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
                npcdata_source_uri="local://fixture/NPCData.lua",
                map_source_uri="local://fixture/data.lua",
            )
            ContractValidator(AUDIT_SCHEMA).validate(record)
            self.assertEqual(record["binding_status"], "COMPLETE")
            self.assertEqual(record["bound_map_area_count"], 2)
            self.assertNotIn("map_name", record)
            self.assertNotIn("name", record)
            bindings = resolve_zygor_map_bindings(librover.decode("utf-8"), {1420, 9017})
            catalog = import_zygor_npc_data(
                npcdata.decode("utf-8"),
                config=NpcDataImportConfig(
                    catalog_id="fixture",
                    target_profile="tbc243_lab",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                    provider_version="8.1.37070",
                    retrieved_at="2026-08-31T00:00:00Z",
                    source_uri="local://fixture/NPCData.lua",
                    zone_area_bindings=bindings,
                ),
            )
            self.assertEqual(len(catalog.entries), 2)
            self.assertEqual(catalog.entries[0].map_scope, "zone_area")


if __name__ == "__main__":
    unittest.main()
