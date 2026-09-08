from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.standalone_world_pack import (
    VerifiedStandaloneWorldPack,
)
from perfect_assassin.movement.client_world_catalog import (
    ClientWorldCatalog,
    ClientWorldMap,
    WorldNavTile,
)
from perfect_assassin.movement.world_structure_index import (
    WorldStructureIndexError,
    WorldStructureSpatialIndex,
    build_world_structure_index_record,
    load_world_structure_index,
    parse_namigator_map_structures,
    verify_world_structure_index_binding,
)


WMO = struct.Struct("<IHH16f6f128s")
DOODAD = struct.Struct("<I16f6f128s")


def _path(value: str) -> bytes:
    encoded = value.encode("ascii")
    return encoded + b"\0" * (128 - len(encoded))


def _matrix() -> tuple[float, ...]:
    return (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def _wmo(
    instance_id: int,
    *,
    asset: str = r"World\Wmo\Dungeon\FixtureInterior.wmo",
    bounds: tuple[float, ...] = (-10.0, -5.0, 2.0, 10.0, 5.0, 12.0),
) -> bytes:
    return WMO.pack(instance_id, 3, 4, *_matrix(), *bounds, _path(asset))


def _doodad(
    instance_id: int,
    *,
    asset: str = r"World\Generic\Fence\Fence01.m2",
    bounds: tuple[float, ...] = (20.0, -1.0, 0.0, 22.0, 1.0, 3.0),
) -> bytes:
    return DOODAD.pack(instance_id, *_matrix(), *bounds, _path(asset))


def _terrain_map(
    *,
    wmos: tuple[bytes, ...] = (_wmo(7),),
    doodads: tuple[bytes, ...] = (_doodad(9),),
) -> bytes:
    tiles = bytearray(512)
    tiles[0] = 0b00000101
    return (
        b"1PAM" + b"\x01" + bytes(tiles)
        + struct.pack("<I", len(wmos)) + b"".join(wmos)
        + struct.pack("<I", len(doodads)) + b"".join(doodads)
    )


def _verified_pack(root: Path, payload: bytes) -> VerifiedStandaloneWorldPack:
    map_path = root / "Fixture.map"
    map_path.write_bytes(payload)
    map_sha = hashlib.sha256(payload).hexdigest()
    manifest = {
        "pack_id": "wow.fixture.worldpack-v1",
        "catalog_id": "wow.fixture.catalog-v1",
        "content_sha256": "a" * 64,
        "client_version": "1.2.3",
        "client_build": "12345",
        "maps": [{"map_id": 33, "internal_name": "Fixture", "adt_count": 2}],
        "files": [{
            "role": "NAV_MAP",
            "relative_path": "Fixture.map",
            "byte_size": len(payload),
            "sha256": map_sha,
        }],
    }
    catalog = ClientWorldCatalog(
        catalog_id="wow.fixture.catalog-v1",
        target_profile="fixture_lab",
        product="wow",
        expansion="fixture",
        client_version="1.2.3",
        client_build="12345",
        asset_container="mpq",
        asset_parser_profile="wow-wdbc-map-v1",
        world_catalog_asset="DBFilesClient/Map.dbc",
        world_catalog_asset_sha256="b" * 64,
        nav_profile_id="fixture-nav-v1",
        maps=(ClientWorldMap(
            map_id=33,
            internal_name="Fixture",
            classification="instance",
            map_artifact="Fixture.map",
            map_artifact_sha256=map_sha,
            nav_tiles_sha256="c" * 64,
            coverage_state="partial",
            interior_coverage="partial",
            road_semantic_coverage="partial",
            road_semantics_sha256="d" * 64,
            tiles=(WorldNavTile(grid_x=32, grid_y=32, artifact="32_32.nav", sha256="e" * 64),),
            road_semantics=(),
        ),),
    )
    return VerifiedStandaloneWorldPack(
        pack_root=root,
        manifest=manifest,
        catalog=catalog,
    )


class WorldStructureIndexTests(unittest.TestCase):
    def test_terrain_map_indexes_wmo_and_doodad_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Fixture.map"
            path.write_bytes(_terrain_map())
            parsed = parse_namigator_map_structures(path, map_id=33)

        self.assertTrue(parsed.terrain_present)
        self.assertEqual(parsed.terrain_tile_count, 2)
        self.assertEqual(parsed.wmo_count, 1)
        self.assertEqual(parsed.doodad_count, 1)
        self.assertEqual(parsed.structures[0]["kind"], "DOODAD")
        self.assertEqual(parsed.structures[0]["asset_path"], "world/generic/fence/fence01.m2")
        self.assertEqual(parsed.structures[1]["kind"], "WMO")
        self.assertEqual(parsed.structures[1]["bounds"]["max"]["z"], 12.0)
        self.assertIn("fixtureinterior", parsed.structures[1]["asset_tokens"])

    def test_global_wmo_map_is_supported_without_terrain_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Global.map"
            path.write_bytes(b"1PAM" + b"\x00" + _wmo(0xFFFFFFFF))
            parsed = parse_namigator_map_structures(path, map_id=532)

        self.assertFalse(parsed.terrain_present)
        self.assertEqual(parsed.terrain_tile_count, 0)
        self.assertEqual(parsed.wmo_count, 1)
        self.assertEqual(parsed.doodad_count, 0)
        self.assertEqual(parsed.structures[0]["instance_id"], 0xFFFFFFFF)

    def test_binary_parser_fails_closed_on_corruption(self) -> None:
        fixtures = {
            "signature": b"BAD!\x01",
            "trailing": _terrain_map() + b"x",
            "duplicate": _terrain_map(wmos=(_wmo(7), _wmo(7)), doodads=()),
            "non-finite": _terrain_map(
                wmos=(_wmo(8, bounds=(-1.0, -1.0, 0.0, math.inf, 1.0, 2.0)),),
                doodads=(),
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in fixtures.items():
                path = root / f"{name}.map"
                path.write_bytes(payload)
                with self.subTest(name=name), self.assertRaises(WorldStructureIndexError):
                    parse_namigator_map_structures(path, map_id=1)

    def test_spatial_index_answers_containment_and_nearby_obstacles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = _verified_pack(Path(directory), _terrain_map())
            record = build_world_structure_index_record(pack, map_name="Fixture")
            self.assertEqual(record["navigation_coverage"], "partial")
            self.assertEqual(record["nav_tile_count"], 1)
            self.assertEqual(record["structures"][1]["nav_coverage"], "PARTIAL")
            spatial = WorldStructureSpatialIndex.from_record(
                record, cell_size_yards=64.0,
            )

        containing = spatial.containing(x=0.0, y=0.0, z=4.0)
        self.assertEqual([hit.structure.kind for hit in containing], ["WMO"])
        nearby = spatial.nearby(x=18.0, y=0.0, z=1.0, radius_yards=5.0)
        self.assertEqual([hit.structure.kind for hit in nearby], ["DOODAD"])
        self.assertEqual(nearby[0].structure.nav_coverage, "NONE")
        self.assertEqual(nearby[0].horizontal_distance_yards, 2.0)
        self.assertTrue(nearby[0].contains_3d is False)

    def test_record_is_bound_to_exact_worldpack_and_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = _verified_pack(Path(directory), _terrain_map())
            record = build_world_structure_index_record(pack, map_name="Fixture")
            schema = (
                Path(__file__).resolve().parents[1]
                / "contracts" / "world-structure-index.schema.json"
            )
            ContractValidator(schema).validate(record)
            verify_world_structure_index_binding(record, pack)

            index_path = Path(directory) / "Fixture.structures.json"
            index_path.write_text(json.dumps(record), encoding="utf-8")
            loaded = load_world_structure_index(
                index_path, schema_path=schema, pack=pack,
            )
            self.assertEqual(loaded.record["structure_count"], 2)
            self.assertEqual(
                loaded.spatial.containing(x=0.0, y=0.0, z=4.0)[0].structure.kind,
                "WMO",
            )

            record["source_pack_content_sha256"] = "b" * 64
            with self.assertRaisesRegex(WorldStructureIndexError, "content_sha256"):
                verify_world_structure_index_binding(record, pack)


if __name__ == "__main__":
    unittest.main()
