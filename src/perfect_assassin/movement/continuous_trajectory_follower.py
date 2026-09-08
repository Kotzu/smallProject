from __future__ import annotations

from math import atan2, hypot, isfinite, sin

from .client_navmesh import NavCorridor
from .predictive_steering import (
    PredictiveSteeringController,
    SteeringIntent,
    SteeringState,
)


class ContinuousTrajectoryFollower(PredictiveSteeringController):
    """Curvature controller for a pre-smoothed, navmesh-validated trajectory.

    Unlike the legacy segment follower, this controller does not chase the
    next vertex or stop at ordinary corners. Pure-pursuit curvature converts a
    point several yards ahead into one continuous RMB angular velocity while W
    remains held. Only a genuine near-reversal may enter a single latched
    alignment phase.
    """

    MIN_LOOKAHEAD_WORLD = 4.5
    TIGHT_TURN_LOOKAHEAD_WORLD = 1.85
    MEDIUM_TURN_LOOKAHEAD_WORLD = 2.75
    MAX_LOOKAHEAD_WORLD = 8.0
    # The 0.85 s carrot crossed the outside of dense, navmesh-valid WMO exit
    # arcs under rare initial-pose perturbations. 0.70 s preserves open-road
    # continuity while keeping the actor capsule inside those narrow curves.
    LOOKAHEAD_TIME_S = 0.70
    NEAR_REVERSAL_RAD = 2.55
    REVERSAL_RESUME_RAD = 0.65
    MAX_CROSS_TRACK_REPLAN_WORLD = 6.0
    MAX_MOUSE_DELTA = 9
    MOUSE_SLEW_PER_TICK = 4
    # The legacy minimap heading is quantised by only a few pixels.  A single
    # sample can therefore ask for a 1-3 px correction on the opposite side
    # of the path even though the physical camera has not finished consuming
    # the prior pulse.  Require a persistent small reversal before changing
    # direction; a real corner (larger error or command) still passes at once.
    SMALL_REVERSAL_MAX_MOUSE_DELTA = 4
    SMALL_REVERSAL_MAX_ERROR_RAD = 0.40
    SMALL_REVERSAL_MAX_CROSS_TRACK_WORLD = 1.50
    # A reversal accepted in six 50 ms control ticks still falls inside the
    # 0.50 s window used by the filmed quality gate. Eleven ticks prove that
    # the correction is persistent rather than delayed camera momentum.
    SMALL_REVERSAL_CONFIRMATION_TICKS = 11
    # When the corridor already shows a meaningful bend, do not keep building
    # yaw momentum in the opposite direction merely to centre the current
    # near carrot. First slew the camera command toward neutral; the regular
    # pure-pursuit command then enters the bend without a late hard reversal.
    UPCOMING_BEND_BRAKE_MIN_RAD = 0.55
    UPCOMING_BEND_BRAKE_MAX_ERROR_RAD = 0.60
    UPCOMING_BEND_BRAKE_MAX_CROSS_TRACK_WORLD = 1.50
    # A narrow client-geometry corridor must start with the actor facing its
    # first tangent.  Moving while the minimap heading is still settling can
    # send W into the wall even when Detour's corridor is valid.  This is a
    # geometry-derived guard: it applies to doodad-inset paths and other
    # confined starts, never to a named location or a hardcoded waypoint.
    PRECISION_INITIAL_ALIGNMENT_ERROR_RAD = 0.50
    # Stop the stationary phase before the delayed/quantised minimap heading
    # can carry a still-fast RMB command across the desired tangent. At 0.32
    # rad the actor is inside the corridor's 0.35-yard safety inset for the
    # next control frame; pure pursuit can finish the turn while W is held.
    # This removes the visible turn-one-way/turn-back start without weakening
    # the initial wall guard or naming a particular WMO/staircase.
    PRECISION_INITIAL_ALIGNMENT_RESUME_RAD = 0.32

    def __init__(self, *, arrival_radius_world: float = 1.2) -> None:
        super().__init__(arrival_radius_world=arrival_radius_world)
        self._trajectory_signature: tuple[tuple[float, float, float], ...] | None = None
        self._trajectory_progress_world = 0.0
        self._trajectory_previous_mouse_delta = 0
        self._trajectory_last_nonzero_mouse_delta = 0
        self._trajectory_pending_reversal_sign = 0
        self._trajectory_pending_reversal_ticks = 0
        self._trajectory_reversal_latched = False
        self._trajectory_precision_alignment_latched = False
        self._trajectory_precision_alignment_completed = False

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        if (
            any(not isfinite(value) for value in (state.x, state.y, state.speed_world_per_s))
            or state.speed_world_per_s <= 0.0
            or (state.heading_rad is not None and not isfinite(state.heading_rad))
        ):
            raise ValueError("trajectory steering state is invalid")
        points = corridor.guidance_points()
        signature = tuple((point.x, point.y, point.z) for point in points)
        if signature != self._trajectory_signature:
            self._trajectory_signature = signature
            self._trajectory_progress_world = 0.0
            # A rolling corridor changes the geometric plan, not the physical
            # camera.  Keep the actuator slew and small-reversal history across
            # that hand-off; resetting them here allowed every fresh preview
            # to emit an immediate opposite 1-4 px pulse.  A genuinely large
            # new turn is still accepted because the reversal filter is
            # bounded by heading error and cross-track distance.
            self._trajectory_reversal_latched = False
            self._trajectory_precision_alignment_latched = False
            self._trajectory_precision_alignment_completed = False

        remaining = hypot(corridor.stop.x - state.x, corridor.stop.y - state.y)
        if remaining <= self._arrival_radius_world:
            return SteeringIntent(
                "ARRIVED", 0, 0, None, "continuous_trajectory_goal_reached",
                self._trajectory_progress_world, 0.0, corridor.stop.z,
            )

        progress, cross_track, projected_z, _signed, _tangent = self._project_progress(
            state, corridor,
        )
        self._trajectory_progress_world = max(self._trajectory_progress_world, progress)
        # Reuse the production topology-windowed projector, including its
        # bounded advance rule. Keep its inherited anchor synchronized with
        # this follower's public trajectory progress.
        self._progress_world = self._trajectory_progress_world
        self._projected_z_world = projected_z
        if cross_track >= self.MAX_CROSS_TRACK_REPLAN_WORLD or state.no_progress_s >= 1.8:
            self._trajectory_previous_mouse_delta = 0
            return SteeringIntent(
                "REPLAN", 0, 0, None, "continuous_trajectory_diverged",
                self._trajectory_progress_world, cross_track, projected_z,
            )

        lookahead_distance = max(
            self.MIN_LOOKAHEAD_WORLD,
            min(self.MAX_LOOKAHEAD_WORLD, state.speed_world_per_s * self.LOOKAHEAD_TIME_S),
        )
        upcoming_bend_signed = 0.0
        # A long road lookahead is stable, but using it unchanged inside a
        # crypt or S-gate cuts corners. Measure the trajectory bend ahead and
        # shorten the carrot before reaching it, while W stays continuously
        # held. This is geometry-driven and contains no location knowledge.
        if corridor.geometry_aware:
            path_here = self._point_at_progress(
                corridor,
                self._trajectory_progress_world,
            )
            path_near = self._point_at_progress(
                corridor,
                self._trajectory_progress_world + self.TIGHT_TURN_LOOKAHEAD_WORLD,
            )
            path_far = self._point_at_progress(
                corridor,
                self._trajectory_progress_world + lookahead_distance,
            )
            near_span = hypot(path_near.x - path_here.x, path_near.y - path_here.y)
            far_span = hypot(path_far.x - path_near.x, path_far.y - path_near.y)
            if near_span > 0.20 and far_span > 0.20:
                near_heading = atan2(
                    path_near.y - path_here.y,
                    path_near.x - path_here.x,
                )
                far_heading = atan2(
                    path_far.y - path_near.y,
                    path_far.x - path_near.x,
                )
                upcoming_bend_signed = self._wrap(far_heading - near_heading)
                upcoming_bend = abs(upcoming_bend_signed)
                if upcoming_bend >= 0.75:
                    lookahead_distance = self.TIGHT_TURN_LOOKAHEAD_WORLD
                elif upcoming_bend >= 0.32:
                    lookahead_distance = self.MEDIUM_TURN_LOOKAHEAD_WORLD
        lookahead = self._point_at_progress(
            corridor,
            self._trajectory_progress_world + lookahead_distance,
        )
        if state.heading_rad is None:
            return SteeringIntent(
                "CALIBRATE_HEADING", 300, 0, lookahead,
                "continuous_trajectory_initial_heading_calibration",
                self._trajectory_progress_world, cross_track, projected_z,
            )

        target_bearing = atan2(lookahead.y - state.y, lookahead.x - state.x)
        alpha = self._wrap(target_bearing - state.heading_rad)
        forced_stationary_pivot = self._forced_stationary_pivot
        if forced_stationary_pivot and abs(alpha) <= self.PIVOT_RESUME_THRESHOLD_RAD:
            self._forced_stationary_pivot = False
            forced_stationary_pivot = False
        precision_start = corridor.doodad_avoidance_applied or (
            corridor.start_awareness is not None
            and (
                "wmo" in corridor.start_awareness.physical_surfaces
                or not corridor.start_awareness.overhead_clear
            )
        )
        if precision_start:
            if self._trajectory_precision_alignment_latched:
                if abs(alpha) <= self.PRECISION_INITIAL_ALIGNMENT_RESUME_RAD:
                    self._trajectory_precision_alignment_latched = False
                    self._trajectory_precision_alignment_completed = True
            elif (
                not self._trajectory_precision_alignment_completed
                and self._trajectory_progress_world <= 0.25
                and abs(alpha) >= self.PRECISION_INITIAL_ALIGNMENT_ERROR_RAD
            ):
                self._trajectory_precision_alignment_latched = True
        if self._trajectory_reversal_latched:
            if abs(alpha) <= self.REVERSAL_RESUME_RAD:
                self._trajectory_reversal_latched = False
        elif abs(alpha) >= self.NEAR_REVERSAL_RAD:
            self._trajectory_reversal_latched = True

        chord = max(0.5, hypot(lookahead.x - state.x, lookahead.y - state.y))
        curvature = 2.0 * sin(alpha) / chord
        pivot = (
            self._trajectory_reversal_latched
            or self._trajectory_precision_alignment_latched
            or forced_stationary_pivot
        )
        yaw_rate = (
            alpha * self.PIVOT_YAW_GAIN_PER_S
            if pivot
            else state.speed_world_per_s * curvature
        )
        requested = round(
            -yaw_rate
            / (
                self.MOUSE_YAW_RAD_PER_PIXEL
                * self.MOUSE_COMMAND_VELOCITY_SCALE_HZ
            )
        )
        requested = max(-self.MAX_MOUSE_DELTA, min(self.MAX_MOUSE_DELTA, requested))
        upcoming_bend_brake = (
            abs(upcoming_bend_signed) >= self.UPCOMING_BEND_BRAKE_MIN_RAD
            and requested * upcoming_bend_signed > 0
            and abs(alpha) <= self.UPCOMING_BEND_BRAKE_MAX_ERROR_RAD
            and cross_track <= self.UPCOMING_BEND_BRAKE_MAX_CROSS_TRACK_WORLD
            and not pivot
        )
        if upcoming_bend_brake:
            requested = 0
        mouse_delta = max(
            self._trajectory_previous_mouse_delta - self.MOUSE_SLEW_PER_TICK,
            min(
                self._trajectory_previous_mouse_delta + self.MOUSE_SLEW_PER_TICK,
                requested,
            ),
        )
        if pivot:
            self._trajectory_last_nonzero_mouse_delta = 0
            self._trajectory_pending_reversal_sign = 0
            self._trajectory_pending_reversal_ticks = 0
        elif mouse_delta:
            prior = self._trajectory_last_nonzero_mouse_delta
            opposite_small_reversal = (
                prior * mouse_delta < 0
                and abs(prior) <= self.SMALL_REVERSAL_MAX_MOUSE_DELTA
                and abs(mouse_delta) <= self.SMALL_REVERSAL_MAX_MOUSE_DELTA
                and abs(alpha) <= self.SMALL_REVERSAL_MAX_ERROR_RAD
                and cross_track <= self.SMALL_REVERSAL_MAX_CROSS_TRACK_WORLD
            )
            if opposite_small_reversal:
                sign = 1 if mouse_delta > 0 else -1
                if sign == self._trajectory_pending_reversal_sign:
                    self._trajectory_pending_reversal_ticks += 1
                else:
                    self._trajectory_pending_reversal_sign = sign
                    self._trajectory_pending_reversal_ticks = 1
                if (
                    self._trajectory_pending_reversal_ticks
                    < self.SMALL_REVERSAL_CONFIRMATION_TICKS
                ):
                    mouse_delta = 0
                else:
                    self._trajectory_last_nonzero_mouse_delta = mouse_delta
                    self._trajectory_pending_reversal_sign = 0
                    self._trajectory_pending_reversal_ticks = 0
            else:
                self._trajectory_last_nonzero_mouse_delta = mouse_delta
                self._trajectory_pending_reversal_sign = 0
                self._trajectory_pending_reversal_ticks = 0
        self._trajectory_previous_mouse_delta = mouse_delta
        return SteeringIntent(
            "PIVOT" if pivot else "FOLLOW",
            0 if pivot else self.CONTROL_TICK_MS,
            mouse_delta,
            lookahead,
            (
                "continuous_precision_initial_alignment"
                if self._trajectory_precision_alignment_latched
                else (
                    "continuous_pure_pursuit_upcoming_bend_brake"
                    if upcoming_bend_brake
                    else "continuous_pure_pursuit_curvature"
                )
            ),
            self._trajectory_progress_world,
            cross_track,
            projected_z,
            strafe=None,
        )
