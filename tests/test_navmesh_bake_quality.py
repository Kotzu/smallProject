from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from scripts.audit_navmesh_bake_quality import build_navmesh_bake_quality_report


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "navmesh-bake-quality-report.schema.json"


def _inventory() -> dict[str, object]:
    return {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.client-world-v1",
        "client_build": "2.4.3.8606",
        "maps": [{
            "map_id": 0,
            "internal_name": "Azeroth",
            "adt_count": 2,
            "tiles": [
                {"grid_x": 28, "grid_y": 27},
                {"grid_x": 28, "grid_y": 28},
            ],
        }],
    }


def _write_nav(root: Path, name: str) -> None:
    path = root / "Nav" / "Azeroth" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"nav")


class NavmeshBakeQualityTests(unittest.TestCase):
    def test_in_progress_report_tracks_exact_missing_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=(
                    b'[time] START ["MapBuilder"]\n'
                    b"Finished Azeroth ADT (28, 27)\n"
                ),
            )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "IN_PROGRESS")
        self.assertEqual(report["missing_coordinates"], [[28, 28]])
        self.assertEqual(report["finished_adt_count"], 1)
        self.assertEqual(report["nav_tiles"][0]["artifact"], "28_27.nav")
        self.assertEqual(
            report["nav_tiles"][0]["sha256"], hashlib.sha256(b"nav").hexdigest(),
        )

    def test_complete_diagnostic_build_still_requires_geometry_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            _write_nav(root, "28_28.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=(
                    b'[time] START ["MapBuilder"]\n'
                    b"Thread # 1 ERROR: rcBuildContours: Multiple outlines for region 5.\n"
                    b"Thread # 1 WARNING: rcBuildPolyMesh: Bad triangulation Contour 2.\n"
                    b"RETURN_CODE 0\n"
                ),
            )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "COMPLETE_WITH_RECAST_DIAGNOSTICS")
        self.assertTrue(report["geometric_validation_required"])
        self.assertEqual(report["diagnostics"]["multiple_outline_error_count"], 1)
        self.assertEqual(len(report["nav_tiles"]), 2)
        self.assertRegex(report["nav_tiles_sha256"], r"^[a-f0-9]{64}$")

    def test_aggregate_mapbuilder_completion_counts_exact_adts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            _write_nav(root, "28_28.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=(
                    b"Finished Azeroth (512 tiles) in 2 seconds.\n"
                    b"RETURN_CODE 0\n"
                ),
            )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "COMPLETE_CLEAN")
        self.assertEqual(report["finished_adt_count"], 2)
        self.assertEqual(report["nav_adt_count"], 2)

    def test_report_catalog_identity_can_bind_to_candidate_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            _write_nav(root, "28_28.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=b'[time] START ["MapBuilder"]\nRETURN_CODE 0\n',
                catalog_id="wow.fixture.client-world-v2",
            )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["catalog_id"], "wow.fixture.client-world-v2")

    def test_zero_return_with_missing_tile_is_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=b'[time] START ["MapBuilder"]\nRETURN_CODE 0\n',
            )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "FAILED")

    def test_only_latest_appended_build_segment_is_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_nav(root, "28_27.nav")
            _write_nav(root, "28_28.nav")
            report = build_navmesh_bake_quality_report(
                _inventory(), map_name="Azeroth", nav_root=root,
                log_bytes=(
                    b'[old] START ["MapBuilder"]\n'
                    b"Thread # 1 ERROR: old error\nRETURN_CODE 1\n"
                    b'[new] START ["MapBuilder"]\nRETURN_CODE 0\n'
                ),
            )

        self.assertEqual(report["status"], "COMPLETE_CLEAN")
        self.assertEqual(report["diagnostics"]["recast_error_count"], 0)


if __name__ == "__main__":
    unittest.main()
