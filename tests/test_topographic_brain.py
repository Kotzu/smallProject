from __future__ import annotations

from math import tau
import unittest

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    NavCorridor,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.topographic_brain import (
    build_topographic_brain_snapshot,
)
from perfect_assassin.movement.world_model import LayeredWorldModel


class TopographicBrainTests(unittest.TestCase):
    def test_snapshot_binds_pose_corridor_world_and_persistent_experience(self) -> None:
        world = LayeredWorldModel(
            map_name="Azeroth",
            static_navmesh_sha256="A" * 64,
        )
        world.observe_position(x=10.0, y=20.0, observed_at_s=1.0)
        start = NavPoint(10.0, 20.0, 5.0)
        stop = NavPoint(30.0, 40.0, 6.0)
        awareness = LocalStaticAwareness(
            physical_surfaces=frozenset({"ground"}),
            probe_radius_yards=12.0,
            overhead_clear=True,
            radial_probes=tuple(
                RadialClearanceProbe(index * tau / 16, 12.0, True)
                for index in range(16)
            ),
            component_polygon_count=9,
        )
        corridor = NavCorridor(
            "Azeroth", 31, 31, start, stop, (start, stop),
            start_awareness=awareness,
            road_polygons_preferred=4,
        )

        snapshot = build_topographic_brain_snapshot(
            world=world,
            observed_monotonic_s=2.0,
            actor=start,
            actor_facing_rad=0.5,
            actor_position_source="COORDINATE_HUD_WORLD_TRANSFORM",
            actor_facing_source="COORDINATE_HUD_EXACT",
            controller_heading_rad=0.52,
            destination=stop,
            corridor=corridor,
            environment=None,
            semantic_route_profile="road_backbone",
            semantic_goal_index=1,
            semantic_goal_count=3,
            visible_dynamic_entity_count=2,
            routine_aggro_travel_enabled=True,
            minimum_travel_health_fraction=0.55,
        )
        record = snapshot.to_record()

        self.assertEqual(record["coordinate_frame"], "CLIENT_WORLD_XYZ")
        self.assertEqual(record["actor"]["position"], [10.0, 20.0, 5.0])
        self.assertEqual(record["actor"]["body_facing_rad"], 0.5)
        self.assertEqual(record["actor"]["controller_heading_rad"], 0.52)
        self.assertTrue(record["foundation"]["autonomous_planning_ready"])
        self.assertFalse(
            record["foundation"]["visual_actor_silhouette_is_authority"]
        )
        self.assertEqual(
            record["knowledge_layers"]["local_topology"]["polygon_count"],
            9,
        )
        self.assertEqual(
            record["knowledge_layers"]["permanent_experience"][
                "visited_cell_count"
            ],
            1,
        )
        self.assertFalse(
            record["active_navigation"]["route_is_operator_hardcoded"]
        )
        self.assertTrue(
            record["routine_aggro_policy"]["continue_destination_corridor"]
        )
        self.assertFalse(record["execution_authority"])

    def test_unknown_initial_facing_is_explicit_not_a_runtime_error(self) -> None:
        world = LayeredWorldModel(
            map_name="Azeroth",
            static_navmesh_sha256="A" * 64,
        )
        start = NavPoint(10.0, 20.0, 5.0)
        stop = NavPoint(30.0, 40.0, 6.0)
        corridor = NavCorridor(
            "Azeroth", 31, 31, start, stop, (start, stop),
        )

        record = build_topographic_brain_snapshot(
            world=world,
            observed_monotonic_s=2.0,
            actor=start,
            actor_facing_rad=None,
            actor_position_source="COORDINATE_HUD_WORLD_TRANSFORM",
            actor_facing_source="UNAVAILABLE",
            controller_heading_rad=0.5,
            destination=stop,
            corridor=corridor,
            environment=None,
            semantic_route_profile=None,
            semantic_goal_index=0,
            semantic_goal_count=0,
            visible_dynamic_entity_count=0,
            routine_aggro_travel_enabled=True,
            minimum_travel_health_fraction=0.55,
        ).to_record()

        self.assertIsNone(record["actor"]["body_facing_rad"])
        self.assertFalse(record["foundation"]["autonomous_planning_ready"])

    def test_implementation_contains_no_named_route_exception(self) -> None:
        # The strict pose/environment binding is exercised by constructor
        # validation elsewhere; this regression protects the global invariant
        # that no named zone or route is embedded in the implementation.
        source = __import__(
            "perfect_assassin.movement.topographic_brain",
            fromlist=["unused"],
        ).__file__
        with open(source, encoding="utf-8") as stream:
            implementation = stream.read().lower()
        self.assertNotIn("deathknell", implementation)
        self.assertNotIn("brill", implementation)


if __name__ == "__main__":
    unittest.main()
