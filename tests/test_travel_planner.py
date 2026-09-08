from __future__ import annotations

import unittest

from perfect_assassin.movement.travel_planner import (
    SemanticLocation, SemanticTravelPlanner, TravelState,
)


class SemanticTravelPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.destination = SemanticLocation(
            "inn:brill", "Azeroth", 2245.0, 290.0, 12.0,
            "reviewed_world_knowledge:v1", 0.95,
        )

    def test_matching_ready_hearth_beats_walking(self) -> None:
        plan = SemanticTravelPlanner().plan(
            state=TravelState("Azeroth", 1676.0, 1677.0, "inn:brill", True),
            destination=self.destination,
        )
        self.assertEqual(plan.method, "HEARTHSTONE")
        self.assertFalse(plan.requires_navmesh)

    def test_unavailable_hearth_falls_back_to_navmesh_for_known_destination(self) -> None:
        plan = SemanticTravelPlanner().plan(
            state=TravelState("Azeroth", 1676.0, 1677.0, "inn:brill", False),
            destination=self.destination,
        )
        self.assertEqual(plan.method, "NAVMESH")
        self.assertTrue(plan.requires_navmesh)

    def test_arrival_is_detected_before_transport_selection(self) -> None:
        plan = SemanticTravelPlanner().plan(
            state=TravelState("Azeroth", 2246.0, 290.0, "inn:brill", True),
            destination=self.destination,
        )
        self.assertEqual(plan.method, "ARRIVED")


if __name__ == "__main__":
    unittest.main()
