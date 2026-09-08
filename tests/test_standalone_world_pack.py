from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    StandaloneWorldPackError,
    build_standalone_world_pack,
    build_standalone_world_pack_from_catalog,
    open_standalone_world_pack,
    verify_standalone_world_pack,
)


ROOT = Path(__file__).resolve().parents[1]
REPAIR_SCHEMA = ROOT / "contracts" / "navmesh-tile-repair-evidence.schema.json"


def _write(path: Path, value: bytes = b"fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _fixture(root: Path) -> tuple[dict, dict, Path, Path]:
    nav_root = root / "nav"
    catalog = root / "Map.dbc"
    _write(catalog, b"world catalog")
    _write(nav_root / "Fixture.map")
    _write(nav_root / "Nav" / "Fixture" / "01_02.nav")
    _write(nav_root / "semantics" / "Fixture_01_02.road")
    _write(nav_root / "BVH" / "bvh.idx")
    _write(nav_root / "BVH" / "ABC.bvh")
    inventory = {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.world-v1",
        "product": "wow",
        "expansion": "fixture",
        "client_version": "1.2.3",
        "client_build": "12345",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset_sha256": hashlib.sha256(b"world catalog").hexdigest(),
        "execution_authority": False,
    }
    queue = {
        "record_type": "client_world_bake_queue",
        "catalog_id": "wow.fixture.world-v1",
        "nav_root": str(nav_root.resolve()),
        "bvh_ready": True,
        "eligible_map_count": 2,
        "maps": [{
            "map_id": 7,
            "internal_name": "Fixture",
            "adt_count": 1,
            "state": "COMPLETE",
            "nav_directory": str((nav_root / "Nav" / "Fixture").resolve()),
            "map_file": str((nav_root / "Fixture.map").resolve()),
        }],
        "execution_authority": False,
    }
    return inventory, queue, nav_root, catalog


def _catalog_fixture(root: Path) -> tuple[dict, Path, Path]:
    _inventory, _queue, nav_root, catalog_path = _fixture(root)
    strings = b"\0Fixture\0"
    map_dbc = b"WDBC" + struct.pack("<4I", 1, 2, 8, len(strings))
    map_dbc += struct.pack("<2I", 7, 1) + strings
    catalog_path.write_bytes(map_dbc)
    file_sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    def named_sha(path: Path) -> str:
        digest = hashlib.sha256()
        encoded_name = path.name.encode("ascii")
        digest.update(len(encoded_name).to_bytes(2, "little"))
        digest.update(encoded_name)
        digest.update(path.read_bytes())
        return digest.hexdigest()
    nav_tile = nav_root / "Nav" / "Fixture" / "01_02.nav"
    road = nav_root / "semantics" / "Fixture_01_02.road"
    catalog = {
        "record_type": "client_world_catalog",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.world-v1",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "fixture",
        "client_version": "1.2.3",
        "client_build": "12345",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
        "world_catalog_asset_sha256": file_sha(catalog_path),
        "nav_profile_id": "fixture-nav-v1",
        "maps": [{
            "map_id": 7,
            "internal_name": "Fixture",
            "classification": "instance",
            "map_artifact": "Fixture.map",
            "map_artifact_sha256": file_sha(nav_root / "Fixture.map"),
            "nav_tiles_sha256": named_sha(nav_tile),
            "coverage_state": "partial",
            "interior_coverage": "partial",
            "road_semantic_coverage": "partial",
            "road_semantics_sha256": named_sha(road),
            "tiles": [{
                "grid_x": 1, "grid_y": 2,
                "artifact": "01_02.nav", "sha256": file_sha(nav_tile),
            }],
            "road_semantics": [{
                "grid_x": 1, "grid_y": 2,
                "artifact": "Fixture_01_02.road", "sha256": file_sha(road),
            }],
        }],
        "execution_authority": False,
    }
    return catalog, nav_root, catalog_path


def _quality_report() -> dict[str, object]:
    payload = b"fixture"
    artifact = "01_02.nav"
    tile_sha256 = hashlib.sha256(payload).hexdigest()
    tile_set = hashlib.sha256()
    encoded_name = artifact.encode("ascii")
    tile_set.update(len(encoded_name).to_bytes(2, "little"))
    tile_set.update(encoded_name)
    tile_set.update(payload)
    return {
        "record_type": "navmesh_bake_quality_report",
        "schema_version": "1.0",
        "status": "COMPLETE_WITH_RECAST_DIAGNOSTICS",
        "catalog_id": "wow.fixture.world-v1",
        "client_build": "12345",
        "map_id": 7,
        "internal_name": "Fixture",
        "expected_adt_count": 1,
        "nav_adt_count": 1,
        "finished_adt_count": 1,
        "missing_coordinates": [],
        "extra_coordinates": [],
        "invalid_nav_artifact_count": 0,
        "nav_tiles": [{
            "grid_x": 1,
            "grid_y": 2,
            "artifact": artifact,
            "byte_size": len(payload),
            "sha256": tile_sha256,
        }],
        "nav_tiles_sha256": tile_set.hexdigest(),
        "diagnostics": {
            "recast_error_count": 1,
            "recast_warning_count": 0,
            "multiple_outline_error_count": 1,
            "bad_outline_error_count": 0,
            "bad_triangulation_warning_count": 0,
            "walk_center_warning_count": 0,
            "dangling_face_warning_count": 0,
            "failed_tile_count": 0,
        },
        "terminal_return_code": 0,
        "log_sha256": "a" * 64,
        "geometric_validation_required": True,
        "execution_authority": False,
    }


def _record_sha256(value: dict[str, object]) -> str:
    wire = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(wire).hexdigest()


def _geometry_report(catalog: dict[str, object]) -> dict[str, object]:
    world_map = catalog["maps"][0]
    assert isinstance(world_map, dict)
    return {
        "record_type": "navmesh_geometry_validation_report",
        "schema_version": "1.0",
        "status": "PASS",
        "validator_id": "perfect-assassin.namigator-detour-v7-structural-v2",
        "catalog_id": catalog["catalog_id"],
        "catalog_sha256": _record_sha256(catalog),
        "client_build": catalog["client_build"],
        "map_id": world_map["map_id"],
        "internal_name": world_map["internal_name"],
        "expected_tile_count": 1,
        "validated_tile_count": 1,
        "expected_inner_tile_count": 1,
        "validated_inner_tile_count": 1,
        "detour_tile_count": 1,
        "empty_inner_tile_count": 0,
        "failure_count": 0,
        "failures": [],
        "nav_tiles_sha256": world_map["nav_tiles_sha256"],
        "execution_authority": False,
    }


def _manifest_content_sha(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda value: str(value["relative_path"])):
        wire = json.dumps(
            {
                "role": item["role"],
                "relative_path": item["relative_path"],
                "byte_size": item["byte_size"],
                "sha256": item["sha256"],
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        digest.update(len(wire).to_bytes(4, "little"))
        digest.update(wire)
    return digest.hexdigest()


def _repair_evidence(
    report: dict[str, object],
    *,
    before_bytes: bytes = b'{"status":"FAIL"}\n',
    after_bytes: bytes = b'{"status":"PASS"}\n',
) -> dict[str, object]:
    replacement_sha256 = hashlib.sha256(b"fixture").hexdigest()
    raw_sha256 = str(report["nav_tiles"][0]["sha256"])
    return {
        "record_type": "navmesh_tile_repair_evidence",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.world-v1",
        "client_build": "12345",
        "map_id": 7,
        "internal_name": "Fixture",
        "tile": {
            "grid_x": 1,
            "grid_y": 2,
            "artifact": "01_02.nav",
            "raw_bake_sha256": raw_sha256,
            "replacement_sha256": replacement_sha256,
        },
        "raw_bake_report_sha256": _record_sha256(report),
        "defect": {
            "failure_code": "CRYPT_EXIT_ROUTE_REGRESSION",
            "evidence_artifact": (
                "evidence/navmesh-repair-regression/Fixture-01-02-before.json"
            ),
            "evidence_sha256": hashlib.sha256(before_bytes).hexdigest(),
        },
        "replacement_source": {
            "pack_id": "wow.fixture.stable-v1",
            "pack_content_sha256": "d" * 64,
            "relative_path": "Nav/Fixture/01_02.nav",
            "artifact_sha256": replacement_sha256,
        },
        "regression": {
            "scenario_id": "fixture-crypt-exit-v1",
            "before": {
                "status": "FAILED",
                "result_artifact": (
                    "evidence/navmesh-repair-regression/Fixture-01-02-before.json"
                ),
                "result_sha256": hashlib.sha256(before_bytes).hexdigest(),
            },
            "after": {
                "status": "PASSED",
                "result_artifact": (
                    "evidence/navmesh-repair-regression/Fixture-01-02-after.json"
                ),
                "result_sha256": hashlib.sha256(after_bytes).hexdigest(),
            },
        },
        "execution_authority": False,
    }


class StandaloneWorldPackTests(unittest.TestCase):
    def test_pack_is_self_contained_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, queue, nav_root, catalog = _fixture(root)
            pack_root = root / "pack"
            manifest = build_standalone_world_pack(
                inventory,
                queue,
                nav_root=nav_root,
                world_catalog_asset_path=catalog,
                staging_root=pack_root,
                pack_id="wow.fixture.pack-v1",
                selected_map_names=["Fixture"],
            )
            verify_standalone_world_pack(pack_root, manifest)

            self.assertEqual(manifest["coverage_state"], "DECLARED_MAPS_ONLY")
            self.assertEqual(manifest["asset_adapter_id"], "wow-mpq-wdbc-v1")
            self.assertEqual(manifest["nav_runtime_layout"], "namigator-nav-bvh-v1")
            self.assertTrue(all(
                value is False
                for value in manifest["runtime_dependencies"].values()
            ))
            self.assertEqual(len(manifest["files"]), 6)

    def test_modified_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, queue, nav_root, catalog = _fixture(root)
            pack_root = root / "pack"
            manifest = build_standalone_world_pack(
                inventory,
                queue,
                nav_root=nav_root,
                world_catalog_asset_path=catalog,
                staging_root=pack_root,
                pack_id="wow.fixture.pack-v1",
                selected_map_names=["Fixture"],
            )
            (pack_root / "Nav" / "Fixture" / "01_02.nav").write_bytes(b"changed")

            with self.assertRaisesRegex(StandaloneWorldPackError, "mismatch"):
                verify_standalone_world_pack(pack_root, manifest)

    def test_incomplete_map_cannot_be_packed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, queue, nav_root, catalog = _fixture(root)
            queue["maps"][0]["state"] = "NAVMESH_PARTIAL"

            with self.assertRaisesRegex(StandaloneWorldPackError, "not complete"):
                build_standalone_world_pack(
                    inventory,
                    queue,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog,
                    staging_root=root / "pack",
                    pack_id="wow.fixture.pack-v1",
                    selected_map_names=["Fixture"],
                )

    def test_runtime_dependency_shape_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory, queue, nav_root, catalog = _fixture(root)
            pack_root = root / "pack"
            manifest = build_standalone_world_pack(
                inventory,
                queue,
                nav_root=nav_root,
                world_catalog_asset_path=catalog,
                staging_root=pack_root,
                pack_id="wow.fixture.pack-v1",
                selected_map_names=["Fixture"],
            )
            manifest["runtime_dependencies"].pop("server_required")

            with self.assertRaisesRegex(StandaloneWorldPackError, "dependency"):
                verify_standalone_world_pack(pack_root, manifest)

    def test_verified_partial_catalog_can_be_sealed_without_full_map_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            pack_root = root / "pack"
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=nav_root,
                world_catalog_asset_path=catalog_path,
                staging_root=pack_root,
                pack_id="wow.fixture.partial-pack-v1",
            )
            verify_standalone_world_pack(pack_root, manifest)

            self.assertEqual(manifest["coverage_state"], "DECLARED_MAPS_ONLY")
            self.assertEqual(manifest["packed_map_count"], 1)

            manifest_path = pack_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest), encoding="utf-8",
            )
            verified = open_standalone_world_pack(
                pack_root,
                pack_schema_path=(
                    Path(__file__).resolve().parents[1]
                    / "contracts" / "standalone-world-pack.schema.json"
                ),
                catalog_schema_path=(
                    Path(__file__).resolve().parents[1]
                    / "contracts" / "client-world-catalog.schema.json"
                ),
                expected_pack_id="wow.fixture.partial-pack-v1",
                expected_content_sha256=manifest["content_sha256"],
            )
            self.assertEqual(verified.nav_root, pack_root.resolve())
            self.assertEqual(verified.catalog.map_by_id(7).internal_name, "Fixture")

    def test_complete_catalog_requires_and_bundles_exact_bake_quality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            with self.assertRaisesRegex(
                StandaloneWorldPackError, "require exact",
            ):
                build_standalone_world_pack_from_catalog(
                    catalog,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog_path,
                    staging_root=root / "missing-evidence",
                    pack_id="wow.fixture.complete-pack-v1",
                )

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "geometry validation reports",
            ):
                build_standalone_world_pack_from_catalog(
                    catalog,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog_path,
                    staging_root=root / "missing-geometry-evidence",
                    pack_id="wow.fixture.complete-pack-v1",
                    bake_quality_reports=[_quality_report()],
                )

            pack_root = root / "pack"
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=nav_root,
                world_catalog_asset_path=catalog_path,
                staging_root=pack_root,
                pack_id="wow.fixture.complete-pack-v1",
                bake_quality_reports=[_quality_report()],
                navmesh_geometry_reports=[_geometry_report(catalog)],
            )
            verify_standalone_world_pack(pack_root, manifest)

            evidence = {
                item["relative_path"]
                for item in manifest["files"]
                if item["role"] == "NAVMESH_BAKE_QUALITY"
            }
            self.assertEqual(
                evidence, {"evidence/navmesh-bake-quality-Fixture.json"},
            )
            geometry_evidence = {
                item["relative_path"]
                for item in manifest["files"]
                if item["role"] == "NAVMESH_GEOMETRY_VALIDATION"
            }
            self.assertEqual(
                geometry_evidence, {"evidence/navmesh-geometry-Fixture.json"},
            )

    def test_complete_catalog_rejects_quality_report_from_other_tile_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            report = _quality_report()
            report["nav_tiles"][0]["sha256"] = "b" * 64

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "lacks repair evidence",
            ):
                build_standalone_world_pack_from_catalog(
                    catalog,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog_path,
                    staging_root=root / "mismatched-evidence",
                    pack_id="wow.fixture.complete-pack-v1",
                    bake_quality_reports=[report],
                    navmesh_geometry_reports=[_geometry_report(catalog)],
                )

    def test_rehashed_tampered_geometry_evidence_is_rejected_when_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            pack_root = root / "pack"
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=nav_root,
                world_catalog_asset_path=catalog_path,
                staging_root=pack_root,
                pack_id="wow.fixture.complete-pack-v1",
                bake_quality_reports=[_quality_report()],
                navmesh_geometry_reports=[_geometry_report(catalog)],
            )
            evidence_path = pack_root / "evidence" / "navmesh-geometry-Fixture.json"
            tampered = json.loads(evidence_path.read_text(encoding="utf-8"))
            tampered["validated_tile_count"] = 0
            evidence_path.write_text(json.dumps(tampered), encoding="utf-8")
            record = next(
                item for item in manifest["files"]
                if item["relative_path"] == "evidence/navmesh-geometry-Fixture.json"
            )
            record["byte_size"] = evidence_path.stat().st_size
            record["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            manifest["content_sha256"] = _manifest_content_sha(manifest["files"])

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "geometry validation is incomplete",
            ):
                verify_standalone_world_pack(pack_root, manifest)

    def test_declared_tile_repair_binds_raw_replacement_source_and_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            report = _quality_report()
            raw_payload = b"raw-bake-defect"
            raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
            report["nav_tiles"][0]["byte_size"] = len(raw_payload)
            report["nav_tiles"][0]["sha256"] = raw_sha256
            aggregate = hashlib.sha256()
            encoded_name = b"01_02.nav"
            aggregate.update(len(encoded_name).to_bytes(2, "little"))
            aggregate.update(encoded_name)
            aggregate.update(raw_payload)
            report["nav_tiles_sha256"] = aggregate.hexdigest()
            repair = _repair_evidence(report)
            ContractValidator(REPAIR_SCHEMA).validate(repair)

            pack_root = root / "repaired-pack"
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=nav_root,
                world_catalog_asset_path=catalog_path,
                staging_root=pack_root,
                pack_id="wow.fixture.repaired-pack-v1",
                bake_quality_reports=[report],
                navmesh_geometry_reports=[_geometry_report(catalog)],
                tile_repair_evidence=[repair],
                tile_repair_artifacts={
                    "evidence/navmesh-repair-regression/Fixture-01-02-before.json": (
                        b'{"status":"FAIL"}\n'
                    ),
                    "evidence/navmesh-repair-regression/Fixture-01-02-after.json": (
                        b'{"status":"PASS"}\n'
                    ),
                },
            )
            verify_standalone_world_pack(pack_root, manifest)

            evidence = {
                item["relative_path"]
                for item in manifest["files"]
                if item["role"] == "NAVMESH_TILE_REPAIR_EVIDENCE"
            }
            self.assertEqual(
                evidence,
                {"evidence/navmesh-tile-repair-Fixture-01-02.json"},
            )

    def test_unused_tile_repair_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            report = _quality_report()
            repair = _repair_evidence(report)

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "undeclared replacements",
            ):
                build_standalone_world_pack_from_catalog(
                    catalog,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog_path,
                    staging_root=root / "unused-repair",
                    pack_id="wow.fixture.complete-pack-v1",
                    bake_quality_reports=[report],
                    navmesh_geometry_reports=[_geometry_report(catalog)],
                    tile_repair_evidence=[repair],
                    tile_repair_artifacts={
                        "evidence/navmesh-repair-regression/Fixture-01-02-before.json": (
                            b'{"status":"FAIL"}\n'
                        ),
                        "evidence/navmesh-repair-regression/Fixture-01-02-after.json": (
                            b'{"status":"PASS"}\n'
                        ),
                    },
                )

    def test_rehashed_tampered_repair_evidence_is_rejected_when_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            report = _quality_report()
            raw_payload = b"raw-bake-defect"
            report["nav_tiles"][0]["sha256"] = hashlib.sha256(raw_payload).hexdigest()
            report["nav_tiles"][0]["byte_size"] = len(raw_payload)
            report["nav_tiles_sha256"] = _record_sha256({
                "artifact": "01_02.nav", "payload": raw_payload.decode("ascii"),
            })
            repair = _repair_evidence(report)
            pack_root = root / "repaired-pack"
            manifest = build_standalone_world_pack_from_catalog(
                catalog,
                nav_root=nav_root,
                world_catalog_asset_path=catalog_path,
                staging_root=pack_root,
                pack_id="wow.fixture.repaired-pack-v1",
                bake_quality_reports=[report],
                navmesh_geometry_reports=[_geometry_report(catalog)],
                tile_repair_evidence=[repair],
                tile_repair_artifacts={
                    "evidence/navmesh-repair-regression/Fixture-01-02-before.json": (
                        b'{"status":"FAIL"}\n'
                    ),
                    "evidence/navmesh-repair-regression/Fixture-01-02-after.json": (
                        b'{"status":"PASS"}\n'
                    ),
                },
            )
            evidence_path = (
                pack_root / "evidence" / "navmesh-tile-repair-Fixture-01-02.json"
            )
            tampered = json.loads(evidence_path.read_text(encoding="utf-8"))
            tampered["tile"]["replacement_sha256"] = "0" * 64
            evidence_path.write_text(json.dumps(tampered), encoding="utf-8")
            evidence_record = next(
                item for item in manifest["files"]
                if item["relative_path"] == "evidence/navmesh-tile-repair-Fixture-01-02.json"
            )
            evidence_record["byte_size"] = evidence_path.stat().st_size
            evidence_record["sha256"] = hashlib.sha256(
                evidence_path.read_bytes(),
            ).hexdigest()
            manifest["content_sha256"] = _manifest_content_sha(manifest["files"])

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "repair evidence is inconsistent",
            ):
                verify_standalone_world_pack(pack_root, manifest)

    def test_complete_catalog_rejects_quality_report_for_another_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, nav_root, catalog_path = _catalog_fixture(root)
            catalog["maps"][0]["coverage_state"] = "complete"
            report = _quality_report()
            report["catalog_id"] = "wow.fixture.other-world-v1"

            with self.assertRaisesRegex(
                StandaloneWorldPackError, "quality is incomplete",
            ):
                build_standalone_world_pack_from_catalog(
                    catalog,
                    nav_root=nav_root,
                    world_catalog_asset_path=catalog_path,
                    staging_root=root / "wrong-catalog-evidence",
                    pack_id="wow.fixture.complete-pack-v1",
                    bake_quality_reports=[report],
                    navmesh_geometry_reports=[_geometry_report(catalog)],
                )


if __name__ == "__main__":
    unittest.main()
