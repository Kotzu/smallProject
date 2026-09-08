from __future__ import annotations

from math import tau
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.client_world_catalog import (
    ClientWorldMap,
    WorldNavTile,
)
from scripts.validate_standalone_movement_portability import (
    ADT_SIZE_YARDS,
    build_probe_candidates,
    exercise_dynamic_policy,
)
from scripts.validate_structure_egress_portability import (
    candidate_goals_beyond_opening,
)


def map_record(name: str) -> ClientWorldMap:
    return ClientWorldMap(
        map_id=77,
        internal_name=name,
        classification="instance",
        map_artifact=f"{name}.map",
        map_artifact_sha256="a" * 64,
        nav_tiles_sha256="b" * 64,
        coverage_state="complete",
        interior_coverage="complete",
        road_semantic_coverage="complete",
        road_semantics_sha256="c" * 64,
        tiles=(WorldNavTile(27, 32, "27_32.nav", "d" * 64),),
        road_semantics=(),
    )


def structure_record(name: str) -> dict[str, object]:
    return {
        "map_id": 77,
        "map_name": name,
        "structures": [{
            "structure_id": "77:wmo:9",
            "kind": "WMO",
            "horizontal_radius_yards": 40.0,
            "nav_coverage": "FULL",
            "bounds": {
                "min": {"x": -30.0, "y": 10.0, "z": 2.0},
                "max": {"x": 50.0, "y": 70.0, "z": 42.0},
            },
            "center": {"x": 10.0, "y": 40.0, "z": 22.0},
        }],
    }


def awareness(*, all_clear: bool) -> LocalStaticAwareness:
    probes = tuple(
        RadialClearanceProbe(
            index * tau / 16,
            12.0 if all_clear or index == 2 else 0.5,
            all_clear or index == 2,
        )
        for index in range(16)
    )
    return LocalStaticAwareness(
        physical_surfaces=frozenset({"wmo"}),
        probe_radius_yards=12.0,
        overhead_clear=True,
        radial_probes=probes,
    )


class StandaloneMovementPortabilityTests(unittest.TestCase):
    def test_probe_strategy_is_identical_for_arbitrary_map_names(self) -> None:
        first = build_probe_candidates(
            map_record("FirstMap"), structure_record("FirstMap"),
            maximum_candidates=32,
        )
        second = build_probe_candidates(
            map_record("CompletelyDifferentMap"),
            structure_record("CompletelyDifferentMap"),
            maximum_candidates=32,
        )

        self.assertEqual(
            tuple((item.source, item.position) for item in first),
            tuple((item.source, item.position) for item in second),
        )
        self.assertEqual(first[0].source, "WORLD_STRUCTURE_WMO")
        self.assertEqual(first[0].position.x, 10.0)

    def test_tile_probe_uses_client_world_transform_not_saved_coordinates(self) -> None:
        record = structure_record("AnyMap")
        record["structures"] = []
        candidates = build_probe_candidates(
            map_record("AnyMap"), record, maximum_candidates=10,
        )

        self.assertEqual(candidates[0].source, "NAV_TILE_INTERIOR")
        self.assertAlmostEqual(
            candidates[0].position.x,
            (32.0 - 32.5) * ADT_SIZE_YARDS,
        )
        self.assertAlmostEqual(
            candidates[0].position.y,
            (32.0 - 27.5) * ADT_SIZE_YARDS,
        )

    def test_real_awareness_contract_controls_arc_without_reversal(self) -> None:
        result = exercise_dynamic_policy(awareness(all_clear=True))

        self.assertEqual(result["state"], "AVOID")
        self.assertEqual(result["applied_state"], "DYNAMIC_AVOID")
        if result["side"] == "LEFT":
            self.assertLessEqual(result["applied_mouse_delta_x"], 0)
        else:
            self.assertGreaterEqual(result["applied_mouse_delta_x"], 0)
        self.assertFalse(result["static_memory_write"])

    def test_validator_has_no_deathknell_or_brill_runtime_branch(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "validate_standalone_movement_portability.py"
        ).read_text(encoding="utf-8").lower()

        self.assertNotIn("deathknell", source)
        self.assertNotIn("brill", source)

    def test_structure_egress_trials_are_derived_from_geometry_only(self) -> None:
        first = candidate_goals_beyond_opening(
            start=NavPoint(1.0, 2.0, 3.0),
            opening=NavPoint(6.0, 2.0, 4.0),
        )
        translated = candidate_goals_beyond_opening(
            start=NavPoint(101.0, -48.0, 13.0),
            opening=NavPoint(106.0, -48.0, 14.0),
        )

        self.assertEqual(
            tuple(NavPoint(
                point.x - 100.0,
                point.y + 50.0,
                point.z - 10.0,
            ) for point in translated),
            first,
        )
        self.assertEqual(tuple(point.x for point in first), (10.0, 14.0, 18.0))

    def test_structure_egress_validator_has_no_location_branch(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "scripts" / "validate_structure_egress_portability.py"
        ).read_text(encoding="utf-8").lower()

        self.assertNotIn("deathknell", source)
        self.assertNotIn("brill", source)


if __name__ == "__main__":
    unittest.main()
