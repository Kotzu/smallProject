from __future__ import annotations

from dataclasses import replace
from math import tau
from pathlib import Path
import unittest

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    LocalTopologicalEgressPortal,
    LocalWallSegment,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.local_environment_awareness import (
    build_local_environment_awareness,
)
from perfect_assassin.movement.world_structure_index import (
    AxisAlignedBounds,
    Vector3,
    WorldStructure,
    WorldStructureSpatialIndex,
)


def _structures() -> WorldStructureSpatialIndex:
    return WorldStructureSpatialIndex((
        WorldStructure(
            structure_id="33:wmo:218202",
            kind="WMO",
            instance_id=218202,
            asset_path="world/wmo/dungeon/fixture/fixtureinterior.wmo",
            asset_tokens=("world", "wmo", "dungeon", "fixtureinterior"),
            bounds=AxisAlignedBounds(
                Vector3(-20.0, -20.0, 0.0),
                Vector3(20.0, 20.0, 30.0),
            ),
            center=Vector3(0.0, 0.0, 15.0),
            horizontal_radius_yards=28.284,
            collision_role="ENCLOSURE_OR_LARGE_STRUCTURE",
            nav_coverage="FULL",
        ),
        WorldStructure(
            structure_id="33:doodad:7",
            kind="DOODAD",
            instance_id=7,
            asset_path="world/generic/fence/fence01.m2",
            asset_tokens=("world", "generic", "fence", "fence01", "m2"),
            bounds=AxisAlignedBounds(
                Vector3(8.0, -1.0, 0.0),
                Vector3(10.0, 1.0, 3.0),
            ),
            center=Vector3(9.0, 0.0, 1.5),
            horizontal_radius_yards=1.414,
            collision_role="STATIC_OBSTACLE_CANDIDATE",
            nav_coverage="FULL",
        ),
    ), cell_size_yards=64.0)


def _awareness() -> LocalStaticAwareness:
    return LocalStaticAwareness(
        physical_surfaces=frozenset({"wmo"}),
        probe_radius_yards=12.0,
        overhead_clear=False,
        radial_probes=tuple(
            RadialClearanceProbe(
                index * tau / 16,
                12.0 if index in {0, 1, 2} else 3.0,
                index in {0, 1, 2},
            )
            for index in range(16)
        ),
        component_polygon_count=125,
        wall_segments=(
            LocalWallSegment(
                NavPoint(4.0, -2.0, 5.0), NavPoint(4.0, 2.0, 5.0), 4.0,
            ),
        ),
        egress_portals=(
            LocalTopologicalEgressPortal(
                NavPoint(10.0, -2.0, 5.0),
                NavPoint(10.0, 2.0, 5.0),
                4.0,
                10.0,
                12.0,
                False,
                True,
                frozenset({"wmo"}),
                frozenset({"ground"}),
            ),
        ),
    )


class LocalEnvironmentAwarenessTests(unittest.TestCase):
    def test_combines_wmo_containment_boundaries_and_verified_egress(self) -> None:
        awareness = build_local_environment_awareness(
            map_name="Shadowfang",
            observed_monotonic_s=12.5,
            position=NavPoint(0.0, 0.0, 5.0),
            nav_awareness=_awareness(),
            structures=_structures(),
        )
        record = awareness.to_record()
        ContractValidator(
            Path(__file__).resolve().parents[1]
            / "contracts" / "local-environment-awareness.schema.json"
        ).validate(record)

        self.assertEqual(awareness.environment_state, "INSIDE_STATIC_WMO")
        self.assertEqual(awareness.environment_confidence, 0.95)
        self.assertEqual(awareness.containing_structures[0].structure_id, "33:wmo:218202")
        self.assertEqual(awareness.boundaries[0].kind, "NAVMESH_COMPONENT_BOUNDARY")
        self.assertEqual(
            awareness.boundaries[0].physical_wall_semantics,
            "CANDIDATE_NOT_OBJECT_CLASSIFIED",
        )
        self.assertEqual(awareness.verified_egresses[0].route_distance_yards, 12.0)
        self.assertTrue(awareness.topology_complete)
        self.assertEqual(awareness.nearby_static_obstacle_count, 1)
        self.assertFalse(record["execution_authority"])

    def test_aabb_alone_cannot_claim_inside_wmo(self) -> None:
        outdoor = replace(
            _awareness(),
            physical_surfaces=frozenset({"ground"}),
            overhead_clear=True,
            egress_portals=(),
        )
        awareness = build_local_environment_awareness(
            map_name="Shadowfang",
            observed_monotonic_s=1.0,
            position=NavPoint(0.0, 0.0, 5.0),
            nav_awareness=outdoor,
            structures=_structures(),
        )

        self.assertNotEqual(awareness.environment_state, "INSIDE_STATIC_WMO")
        self.assertEqual(awareness.environment_state, "CONFINED_STATIC_SPACE")

    def test_wmo_surface_without_bound_structure_remains_unresolved(self) -> None:
        awareness = build_local_environment_awareness(
            map_name="Shadowfang",
            observed_monotonic_s=2.0,
            position=NavPoint(100.0, 100.0, 5.0),
            nav_awareness=replace(_awareness(), egress_portals=()),
            structures=_structures(),
        )

        self.assertEqual(
            awareness.environment_state, "WMO_TRANSITION_OR_UNRESOLVED",
        )
        self.assertEqual(awareness.containing_structures, ())

    def test_tall_wmo_with_clear_short_overhead_probe_is_still_inside(self) -> None:
        awareness = build_local_environment_awareness(
            map_name="Shadowfang",
            observed_monotonic_s=2.5,
            position=NavPoint(0.0, 0.0, 5.0),
            nav_awareness=replace(
                _awareness(), overhead_clear=True, egress_portals=(),
            ),
            structures=_structures(),
        )

        self.assertEqual(awareness.environment_state, "INSIDE_STATIC_WMO")
        self.assertEqual(awareness.environment_confidence, 0.95)
        self.assertEqual(
            awareness.containing_structures[0].structure_id,
            "33:wmo:218202",
        )

    def test_truncated_topology_never_claims_complete_awareness(self) -> None:
        awareness = build_local_environment_awareness(
            map_name="Shadowfang",
            observed_monotonic_s=3.0,
            position=NavPoint(0.0, 0.0, 5.0),
            nav_awareness=replace(_awareness(), wall_segments_truncated=True),
            structures=_structures(),
        )

        self.assertFalse(awareness.topology_complete)


if __name__ == "__main__":
    unittest.main()
