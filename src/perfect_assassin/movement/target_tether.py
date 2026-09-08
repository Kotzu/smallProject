from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, pi, sin

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint


TETHER_STATES = frozenset({
    "IN_MELEE",
    "WAITING_NAVMESH",
    "DIRECT",
    "DETOUR_LEFT",
    "DETOUR_RIGHT",
    "PARTIAL_ADVANCE_DIRECT",
    "PARTIAL_ADVANCE_LEFT",
    "PARTIAL_ADVANCE_RIGHT",
    "PARTIAL_BLOCKED",
})


def _wrap_angle(value: float) -> float:
    while value > pi:
        value -= 2.0 * pi
    while value < -pi:
        value += 2.0 * pi
    return value


@dataclass(frozen=True, slots=True)
class TargetTetherProjection:
    player: NavPoint
    player_heading_rad: float
    target_bearing_error_x_normalized: float
    projected_target: NavPoint
    projected_distance_world: float
    client_in_melee: bool | None

    def __post_init__(self) -> None:
        if (
            not isfinite(self.player_heading_rad)
            or not -pi <= self.player_heading_rad <= 2.0 * pi
        ):
            raise ValueError("tether player heading is invalid")
        if (
            not isfinite(self.target_bearing_error_x_normalized)
            or not -1 <= self.target_bearing_error_x_normalized <= 1
        ):
            raise ValueError("tether target bearing is invalid")
        if (
            not isfinite(self.projected_distance_world)
            or not 0 < self.projected_distance_world <= 20
        ):
            raise ValueError("tether projection distance is invalid")
        if self.client_in_melee is not None and type(self.client_in_melee) is not bool:
            raise ValueError("tether melee witness is invalid")


@dataclass(frozen=True, slots=True)
class TargetTetherIntent:
    state: str
    projected_target: NavPoint
    projected_distance_world: float
    guidance_error_rad: float | None
    guidance_point: NavPoint | None
    corridor_centerline_world: tuple[tuple[float, float], ...]
    direct_distance_world: float
    corridor_distance_world: float | None
    maximum_lateral_detour_world: float | None
    reason: str
    navmesh_polygons_world: tuple[tuple[tuple[float, float], ...], ...] = ()
    corridor_edge_clearance_world: float | None = None
    corridor_edge_safe: bool | None = None

    def __post_init__(self) -> None:
        if self.state not in TETHER_STATES:
            raise ValueError("target tether state is invalid")
        for label, value in (
            ("projected target distance", self.projected_distance_world),
            ("direct tether distance", self.direct_distance_world),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{label} is invalid")
        if self.guidance_error_rad is not None and (
            not isfinite(self.guidance_error_rad)
            or not -pi <= self.guidance_error_rad <= pi
        ):
            raise ValueError("tether guidance error is invalid")
        for value in (self.corridor_distance_world, self.maximum_lateral_detour_world):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError("tether corridor metric is invalid")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("target tether reason is invalid")
        if len(self.navmesh_polygons_world) > 256 or any(
            not 3 <= len(polygon) <= 6
            or any(
                len(point) != 2 or any(not isfinite(value) for value in point)
                for point in polygon
            )
            for polygon in self.navmesh_polygons_world
        ):
            raise ValueError("target tether navmesh geometry is invalid")
        if self.corridor_edge_clearance_world is not None and (
            not isfinite(self.corridor_edge_clearance_world)
            or self.corridor_edge_clearance_world < 0
        ):
            raise ValueError("target tether edge clearance is invalid")
        if self.corridor_edge_safe is not None and type(self.corridor_edge_safe) is not bool:
            raise ValueError("target tether edge safety state is invalid")
        if (
            self.corridor_edge_safe is not None
            and self.corridor_edge_clearance_world is None
        ):
            raise ValueError("target tether edge safety lacks clearance evidence")


class TargetTetherPlanner:
    """Build a short moving navmesh corridor toward a visible selected unit.

    The client exposes exact facing and a CRC-bound screen bearing but no
    portable target world coordinate.  The planner therefore projects only a
    conservative local horizon and replans it as fresh frames arrive.  It
    never presents that projection as an exact mob location.
    """

    HORIZONTAL_HALF_FOV_RAD = pi / 4.0
    OUT_OF_MELEE_HORIZON_WORLD = 8.0
    UNKNOWN_RANGE_HORIZON_WORLD = 6.0
    IN_MELEE_HORIZON_WORLD = 3.5
    DIRECT_EXTRA_RATIO = 1.12
    DIRECT_LATERAL_TOLERANCE_WORLD = 0.75
    PARTIAL_MINIMUM_SAFE_CORRIDOR_WORLD = 1.50
    PARTIAL_MINIMUM_TARGET_PROGRESS_WORLD = 1.00

    def project(
        self,
        *,
        player: NavPoint,
        player_heading_rad: float,
        target_bearing_error_x_normalized: float,
        client_in_melee: bool | None,
    ) -> TargetTetherProjection:
        if (
            not isfinite(player_heading_rad)
            or not isfinite(target_bearing_error_x_normalized)
            or not -1 <= target_bearing_error_x_normalized <= 1
        ):
            raise ValueError("target tether projection input is invalid")
        distance = (
            self.IN_MELEE_HORIZON_WORLD
            if client_in_melee is True
            else self.OUT_OF_MELEE_HORIZON_WORLD
            if client_in_melee is False
            else self.UNKNOWN_RANGE_HORIZON_WORLD
        )
        # Positive screen X is camera-right. In this client/RMB convention a
        # rightward mouse command decreases the world heading angle.
        target_heading = player_heading_rad - (
            target_bearing_error_x_normalized * self.HORIZONTAL_HALF_FOV_RAD
        )
        target = NavPoint(
            player.x + cos(target_heading) * distance,
            player.y + sin(target_heading) * distance,
            player.z,
        )
        return TargetTetherProjection(
            player=player,
            player_heading_rad=player_heading_rad,
            target_bearing_error_x_normalized=target_bearing_error_x_normalized,
            projected_target=target,
            projected_distance_world=distance,
            client_in_melee=client_in_melee,
        )

    def decide(
        self,
        projection: TargetTetherProjection,
        corridor: NavCorridor | None,
    ) -> TargetTetherIntent:
        direct_distance = projection.player.distance_2d(projection.projected_target)
        if projection.client_in_melee is True:
            return TargetTetherIntent(
                state="IN_MELEE",
                projected_target=projection.projected_target,
                projected_distance_world=projection.projected_distance_world,
                guidance_error_rad=0.0,
                guidance_point=projection.projected_target,
                corridor_centerline_world=(
                    (projection.player.x, projection.player.y),
                    (projection.projected_target.x, projection.projected_target.y),
                ),
                direct_distance_world=direct_distance,
                corridor_distance_world=direct_distance,
                maximum_lateral_detour_world=0.0,
                reason="exact_client_melee_range_witness",
            )
        if corridor is None:
            return TargetTetherIntent(
                state="WAITING_NAVMESH",
                projected_target=projection.projected_target,
                projected_distance_world=projection.projected_distance_world,
                guidance_error_rad=None,
                guidance_point=None,
                corridor_centerline_world=(
                    (projection.player.x, projection.player.y),
                    (projection.projected_target.x, projection.projected_target.y),
                ),
                direct_distance_world=direct_distance,
                corridor_distance_world=None,
                maximum_lateral_detour_world=None,
                reason="local_target_corridor_not_ready",
            )

        points = corridor.guidance_points()
        centerline = tuple((point.x, point.y) for point in points)
        if not centerline:
            centerline = ((projection.player.x, projection.player.y),)
        corridor_distance = sum(
            points[index - 1].distance_2d(points[index])
            for index in range(1, len(points))
        )
        lateral = max(
            (
                self._distance_to_segment(
                    point,
                    projection.player,
                    projection.projected_target,
                )
                for point in points
            ),
            default=0.0,
        )
        guidance = next(
            (
                point for point in points
                if point.distance_2d(projection.player) >= 0.75
            ),
            corridor.stop,
        )
        guidance_error = _wrap_angle(
            atan2(
                guidance.y - projection.player.y,
                guidance.x - projection.player.x,
            ) - projection.player_heading_rad
        )
        endpoint_error = corridor.stop.distance_2d(projection.projected_target)
        portal_clearance = corridor.portal_lateral_clearance_at(
            projection.player,
        )
        if not corridor.complete:
            target_progress = direct_distance - endpoint_error
            safe_partial = (
                len(points) >= 2
                and corridor_distance >= self.PARTIAL_MINIMUM_SAFE_CORRIDOR_WORLD
                and target_progress >= self.PARTIAL_MINIMUM_TARGET_PROGRESS_WORLD
                and corridor.doodad_unresolved_segment_count == 0
            )
            if safe_partial:
                if (
                    abs(guidance_error) <= 0.12
                    and lateral <= self.DIRECT_LATERAL_TOLERANCE_WORLD
                ):
                    state = "PARTIAL_ADVANCE_DIRECT"
                elif guidance_error > 0:
                    state = "PARTIAL_ADVANCE_LEFT"
                else:
                    state = "PARTIAL_ADVANCE_RIGHT"
                reason = "safe_partial_navmesh_horizon_requires_replan"
            else:
                state = "PARTIAL_BLOCKED"
                reason = "partial_navmesh_horizon_has_no_safe_progress"
        elif endpoint_error > 1.0:
            state = "PARTIAL_BLOCKED"
            reason = "navmesh_cannot_reach_local_target_projection"
        else:
            detour = (
                corridor.doodad_avoidance_applied
                or corridor.observed_blocker_polygons_excluded > 0
                or lateral > self.DIRECT_LATERAL_TOLERANCE_WORLD
                or corridor_distance > direct_distance * self.DIRECT_EXTRA_RATIO
            )
            if detour:
                direct_x = projection.projected_target.x - projection.player.x
                direct_y = projection.projected_target.y - projection.player.y
                guide_x = guidance.x - projection.player.x
                guide_y = guidance.y - projection.player.y
                cross = direct_x * guide_y - direct_y * guide_x
                state = "DETOUR_LEFT" if cross >= 0 else "DETOUR_RIGHT"
                reason = "navmesh_detour_around_obstacle"
            else:
                state = "DIRECT"
                reason = "navmesh_confirms_direct_target_tether"
        return TargetTetherIntent(
            state=state,
            projected_target=projection.projected_target,
            projected_distance_world=projection.projected_distance_world,
            guidance_error_rad=guidance_error,
            guidance_point=guidance,
            corridor_centerline_world=centerline,
            direct_distance_world=direct_distance,
            corridor_distance_world=corridor_distance,
            maximum_lateral_detour_world=lateral,
            reason=reason,
            navmesh_polygons_world=tuple(
                tuple((vertex.x, vertex.y) for vertex in polygon.vertices)
                for polygon in corridor.polygons
            ),
            corridor_edge_clearance_world=(
                None
                if portal_clearance is None
                else portal_clearance.minimum_edge_clearance_yards
            ),
            corridor_edge_safe=(
                None
                if portal_clearance is None
                else portal_clearance.actor_capsule_inside_safe_envelope
            ),
        )

    @staticmethod
    def _distance_to_segment(point: NavPoint, start: NavPoint, stop: NavPoint) -> float:
        dx, dy = stop.x - start.x, stop.y - start.y
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-9:
            return point.distance_2d(start)
        fraction = max(
            0.0,
            min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_sq),
        )
        return hypot(
            point.x - (start.x + fraction * dx),
            point.y - (start.y + fraction * dy),
        )
