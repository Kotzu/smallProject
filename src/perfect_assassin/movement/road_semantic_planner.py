from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot, inf, isfinite, sqrt
from pathlib import Path

import numpy as np

from perfect_assassin.adapter.adt_road import (
    AdtRoadSemantic,
    ROAD_SIDECAR_DIMENSION,
)


ADT_SIZE = 533.0 + 1.0 / 3.0
WORLD_ADTS = 64


class RoadSemanticPlanError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RoadWorldPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise ValueError("road world point must be finite")


@dataclass(frozen=True, slots=True)
class SemanticRoadRoute:
    start: RoadWorldPoint
    destination: RoadWorldPoint
    road_entry: RoadWorldPoint
    road_exit: RoadWorldPoint
    waypoints: tuple[RoadWorldPoint, ...]
    road_cell_count: int
    near_road_cell_count: int
    offroad_bridge_cell_count: int
    expanded_cell_count: int
    path_cost: float = 0.0
    profile_id: str = "road_backbone"
    source: str = "client_adt_texture_semantics"
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.waypoints:
            raise ValueError("semantic road route has no waypoints")
        if self.waypoints[0] != self.road_entry or self.waypoints[-1] != self.road_exit:
            raise ValueError("semantic road route endpoints are inconsistent")
        if min(
            self.road_cell_count,
            self.near_road_cell_count,
            self.offroad_bridge_cell_count,
            self.expanded_cell_count,
        ) < 0:
            raise ValueError("semantic road route diagnostics are invalid")
        if not isfinite(self.path_cost) or self.path_cost < 0.0 or not self.profile_id:
            raise ValueError("semantic road route cost or profile is invalid")


class ClientRoadSemanticPlanner:
    """Global road prior from exact client ADT texture layers.

    This planner does not produce executable movement. It supplies global
    semantic waypoints; local 3D navmesh queries remain authoritative for
    terrain, WMO, M2, slope, and recovery.
    """

    def __init__(
        self,
        *,
        sidecar_root: Path,
        map_name: str = "Azeroth",
        cell_pixels: int = 8,
        road_threshold: int = 48,
        near_road_radius_cells: int = 2,
        near_road_cost: float = 4.0,
        offroad_cost: float = 80.0,
        waypoint_stride_cells: int = 3,
        snap_radius_yards: float = 500.0,
    ) -> None:
        if ROAD_SIDECAR_DIMENSION % cell_pixels:
            raise ValueError("semantic grid cell size must divide the ADT sidecar")
        if not 1 <= road_threshold <= 255:
            raise ValueError("road threshold is invalid")
        if not 0 <= near_road_radius_cells <= 8:
            raise ValueError("near-road radius is invalid")
        if (
            near_road_cost < 1.0
            or offroad_cost < near_road_cost
            or waypoint_stride_cells < 1
            or snap_radius_yards <= 0
        ):
            raise ValueError("semantic road planner cost or range is invalid")
        self.sidecar_root = sidecar_root
        self.map_name = map_name
        self.cell_pixels = cell_pixels
        self.road_threshold = road_threshold
        self.near_road_radius_cells = near_road_radius_cells
        self.near_road_cost = float(near_road_cost)
        self.offroad_cost = offroad_cost
        self.waypoint_stride_cells = waypoint_stride_cells
        self.snap_radius_yards = snap_radius_yards
        self.cells_per_adt = ROAD_SIDECAR_DIMENSION // cell_pixels
        self.cell_world = ADT_SIZE / self.cells_per_adt
        self._grid_cache: tuple[
            set[tuple[int, int]],
            set[tuple[int, int]],
            tuple[int, int, int, int],
            dict[tuple[int, int], RoadWorldPoint],
        ] | None = None

    def world_to_cell(self, point: RoadWorldPoint) -> tuple[int, int]:
        origin = WORLD_ADTS / 2 * ADT_SIZE
        return (
            int((origin - point.x) // self.cell_world),
            int((origin - point.y) // self.cell_world),
        )

    def cell_to_world(self, cell: tuple[int, int]) -> RoadWorldPoint:
        origin = WORLD_ADTS / 2 * ADT_SIZE
        row, column = cell
        return RoadWorldPoint(
            origin - (row + 0.5) * self.cell_world,
            origin - (column + 0.5) * self.cell_world,
        )

    def _load_cells(
        self,
    ) -> tuple[
        set[tuple[int, int]],
        tuple[int, int, int, int],
        dict[tuple[int, int], RoadWorldPoint],
    ]:
        sidecars = sorted(self.sidecar_root.glob(f"{self.map_name}_*_*.road"))
        if not sidecars:
            raise RoadSemanticPlanError("no client ADT road sidecars are available")
        road_cells: set[tuple[int, int]] = set()
        road_anchors: dict[tuple[int, int], RoadWorldPoint] = {}
        tile_coordinates: list[tuple[int, int]] = []
        pixels_per_cell = self.cell_pixels * self.cell_pixels
        pixel_world = ADT_SIZE / ROAD_SIDECAR_DIMENSION
        origin = WORLD_ADTS / 2 * ADT_SIZE
        for path in sidecars:
            semantic = AdtRoadSemantic.from_bytes(path.read_bytes())
            tile_coordinates.append((semantic.adt_x, semantic.adt_y))
            pixels = np.frombuffer(semantic.affinity, dtype=np.uint8).reshape(
                ROAD_SIDECAR_DIMENSION,
                ROAD_SIDECAR_DIMENSION,
            )
            blocks = pixels.reshape(
                self.cells_per_adt,
                self.cell_pixels,
                self.cells_per_adt,
                self.cell_pixels,
            ).transpose(0, 2, 1, 3)
            block_sums = blocks.sum(axis=(2, 3), dtype=np.uint32)
            # A coarse cell is a road only when the road contribution across
            # its whole footprint reaches the same configured affinity used
            # for individual source pixels.  The former any-pixel rule moved
            # waypoints into grass whenever a road merely touched one corner.
            road_mask = block_sums >= self.road_threshold * pixels_per_cell
            for local_row, local_column in np.argwhere(road_mask):
                cell = (
                    semantic.adt_y * self.cells_per_adt + int(local_row),
                    semantic.adt_x * self.cells_per_adt + int(local_column),
                )
                road_cells.add(cell)
                block = blocks[local_row, local_column].astype(np.float64)
                weight = float(block.sum())
                if weight <= 0.0:
                    continue
                row_weights = block.sum(axis=1)
                column_weights = block.sum(axis=0)
                source_row = (
                    semantic.adt_y * ROAD_SIDECAR_DIMENSION
                    + int(local_row) * self.cell_pixels
                    + float(np.dot(
                        np.arange(self.cell_pixels, dtype=np.float64) + 0.5,
                        row_weights,
                    )) / weight
                )
                source_column = (
                    semantic.adt_x * ROAD_SIDECAR_DIMENSION
                    + int(local_column) * self.cell_pixels
                    + float(np.dot(
                        np.arange(self.cell_pixels, dtype=np.float64) + 0.5,
                        column_weights,
                    )) / weight
                )
                road_anchors[cell] = RoadWorldPoint(
                    origin - source_row * pixel_world,
                    origin - source_column * pixel_world,
                )
        if not road_cells:
            raise RoadSemanticPlanError("client ADT sidecars contain no road affinity")
        min_x = min(value[0] for value in tile_coordinates) * self.cells_per_adt
        max_x = (max(value[0] for value in tile_coordinates) + 1) * self.cells_per_adt - 1
        min_y = min(value[1] for value in tile_coordinates) * self.cells_per_adt
        max_y = (max(value[1] for value in tile_coordinates) + 1) * self.cells_per_adt - 1
        # Grid rows follow ADT Y; columns follow ADT X.
        return road_cells, (min_y, max_y, min_x, max_x), road_anchors

    def _nearest_road_cell(
        self,
        point: RoadWorldPoint,
        road_cells: set[tuple[int, int]],
    ) -> tuple[int, int]:
        origin = self.world_to_cell(point)
        nearest = min(
            road_cells,
            key=lambda cell: (cell[0] - origin[0]) ** 2 + (cell[1] - origin[1]) ** 2,
        )
        distance = hypot(nearest[0] - origin[0], nearest[1] - origin[1]) * self.cell_world
        if distance > self.snap_radius_yards:
            raise RoadSemanticPlanError("no road semantic is near enough to the endpoint")
        return nearest

    def _near_road_cells(
        self,
        road_cells: set[tuple[int, int]],
        bounds: tuple[int, int, int, int],
    ) -> set[tuple[int, int]]:
        min_row, max_row, min_column, max_column = bounds
        radius = self.near_road_radius_cells
        nearby: set[tuple[int, int]] = set()
        for row, column in road_cells:
            for row_offset in range(-radius, radius + 1):
                for column_offset in range(-radius, radius + 1):
                    if row_offset * row_offset + column_offset * column_offset > radius * radius:
                        continue
                    candidate = row + row_offset, column + column_offset
                    if (
                        min_row <= candidate[0] <= max_row
                        and min_column <= candidate[1] <= max_column
                    ):
                        nearby.add(candidate)
        return nearby

    def _grid(
        self,
    ) -> tuple[
        set[tuple[int, int]],
        set[tuple[int, int]],
        tuple[int, int, int, int],
        dict[tuple[int, int], RoadWorldPoint],
    ]:
        """Load and expand immutable atlas semantics once per planner.

        Risk-aware planning evaluates several cost profiles over the same
        exact client atlas. Re-reading every sidecar and rebuilding the
        near-road dilation for each profile caused minute-long stationary
        starts without adding any evidence.
        """

        if self._grid_cache is None:
            road_cells, bounds, road_anchors = self._load_cells()
            near_road_cells = self._near_road_cells(road_cells, bounds)
            self._grid_cache = (
                road_cells,
                near_road_cells,
                bounds,
                road_anchors,
            )
        return self._grid_cache

    def _anchored_world_point(
        self,
        cell: tuple[int, int],
        road_anchors: dict[tuple[int, int], RoadWorldPoint],
    ) -> RoadWorldPoint:
        return road_anchors.get(cell, self.cell_to_world(cell))

    def _astar(
        self,
        *,
        start: tuple[int, int],
        stop: tuple[int, int],
        road_cells: set[tuple[int, int]],
        near_road_cells: set[tuple[int, int]],
        bounds: tuple[int, int, int, int],
        near_road_cost: float,
        offroad_cost: float,
    ) -> tuple[list[tuple[int, int]], int, float]:
        min_row, max_row, min_column, max_column = bounds
        frontier: list[tuple[float, float, tuple[int, int]]] = [(0.0, 0.0, start)]
        parent: dict[tuple[int, int], tuple[int, int]] = {}
        cost = {start: 0.0}
        expanded = 0
        neighbors = (
            (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, sqrt(2.0)), (-1, 1, sqrt(2.0)),
            (1, -1, sqrt(2.0)), (1, 1, sqrt(2.0)),
        )
        while frontier:
            _priority, known_cost, current = heappop(frontier)
            if known_cost != cost.get(current):
                continue
            expanded += 1
            if current == stop:
                path = [current]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path, expanded, known_cost
            for row_offset, column_offset, distance in neighbors:
                candidate = current[0] + row_offset, current[1] + column_offset
                if not (
                    min_row <= candidate[0] <= max_row
                    and min_column <= candidate[1] <= max_column
                ):
                    continue
                if candidate in road_cells:
                    semantic_cost = 1.0
                elif candidate in near_road_cells:
                    semantic_cost = near_road_cost
                else:
                    semantic_cost = offroad_cost
                candidate_cost = known_cost + distance * semantic_cost
                if candidate_cost >= cost.get(candidate, inf):
                    continue
                cost[candidate] = candidate_cost
                parent[candidate] = current
                heuristic = hypot(candidate[0] - stop[0], candidate[1] - stop[1])
                heappush(frontier, (candidate_cost + heuristic, candidate_cost, candidate))
        raise RoadSemanticPlanError("semantic road graph has no route inside loaded ADTs")

    def _waypoint_cells(self, path: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
        if len(path) <= 2:
            return tuple(path)
        selected = [path[0]]
        for index in range(self.waypoint_stride_cells, len(path) - 1, self.waypoint_stride_cells):
            selected.append(path[index])
        if selected[-1] != path[-1]:
            selected.append(path[-1])
        return tuple(selected)

    def plan(
        self,
        *,
        start_x: float,
        start_y: float,
        destination_x: float,
        destination_y: float,
        profile_id: str = "road_backbone",
        near_road_cost: float | None = None,
        offroad_cost: float | None = None,
    ) -> SemanticRoadRoute:
        selected_near_road_cost = (
            self.near_road_cost
            if near_road_cost is None else float(near_road_cost)
        )
        selected_offroad_cost = (
            self.offroad_cost if offroad_cost is None else float(offroad_cost)
        )
        if (
            not profile_id
            or not isfinite(selected_near_road_cost)
            or not isfinite(selected_offroad_cost)
            or selected_near_road_cost < 1.0
            or selected_offroad_cost < selected_near_road_cost
        ):
            raise ValueError("semantic road route costs are invalid")
        start = RoadWorldPoint(start_x, start_y)
        destination = RoadWorldPoint(destination_x, destination_y)
        road_cells, near_road_cells, bounds, road_anchors = self._grid()
        entry_cell = self._nearest_road_cell(start, road_cells)
        exit_cell = self._nearest_road_cell(destination, road_cells)
        path, expanded, path_cost = self._astar(
            start=entry_cell,
            stop=exit_cell,
            road_cells=road_cells,
            near_road_cells=near_road_cells,
            bounds=bounds,
            near_road_cost=selected_near_road_cost,
            offroad_cost=selected_offroad_cost,
        )
        road_count = sum(cell in road_cells for cell in path)
        near_count = sum(
            cell not in road_cells and cell in near_road_cells for cell in path
        )
        bridge_count = len(path) - road_count - near_count
        waypoint_cells = self._waypoint_cells(path)
        waypoints = tuple(
            self._anchored_world_point(cell, road_anchors)
            for cell in waypoint_cells
        )
        return SemanticRoadRoute(
            start=start,
            destination=destination,
            road_entry=self._anchored_world_point(entry_cell, road_anchors),
            road_exit=self._anchored_world_point(exit_cell, road_anchors),
            waypoints=waypoints,
            road_cell_count=road_count,
            near_road_cell_count=near_count,
            offroad_bridge_cell_count=bridge_count,
            expanded_cell_count=expanded,
            path_cost=path_cost,
            profile_id=profile_id,
        )

    def plan_variants(
        self,
        *,
        start_x: float,
        start_y: float,
        destination_x: float,
        destination_y: float,
    ) -> tuple[SemanticRoadRoute, ...]:
        """Generate road, balanced, and shortcut priors from client atlas cells.

        These remain semantic candidates. A caller must score them against
        observed risks and validate every chosen leg with the local 3D Detour
        corridor before any movement is attempted.
        """

        profiles = (
            ("road_backbone", self.near_road_cost, self.offroad_cost),
            ("balanced", 1.75, 3.0),
            ("shortcut", 1.05, 1.12),
        )
        return tuple(
            self.plan(
                start_x=start_x,
                start_y=start_y,
                destination_x=destination_x,
                destination_y=destination_y,
                profile_id=profile_id,
                near_road_cost=profile_near_road_cost,
                offroad_cost=profile_offroad_cost,
            )
            for profile_id, profile_near_road_cost, profile_offroad_cost in profiles
        )
