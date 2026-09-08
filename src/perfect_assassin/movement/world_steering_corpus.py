from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, degrees, hypot, pi
from typing import Protocol

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.steering_simulation import SteeringSimulationScenario


ADT_SIZE_WORLD = 533.0 + (1.0 / 3.0)
_LATTICE_FRACTIONS = (0.10, 0.30, 0.50, 0.70, 0.90)
_LOCAL_COURSE_HALF_SPAN = 0.07
_COURSE_FRACTIONS = tuple(
    ((x - _LOCAL_COURSE_HALF_SPAN, y),
     (x + _LOCAL_COURSE_HALF_SPAN, y))
    for y in _LATTICE_FRACTIONS
    for x in _LATTICE_FRACTIONS
) + tuple(
    ((x, y - _LOCAL_COURSE_HALF_SPAN),
     (x, y + _LOCAL_COURSE_HALF_SPAN))
    for x in _LATTICE_FRACTIONS
    for y in _LATTICE_FRACTIONS
)



class CatalogTile(Protocol):
    grid_x: int
    grid_y: int


class CatalogMap(Protocol):
    map_id: int
    internal_name: str
    tiles: tuple[CatalogTile, ...]


@dataclass(frozen=True, slots=True)
class WorldSteeringCourseRequest:
    request_id: str
    map_id: int
    map_name: str
    grid_x: int
    grid_y: int
    start: NavPoint
    stop: NavPoint


@dataclass(frozen=True, slots=True)
class CorridorRisk:
    tier: str
    reasons: tuple[str, ...]
    maximum_turn_degrees: float
    minimum_portal_width_world: float | None
    maximum_slope_degrees: float


def tile_world_bounds(
    grid_x: int,
    grid_y: int,
) -> tuple[float, float, float, float]:
    if not 0 <= grid_x <= 63 or not 0 <= grid_y <= 63:
        raise ValueError("ADT coordinates are outside the client world grid")
    x_low = (31.0 - grid_y) * ADT_SIZE_WORLD
    x_high = (32.0 - grid_y) * ADT_SIZE_WORLD
    y_low = (31.0 - grid_x) * ADT_SIZE_WORLD
    y_high = (32.0 - grid_x) * ADT_SIZE_WORLD
    return x_low, x_high, y_low, y_high


def build_world_steering_course_requests(
    world_map: CatalogMap,
    *,
    courses_per_tile: int = 1,
) -> tuple[WorldSteeringCourseRequest, ...]:
    """Create the same data-derived local probes for every catalog ADT.

    These are query requests, not executable waypoints.  The Detour worker must
    still resolve both endpoints and return a complete corridor before a probe
    can enter the steering corpus.
    """

    if not 1 <= courses_per_tile <= len(_COURSE_FRACTIONS):
        raise ValueError("courses per tile must be between one and fifty")
    requests: list[WorldSteeringCourseRequest] = []
    seen_tiles: set[tuple[int, int]] = set()
    for tile in sorted(world_map.tiles, key=lambda item: (item.grid_x, item.grid_y)):
        identity = (int(tile.grid_x), int(tile.grid_y))
        if identity in seen_tiles:
            raise ValueError("world map has duplicate ADT coordinates")
        seen_tiles.add(identity)
        x_low, x_high, y_low, y_high = tile_world_bounds(*identity)
        for pattern_index, (start_fraction, stop_fraction) in enumerate(
            _COURSE_FRACTIONS[:courses_per_tile],
        ):
            start = NavPoint(
                x_low + (x_high - x_low) * start_fraction[0],
                y_low + (y_high - y_low) * start_fraction[1],
                0.0,
            )
            stop = NavPoint(
                x_low + (x_high - x_low) * stop_fraction[0],
                y_low + (y_high - y_low) * stop_fraction[1],
                0.0,
            )
            requests.append(WorldSteeringCourseRequest(
                request_id=(
                    f"{world_map.internal_name}:"
                    f"{identity[0]:02d}_{identity[1]:02d}:p{pattern_index}"
                ),
                map_id=int(world_map.map_id),
                map_name=str(world_map.internal_name),
                grid_x=identity[0],
                grid_y=identity[1],
                start=start,
                stop=stop,
            ))
    return tuple(requests)


def _guidance_headings(corridor: NavCorridor) -> tuple[float, ...]:
    headings = []
    points = corridor.guidance_points()
    for start, stop in zip(points, points[1:]):
        dx = stop.x - start.x
        dy = stop.y - start.y
        if hypot(dx, dy) >= 0.25:
            headings.append(atan2(dy, dx))
    return tuple(headings)


def _turn_degrees(left: float, right: float) -> float:
    return abs(degrees((right - left + pi) % (2.0 * pi) - pi))


def classify_world_corridor_risk(corridor: NavCorridor) -> CorridorRisk:
    headings = _guidance_headings(corridor)
    maximum_turn = max(
        (_turn_degrees(left, right) for left, right in zip(headings, headings[1:])),
        default=0.0,
    )
    minimum_portal = min(
        (portal.width for portal in corridor.portals),
        default=None,
    )
    maximum_slope = max(
        (polygon.slope_degrees for polygon in corridor.polygons),
        default=0.0,
    )
    reasons: list[str] = []
    extreme = False
    if maximum_turn >= 110.0:
        reasons.append("HAIRPIN_TURN")
        extreme = True
    elif maximum_turn >= 60.0:
        reasons.append("SHARP_TURN")
    if minimum_portal is not None and minimum_portal < 2.5:
        reasons.append("ACTOR_SCALE_PORTAL")
        extreme = True
    elif minimum_portal is not None and minimum_portal < 4.0:
        reasons.append("NARROW_PORTAL")
    if maximum_slope >= 30.0 or corridor.steep_polygons_penalized:
        reasons.append("STEEP_GEOMETRY")
    if corridor.doodad_avoidance_applied or corridor.doodad_polygons_penalized:
        reasons.append("DOODAD_DETOUR")
    if corridor.clearance_inset_count:
        reasons.append("CLEARANCE_INSET")
    awareness = corridor.start_awareness
    if awareness is not None and awareness.environment_class != "OPEN_GROUND":
        reasons.append("CONFINED_OR_TRANSITION_SPACE")
    tier = "EXTREME" if extreme else "RISK" if reasons else "BASE"
    return CorridorRisk(
        tier=tier,
        reasons=tuple(reasons),
        maximum_turn_degrees=maximum_turn,
        minimum_portal_width_world=minimum_portal,
        maximum_slope_degrees=maximum_slope,
    )


def simulation_runs_for_risk(
    risk: CorridorRisk,
    *,
    base_runs: int = 100,
    risk_runs: int = 1_000,
    extreme_runs: int = 10_000,
) -> int:
    if not 100 <= base_runs <= risk_runs <= extreme_runs <= 100_000:
        raise ValueError("simulation escalation counts are invalid")
    return {
        "BASE": base_runs,
        "RISK": risk_runs,
        "EXTREME": extreme_runs,
    }[risk.tier]


def build_world_steering_scenario(
    request: WorldSteeringCourseRequest,
    corridor: NavCorridor,
    *,
    runs: int,
) -> SteeringSimulationScenario:
    if not corridor.complete:
        raise ValueError("partial corridor cannot enter the steering corpus")
    length = sum(
        start.distance_2d(stop)
        for start, stop in zip(corridor.guidance_points(), corridor.guidance_points()[1:])
    )
    if length < 5.0:
        raise ValueError("corridor is too short for steering coverage")
    risk = classify_world_corridor_risk(corridor)
    significant_turns = sum(
        _turn_degrees(left, right) >= 20.0
        for left, right in zip(
            _guidance_headings(corridor), _guidance_headings(corridor)[1:],
        )
    )
    return SteeringSimulationScenario(
        scenario_id=request.request_id,
        corridor=corridor,
        runs=runs,
        maximum_observations=min(20_000, max(1_200, ceil(length / 0.5) * 6)),
        maximum_allowed_cross_track_world=(
            2.0 if risk.minimum_portal_width_world is not None
            and risk.minimum_portal_width_world < 4.0 else 2.5
        ),
        maximum_allowed_pivot_fraction=0.30 if risk.tier != "BASE" else 0.15,
        maximum_allowed_steering_sign_changes=min(
            100, max(4, significant_turns * 2 + 4),
        ),
    )
