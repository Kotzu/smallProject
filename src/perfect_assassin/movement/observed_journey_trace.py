from __future__ import annotations

from math import isfinite

from perfect_assassin.movement.client_navmesh import NavPoint


class ObservedJourneyTrace:
    """Bounded, read-only visual history of client-observed movement.

    This is diagnostic evidence, not a route and not execution authority.  A
    teleport-sized discontinuity starts a new visible trace instead of drawing
    a false line across the world.  Long journeys are progressively decimated
    so one continuous trip remains visible without unbounded state growth.
    """

    def __init__(
        self,
        *,
        sample_spacing_world: float = 1.0,
        maximum_points: int = 2048,
        maximum_sample_jump_world: float = 12.0,
    ) -> None:
        if (
            not isfinite(sample_spacing_world)
            or sample_spacing_world <= 0
            or type(maximum_points) is not int
            or not 64 <= maximum_points <= 4096
            or not isfinite(maximum_sample_jump_world)
            or maximum_sample_jump_world <= sample_spacing_world
        ):
            raise ValueError("observed journey trace bounds are invalid")
        self._base_spacing_world = float(sample_spacing_world)
        self._effective_spacing_world = float(sample_spacing_world)
        self._maximum_points = maximum_points
        self._maximum_sample_jump_world = float(maximum_sample_jump_world)
        self._points: list[NavPoint] = []

    @property
    def points(self) -> tuple[NavPoint, ...]:
        return tuple(self._points)

    @property
    def effective_spacing_world(self) -> float:
        return self._effective_spacing_world

    def observe(self, point: NavPoint) -> bool:
        if not isinstance(point, NavPoint):
            raise ValueError("observed journey trace point must be a NavPoint")
        if not self._points:
            self._points.append(point)
            return True
        distance = self._points[-1].distance_2d(point)
        if distance > self._maximum_sample_jump_world:
            self._points = [point]
            self._effective_spacing_world = self._base_spacing_world
            return True
        if distance < self._effective_spacing_world:
            return False
        self._points.append(point)
        if len(self._points) > self._maximum_points:
            retained = self._points[::2]
            if retained[-1] != self._points[-1]:
                retained.append(self._points[-1])
            self._points = retained
            self._effective_spacing_world *= 2.0
        return True
