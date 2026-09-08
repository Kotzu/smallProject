from __future__ import annotations

import unittest

from perfect_assassin.movement.client_navmesh import (
    NavCorridor,
    NavPoint,
    NavPolygon,
    NavPortal,
)
from perfect_assassin.movement.target_tether import TargetTetherPlanner


class TargetTetherPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = TargetTetherPlanner()
        self.player = NavPoint(10.0, 20.0, 5.0)

    def projection(self, *, in_melee: bool | None = False):
        return self.planner.project(
            player=self.player,
            player_heading_rad=0.0,
            target_bearing_error_x_normalized=0.0,
            client_in_melee=in_melee,
        )

    def corridor(self, points, *, complete=True, **changes):
        projection = self.projection()
        stop = points[-1]
        return NavCorridor(
            map_name="Azeroth",
            adt_x=31,
            adt_y=31,
            start=self.player,
            stop=stop,
            points=tuple(points),
            complete=complete,
            requested_stop=None if complete else projection.projected_target,
            **changes,
        )

    def test_in_melee_never_requests_translation_corridor(self) -> None:
        intent = self.planner.decide(self.projection(in_melee=True), None)
        self.assertEqual(intent.state, "IN_MELEE")
        self.assertEqual(intent.guidance_error_rad, 0.0)

    def test_missing_navmesh_waits_instead_of_walking_through_wall(self) -> None:
        intent = self.planner.decide(self.projection(), None)
        self.assertEqual(intent.state, "WAITING_NAVMESH")
        self.assertIsNone(intent.guidance_point)

    def test_straight_complete_corridor_is_direct(self) -> None:
        projection = self.projection()
        corridor = self.corridor([
            self.player,
            NavPoint(14.0, 20.0, 5.0),
            projection.projected_target,
        ])
        intent = self.planner.decide(projection, corridor)
        self.assertEqual(intent.state, "DIRECT")
        self.assertAlmostEqual(intent.guidance_error_rad, 0.0)

    def test_obstacle_arc_is_a_left_detour(self) -> None:
        projection = self.projection()
        corridor = self.corridor([
            self.player,
            NavPoint(12.0, 22.0, 5.0),
            NavPoint(16.0, 22.0, 5.0),
            projection.projected_target,
        ], doodad_avoidance_applied=True, doodad_detour_count=1)
        intent = self.planner.decide(projection, corridor)
        self.assertEqual(intent.state, "DETOUR_LEFT")
        self.assertGreater(intent.guidance_error_rad, 0.0)

    def test_partial_corridor_with_confirmed_progress_advances_then_replans(self) -> None:
        projection = self.projection()
        corridor = self.corridor([
            self.player,
            NavPoint(12.0, 20.0, 5.0),
        ], complete=False)
        intent = self.planner.decide(projection, corridor)
        self.assertEqual(intent.state, "PARTIAL_ADVANCE_DIRECT")
        self.assertEqual(
            intent.reason,
            "safe_partial_navmesh_horizon_requires_replan",
        )

    def test_tiny_partial_corridor_never_authorizes_blind_approach(self) -> None:
        projection = self.projection()
        corridor = self.corridor([
            self.player,
            NavPoint(10.4, 20.0, 5.0),
        ], complete=False)
        intent = self.planner.decide(projection, corridor)
        self.assertEqual(intent.state, "PARTIAL_BLOCKED")

    def test_partial_corridor_with_unresolved_doodad_stays_blocked(self) -> None:
        projection = self.projection()
        corridor = self.corridor([
            self.player,
            NavPoint(13.0, 20.0, 5.0),
        ], complete=False, doodad_unresolved_segment_count=1)
        intent = self.planner.decide(projection, corridor)
        self.assertEqual(intent.state, "PARTIAL_BLOCKED")

    def test_geometry_corridor_reports_space_to_both_edges(self) -> None:
        projection = self.projection()
        polygons = (
            NavPolygon(
                0, 1, 0, 0.0, NavPoint(12.0, 20.0, 5.0),
                (NavPoint(10.0, 18.0, 5.0), NavPoint(14.0, 18.0, 5.0),
                 NavPoint(14.0, 22.0, 5.0)),
                frozenset({"ground"}),
            ),
            NavPolygon(
                1, 1, 0, 0.0, NavPoint(16.0, 20.0, 5.0),
                (NavPoint(14.0, 18.0, 5.0), NavPoint(18.0, 18.0, 5.0),
                 NavPoint(18.0, 22.0, 5.0)),
                frozenset({"ground"}),
            ),
        )
        corridor = self.corridor(
            [self.player, NavPoint(16.0, 20.0, 5.0), projection.projected_target],
            polygons=polygons,
            portals=(NavPortal(
                0, 1, NavPoint(14.0, 21.0, 5.0),
                NavPoint(14.0, 19.0, 5.0), 2.0,
            ),),
        )

        intent = self.planner.decide(projection, corridor)

        self.assertAlmostEqual(intent.corridor_edge_clearance_world, 1.0)
        self.assertTrue(intent.corridor_edge_safe)

    def test_geometry_corridor_marks_actor_too_close_to_bridge_edge(self) -> None:
        player = NavPoint(10.0, 20.8, 5.0)
        projection = self.planner.project(
            player=player,
            player_heading_rad=0.0,
            target_bearing_error_x_normalized=0.0,
            client_in_melee=False,
        )
        polygons = (
            NavPolygon(
                0, 1, 0, 0.0, NavPoint(12.0, 20.0, 5.0),
                (NavPoint(10.0, 18.0, 5.0), NavPoint(14.0, 18.0, 5.0),
                 NavPoint(14.0, 22.0, 5.0)),
                frozenset({"ground"}),
            ),
            NavPolygon(
                1, 1, 0, 0.0, NavPoint(16.0, 20.0, 5.0),
                (NavPoint(14.0, 18.0, 5.0), NavPoint(18.0, 18.0, 5.0),
                 NavPoint(18.0, 22.0, 5.0)),
                frozenset({"ground"}),
            ),
        )
        corridor = NavCorridor(
            map_name="Azeroth", adt_x=31, adt_y=31,
            start=player, stop=projection.projected_target,
            points=(player, NavPoint(16.0, 20.8, 5.0), projection.projected_target),
            polygons=polygons,
            portals=(NavPortal(
                0, 1, NavPoint(14.0, 21.0, 5.0),
                NavPoint(14.0, 19.0, 5.0), 2.0,
            ),),
        )

        intent = self.planner.decide(projection, corridor)

        self.assertLess(intent.corridor_edge_clearance_world, 0.65)
        self.assertFalse(intent.corridor_edge_safe)


if __name__ == "__main__":
    unittest.main()
