from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from perfect_assassin.adapter.world_map_zone_catalog import (
    WorldMapZoneTransformCatalogError,
    load_world_map_zone_transform_catalog,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "pose" / "world-map-zone-transforms-tbc243-8606.json"
SCHEMA = ROOT / "contracts" / "world-map-zone-transform-catalog.schema.json"


class WorldMapZoneTransformCatalogTests(unittest.TestCase):
    def test_client_asset_catalog_covers_all_audited_map_area_rows(self) -> None:
        catalog = load_world_map_zone_transform_catalog(CATALOG, schema_path=SCHEMA)
        self.assertEqual(len(catalog.zones), 68)
        self.assertFalse(catalog.execution_authority)
        tirisfal = catalog.resolve(map_id=0, area_id=85)
        self.assertEqual(tirisfal.internal_name, "Tirisfal")
        self.assertAlmostEqual(
            tirisfal.world_from_normalized(0.5, 0.5)[0],
            2331.2498474121094,
            places=5,
        )

    def test_kalimdor_and_outland_transforms_round_trip(self) -> None:
        catalog = load_world_map_zone_transform_catalog(CATALOG, schema_path=SCHEMA)
        for map_id, area_id in ((1, 14), (530, 3483), (530, 3703)):
            zone = catalog.resolve(map_id=map_id, area_id=area_id)
            world = zone.world_from_normalized(0.23, 0.71)
            restored = zone.normalized_from_world(*world)
            self.assertAlmostEqual(restored[0], 0.23, places=10)
            self.assertAlmostEqual(restored[1], 0.71, places=10)

    def test_duplicate_map_area_is_rejected(self) -> None:
        record = json.loads(CATALOG.read_text(encoding="utf-8"))
        record["zones"].append(dict(record["zones"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(WorldMapZoneTransformCatalogError):
                load_world_map_zone_transform_catalog(path, schema_path=SCHEMA)

    def test_out_of_zone_world_position_fails_closed(self) -> None:
        catalog = load_world_map_zone_transform_catalog(CATALOG, schema_path=SCHEMA)
        zone = catalog.resolve(map_id=1, area_id=14)
        with self.assertRaises(WorldMapZoneTransformCatalogError):
            zone.normalized_from_world(zone.loc_top + 1.0, zone.loc_left + 1.0)
