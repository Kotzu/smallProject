from __future__ import annotations

import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.movement import AStarGridPlanner, GridMap, GridPoint, NoPathError


ROOT = Path(__file__).resolve().parents[1]


class MovementPlannerTests(unittest.TestCase):
    def test_astar_routes_around_obstacle_deterministically(self) -> None:
        grid = GridMap(
            width=5,
            height=3,
            blocked=frozenset({GridPoint(2, 0), GridPoint(2, 1)}),
        )
        planner = AStarGridPlanner()
        first = planner.plan(grid, GridPoint(0, 1), GridPoint(4, 1))
        second = planner.plan(grid, GridPoint(0, 1), GridPoint(4, 1))
        self.assertEqual(first, second)
        self.assertNotIn(GridPoint(2, 1), first.points)
        self.assertEqual(first.points[0], GridPoint(0, 1))
        self.assertEqual(first.points[-1], GridPoint(4, 1))

    def test_tactical_cost_can_prefer_a_longer_safe_route(self) -> None:
        risky = {GridPoint(x, 1): 10.0 for x in range(1, 4)}
        grid = GridMap(width=5, height=3, traversal_costs=risky)
        plan = AStarGridPlanner().plan(grid, GridPoint(0, 1), GridPoint(4, 1))
        self.assertTrue(any(point.y != 1 for point in plan.points[1:-1]))
        self.assertLess(plan.total_cost, 31.0)

    def test_no_path_fails_closed(self) -> None:
        grid = GridMap(
            width=3,
            height=3,
            blocked=frozenset({GridPoint(1, 0), GridPoint(1, 1), GridPoint(1, 2)}),
        )
        with self.assertRaises(NoPathError):
            AStarGridPlanner().plan(grid, GridPoint(0, 1), GridPoint(2, 1))

    def test_tactical_cost_cannot_break_astar_heuristic_floor(self) -> None:
        with self.assertRaises(ValueError):
            GridMap(width=2, height=1, traversal_costs={GridPoint(1, 0): 0.5})

    def test_champion_path_contract_rejects_lab_oracle(self) -> None:
        validator = ContractValidator(ROOT / "contracts" / "movement.schema.json")
        invalid = {
            "record_type": "path_proposal",
            "schema_version": "0.1",
            "path_id": "path:test",
            "goal_id": "goal:test",
            "decision_context": "champion",
            "target_profile": "tbc_243_lab",
            "planner_id": "fixture_astar",
            "planner_version": "0.1.0",
            "map_signature": "fixture:test",
            "nav_source_origin": "lab_oracle",
            "waypoints": [
                {"coordinate_space": "fixture", "x": 0, "y": 0},
                {"coordinate_space": "fixture", "x": 1, "y": 0}
            ],
            "total_cost": 1,
            "confidence": 1,
            "evidence_refs": ["lab:mmap:path"],
            "execution_authority": False,
            "created_at": "2026-08-22T16:00:00Z"
        }
        with self.assertRaises(ContractValidationError):
            validator.validate(invalid)


if __name__ == "__main__":
    unittest.main()
