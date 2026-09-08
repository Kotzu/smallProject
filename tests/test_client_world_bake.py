from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from perfect_assassin.movement.client_world_bake import (
    ClientWorldBakeError,
    build_client_world_bake_queue_record,
)


def _inventory() -> dict[str, object]:
    return {
        "record_type": "client_world_asset_inventory",
        "schema_version": "1.0",
        "catalog_id": "wow.test.client-world-v1",
        "product": "wow",
        "expansion": "test_expansion",
        "client_version": "1.2.3",
        "client_build": "1.2.3.4",
        "asset_container": "mpq",
        "asset_parser_profile": "wow-wdbc-map-v1",
        "maps": [
            {
                "map_id": 1,
                "internal_name": "TestMap",
                "wdt_present": True,
                "adt_count": 2,
                "adt_bounds": [3, 4, 5, 6],
                "tiles": [
                    {"grid_x": 3, "grid_y": 4},
                    {"grid_x": 5, "grid_y": 6},
                ],
            },
            {
                "map_id": 2,
                "internal_name": "NoTerrain",
                "wdt_present": True,
                "adt_count": 0,
                "adt_bounds": None,
                "tiles": [],
            },
        ],
        "execution_authority": False,
    }


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")


class ClientWorldBakeTests(unittest.TestCase):
    def test_queue_starts_with_exact_inventory_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = build_client_world_bake_queue_record(
                _inventory(), asset_root=root / "assets", nav_root=root / "nav",
            )

        self.assertEqual(record["eligible_map_count"], 1)
        self.assertEqual(record["eligible_adt_count"], 2)
        self.assertFalse(record["bvh_ready"])
        self.assertEqual(record["maps"][0]["state"], "READY_FOR_EXTRACTION")
        self.assertFalse(record["execution_authority"])

    def test_queue_advances_only_when_each_exact_artifact_set_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets" / "TestMap"
            nav_root = root / "nav"
            for name in (
                "TestMap.wdt", "TestMap_3_4.adt", "TestMap_5_6.adt",
            ):
                _write(assets / name)
            extracted = build_client_world_bake_queue_record(
                _inventory(), asset_root=root / "assets", nav_root=nav_root,
            )
            self.assertEqual(
                extracted["maps"][0]["state"], "READY_FOR_SEMANTICS",
            )

            for name in ("TestMap_03_04.road", "TestMap_05_06.road"):
                _write(nav_root / "semantics" / name)
            semantic = build_client_world_bake_queue_record(
                _inventory(), asset_root=root / "assets", nav_root=nav_root,
            )
            self.assertEqual(
                semantic["maps"][0]["state"], "READY_FOR_NAVMESH",
            )

            for name in ("03_04.nav", "05_06.nav"):
                _write(nav_root / "Nav" / "TestMap" / name)
            _write(nav_root / "TestMap.map")
            complete = build_client_world_bake_queue_record(
                _inventory(), asset_root=root / "assets", nav_root=nav_root,
            )
            self.assertEqual(complete["maps"][0]["state"], "COMPLETE")
            self.assertEqual(complete["complete_map_count"], 1)

    def test_downstream_artifacts_without_sources_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nav_root = root / "nav"
            for name in ("TestMap_03_04.road", "TestMap_05_06.road"):
                _write(nav_root / "semantics" / name)
            record = build_client_world_bake_queue_record(
                _inventory(), asset_root=root / "assets", nav_root=nav_root,
            )

        self.assertEqual(
            record["maps"][0]["state"],
            "INCONSISTENT_DOWNSTREAM_ARTIFACTS",
        )

    def test_duplicate_inventory_coordinates_are_rejected(self) -> None:
        inventory = _inventory()
        inventory["maps"][0]["tiles"][1] = {"grid_x": 3, "grid_y": 4}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ClientWorldBakeError):
                build_client_world_bake_queue_record(
                    inventory, asset_root=root / "assets", nav_root=root / "nav",
                )


if __name__ == "__main__":
    unittest.main()
