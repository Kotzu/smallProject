from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_zygor_leveling_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("zygor_leveling_catalog_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildZygorLevelingCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_horde_catalog_merges_common_steps_without_copying_source_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "leveling").mkdir()
            guide = '''ZygorGuidesViewer:RegisterGuide("fixture",{},[[
step
|goto Tirisfal Glades 10,20
]])\n'''
            for name in (
                "ZygorLevelingHordeCLASSIC.lua",
                "ZygorLevelingCommonCLASSIC.lua",
            ):
                (root / "leveling" / name).write_text(guide, encoding="utf-8")
            catalog = self.module.build_catalog(
                root,
                faction="horde",
                retrieved_at="2026-09-02T00:00:00Z",
            )
        self.assertEqual(len(catalog.entries), 2)
        self.assertNotEqual(catalog.entries[0].entry_id, catalog.entries[1].entry_id)
        self.assertEqual([entry.step_order for entry in catalog.entries], [1, 2])
        self.assertEqual(
            catalog.entries[0].source.retrieved_at,
            "2026-09-02T00:00:00Z",
        )
        ContractValidator(
            ROOT / "contracts" / "knowledge-broker-catalog.schema.json"
        ).validate(catalog.to_record())
        self.assertFalse(catalog.execution_authority)

    def test_missing_selected_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                self.module.build_catalog(Path(directory), faction="horde")

    def test_long_guide_ids_keep_each_step_unique_after_bounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "leveling").mkdir()
            guide_name = "guide-" + ("x" * 100)
            guide = f'''ZygorGuidesViewer:RegisterGuide("{guide_name}",{{}},[[
step
|goto Tirisfal Glades 10,20
step
|goto Tirisfal Glades 11,21
]])\n'''
            for name in (
                "ZygorLevelingHordeCLASSIC.lua",
                "ZygorLevelingCommonCLASSIC.lua",
            ):
                (root / "leveling" / name).write_text(guide, encoding="utf-8")
            catalog = self.module.build_catalog(root, faction="horde")

        entry_ids = [entry.entry_id for entry in catalog.entries]
        self.assertEqual(len(entry_ids), 4)
        self.assertEqual(len(set(entry_ids)), len(entry_ids))
        self.assertTrue(all(len(entry_id) <= 128 for entry_id in entry_ids))
        ContractValidator(
            ROOT / "contracts" / "knowledge-broker-catalog.schema.json"
        ).validate(catalog.to_record())


if __name__ == "__main__":
    unittest.main()
