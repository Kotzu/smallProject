from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    build_standalone_world_pack,
)
from scripts.build_navmesh_tile_repair_evidence import (
    build_navmesh_tile_repair_evidence,
    run as run_repair_evidence,
)
from scripts.build_navmesh_repair_evidence_batch import (
    build_navmesh_repair_evidence_batch,
)
from scripts.seal_standalone_world_pack import run as run_world_pack_sealer


ROOT = Path(__file__).resolve().parents[1]
REPAIR_SCHEMA = ROOT / "contracts" / "navmesh-tile-repair-evidence.schema.json"


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _named_sha(name: str, payload: bytes) -> str:
    digest = hashlib.sha256()
    encoded = name.encode("ascii")
    digest.update(len(encoded).to_bytes(2, "little"))
    digest.update(encoded)
    digest.update(payload)
    return digest.hexdigest()


def _record_sha(value: object) -> str:
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
        "catalog_sha256": _record_sha(catalog),
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


def _failed_geometry_report(
    catalog: dict[str, object], *, code: str = "DETOUR_PAYLOAD_INVALID",
) -> dict[str, object]:
    report = _geometry_report(catalog)
    report.update({
        "status": "FAIL",
        "validated_tile_count": 0,
        "validated_inner_tile_count": 0,
        "detour_tile_count": 0,
        "failure_count": 1,
        "failures": [{"artifact": "01_02.nav", "code": code}],
    })
    return report


def _fixture(root: Path) -> tuple[dict, dict, Path]:
    nav_root = root / "nav"
    replacement = b"corrected-nav"
    raw = b"raw-defective-nav"
    artifact = "01_02.nav"
    _write(nav_root / "Fixture.map", b"map")
    _write(nav_root / "Nav" / "Fixture" / artifact, replacement)
    _write(nav_root / "semantics" / "Fixture_01_02.road", b"road")
    _write(nav_root / "BVH" / "bvh.idx", b"idx")
    _write(nav_root / "BVH" / "fixture.bvh", b"bvh")
    strings = b"\0Fixture\0"
    map_dbc = b"WDBC" + struct.pack("<4I", 1, 2, 8, len(strings))
    map_dbc += struct.pack("<2I", 7, 1) + strings
    catalog_asset = root / "Map.dbc"
    _write(catalog_asset, map_dbc)
    inventory = {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.source-v1",
        "product": "wow",
        "expansion": "fixture",
        "client_version": "1.2.3",
        "client_build": "12345",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset_sha256": hashlib.sha256(map_dbc).hexdigest(),
        "execution_authority": False,
    }
    queue = {
        "record_type": "client_world_bake_queue",
        "catalog_id": inventory["catalog_id"],
        "nav_root": str(nav_root.resolve()),
        "bvh_ready": True,
        "eligible_map_count": 1,
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
    source_pack = root / "source-pack"
    manifest = build_standalone_world_pack(
        inventory,
        queue,
        nav_root=nav_root,
        world_catalog_asset_path=catalog_asset,
        staging_root=source_pack,
        pack_id="wow.fixture.source-pack-v1",
        selected_map_names=["Fixture"],
    )
    (source_pack / "manifest.json").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8",
    )
    replacement_sha = hashlib.sha256(replacement).hexdigest()
    road_sha = hashlib.sha256(b"road").hexdigest()
    catalog = {
        "record_type": "client_world_catalog",
        "schema_version": "1.0",
        "catalog_id": "wow.fixture.final-v1",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "fixture",
        "client_version": "1.2.3",
        "client_build": "12345",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
        "world_catalog_asset_sha256": hashlib.sha256(map_dbc).hexdigest(),
        "nav_profile_id": "fixture-nav-v1",
        "maps": [{
            "map_id": 7,
            "internal_name": "Fixture",
            "classification": "instance",
            "map_artifact": "Fixture.map",
            "map_artifact_sha256": hashlib.sha256(b"map").hexdigest(),
            "nav_tiles_sha256": _named_sha(artifact, replacement),
            "coverage_state": "complete",
            "interior_coverage": "partial",
            "road_semantic_coverage": "complete",
            "road_semantics_sha256": _named_sha("Fixture_01_02.road", b"road"),
            "tiles": [{
                "grid_x": 1, "grid_y": 2, "artifact": artifact,
                "sha256": replacement_sha,
            }],
            "road_semantics": [{
                "grid_x": 1, "grid_y": 2,
                "artifact": "Fixture_01_02.road", "sha256": road_sha,
            }],
        }],
        "execution_authority": False,
    }
    raw_sha = hashlib.sha256(raw).hexdigest()
    quality = {
        "record_type": "navmesh_bake_quality_report",
        "schema_version": "1.0",
        "status": "COMPLETE_WITH_RECAST_DIAGNOSTICS",
        "catalog_id": catalog["catalog_id"],
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
            "grid_x": 1, "grid_y": 2, "artifact": artifact,
            "byte_size": len(raw), "sha256": raw_sha,
        }],
        "nav_tiles_sha256": _named_sha(artifact, raw),
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
    return catalog, quality, source_pack


class NavmeshTileRepairEvidenceTests(unittest.TestCase):
    def test_batch_verifies_source_once_and_writes_exact_repair_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, quality, source_pack = _fixture(root)
            before = _failed_geometry_report(catalog)
            after = _geometry_report(catalog)
            result = build_navmesh_repair_evidence_batch(
                catalog,
                quality,
                map_name="Fixture",
                source_world_pack_root=source_pack,
                before_results=((
                    before, (json.dumps(before) + "\n").encode(),
                ),),
                after_result=after,
                after_result_bytes=(json.dumps(after) + "\n").encode(),
                scenario_prefix="fixture-structural-repair-v1",
                output_root=root / "repair-evidence",
            )
            evidence_path = root / "repair-evidence" / "01_02.json"
            self.assertTrue(evidence_path.is_file())
            ContractValidator(REPAIR_SCHEMA).validate(json.loads(
                evidence_path.read_text(encoding="utf-8")
            ))
        self.assertEqual(result["replacement_count"], 1)
        self.assertEqual(
            result["source_pack_id"], "wow.fixture.source-pack-v1",
        )

    def test_verified_source_and_before_after_results_produce_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog, quality, source_pack = _fixture(Path(directory))
            before = (json.dumps(_failed_geometry_report(catalog)) + "\n").encode()
            after = (json.dumps(_geometry_report(catalog)) + "\n").encode()
            evidence, artifacts = build_navmesh_tile_repair_evidence(
                catalog,
                quality,
                map_name="Fixture",
                artifact="01_02.nav",
                source_world_pack_root=source_pack,
                before_result_bytes=before,
                after_result_bytes=after,
                scenario_id="fixture-crypt-exit-v1",
                failure_code="DETOUR_PAYLOAD_INVALID",
            )

        ContractValidator(REPAIR_SCHEMA).validate(evidence)
        self.assertEqual(
            evidence["tile"]["raw_bake_sha256"],
            quality["nav_tiles"][0]["sha256"],
        )
        self.assertEqual(
            evidence["replacement_source"]["pack_id"],
            "wow.fixture.source-pack-v1",
        )
        self.assertEqual(len(artifacts), 2)

    def test_matching_raw_tile_is_not_a_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog, quality, source_pack = _fixture(Path(directory))
            quality["nav_tiles"][0]["sha256"] = catalog["maps"][0]["tiles"][0]["sha256"]
            with self.assertRaisesRegex(ValueError, "forbidden"):
                build_navmesh_tile_repair_evidence(
                    catalog,
                    quality,
                    map_name="Fixture",
                    artifact="01_02.nav",
                    source_world_pack_root=source_pack,
                    before_result_bytes=b'{"status":"FAIL"}\n',
                    after_result_bytes=b'{"status":"PASS"}\n',
                    scenario_id="fixture-crypt-exit-v1",
                    failure_code="CRYPT_EXIT_ROUTE_REGRESSION",
                )

    def test_after_regression_must_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog, quality, source_pack = _fixture(Path(directory))
            before = (json.dumps(_failed_geometry_report(catalog)) + "\n").encode()
            after = (json.dumps(_failed_geometry_report(catalog)) + "\n").encode()
            with self.assertRaisesRegex(ValueError, "exact final catalog"):
                build_navmesh_tile_repair_evidence(
                    catalog,
                    quality,
                    map_name="Fixture",
                    artifact="01_02.nav",
                    source_world_pack_root=source_pack,
                    before_result_bytes=before,
                    after_result_bytes=after,
                    scenario_id="fixture-crypt-exit-v1",
                    failure_code="DETOUR_PAYLOAD_INVALID",
                )

    def test_cli_bundle_is_accepted_by_the_world_pack_sealer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, quality, source_pack = _fixture(root)
            catalog_path = root / "catalog.json"
            quality_path = root / "quality.json"
            geometry_path = root / "geometry.json"
            before_path = root / "before.json"
            after_path = root / "after.json"
            evidence_path = root / "repair-evidence" / "01_02.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            quality_path.write_text(json.dumps(quality), encoding="utf-8")
            geometry_path.write_text(
                json.dumps(_geometry_report(catalog)), encoding="utf-8",
            )
            before_path.write_text(
                json.dumps(_failed_geometry_report(
                    catalog, code="CRYPT_EXIT_ROUTE_REGRESSION",
                )),
                encoding="utf-8",
            )
            after_path.write_text(
                json.dumps(_geometry_report(catalog)), encoding="utf-8",
            )

            self.assertEqual(run_repair_evidence([
                "--catalog", str(catalog_path),
                "--quality-report", str(quality_path),
                "--map-name", "Fixture",
                "--artifact", "01_02.nav",
                "--source-world-pack-root", str(source_pack),
                "--before-result", str(before_path),
                "--after-result", str(after_path),
                "--scenario-id", "fixture-crypt-exit-v1",
                "--failure-code", "CRYPT_EXIT_ROUTE_REGRESSION",
                "--output", str(evidence_path),
            ]), 0)
            self.assertTrue(evidence_path.is_file())
            self.assertTrue((evidence_path.parent / "evidence" / "navmesh-repair-regression"
                             / "Fixture-01-02-before.json").is_file())

            pack_root = root / "final-pack"
            self.assertEqual(run_world_pack_sealer([
                "--catalog", str(catalog_path),
                "--bake-quality-report", str(quality_path),
                "--navmesh-geometry-validation", str(geometry_path),
                "--tile-repair-evidence-directory", str(evidence_path.parent),
                "--nav-root", str(root / "nav"),
                "--world-catalog-asset", str(root / "Map.dbc"),
                "--pack-root", str(pack_root),
                "--pack-id", "wow.fixture.final-pack-v1",
            ]), 0)
            manifest = json.loads((pack_root / "manifest.json").read_text(
                encoding="utf-8",
            ))
            self.assertEqual(
                sum(
                    item["role"] == "NAVMESH_TILE_REPAIR_REGRESSION"
                    for item in manifest["files"]
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
