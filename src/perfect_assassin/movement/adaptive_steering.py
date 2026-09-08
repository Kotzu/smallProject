from __future__ import annotations

from math import atan2, hypot, pi
from typing import Callable

from .client_navmesh import NavCorridor
from .mppi_steering import (
    AsyncMppiSteeringController,
    MppiDynamicObstacle,
    MppiSteeringController,
)
from .predictive_steering import (
    PredictiveSteeringController,
    SteeringIntent,
    SteeringState,
)


class AdaptiveTrajectorySteeringController(PredictiveSteeringController):
    """Choose a local controller from corridor geometry, never from location.

    Ordinary roads remain on the deterministic geometric follower.  A narrow
    sharp turn is handed to MPPI, where a receding-horizon rollout can preserve
    the turn without inventing a straight chord.  The decision is latched for
    one corridor signature so a live replan cannot make the camera oscillate
    between controllers.
    """

    NARROW_PORTAL_MAX_WORLD = 3.5
    SHARP_TURN_MIN_RAD = 1.35
    TURN_SCAN_WORLD = 12.0
    PORTAL_ASSOCIATION_MAX_WORLD = 6.0

    def __init__(
        self,
        *,
        arrival_radius_world: float = 1.2,
        mppi_factory: Callable[[], AsyncMppiSteeringController] | None = None,
    ) -> None:
        super().__init__(arrival_radius_world=arrival_radius_world)
        self._geometric = PredictiveSteeringController(
            arrival_radius_world=arrival_radius_world,
        )
        self._mppi = (
            mppi_factory()
            if mppi_factory is not None
            else AsyncMppiSteeringController(
                arrival_radius_world=arrival_radius_world,
            )
        )
        self._corridor_signature: tuple[tuple[float, float, float], ...] | None = None
        self._mppi_selected = False
        # ``PredictiveSteeringController`` owns a stationary-pivot latch, but
        # this facade never calls its inherited ``decide`` implementation.
        # Keep the runtime request here until the corridor has selected the
        # child that will actually emit the next input intent.
        self._pending_stationary_pivot = False

    def request_stationary_pivot(self) -> None:
        """Forward a runtime realignment to the controller that owns input.

        Deferring the hand-off until ``decide_with_environment`` is important:
        the initial direction probe can request a pivot before this adaptive
        facade has classified the new corridor.  Forwarding immediately to the
        previously active child either loses the request or leaves a stale
        pivot waiting in the inactive controller.
        """

        self._pending_stationary_pivot = True

    @classmethod
    def needs_mppi(cls, corridor: NavCorridor) -> bool:
        if not corridor.geometry_aware or corridor.minimum_portal_width is None:
            return False
        points = corridor.guidance_points()
        if len(points) < 3:
            return False
        # Portal width or slope alone is not a reason to switch controller.
        # The live v16 Crypt baseline traversed narrow stairs cleanly with the
        # geometric follower; selecting MPPI for every narrow/steep transition
        # later increased cross-track and forward stalls. MPPI is reserved for
        # the combination it demonstrably improves: a sharp turn whose local
        # portal cannot safely accommodate an ordinary running arc.
        travelled = 0.0
        for first, center, last in zip(points, points[1:], points[2:]):
            inbound = atan2(center.y - first.y, center.x - first.x)
            outbound = atan2(last.y - center.y, last.x - center.x)
            turn = abs((outbound - inbound + pi) % (2.0 * pi) - pi)
            local_portal_widths = tuple(
                portal.width
                for portal in corridor.portals
                if hypot(
                    (portal.left.x + portal.right.x) * 0.5 - center.x,
                    (portal.left.y + portal.right.y) * 0.5 - center.y,
                ) <= cls.PORTAL_ASSOCIATION_MAX_WORLD
            )
            if (
                turn >= cls.SHARP_TURN_MIN_RAD
                and local_portal_widths
                and min(local_portal_widths) <= cls.NARROW_PORTAL_MAX_WORLD
            ):
                return True
            travelled += hypot(center.x - first.x, center.y - first.y)
            if travelled >= cls.TURN_SCAN_WORLD:
                break
        return False

    def _select(self, corridor: NavCorridor) -> bool:
        signature = tuple(
            (point.x, point.y, point.z) for point in corridor.guidance_points()
        )
        if signature != self._corridor_signature:
            self._corridor_signature = signature
            self._mppi_selected = self.needs_mppi(corridor)
        return self._mppi_selected

    def decide_with_environment(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        *,
        obstacles: tuple[MppiDynamicObstacle, ...] = (),
        pose_uncertainty_world: float = 0.0,
    ) -> SteeringIntent:
        mppi_selected = self._select(corridor)
        if self._pending_stationary_pivot:
            selected = self._mppi if mppi_selected else self._geometric
            request = getattr(selected, "request_stationary_pivot", None)
            if callable(request):
                request()
            self._pending_stationary_pivot = False
        if not mppi_selected:
            return self._geometric.decide(state, corridor)
        mppi_intent = self._mppi.decide_with_environment(
            state,
            corridor,
            obstacles=obstacles,
            pose_uncertainty_world=pose_uncertainty_world,
        )
        if mppi_intent.reason.startswith("pa_mppi_"):
            return mppi_intent
        # Planner startup, stale plans, and partial frontiers never block the
        # deterministic follower.  Keep the fallback produced by the same
        # MPPI controller, though: it owns the mouse slew/reversal history.
        # Calling a second geometric controller here would create two
        # independent histories and can expose a stale opposite-sign pulse at
        # every planner handoff (the source of the synthetic hairpin drift).
        return mppi_intent

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        return self.decide_with_environment(state, corridor)

    @property
    def mppi_telemetry(self):
        return self._mppi.mppi_telemetry

    def close(self) -> None:
        self._mppi.close()

    def __enter__(self) -> "AdaptiveTrajectorySteeringController":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
