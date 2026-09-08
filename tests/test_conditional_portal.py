from __future__ import annotations

from math import tau
import unittest

from perfect_assassin.movement.client_navmesh import (
    LocalStaticAwareness,
    LocalTopologicalEgressPortal,
    LocalWallSegment,
    NavCorridor,
    NavPoint,
    RadialClearanceProbe,
)
from perfect_assassin.movement.conditional_portal import (
    infer_conditional_traversal_frontier,
)


def _awareness(*, surface: str = "wmo", with_egress: bool = False) -> LocalStaticAwareness:
    egresses = ()
    if with_egress:
        egresses = (LocalTopologicalEgressPortal(
            NavPoint(4, 0, 0), NavPoint(4, 3, 0), 3.0, 4.0, 8.0,
            False, True, frozenset({"wmo"}), frozenset({"ground"}),
        ),)
    return LocalStaticAwareness(
        physical_surfaces=frozenset({surface}),
        probe_radius_yards=12.0,
        overhead_clear=surface != "wmo",
        radial_probes=tuple(
            RadialClearanceProbe(index * tau / 16, 4.0, False)
            for index in range(16)
        ),
        component_polygon_count=126,
        wall_segments=(
            LocalWallSegment(NavPoint(1, -2, 0), NavPoint(1, 2, 0), 1.0),
            LocalWallSegment(NavPoint(20, -2, 0), NavPoint(20, 2, 0), 20.0),
        ),
        egress_portals=egresses,
    )


class ConditionalPortalTests(unittest.TestCase):
    def test_stalled_multifloor_wmo_frontier_requires_visible_confirmation(self) -> None:
        start = NavPoint(-187.20, 2139.88, 83.23)
        requested = NavPoint(-76.75, 2152.41, 155.71)
        corridor = NavCorridor(
            "Shadowfang", 27, 31, start, start, (start,),
            complete=False, requested_stop=requested,
            start_awareness=_awareness(),
        )

        frontier = infer_conditional_traversal_frontier(corridor)

        self.assertIsNotNone(frontier)
        assert frontier is not None
        self.assertEqual(
            frontier.kind,
            "POSSIBLE_WMO_DOOR_GATE_OR_FLOOR_TRANSITION",
        )
        self.assertEqual(len(frontier.boundary_segments), 1)
        self.assertTrue(frontier.requires_live_visible_confirmation)
        self.assertFalse(frontier.execution_authority)

    def test_partial_corridor_with_real_progress_is_not_a_portal_claim(self) -> None:
        start = NavPoint(0, 0, 0)
        corridor = NavCorridor(
            "Shadowfang", 27, 31, start, NavPoint(10, 0, 0),
            (start, NavPoint(10, 0, 0)), complete=False,
            requested_stop=NavPoint(30, 0, 0), start_awareness=_awareness(),
        )
        self.assertIsNone(infer_conditional_traversal_frontier(corridor))

    def test_same_xy_different_floor_remains_a_conditional_frontier(self) -> None:
        start = NavPoint(10, 20, 30)
        corridor = NavCorridor(
            "Shadowfang", 27, 31, start, start, (start,), complete=False,
            requested_stop=NavPoint(10, 20, 45), start_awareness=_awareness(),
        )

        frontier = infer_conditional_traversal_frontier(corridor)

        self.assertIsNotNone(frontier)
        assert frontier is not None
        self.assertEqual(frontier.remaining_distance_yards, 15)

    def test_open_ground_and_verified_egress_are_not_conditional_portals(self) -> None:
        start = NavPoint(0, 0, 0)
        for awareness in (_awareness(surface="ground"), _awareness(with_egress=True)):
            corridor = NavCorridor(
                "Shadowfang", 27, 31, start, start, (start,),
                complete=False, requested_stop=NavPoint(10, 0, 0),
                start_awareness=awareness,
            )
            self.assertIsNone(infer_conditional_traversal_frontier(corridor))


if __name__ == "__main__":
    unittest.main()
