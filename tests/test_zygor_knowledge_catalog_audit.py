from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_zygor_knowledge_catalogs import (
    AUDIT_SCHEMA,
    build_knowledge_catalog_audit,
)


class ZygorKnowledgeCatalogAuditTests(unittest.TestCase):
    @staticmethod
    def _catalog(path: Path, *, catalog_id: str, with_position: bool) -> None:
        entry = {
            "entry_id": f"{catalog_id}.entry",
            "kind": "class_trainer",
            "name": "Trainer",
            "map_id": 0,
            "map_name": "Azeroth",
            "map_scope": "zone_area",
            "level_range": {"min": 1, "max": 70},
            "source": {
                "provider": "route_teacher",
                "origin": "route_guidance",
                "uri": "local://fixture/zygor.lua",
                "provider_version": "8.1.37070",
                "retrieved_at": "2026-09-03T00:00:00Z",
                "content_mode": "user_owned_export",
            },
            "confidence": 0.75,
            "evidence_refs": ["local://fixture/zygor.lua#L1"],
            "position": (
                {
                    "x": 0.25,
                    "y": 0.50,
                    "coordinate_frame": "normalized_map_2d",
                    "position_semantics": "STATIC_SOURCE_CANDIDATE",
                }
                if with_position
                else None
            ),
            "execution_authority": False,
        }
        payload = {
            "record_type": "knowledge_broker_catalog",
            "schema_version": "1.0",
            "catalog_id": catalog_id,
            "target_profile": "tbc243_lab",
            "product": "wow",
            "expansion": "the_burning_crusade",
            "client_version": "2.4.3",
            "client_build": "2.4.3.8606",
            "entries": [entry],
            "execution_authority": False,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_audit_counts_positions_and_requires_client_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "one.json", root / "two.json"
            self._catalog(first, catalog_id="fixture.one", with_position=True)
            self._catalog(second, catalog_id="fixture.two", with_position=False)
            record = build_knowledge_catalog_audit([first, second])
            ContractValidator(AUDIT_SCHEMA).validate(record)
            self.assertEqual(record["catalog_count"], 2)
            self.assertEqual(record["catalogs"][0]["position_count"], 1)
            self.assertEqual(record["catalogs"][1]["missing_position_count"], 1)
            self.assertEqual(
                record["dynamic_position_policy"],
                "CLIENT_OBSERVED_CONFIRMATION_REQUIRED",
            )
            self.assertFalse(record["input_emitted"])
            self.assertFalse(record["server_truth_used"])

    def test_audit_rejects_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.json"
            self._catalog(path, catalog_id="fixture.one", with_position=True)
            with self.assertRaises(ValueError):
                build_knowledge_catalog_audit([path, path])


if __name__ == "__main__":
    unittest.main()
