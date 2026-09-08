from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_catalog import (
    build_client_world_catalog_record,
)
from scripts.audit_navmesh_geometry import (
    build_navmesh_geometry_validation_report,
)
from tests.test_navigation_contracts import detour_fixture_payload


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "navmesh-geometry-validation-report.schema.json"


def _map_dbc() -> bytes:
    strings = b"\0Azeroth\0"
    # One WDBC row: map id 0 and the string offset for Azeroth.
    return b"".join((
        b"WDBC", struct.pack("<4I", 1, 2, 8, len(strings)),
        struct.pack("<2I", 0, 1), strings,
    ))


def _profile() -> dict[str, object]:
    return {
        "record_type": "client_world_coverage_profile",
        "schema_version": "1.0",
        "catalog_id": "fixture.detour-v7",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "the_burning_crusade",
        "client_version": "2.4.3",
        "client_build": "2.4.3.8606",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
        "nav_profile_id": "fixture-detour-v7",
        "maps": [{
            "map_id": 0,
            "internal_name": "Azeroth",
            "classification": "continent",
            "coverage_state": "partial",
            "interior_coverage": "partial",
            "road_semantic_coverage": "partial",
        }],
        "execution_authority": False,
    }


def _namigator_adt_fixture(
    *, adt_x: int, adt_y: int, empty_first_tile: bool = False,
) -> bytes:
    """One minimal Namigator-shaped ADT, padded to the declared 16x16 grid.

    The production builder uses a 64-bit ``dtPolyRef``.  This fixture verifies
    that the gate validates that native serialization layout rather than only
    accepting the portable 32-bit Detour unit fixture.
    """

    records: list[bytes] = []
    for local_x in range(16):
        for local_y in range(16):
            mesh = detour_fixture_payload(
                grid_x=adt_x * 16 + local_x,
                grid_y=adt_y * 16 + local_y,
            )
            if empty_first_tile and local_x == 0 and local_y == 0:
                mesh = b""
            else:
                link_offset = 100 + 3 * 12 + 32
                mesh = b"".join((
                    mesh[:link_offset],
                    bytes(3 * 16),
                    mesh[link_offset + 3 * 12 :],
                ))
            records.append(b"".join((
                struct.pack("<2I", adt_x * 16 + local_x, adt_y * 16 + local_y),
                struct.pack("<2I", 0, 0),
                b"\x00",
                struct.pack(
                    "<2i8f",
                    1,
                    1,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    0.25,
                ),
                struct.pack("<I", 0),
                struct.pack("<I", len(mesh)),
                mesh,
            )))
    raw = b"".join((
        struct.pack("<6I", 1313751382, 808464693, 1094996992, adt_x, adt_y, 256),
        *records,
    ))
    return zlib.compress(raw)


class NavmeshGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.nav_root = self.root / "nav"
        self.nav_directory = self.nav_root / "Nav" / "Azeroth"
        self.nav_directory.mkdir(parents=True)
        semantic_directory = self.nav_root / "semantics"
        semantic_directory.mkdir()
        (self.nav_root / "Azeroth.map").write_bytes(b"fixture map")
        self.tile_path = self.nav_directory / "28_28.nav"
        self.tile_path.write_bytes(detour_fixture_payload(grid_x=28, grid_y=28))
        (semantic_directory / "Azeroth_28_28.road").write_bytes(b"fixture road")
        self.map_dbc_path = self.root / "Map.dbc"
        self.map_dbc_path.write_bytes(_map_dbc())
        self.catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_validates_the_exact_detour_v7_payload_for_every_catalogued_tile(self) -> None:
        report = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth",
        )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["expected_tile_count"], 1)
        self.assertEqual(report["validated_tile_count"], 1)

    def test_parallel_audit_is_identical_to_serial_audit(self) -> None:
        serial = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth", workers=1,
        )
        parallel = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth", workers=2,
        )

        self.assertEqual(parallel, serial)

    def test_parallel_workers_are_replaced_across_multiple_batches(self) -> None:
        for grid_x in (29, 30):
            (self.nav_directory / f"{grid_x}_28.nav").write_bytes(
                detour_fixture_payload(grid_x=grid_x, grid_y=28)
            )
            (self.nav_root / "semantics" / f"Azeroth_{grid_x}_28.road").write_bytes(
                b"fixture road"
            )
        catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        report = build_navmesh_geometry_validation_report(
            catalog,
            nav_root=self.nav_root,
            map_name="Azeroth",
            workers=2,
            worker_tasks_per_child=1,
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validated_tile_count"], 3)

    def test_rejects_unbounded_worker_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "workers must be between 1 and 16"):
            build_navmesh_geometry_validation_report(
                self.catalog, nav_root=self.nav_root, map_name="Azeroth", workers=17,
            )

    def test_fails_closed_when_a_catalogued_payload_changes(self) -> None:
        self.tile_path.write_bytes(b"not a Detour tile")

        report = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth",
        )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["validated_tile_count"], 0)
        self.assertEqual(
            report["failures"],
            [{"artifact": "28_28.nav", "code": "NAV_TILE_SHA256_MISMATCH"}],
        )

    def test_validates_a_compressed_namigator_adt_with_64_bit_detour_links(self) -> None:
        self.tile_path.write_bytes(_namigator_adt_fixture(adt_x=28, adt_y=28))
        self.catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        report = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth",
        )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validated_tile_count"], 1)
        self.assertEqual(report["validated_inner_tile_count"], 256)
        self.assertEqual(report["detour_tile_count"], 256)
        self.assertEqual(report["empty_inner_tile_count"], 0)

    def test_parallel_worker_validates_compressed_namigator_adt(self) -> None:
        self.tile_path.write_bytes(_namigator_adt_fixture(adt_x=28, adt_y=28))
        self.catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        report = build_navmesh_geometry_validation_report(
            self.catalog,
            nav_root=self.nav_root,
            map_name="Azeroth",
            workers=2,
        )

        ContractValidator(SCHEMA).validate(report)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validated_tile_count"], 1)
        self.assertEqual(report["validated_inner_tile_count"], 256)

    def test_accepts_and_accounts_for_a_source_declared_empty_inner_tile(self) -> None:
        self.tile_path.write_bytes(
            _namigator_adt_fixture(adt_x=28, adt_y=28, empty_first_tile=True)
        )
        self.catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        report = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth",
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["validated_inner_tile_count"], 256)
        self.assertEqual(report["detour_tile_count"], 255)
        self.assertEqual(report["empty_inner_tile_count"], 1)

    def test_failed_namigator_adt_does_not_shrink_the_expected_inner_count(self) -> None:
        self.tile_path.write_bytes(_namigator_adt_fixture(adt_x=29, adt_y=28))
        self.catalog = build_client_world_catalog_record(
            _profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        report = build_navmesh_geometry_validation_report(
            self.catalog, nav_root=self.nav_root, map_name="Azeroth",
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["expected_inner_tile_count"], 256)
        self.assertEqual(report["validated_inner_tile_count"], 0)
        self.assertEqual(report["detour_tile_count"], 0)
        self.assertEqual(report["empty_inner_tile_count"], 0)

    def test_asset_inventory_is_rejected_as_the_wrong_contract(self) -> None:
        wrong_record = {
            "record_type": "client_world_asset_inventory",
            "schema_version": "1.0",
            "catalog_id": "fixture.wrong-contract",
            "client_build": "2.4.3.8606",
            "maps": [],
        }

        with self.assertRaisesRegex(Exception, "client-world-catalog"):
            build_navmesh_geometry_validation_report(
                wrong_record, nav_root=self.nav_root, map_name="Azeroth",
            )


if __name__ == "__main__":
    unittest.main()
