from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, order=True, slots=True)
class GridPoint:
    x: int
    y: int


class NoPathError(ValueError):
    """Raised when no route exists inside the supplied navigation fixture."""


@dataclass(frozen=True, slots=True)
class GridMap:
    width: int
    height: int
    blocked: frozenset[GridPoint] = frozenset()
    traversal_costs: Mapping[GridPoint, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Grid dimensions must be positive")
        for point in self.blocked:
            if not self.contains(point):
                raise ValueError(f"Blocked point is outside grid: {point}")
        normalized = dict(self.traversal_costs)
        for point, cost in normalized.items():
            if not self.contains(point):
                raise ValueError(f"Traversal-cost point is outside grid: {point}")
            if point in self.blocked:
                raise ValueError(f"Blocked point cannot have traversal cost: {point}")
            if not isfinite(cost) or cost < 1:
                raise ValueError(f"Traversal cost must be finite and at least 1: {cost}")
        object.__setattr__(self, "traversal_costs", MappingProxyType(normalized))

    def contains(self, point: GridPoint) -> bool:
        return 0 <= point.x < self.width and 0 <= point.y < self.height

    def walkable(self, point: GridPoint) -> bool:
        return self.contains(point) and point not in self.blocked

    def cost(self, point: GridPoint) -> float:
        return self.traversal_costs.get(point, 1.0)


@dataclass(frozen=True, slots=True)
class PathPlan:
    points: tuple[GridPoint, ...]
    total_cost: float


class AStarGridPlanner:
    """Deterministic four-neighbour A* used as the pre-navmesh contract slice."""

    version = "0.1.0"
    _deltas = ((0, -1), (1, 0), (0, 1), (-1, 0))

    @staticmethod
    def _heuristic(point: GridPoint, goal: GridPoint) -> int:
        return abs(point.x - goal.x) + abs(point.y - goal.y)

    def plan(self, grid: GridMap, start: GridPoint, goal: GridPoint) -> PathPlan:
        if not grid.walkable(start):
            raise NoPathError(f"Start is not walkable: {start}")
        if not grid.walkable(goal):
            raise NoPathError(f"Goal is not walkable: {goal}")

        frontier: list[tuple[float, int, int, int, GridPoint]] = []
        start_h = self._heuristic(start, goal)
        heapq.heappush(frontier, (float(start_h), start_h, start.y, start.x, start))
        came_from: dict[GridPoint, GridPoint | None] = {start: None}
        costs: dict[GridPoint, float] = {start: 0.0}

        while frontier:
            _, _, _, _, current = heapq.heappop(frontier)
            if current == goal:
                return PathPlan(self._reconstruct(came_from, goal), costs[goal])

            for delta_x, delta_y in self._deltas:
                neighbour = GridPoint(current.x + delta_x, current.y + delta_y)
                if not grid.walkable(neighbour):
                    continue
                candidate_cost = costs[current] + grid.cost(neighbour)
                if candidate_cost >= costs.get(neighbour, float("inf")):
                    continue
                costs[neighbour] = candidate_cost
                came_from[neighbour] = current
                heuristic = self._heuristic(neighbour, goal)
                heapq.heappush(
                    frontier,
                    (
                        candidate_cost + heuristic,
                        heuristic,
                        neighbour.y,
                        neighbour.x,
                        neighbour,
                    ),
                )

        raise NoPathError(f"No path from {start} to {goal}")

    @staticmethod
    def _reconstruct(
        came_from: Mapping[GridPoint, GridPoint | None], goal: GridPoint
    ) -> tuple[GridPoint, ...]:
        path = [goal]
        current = goal
        while came_from[current] is not None:
            current = came_from[current]  # type: ignore[assignment]
            path.append(current)
        path.reverse()
        return tuple(path)
