from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_world_catalog import (
    ClientWorldCatalogError,
    build_client_world_catalog_record,
    decode_client_world_catalog,
    load_client_world_catalog,
    verify_client_world_catalog,
)
from perfect_assassin.movement.client_world_bake import (
    build_client_world_bake_queue_record,
)
from scripts.build_client_world_catalog import _validate_complete_coverage_evidence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "client-world-catalog.schema.json"
REAL_CATALOG = (
    ROOT / "config" / "navigation" / "client-world-catalog-tbc243-8606.json"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _map_dbc(*records: tuple[int, str]) -> bytes:
    string_block = bytearray(b"\0")
    encoded_records: list[bytes] = []
    for map_id, internal_name in records:
        name_offset = len(string_block)
        string_block.extend(internal_name.encode("utf-8") + b"\0")
        encoded_records.append(struct.pack("<2I", map_id, name_offset))
    return b"".join(
        (
            b"WDBC",
            struct.pack("<4I", len(records), 2, 8, len(string_block)),
            *encoded_records,
            bytes(string_block),
        )
    )


def _tile_set_sha256(tiles: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(tiles):
        encoded_name = name.encode("ascii")
        digest.update(len(encoded_name).to_bytes(2, "little"))
        digest.update(encoded_name)
        digest.update(tiles[name])
    return digest.hexdigest()


def _catalog_record(
    *,
    map_dbc: bytes,
    map_artifact: bytes,
    tiles: dict[str, bytes],
    road_semantics: dict[str, bytes],
) -> dict[str, object]:
    tile_records = []
    for name, raw in sorted(tiles.items()):
        grid_x, grid_y = (int(part) for part in name.removesuffix(".nav").split("_"))
        tile_records.append(
            {
                "grid_x": grid_x,
                "grid_y": grid_y,
                "artifact": name,
                "sha256": _sha256(raw),
            }
        )
    semantic_records = []
    for name, raw in sorted(road_semantics.items()):
        coordinate_text = name.removeprefix("Azeroth_").removesuffix(".road")
        grid_x, grid_y = (int(part) for part in coordinate_text.split("_"))
        semantic_records.append(
            {
                "grid_x": grid_x,
                "grid_y": grid_y,
                "artifact": name,
                "sha256": _sha256(raw),
            }
        )
    return {
        "record_type": "client_world_catalog",
        "schema_version": "1.0",
        "catalog_id": "fixture.tbc.8606",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "the_burning_crusade",
        "client_version": "2.4.3",
        "client_build": "2.4.3.8606",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
        "world_catalog_asset_sha256": _sha256(map_dbc),
        "nav_profile_id": "fixture-nav-v1",
        "maps": [
            {
                "map_id": 0,
                "internal_name": "Azeroth",
                "classification": "continent",
                "map_artifact": "Azeroth.map",
                "map_artifact_sha256": _sha256(map_artifact),
                "nav_tiles_sha256": _tile_set_sha256(tiles),
                "coverage_state": "partial",
                "interior_coverage": "partial",
                "road_semantic_coverage": "partial",
                "road_semantics_sha256": _tile_set_sha256(road_semantics),
                "tiles": tile_records,
                "road_semantics": semantic_records,
            }
        ],
        "execution_authority": False,
    }


def _coverage_profile() -> dict[str, object]:
    return {
        "record_type": "client_world_coverage_profile",
        "schema_version": "1.0",
        "catalog_id": "fixture.tbc.8606",
        "target_profile": "fixture_lab",
        "product": "wow",
        "expansion": "the_burning_crusade",
        "client_version": "2.4.3",
        "client_build": "2.4.3.8606",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "world_catalog_asset": "DBFilesClient/Map.dbc",
        "nav_profile_id": "fixture-nav-v1",
        "maps": [
            {
                "map_id": 0,
                "internal_name": "Azeroth",
                "classification": "continent",
                "coverage_state": "partial",
                "interior_coverage": "partial",
                "road_semantic_coverage": "partial",
            }
        ],
        "execution_authority": False,
    }


class ClientWorldCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.nav_root = self.root / "nav"
        self.nav_directory = self.nav_root / "Nav" / "Azeroth"
        self.nav_directory.mkdir(parents=True)
        self.semantic_directory = self.nav_root / "semantics"
        self.semantic_directory.mkdir()
        self.map_dbc = _map_dbc((0, "Azeroth"), (1, "Kalimdor"))
        self.map_artifact = b"fixture map artifact"
        self.tiles = {
            "28_27.nav": b"first nav tile",
            "28_28.nav": b"second nav tile",
        }
        self.road_semantics = {
            "Azeroth_28_27.road": b"first road semantic",
            "Azeroth_28_28.road": b"second road semantic",
        }
        (self.nav_root / "Azeroth.map").write_bytes(self.map_artifact)
        for name, raw in self.tiles.items():
            (self.nav_directory / name).write_bytes(raw)
        for name, raw in self.road_semantics.items():
            (self.semantic_directory / name).write_bytes(raw)
        self.map_dbc_path = self.root / "Map.dbc"
        self.map_dbc_path.write_bytes(self.map_dbc)
        self.record = _catalog_record(
            map_dbc=self.map_dbc,
            map_artifact=self.map_artifact,
            tiles=self.tiles,
            road_semantics=self.road_semantics,
        )
        self.catalog_path = self.root / "catalog.json"
        self.catalog_path.write_text(json.dumps(self.record), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _verify(self):
        catalog = load_client_world_catalog(self.catalog_path, schema_path=SCHEMA)
        return verify_client_world_catalog(
            catalog,
            target_profile="fixture_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            nav_profile_id="fixture-nav-v1",
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

    def test_real_tbc_catalog_satisfies_contract_and_declares_partial_coverage(self):
        record = json.loads(REAL_CATALOG.read_text(encoding="utf-8"))
        ContractValidator(SCHEMA).validate(record)
        catalog = decode_client_world_catalog(record)

        self.assertEqual(catalog.map_by_id(0).internal_name, "Azeroth")
        self.assertEqual(catalog.map_by_internal_name("Azeroth").coverage_state, "partial")
        self.assertEqual(catalog.map_by_id(0).interior_coverage, "partial")
        self.assertEqual(catalog.map_by_id(0).road_semantic_coverage, "partial")

    def test_exact_client_assets_and_navigation_profile_are_verified(self):
        verified = self._verify()

        self.assertEqual(verified.catalog.expansion, "the_burning_crusade")
        self.assertEqual(verified.catalog.map_by_id(0).internal_name, "Azeroth")
        self.assertEqual(verified.nav_root, self.nav_root.resolve())

    def test_deterministic_builder_reproduces_catalog_from_actual_artifacts(self):
        generated = build_client_world_catalog_record(
            _coverage_profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
        )

        self.assertEqual(generated, self.record)

    def test_complete_coverage_requires_exact_bake_evidence(self):
        profile = _coverage_profile()
        profile["maps"][0]["coverage_state"] = "complete"

        with self.assertRaisesRegex(ValueError, "requires exact"):
            _validate_complete_coverage_evidence(
                coverage_profile=profile,
                inventory=None,
                queue=None,
                nav_root=self.nav_root,
            )

    def test_complete_coverage_recomputes_exact_inventory_coordinates(self):
        profile = _coverage_profile()
        profile["maps"][0]["coverage_state"] = "complete"
        asset_root = self.root / "assets"
        asset_directory = asset_root / "Azeroth"
        asset_directory.mkdir(parents=True)
        for name in ("Azeroth.wdt", "Azeroth_28_27.adt", "Azeroth_28_28.adt"):
            (asset_directory / name).write_bytes(b"fixture")
        inventory = {
            "record_type": "client_world_asset_inventory",
            "schema_version": "1.0",
            "catalog_id": "fixture.inventory.tbc.8606",
            "target_profile": "fixture_lab",
            "product": "wow",
            "expansion": "the_burning_crusade",
            "client_version": "2.4.3",
            "client_build": "2.4.3.8606",
            "asset_container": "mpq",
            "asset_parser_profile": "wow-wdbc-map-v1",
            "world_catalog_asset": "DBFilesClient/Map.dbc",
            "world_catalog_asset_sha256": _sha256(self.map_dbc),
            "map_count": 1,
            "maps": [{
                "map_id": 0,
                "internal_name": "Azeroth",
                "wdt_present": True,
                "adt_count": 2,
                "adt_bounds": [28, 27, 28, 28],
                "tiles": [
                    {"grid_x": 28, "grid_y": 27},
                    {"grid_x": 28, "grid_y": 28},
                ],
            }],
            "execution_authority": False,
        }
        queue = build_client_world_bake_queue_record(
            inventory, asset_root=asset_root, nav_root=self.nav_root,
        )

        _validate_complete_coverage_evidence(
            coverage_profile=profile,
            inventory=inventory,
            queue=queue,
            nav_root=self.nav_root,
        )
        (self.nav_directory / "28_28.nav").unlink()
        with self.assertRaisesRegex(ValueError, "stale"):
            _validate_complete_coverage_evidence(
                coverage_profile=profile,
                inventory=inventory,
                queue=queue,
                nav_root=self.nav_root,
            )

    def test_builder_requires_reviewed_coverage_for_every_baked_map(self):
        (self.nav_root / "Kalimdor.map").write_bytes(b"kalimdor map")
        kalimdor_nav = self.nav_root / "Nav" / "Kalimdor"
        kalimdor_nav.mkdir(parents=True)
        (kalimdor_nav / "30_30.nav").write_bytes(b"kalimdor tile")

        with self.assertRaisesRegex(ClientWorldCatalogError, "no reviewed coverage"):
            build_client_world_catalog_record(
                _coverage_profile(),
                nav_root=self.nav_root,
                world_catalog_asset_path=self.map_dbc_path,
            )

        selected = build_client_world_catalog_record(
            _coverage_profile(),
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
            strict_root_artifacts=False,
        )
        self.assertEqual(
            [item["internal_name"] for item in selected["maps"]],
            ["Azeroth"],
        )

    def test_runtime_identity_mismatch_fails_closed(self):
        catalog = load_client_world_catalog(self.catalog_path, schema_path=SCHEMA)

        with self.assertRaisesRegex(ClientWorldCatalogError, "client_build"):
            verify_client_world_catalog(
                catalog,
                target_profile="fixture_lab",
                client_version="2.4.3",
                client_build="3.3.5.12340",
                nav_profile_id="fixture-nav-v1",
                nav_root=self.nav_root,
                world_catalog_asset_path=self.map_dbc_path,
            )

    def test_map_id_must_resolve_to_the_catalog_name_in_client_assets(self):
        different_dbc = _map_dbc((0, "Kalimdor"))
        self.map_dbc_path.write_bytes(different_dbc)
        changed = copy.deepcopy(self.record)
        changed["world_catalog_asset_sha256"] = _sha256(different_dbc)
        self.catalog_path.write_text(json.dumps(changed), encoding="utf-8")

        with self.assertRaisesRegex(ClientWorldCatalogError, "is not 'Azeroth'"):
            self._verify()

    def test_modified_or_extra_navigation_tiles_fail_closed(self):
        (self.nav_directory / "28_27.nav").write_bytes(b"tampered")
        with self.assertRaisesRegex(ClientWorldCatalogError, "tile hash mismatch"):
            self._verify()

        (self.nav_directory / "28_27.nav").write_bytes(self.tiles["28_27.nav"])
        (self.nav_directory / "29_29.nav").write_bytes(b"uncatalogued")
        with self.assertRaisesRegex(ClientWorldCatalogError, "do not exactly match"):
            self._verify()

    def test_modified_or_extra_road_semantics_fail_closed(self):
        semantic_path = self.semantic_directory / "Azeroth_28_27.road"
        semantic_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ClientWorldCatalogError, "road semantic hash mismatch"):
            self._verify()

        semantic_path.write_bytes(self.road_semantics["Azeroth_28_27.road"])
        (self.semantic_directory / "Azeroth_29_29.road").write_bytes(b"uncatalogued")
        with self.assertRaisesRegex(ClientWorldCatalogError, "do not exactly match"):
            self._verify()

    def test_packaging_can_verify_one_catalog_inside_a_shared_bake_root(self):
        (self.nav_root / "Kalimdor.map").write_bytes(b"kalimdor map")
        (self.semantic_directory / "Kalimdor_30_30.road").write_bytes(
            b"unselected semantic"
        )
        catalog = load_client_world_catalog(self.catalog_path, schema_path=SCHEMA)

        verified = verify_client_world_catalog(
            catalog,
            target_profile="fixture_lab",
            client_version="2.4.3",
            client_build="2.4.3.8606",
            nav_profile_id="fixture-nav-v1",
            nav_root=self.nav_root,
            world_catalog_asset_path=self.map_dbc_path,
            allow_extra_unselected_artifacts=True,
        )

        self.assertEqual(verified.catalog.map_by_id(0).internal_name, "Azeroth")

    def test_tile_coordinates_must_match_the_artifact_name(self):
        changed = copy.deepcopy(self.record)
        changed["maps"][0]["tiles"][0]["grid_x"] = 31

        with self.assertRaisesRegex(ClientWorldCatalogError, "coordinates"):
            decode_client_world_catalog(changed)

    def test_road_semantic_coordinates_must_match_tiles_and_artifact_name(self):
        changed = copy.deepcopy(self.record)
        changed["maps"][0]["road_semantics"][0]["grid_x"] = 31

        with self.assertRaisesRegex(ClientWorldCatalogError, "identical coordinates"):
            decode_client_world_catalog(changed)


if __name__ == "__main__":
    unittest.main()
