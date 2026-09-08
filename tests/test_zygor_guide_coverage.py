from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator

from scripts.audit_zygor_guide_coverage import (
    AUDIT_SCHEMA,
    SELECTED_FILES,
    build_zygor_guide_coverage,
)


class ZygorGuideCoverageTests(unittest.TestCase):
    def test_content_minimal_coverage_counts_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "guides"
            for relative in SELECTED_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'ZygorGuidesViewer:RegisterGuide("fixture",{},[[\n'
                    "step\n|goto Tirisfal Glades 30,70\n"
                    "step\nkill 1 rat##1 |goto Tirisfal Glades 31,71\n"
                    "]])\n",
                    encoding="utf-8",
                )
            archive = Path(directory) / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            record = build_zygor_guide_coverage(
                root,
                archive,
                archive_reference="local://Zygor.rar",
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
            )
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["selected_file_count"], 6)
        self.assertEqual(record["step_count"], 12)
        self.assertEqual(record["coordinate_candidate_count"], 12)
        self.assertEqual(record["kind_counts"]["route_step"], 12)
        self.assertFalse(record["execution_authority"])
        self.assertNotIn("Tirisfal", json.dumps(record))

    def test_missing_selected_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "guides"
            root.joinpath(SELECTED_FILES[0]).parent.mkdir(parents=True, exist_ok=True)
            root.joinpath(SELECTED_FILES[0]).write_text("step\n", encoding="utf-8")
            archive = Path(directory) / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            with self.assertRaises(FileNotFoundError):
                build_zygor_guide_coverage(
                    root,
                    archive,
                    archive_reference="local://Zygor.rar",
                    provider_version="8.1.37070",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                )


if __name__ == "__main__":
    unittest.main()
