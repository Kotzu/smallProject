from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator

from scripts.audit_zygor_route_transform_coverage import (
    AUDIT_SCHEMA,
    BINDING_SCHEMA,
    SELECTED_FILES,
    TRANSFORM_SCHEMA,
    build_zygor_route_transform_coverage,
)


class ZygorRouteTransformCoverageTests(unittest.TestCase):
    def _bindings(self, root: Path) -> Path:
        path = root / "bindings.json"
        path.write_text(json.dumps({
            "record_type": "zygor_zone_map_bindings",
            "schema_version": "1.0",
            "client_build": "2.4.3.8606",
            "provenance": "client_world_map_area_reviewed",
            "bindings": [
                {"zone": "Tirisfal Glades", "map_id": 0, "map_name": "Azeroth"},
                {"zone": "Black Temple", "map_id": 564, "map_name": "BlackTemple"},
            ],
            "execution_authority": False,
        }), encoding="utf-8")
        ContractValidator(BINDING_SCHEMA).validate(json.loads(path.read_text(encoding="utf-8")))
        return path

    def _catalog(self, root: Path) -> Path:
        path = root / "transforms.json"
        path.write_text(json.dumps({
            "record_type": "tbc243_world_map_zone_transform_catalog",
            "schema_version": "1.0",
            "target_profile": "tbc_243_lab",
            "client_build": "2.4.3.8606",
            "asset_name": "WorldMapArea.dbc",
            "asset_sha256": "a" * 64,
            "record_fingerprint_sha256": "b" * 64,
            "coordinate_space": "wow_world_map_2d",
            "provenance_origin": "client_asset_calibration",
            "source_reference": "fixture",
            "retrieved_at": "2026-08-31T00:00:00Z",
            "zones": [{
                "map_id": 0, "area_id": 85, "internal_name": "Tirisfal",
                "bounds": [1.0, -1.0, 2.0, -2.0],
            }],
            "execution_authority": False,
        }), encoding="utf-8")
        ContractValidator(TRANSFORM_SCHEMA).validate(json.loads(path.read_text(encoding="utf-8")))
        return path

    def test_counts_transformed_and_unresolved_without_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "guides"
            for relative in SELECTED_FILES:
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'ZygorGuidesViewer:RegisterGuide("fixture",{},[[\n'
                    "step\n|goto Tirisfal Glades 25,75\n"
                    "step\n|goto Black Temple 30,70\n]])\n",
                    encoding="utf-8",
                )
            archive = root / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            record = build_zygor_route_transform_coverage(
                source, archive,
                bindings_path=self._bindings(root),
                transform_catalog_path=self._catalog(root),
                archive_reference="local://Zygor.rar",
                provider_version="8.1.37070",
                client_version="2.4.3",
                client_build="2.4.3.8606",
            )
        ContractValidator(AUDIT_SCHEMA).validate(record)
        self.assertEqual(record["coordinate_candidate_count"], 12)
        self.assertEqual(record["transformed_coordinate_count"], 6)
        self.assertEqual(record["unresolved_coordinate_count"], 6)
        self.assertEqual(record["coverage_state"], "PARTIAL_CLIENT_2D_TRANSFORM")
        self.assertFalse(record["execution_authority"])
        serialized = json.dumps(record)
        self.assertNotIn("25,75", serialized)
        self.assertNotIn("Black Temple", serialized)

    def test_unknown_zone_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "guides"
            for relative in SELECTED_FILES:
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    'ZygorGuidesViewer:RegisterGuide("fixture",{},[[\n'
                    "step\n|goto Unknown Zone 25,75\n]])\n",
                    encoding="utf-8",
                )
            archive = root / "Zygor.rar"
            archive.write_bytes(b"fixture archive")
            with self.assertRaisesRegex(ValueError, "no explicit WorldPack binding"):
                build_zygor_route_transform_coverage(
                    source, archive,
                    bindings_path=self._bindings(root),
                    transform_catalog_path=self._catalog(root),
                    archive_reference="local://Zygor.rar",
                    provider_version="8.1.37070",
                    client_version="2.4.3",
                    client_build="2.4.3.8606",
                )


if __name__ == "__main__":
    unittest.main()
