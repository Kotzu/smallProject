from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator

from scripts.audit_zygor_route_coverage import (
    AUDIT_SCHEMA,
    BINDING_SCHEMA,
    SELECTED_FILES,
    build_zygor_route_coverage,
)


class ZygorRouteCoverageTests(unittest.TestCase):
    def _bindings(self, root: Path, *, zone: str = "Tirisfal Glades") -> Path:
        path = root / "bindings.json"
        path.write_text(
            json.dumps({
                "record_type": "zygor_zone_map_bindings",
                "schema_version": "1.0",
                "client_build": "2.4.3.8606",
                "provenance": "client_world_map_area_reviewed",
                "bindings": [{"zone": zone, "map_id": 0, "map_name": "Azeroth"}],
                "execution_authority": False,
            }),
            encoding="utf-8",
        )
        ContractValidator(BINDING_SCHEMA).validate(json.loads(path.read_text(encoding="utf-8")))
        return path

    def test_explicit_binding_reports_map_counts_without_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "guides"
            for relative in SELECTED_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'ZygorGuidesViewer:RegisterGuide("fixture",{},[[\n'
                    "step\n"
                    "talk Trainer##1\n"
                    "Train Abilities |trainer Trainer##1 |goto Tirisfal Glades/0 30,70\n"
                    "step\n"
                    "kill 1 rat##2 |goto Tirisfal Glades 31,71\n"
                    "]])\n",
                    encoding="utf-8",
                )
            archive = Path(directory) / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            bindings = self._bindings(Path(directory))
            record = build_zygor_route_coverage(
                root,
                archive,
                bindings_path=bindings,
                archive_reference="local://Zygor.rar",
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
            )
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["selected_file_count"], 6)
        self.assertEqual(record["step_count"], 12)
        self.assertEqual(record["coordinate_candidate_count"], 12)
        self.assertEqual(record["map_coverage"][0]["map_id"], 0)
        self.assertEqual(record["map_coverage"][0]["step_count"], 12)
        self.assertNotIn("Trainer", json.dumps(record))
        self.assertFalse(record["execution_authority"])

    def test_unknown_zone_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "guides"
            for relative in SELECTED_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'ZygorGuidesViewer:RegisterGuide("fixture",{},[[\n'
                    "step\n|goto Unknown Zone 30,70\n]])\n",
                    encoding="utf-8",
                )
            archive = Path(directory) / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            bindings = self._bindings(Path(directory))
            with self.assertRaisesRegex(ValueError, "no explicit WorldPack binding"):
                build_zygor_route_coverage(
                    root,
                    archive,
                    bindings_path=bindings,
                    archive_reference="local://Zygor.rar",
                    provider_version="8.1.37070",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                )


if __name__ == "__main__":
    unittest.main()
