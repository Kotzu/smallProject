from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint


DEFAULT_SAMPLE_SPACING_WORLD = 1.5
DEFAULT_MAXIMUM_TRAIL_WORLD = 300.0
MAXIMUM_CONTEXT_BREADCRUMBS = 224
MAXIMUM_CONTEXT_TRAIL_WORLD = 302.0


@dataclass(frozen=True, slots=True)
class RetreatTrailRecord:
    map_name: str
    points: tuple[NavPoint, ...]
    sampled_distance_world: float
    execution_authority: bool = False


class SafeRetreatTrail:
    """Short, verified breadcrumb memory for a combat disengage.

    The trail is made only from fresh client-visible positions that the actor
    actually traversed.  It is not a planned route and it grants no input
    authority.  A discontinuity clears the old trail instead of connecting a
    teleport, death recovery, or stale coordinate to the current position.
    """

    def __init__(
        self,
        *,
        map_name: str,
        sample_spacing_world: float = DEFAULT_SAMPLE_SPACING_WORLD,
        maximum_trail_world: float = DEFAULT_MAXIMUM_TRAIL_WORLD,
        maximum_sample_jump_world: float = 8.0,
    ) -> None:
        if not map_name:
            raise ValueError("retreat trail map is required")
        values = (
            sample_spacing_world,
            maximum_trail_world,
            maximum_sample_jump_world,
        )
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("retreat trail bounds are invalid")
        if maximum_trail_world < sample_spacing_world * 2:
            raise ValueError("retreat trail is too short")
        if maximum_sample_jump_world <= sample_spacing_world:
            raise ValueError("retreat discontinuity bound is invalid")
        self.map_name = map_name
        self.sample_spacing_world = float(sample_spacing_world)
        self.maximum_trail_world = float(maximum_trail_world)
        self.maximum_sample_jump_world = float(maximum_sample_jump_world)
        self._points: deque[NavPoint] = deque()

    def observe(self, point: NavPoint) -> bool:
        if not isinstance(point, NavPoint):
            raise ValueError("retreat trail observation must be a NavPoint")
        if not self._points:
            self._points.append(point)
            return True
        distance = self._points[-1].distance_2d(point)
        if distance > self.maximum_sample_jump_world:
            self._points.clear()
            self._points.append(point)
            return True
        if distance < self.sample_spacing_world:
            return False
        self._points.append(point)
        self._trim()
        return True

    def _trim(self) -> None:
        total = 0.0
        points = tuple(self._points)
        keep_from = 0
        for index in range(len(points) - 1, 0, -1):
            total += points[index].distance_2d(points[index - 1])
            if total > self.maximum_trail_world:
                keep_from = index
                break
        for _ in range(keep_from):
            self._points.popleft()

    def record(self) -> RetreatTrailRecord:
        points = tuple(self._points)
        distance = sum(
            left.distance_2d(right) for left, right in zip(points, points[1:])
        )
        return RetreatTrailRecord(
            map_name=self.map_name,
            points=points,
            sampled_distance_world=distance,
        )

    def reversed_corridor(
        self,
        *,
        current: NavPoint,
        maximum_retreat_world: float = DEFAULT_MAXIMUM_TRAIL_WORLD,
    ) -> NavCorridor:
        if not isfinite(maximum_retreat_world) or not 4.0 <= maximum_retreat_world <= 300.0:
            raise ValueError("maximum retreat distance is invalid")
        candidates = list(reversed(self._points))
        points = [current]
        distance = 0.0
        for candidate in candidates:
            segment = points[-1].distance_2d(candidate)
            if segment < 0.25:
                continue
            if segment > self.maximum_sample_jump_world:
                break
            if distance + segment > maximum_retreat_world:
                break
            points.append(candidate)
            distance += segment
        if len(points) < 3 or distance < 4.0:
            raise ValueError("verified retreat trail is insufficient")
        return NavCorridor(
            map_name=self.map_name,
            adt_x=0,
            adt_y=0,
            start=points[0],
            stop=points[-1],
            points=tuple(points),
            source="fresh_client_visible_reverse_breadcrumbs",
            execution_authority=False,
        )


def corridor_from_retreat_context(
    context: object,
    *,
    current: NavPoint,
    expected_map_name: str,
    maximum_retreat_world: float = DEFAULT_MAXIMUM_TRAIL_WORLD,
) -> NavCorridor:
    """Validate a navigation handoff and recover its reverse breadcrumb path."""

    if not isinstance(context, dict):
        raise ValueError("safe retreat context is missing")
    if (
        context.get("map") != expected_map_name
        or context.get("source") != "fresh_client_visible_positions"
        or context.get("execution_authority") is not False
    ):
        raise ValueError("safe retreat context provenance is invalid")
    raw_points = context.get("points")
    # A complete default trail can contain roughly 201 samples
    # (300 yd / 1.5 yd plus its endpoints).  A lower consumer ceiling
    # contradicted the producer and rejected a legitimate long-leash handoff
    # before combat could even attempt the verified reverse corridor.
    if (
        not isinstance(raw_points, list)
        or not 3 <= len(raw_points) <= MAXIMUM_CONTEXT_BREADCRUMBS
    ):
        raise ValueError("safe retreat breadcrumb count is invalid")
    trail = SafeRetreatTrail(map_name=expected_map_name)
    parsed_points: list[NavPoint] = []
    previous: NavPoint | None = None
    raw_distance_world = 0.0
    for raw in raw_points:
        if (
            not isinstance(raw, list)
            or len(raw) != 3
            or any(type(value) not in {int, float} for value in raw)
        ):
            raise ValueError("safe retreat breadcrumb geometry is invalid")
        point = NavPoint(float(raw[0]), float(raw[1]), float(raw[2]))
        if (
            previous is not None
            and previous.distance_2d(point) > trail.maximum_sample_jump_world
        ):
            raise ValueError("safe retreat breadcrumb continuity is invalid")
        if previous is not None:
            raw_distance_world += previous.distance_2d(point)
        parsed_points.append(point)
        previous = point
    if raw_distance_world > MAXIMUM_CONTEXT_TRAIL_WORLD:
        raise ValueError("safe retreat breadcrumb distance is invalid")
    nearest_index = min(
        range(len(parsed_points)),
        key=lambda index: parsed_points[index].distance_2d(current),
    )
    if (
        parsed_points[nearest_index].distance_2d(current)
        > trail.maximum_sample_jump_world
    ):
        raise ValueError("live pose is detached from safe retreat breadcrumbs")
    # A fail-closed interruption may leave the actor part-way along the already
    # verified reverse trail.  Retain only the chronological prefix ending at
    # the nearest physically observed sample; reversing that prefix continues
    # away from the encounter and cannot replay the section already traversed.
    for point in parsed_points[: nearest_index + 1]:
        trail.observe(point)
    return trail.reversed_corridor(
        current=current,
        maximum_retreat_world=maximum_retreat_world,
    )
