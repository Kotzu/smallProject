from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.structure_access_scan_plan import (
    StructureAccessScanPlanError,
    build_structure_access_scan_plan_record,
    load_structure_access_scan_plan,
    verify_structure_access_scan_plan_binding,
)


ROOT = Path(__file__).parents[1]


class _Catalog:
    catalog_id = "wow.test.catalog-v1"
    target_profile = "test_lab"
    client_version = "2.4.3"
    client_build = "2.4.3.8606"
    nav_profile_id = "test-nav-v1"

    @staticmethod
    def map_by_id(map_id: int) -> SimpleNamespace:
        if map_id != 0:
            raise KeyError(map_id)
        return SimpleNamespace(
            internal_name="Azeroth",
            tiles=(SimpleNamespace(grid_x=31, grid_y=31),),
        )


def _pack() -> SimpleNamespace:
    return SimpleNamespace(
        manifest={
            "pack_id": "wow.test.pack-v1",
            "content_sha256": "a" * 64,
        },
        catalog=_Catalog(),
    )


def _wmo(
    structure_id: str,
    *,
    coverage: str,
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "structure_id": structure_id,
        "kind": "WMO",
        "asset_path": "world/wmo/fixture/house.wmo",
        "nav_coverage": coverage,
        "bounds": {
            "min": dict(zip(("x", "y", "z"), minimum, strict=True)),
            "max": dict(zip(("x", "y", "z"), maximum, strict=True)),
        },
    }


def _index() -> dict[str, object]:
    return {
        "record_type": "world_structure_index",
        "schema_version": "1.0",
        "index_id": "wow.test.pack-v1:Azeroth:structures-v1",
        "pack_id": "wow.test.pack-v1",
        "catalog_id": "wow.test.catalog-v1",
        "source_pack_content_sha256": "a" * 64,
        "client_version": "2.4.3",
        "client_build": "2.4.3.8606",
        "map_id": 0,
        "map_name": "Azeroth",
        "map_artifact_sha256": "b" * 64,
        "terrain_present": True,
        "wmo_count": 2,
        "structures": [
            _wmo(
                "0:wmo:7", coverage="PARTIAL",
                minimum=(500.0, 500.0, 0.0),
                maximum=(600.0, 600.0, 20.0),
            ),
            _wmo(
                "0:wmo:8", coverage="NONE",
                minimum=(1000.0, 1000.0, 0.0),
                maximum=(1010.0, 1010.0, 10.0),
            ),
            {
                "structure_id": "0:doodad:9",
                "kind": "DOODAD",
                "asset_path": "world/doodad/tree.mdx",
                "nav_coverage": "FULL",
                "bounds": {
                    "min": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "max": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            },
        ],
        "execution_authority": False,
    }


class StructureAccessScanPlanTests(unittest.TestCase):
    def test_every_covered_wmo_is_planned_and_uncovered_wmo_is_deferred(self) -> None:
        record = build_structure_access_scan_plan_record(
            _pack(),
            structure_index_record=_index(),
            probe_worker_sha256="c" * 64,
        )
        ContractValidator(
            ROOT / "contracts" / "structure-access-scan-plan.schema.json"
        ).validate(record)

        self.assertEqual(record["wmo_count"], 2)
        self.assertEqual(record["eligible_structure_count"], 1)
        self.assertEqual(record["deferred_structure_count"], 1)
        self.assertEqual(record["tasks"][0]["structure_id"], "0:wmo:7")
        self.assertEqual(
            record["deferred_structures"][0]["reason"],
            "NAV_COVERAGE_ABSENT",
        )
        self.assertGreater(record["initial_seed_count"], 0)
        for seed in record["tasks"][0]["initial_seeds"]:
            x, y, z = seed["position"]
            self.assertLessEqual(500.0, x)
            self.assertLessEqual(x, 600.0)
            self.assertLessEqual(500.0, y)
            self.assertLessEqual(y, 600.0)
            self.assertLessEqual(0.0, z)
            self.assertLessEqual(z, 20.0)
            self.assertFalse(seed["execution_authority"])
        self.assertFalse(record["execution_authority"])

    def test_plan_is_deterministic_and_not_named_for_one_zone(self) -> None:
        first = build_structure_access_scan_plan_record(
            _pack(), structure_index_record=_index(), probe_worker_sha256="c" * 64,
        )
        second = build_structure_access_scan_plan_record(
            _pack(), structure_index_record=_index(), probe_worker_sha256="c" * 64,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first["planner_profile"],
            "adaptive-wmo-aabb-nav-intersection-v1",
        )
        self.assertNotIn("brill", json.dumps(first).lower())
        self.assertNotIn("shadowfang", json.dumps(first).lower())

    def test_loader_rejects_tampering_or_other_worker(self) -> None:
        record = build_structure_access_scan_plan_record(
            _pack(), structure_index_record=_index(), probe_worker_sha256="c" * 64,
        )
        verify_structure_access_scan_plan_binding(
            record,
            pack=_pack(),
            structure_index_record=_index(),
            expected_probe_worker_sha256="c" * 64,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            altered = json.loads(json.dumps(record))
            altered["tasks"][0]["initial_seeds"][0]["position"][0] += 1.0
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaisesRegex(StructureAccessScanPlanError, "hash mismatch"):
                load_structure_access_scan_plan(
                    path,
                    schema_path=ROOT / "contracts" / "structure-access-scan-plan.schema.json",
                    pack=_pack(),
                    structure_index_record=_index(),
                    expected_probe_worker_sha256="c" * 64,
                )
        with self.assertRaisesRegex(StructureAccessScanPlanError, "probe worker"):
            verify_structure_access_scan_plan_binding(
                record,
                pack=_pack(),
                structure_index_record=_index(),
                expected_probe_worker_sha256="d" * 64,
            )

    def test_global_wmo_does_not_require_terrain_tiles(self) -> None:
        index = _index()
        index["terrain_present"] = False
        index["wmo_count"] = 1
        index["structures"] = [
            _wmo(
                "0:wmo:7", coverage="GLOBAL_WMO",
                minimum=(-30.0, -30.0, -5.0),
                maximum=(30.0, 30.0, 25.0),
            )
        ]
        record = build_structure_access_scan_plan_record(
            _pack(), structure_index_record=index, probe_worker_sha256="c" * 64,
        )
        self.assertEqual(record["eligible_structure_count"], 1)
        self.assertEqual(record["deferred_structure_count"], 0)
        self.assertEqual(record["initial_seed_count"], 27)


if __name__ == "__main__":
    unittest.main()
