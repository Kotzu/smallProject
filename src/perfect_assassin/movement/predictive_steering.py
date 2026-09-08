from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import atan2, hypot, isfinite, pi, sqrt

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint


@dataclass(frozen=True, slots=True)
class SteeringState:
    x: float
    y: float
    heading_rad: float | None
    speed_world_per_s: float
    no_progress_s: float = 0.0


@dataclass(frozen=True, slots=True)
class SteeringIntent:
    state: str
    forward_hold_ms: int
    mouse_delta_x: int
    lookahead: NavPoint | None
    reason: str
    progress_world: float = 0.0
    cross_track_error_world: float = 0.0
    projected_z_world: float | None = None
    strafe: str | None = None


@dataclass(slots=True)
class CorridorProgressGate:
    """Accept only meaningful progress along a corridor or toward its goal.

    Raw displacement is deliberately excluded: collision sliding and small
    left/right oscillations move the coordinate HUD without advancing the
    journey.  The gate retains anchors until either path progress or remaining
    goal distance improves by a player-sized amount.
    """

    minimum_progress_world: float = 0.50
    _path_anchor_world: float | None = None
    _goal_distance_anchor_world: float | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.minimum_progress_world) or not 0.20 <= self.minimum_progress_world <= 2.0:
            raise ValueError("meaningful progress threshold is invalid")

    def reset(self, *, path_progress_world: float, goal_distance_world: float) -> None:
        if any(
            not isfinite(value) or value < 0
            for value in (path_progress_world, goal_distance_world)
        ):
            raise ValueError("progress gate reset is invalid")
        self._path_anchor_world = float(path_progress_world)
        self._goal_distance_anchor_world = float(goal_distance_world)

    def observe(self, *, path_progress_world: float, goal_distance_world: float) -> bool:
        if any(
            not isfinite(value) or value < 0
            for value in (path_progress_world, goal_distance_world)
        ):
            raise ValueError("progress gate observation is invalid")
        if self._path_anchor_world is None or self._goal_distance_anchor_world is None:
            self.reset(
                path_progress_world=path_progress_world,
                goal_distance_world=goal_distance_world,
            )
            return True
        path_advance = path_progress_world - self._path_anchor_world
        goal_advance = self._goal_distance_anchor_world - goal_distance_world
        if max(path_advance, goal_advance) < self.minimum_progress_world:
            return False
        self.reset(
            path_progress_world=path_progress_world,
            goal_distance_world=goal_distance_world,
        )
        return True


def observed_motion_is_continuous(
    *,
    displacement_world: float,
    observation_interval_s: float,
    forward_requested: bool,
    minimum_displacement_world: float = 0.08,
    long_interval_s: float = 0.30,
    minimum_long_interval_speed_world_per_s: float = 1.50,
) -> bool:
    """Require physical movement before accepting projected progress.

    A corridor projection can advance while the client is stationary (for
    example, during an observer/capture stall at a bridge).  This helper is
    deliberately independent of route geometry: it only decides whether the
    latest observed pose contains enough physical motion to reset the
    no-progress clock.  Short observations use the existing player-sized
    displacement threshold; a long observation gap additionally requires a
    minimum average speed so a visible pause cannot be hidden by projection.
    """

    if not isfinite(displacement_world) or displacement_world < 0:
        raise ValueError("observed displacement is invalid")
    if not isfinite(observation_interval_s) or observation_interval_s <= 0:
        raise ValueError("observation interval is invalid")
    if not isfinite(minimum_displacement_world) or not 0 < minimum_displacement_world <= 2.0:
        raise ValueError("minimum displacement threshold is invalid")
    if not isfinite(long_interval_s) or not 0 < long_interval_s <= 5.0:
        raise ValueError("long observation interval threshold is invalid")
    if (
        not isfinite(minimum_long_interval_speed_world_per_s)
        or not 0 < minimum_long_interval_speed_world_per_s <= 12.0
    ):
        raise ValueError("minimum long-interval speed threshold is invalid")
    if not forward_requested:
        return True
    if displacement_world < minimum_displacement_world:
        return False
    if observation_interval_s <= long_interval_s:
        return True
    return displacement_world / observation_interval_s >= minimum_long_interval_speed_world_per_s


@dataclass(frozen=True, slots=True)
class TrajectoryLoopEvidence:
    path_length_world: float
    revisit_distance_world: float
    goal_progress_world: float
    accumulated_turn_rad: float


@dataclass(frozen=True, slots=True)
class _TrajectorySample:
    x: float
    y: float
    goal_distance_world: float
    cumulative_path_world: float
    cumulative_turn_rad: float
    segment_heading_rad: float | None


class TrajectoryLoopGuard:
    """Detect an unproductive orbit from the observed path, not map names.

    A normal bend or hairpin can return close to an older XY position, so a
    revisit alone is not enough.  The actor must also have travelled a long
    arc, accumulated substantial heading change, and made little progress
    toward the active local goal.  The bounded trail is reset whenever a new
    navmesh corridor becomes authoritative.
    """

    MINIMUM_SAMPLE_DISPLACEMENT_WORLD = 0.20
    REVISIT_RADIUS_WORLD = 2.50
    MINIMUM_LOOP_PATH_WORLD = 18.0
    MINIMUM_ACCUMULATED_TURN_RAD = 1.50 * pi
    MAXIMUM_GOAL_PROGRESS_WORLD = 3.0
    HISTORY_PATH_WORLD = 70.0
    MAXIMUM_SAMPLES = 384

    def __init__(self) -> None:
        self._samples: deque[_TrajectorySample] = deque()
        self._cumulative_path_world = 0.0
        self._cumulative_turn_rad = 0.0

    def reset(self) -> None:
        self._samples.clear()
        self._cumulative_path_world = 0.0
        self._cumulative_turn_rad = 0.0

    def observe(
        self, *, x: float, y: float, goal_distance_world: float,
    ) -> TrajectoryLoopEvidence | None:
        if any(
            not isfinite(value) for value in (x, y, goal_distance_world)
        ) or goal_distance_world < 0:
            raise ValueError("trajectory loop observation is invalid")
        if not self._samples:
            self._samples.append(_TrajectorySample(
                float(x), float(y), float(goal_distance_world), 0.0, 0.0, None,
            ))
            return None

        previous = self._samples[-1]
        displacement = hypot(x - previous.x, y - previous.y)
        if displacement < self.MINIMUM_SAMPLE_DISPLACEMENT_WORLD:
            return None
        segment_heading = atan2(y - previous.y, x - previous.x)
        self._cumulative_path_world += displacement
        if previous.segment_heading_rad is not None:
            self._cumulative_turn_rad += abs(
                PredictiveSteeringController._wrap(
                    segment_heading - previous.segment_heading_rad,
                )
            )
        current = _TrajectorySample(
            float(x), float(y), float(goal_distance_world),
            self._cumulative_path_world, self._cumulative_turn_rad,
            segment_heading,
        )

        evidence: TrajectoryLoopEvidence | None = None
        for older in self._samples:
            path_length = (
                current.cumulative_path_world - older.cumulative_path_world
            )
            if path_length < self.MINIMUM_LOOP_PATH_WORLD:
                continue
            revisit_distance = hypot(current.x - older.x, current.y - older.y)
            if revisit_distance > self.REVISIT_RADIUS_WORLD:
                continue
            accumulated_turn = (
                current.cumulative_turn_rad - older.cumulative_turn_rad
            )
            goal_progress = (
                older.goal_distance_world - current.goal_distance_world
            )
            if (
                accumulated_turn >= self.MINIMUM_ACCUMULATED_TURN_RAD
                and goal_progress <= self.MAXIMUM_GOAL_PROGRESS_WORLD
            ):
                evidence = TrajectoryLoopEvidence(
                    path_length_world=path_length,
                    revisit_distance_world=revisit_distance,
                    goal_progress_world=goal_progress,
                    accumulated_turn_rad=accumulated_turn,
                )
                break

        self._samples.append(current)
        while (
            len(self._samples) > self.MAXIMUM_SAMPLES
            or self._cumulative_path_world
            - self._samples[0].cumulative_path_world
            > self.HISTORY_PATH_WORLD
        ):
            self._samples.popleft()
        return evidence


class PredictiveSteeringController:
    """Closed-loop path-corridor follower with travel-time look-ahead.

    The old controller selected 650-950 ms open-loop strides.  This controller
    emits one 50 ms control tick, projects the player onto the complete polyline
    and advances monotonically through the corridor.  The next observation,
    rather than dead reckoning, closes the loop.
    """

    # Controlled TBC 2.4.3 replay calibration, measured in both directions.
    # The former 0.0075 estimate requested only about one third of the physical
    # turn needed and made every pivot visibly crawl.
    MOUSE_YAW_RAD_PER_PIXEL = 0.0026
    MOUSE_COMMAND_VELOCITY_SCALE_HZ = 80.0
    FOLLOW_YAW_GAIN_PER_S = 3.4
    PIVOT_YAW_GAIN_PER_S = 3.4
    FOLLOW_MAX_MOUSE_DELTA = 9
    FOLLOW_HEADING_DEADBAND_RAD = 0.025
    # A one-pixel counter-pulse immediately after another small pulse is below
    # the measured TBC camera quantisation.  It is handled as reversal
    # hysteresis after slew (the first small correction is still preserved for
    # momentum calibration and rolling-corridor handoffs).
    # A bounded live road trace showed that heading quantisation can alternate
    # 1-3 pixel velocity requests even on ordinary bends, not only on a
    # mathematically straight local segment.  Suppress an opposite command
    # only while both sides remain small, the stabilized geometric bearing is
    # already inside the ordinary recenter threshold, and the actor is in the
    # geometry-derived recovery envelope.  A real bend, corridor departure or
    # pivot therefore remains authoritative without a map-specific rule.
    FOLLOW_REVERSAL_HYSTERESIS_MAX_DELTA = 3
    FOLLOW_REVERSAL_HYSTERESIS_MAX_PRIOR_DELTA = 6
    FOLLOW_REVERSAL_HYSTERESIS_MAX_ERROR_RAD = 0.40
    STRAIGHT_REVERSAL_HYSTERESIS_MAX_PRIOR_DELTA = 3
    # Live client quantisation clusters settled straight-road reversals around
    # 0.20-0.21 rad.  Keep that one-pixel boundary inside the neutral Schmitt
    # band; a quarter radian is still well below the ordinary recenter gate and
    # the rule never applies to a larger command.
    STRAIGHT_REVERSAL_HYSTERESIS_MAX_ERROR_RAD = 0.25
    # Once a small correction changes direction, let the physical camera
    # consume that pulse before accepting another small counter-pulse.  This
    # is an actuator settling window, not route smoothing: a real error above
    # the ordinary recenter threshold remains immediately authoritative.
    # Live heading observations arrive around 25 Hz. Eight non-zero commands
    # allowed the quantised servo to accept a second direction change after
    # only 0.3-0.4 s around an obstacle S-curve. Sixteen command observations
    # cover the 0.5 s balance window while still yielding immediately to a
    # genuine error outside the recenter envelope below.
    FOLLOW_REVERSAL_SETTLE_TICKS = 16
    FOLLOW_REVERSAL_SETTLE_MAX_ERROR_RAD = 0.40
    PIVOT_MAX_MOUSE_DELTA = 11
    # A running player naturally carves moderate corners, but the controlled
    # road replay proved that allowing forward motion at 60-80 degrees crosses
    # the corridor and creates a left/right sawtooth.  Finish large corrections
    # in place, then carve the remaining sub-45-degree heading error in motion.
    PIVOT_THRESHOLD_RAD = 0.78
    # When already displaced by roughly one player radius, a somewhat broader
    # arc is less robotic than stop/start steering and still converges before
    # the hard-recenter boundary takes over.
    OFF_CORRIDOR_PIVOT_THRESHOLD_RAD = 1.05
    # Target-side smoothing must not hide a genuinely large bearing change.
    # The road replay captured several frames where the filtered camera error
    # was small enough to keep W held while the live pursuit point had moved
    # 70-160 degrees away.  One degree beyond 60 is treated as a deliberate
    # stationary correction; smaller road bends are still carved in motion.
    # Outdoors a player keeps running and steers with RMB through ordinary
    # bends, including a broad 60-120 degree correction.  Only a near-reversal
    # is stationary; confined geometry retains the conservative threshold.
    # Keep 90-degree road bends as running RMB arcs, but a correction beyond
    # roughly 100 degrees is no longer a curve: continuing W at that bearing
    # creates the large tree/signpost orbits seen in controlled replay.
    OPEN_GROUND_PIVOT_THRESHOLD_RAD = 1.75
    PIVOT_RESUME_THRESHOLD_RAD = 0.45
    MOUSE_ACCEL_SLEW_PER_TICK = 1
    MOUSE_BRAKE_SLEW_PER_TICK = 3
    CURVE_MOUSE_ACCEL_SLEW_PER_TICK = 3
    CURVE_MOUSE_BRAKE_SLEW_PER_TICK = 6
    PROJECTION_BACKTRACK_WORLD = 1.25
    PROJECTION_ADVANCE_TIME_S = 0.40
    MIN_PROJECTION_ADVANCE_WORLD = 1.75
    MAX_PROJECTION_ADVANCE_WORLD = 4.0
    # A closed-loop observation can arrive just after a geometry-proven sharp
    # corner while the monotonic projection window still ends on the inbound
    # strip.  When the observed facing already agrees with the outbound
    # tangent, allow the existing four-yard topology window to reach the
    # locally associated post-corner strip.  This is not a route hint: the
    # candidate still has to win the nearest-segment projection and remains
    # bounded by the same maximum advance used for overlapping floors.
    PROJECTION_CORNER_MAX_HEADING_ERROR_RAD = 0.85
    PROJECTION_CORNER_MAX_DISTANCE_WORLD = 4.0
    CORNER_SAMPLE_WORLD = 1.25
    CORNER_SCAN_STEP_WORLD = 0.50
    CORNER_THRESHOLD_RAD = 0.60
    # Object-avoidance detours are short capsule-clearance manoeuvres.  Their
    # bends can be shallower than a normal architectural corner yet still be
    # safety-critical, so the pursuit carrot must not look through their apex.
    DOODAD_CORNER_THRESHOLD_RAD = 0.30
    CURVE_PREVIEW_MAX_WORLD = 6.0
    CURVE_PREVIEW_CAPSULE_AND_MARGIN_WORLD = 1.12
    # A funnel corner belongs to the portal geometry nearest that corner, not
    # to the narrowest portal anywhere in the rolling corridor.  A remote
    # sliver previously disabled anticipation for an otherwise wide turn.
    CURVE_PORTAL_ASSOCIATION_MAX_WORLD = 6.0
    # For a right-angle bend the rounded center path can use both adjoining
    # corridor strips.  Twice the free half-width is a conservative fillet
    # lead distance and remains bounded by the actual local portal clearance.
    CURVE_PREVIEW_FREE_HALF_WIDTH_MULTIPLIER = 1.8
    MINIMUM_CURVE_FREE_HALF_WIDTH_WORLD = 0.50
    # Once a sharp corner has consumed the available portal clearance, the
    # controller must keep the outbound tangent authoritative while crossing
    # the apex.  A forward-only corner scan naturally loses the corner at that
    # exact moment; without this short geometric commitment, open-ground mode
    # resumes W while the actor can still be facing across the passage.
    NARROW_CORNER_COMMIT_BEFORE_WORLD = 0.85
    NARROW_CORNER_RELEASE_AFTER_WORLD = 2.00
    # A one-yard lateral displacement on an outdoor road is ordinary steering
    # error, not loss of the corridor.  The former 0.35/0.85 ramp collapsed a
    # six-yard pursuit horizon to 0.65 yd, putting the carrot beside or behind
    # the actor and creating the observed left/right sawtooth.  Pure pursuit
    # remains authoritative through normal road drift; the shortened horizon
    # is reserved for a real multi-yard departure.
    OFF_CORRIDOR_RECOVERY_START_WORLD = 1.25
    OFF_CORRIDOR_THRESHOLD_WORLD = 3.0
    # Once the player capsule has genuinely departed a narrow corridor, a
    # carrot several yards ahead can be almost parallel to the corridor.  The
    # apparent heading is then correct while the character continues alongside
    # a wall or stair edge.  Aim just beyond the projected centreline instead.
    OFF_CORRIDOR_REENTRY_LOOKAHEAD_WORLD = 3.0
    RECENTER_HEADING_THRESHOLD_RAD = 0.40
    OFF_CORRIDOR_HARD_RECENTER_WORLD = 3.5
    # Controlled crypt replay showed that a 0.65 yd carrot is shorter than one
    # observed movement stride.  Pure pursuit then crosses the centreline,
    # swaps the carrot behind the actor and repeats as a visibly robotic
    # zigzag.  Keep the WMO correction inside a player-safe corridor, but far
    # enough ahead to converge instead of chasing the nearest center point.
    CONFINED_RECOVERY_START_WORLD = 0.60
    CONFINED_RECOVERY_FULL_WORLD = 0.90
    CONFINED_REENTRY_LOOKAHEAD_WORLD = 1.35
    CONFINED_HARD_RECENTER_WORLD = 2.50
    # A moderate departure from a narrow corridor can still be corrected by
    # carrying W through the turn.  Stopping at the first hard-recenter
    # crossing produced the stationary pivot bursts seen in the live trace,
    # even while the navmesh still had a valid running corridor.  Keep a
    # bounded soft band for running recenter; larger departures still pivot.
    RUNNING_RECENTER_MARGIN_WORLD = 1.0
    RUNNING_RECENTER_MAX_ERROR_RAD = 1.40
    # Recovery distance is a time horizon, not a map constant.  At running
    # speed the old fixed 1.35 yd target was nearly lateral by the time a fresh
    # client observation arrived, demanding another 60-90 degree pivot.  Keep
    # at least 450 ms of travel ahead; _first_sharp_corner_progress still caps
    # this target at real portal/stair corners, so the preview cannot cut a
    # wall merely to obtain a smoother curve.
    MINIMUM_RECOVERY_LOOKAHEAD_TIME_S = 0.45
    RECOVERY_SPEED_HORIZON_BLEND_WORLD = 0.30
    PERSISTENT_OFF_CORRIDOR_REPLAN_TICKS = 12
    # In a confined client-geometry corridor, half a second of forward input
    # without physical progress is enough to prove that the current local
    # alignment is unusable.  Do a clean live-pose replan before the generic
    # 1.8 s collision-learning threshold.  This releases W quickly without
    # inventing a permanent obstacle from a transient heading error.
    CONFINED_FORWARD_STALL_REALIGN_S = 0.60

    # Human players keep RMB held and correct small lateral road drift with
    # W+A/W+D. Rotating the camera toward the centreline for every sub-yard
    # error makes the recording sway even when the route itself is straight.
    CAMERA_STABLE_STRAFE_START_WORLD = 0.65
    CAMERA_STABLE_STRAFE_STOP_WORLD = 0.12
    CAMERA_STABLE_STRAFE_MAX_WORLD = 0.90
    CAMERA_STABLE_STRAFE_MAX_TANGENT_ERROR_RAD = 0.30
    CAMERA_STABLE_STRAFE_MAX_PATH_BEND_RAD = 0.12
    CAMERA_STABLE_STRAFE_PREVIEW_WORLD = 12.0
    CAMERA_STABLE_STRAFE_REVERSAL_CONFIRMATION_TICKS = 5
    CAMERA_STABLE_STRAFE_COOLDOWN_TICKS = 10
    # A WMO doorway can press the capsule sideways before the ordinary
    # open-ground lateral-drift band is reached.  Permit only a short tap in
    # a locally straight, complete WMO corridor; the navmesh remains the
    # authority and this never becomes a blind A/D macro.
    CONFINED_STRAFE_START_WORLD = 0.35
    CONFINED_STRAFE_MAX_WORLD = 1.75
    CONFINED_STRAFE_REVERSAL_CONFIRMATION_TICKS = 2
    CONFINED_STRAFE_COOLDOWN_TICKS = 8

    # Operator system-identification showed W/RMB as the ordinary turning
    # primitive. A/D appeared only occasionally, not once per large heading
    # error. Keep the separate, measured lateral-correction rule below; a
    # normal running arc is carved by mouse yaw alone.
    MINIMUM_RUNNING_CURVE_FREE_HALF_WIDTH_WORLD = 1.25

    # The next look-ahead point moves every observation and also changes at a
    # rolling semantic-corridor hand-off.  Slewing its bearing makes the camera
    # turn as one deliberate arc instead of chasing those small changes frame
    # by frame.  A pivot is allowed to converge faster, but never to snap.
    FOLLOW_DESIRED_HEADING_SLEW_RAD_PER_TICK = 0.10
    CURVE_DESIRED_HEADING_SLEW_RAD_PER_TICK = 0.30
    PIVOT_DESIRED_HEADING_SLEW_RAD_PER_TICK = 0.22

    # RMB turning has visible momentum between coordinate observations: the
    # client keeps consuming the current mouse velocity while the next HUD
    # sample is captured.  A position-only servo therefore brakes after the
    # desired bearing has already been crossed and repeats the same correction
    # from the other side.  Predict a short, bounded heading horizon from the
    # *observed* yaw delta so braking begins before the crossing.  This is a
    # generic actuator model; it contains no map or route knowledge.
    HEADING_DELTA_FILTER_CURRENT_WEIGHT = 0.70
    HEADING_BRAKE_PREVIEW_TICKS = 2.0
    MAX_OBSERVED_HEADING_DELTA_RAD = 0.65
    MAX_HEADING_BRAKE_PREVIEW_RAD = 0.90

    CONTROL_TICK_MS = 50

    def __init__(
        self,
        *,
        lookahead_world: float | None = None,
        lookahead_time_s: float = 0.90,
        min_lookahead_world: float = 5.0,
        max_lookahead_world: float = 18.0,
        arrival_radius_world: float = 2.0,
    ):
        if lookahead_world is not None and not 1.0 <= lookahead_world <= 30.0:
            raise ValueError("steering lookahead is invalid")
        if not 0.2 <= lookahead_time_s <= 1.5:
            raise ValueError("steering lookahead time is invalid")
        if not 0.5 <= min_lookahead_world < max_lookahead_world <= 30.0:
            raise ValueError("steering lookahead bounds are invalid")
        if not 0.5 <= arrival_radius_world <= 100.0:
            raise ValueError("steering arrival radius is invalid")
        self._fixed_lookahead_world = (
            None if lookahead_world is None else float(lookahead_world)
        )
        self._lookahead_time_s = float(lookahead_time_s)
        self._min_lookahead_world = float(min_lookahead_world)
        self._max_lookahead_world = float(max_lookahead_world)
        self._arrival_radius_world = float(arrival_radius_world)
        self._corridor_signature: tuple[tuple[float, float, float], ...] | None = None
        self._guidance_points_cache: tuple[NavPoint, ...] | None = None
        self._progress_world = 0.0
        self._projected_z_world: float | None = None
        self._projection_initialized = False
        self._previous_mouse_delta = 0
        self._last_nonzero_follow_delta = 0
        self._follow_reversal_settle_ticks = 0
        self._desired_heading_rad: float | None = None
        self._previous_heading_rad: float | None = None
        self._filtered_heading_delta_rad = 0.0
        self._curve_preview_active = False
        self._curve_free_half_width_world: float | None = None
        self._corner_precision_required = False
        self._precision_corner_progress_world: float | None = None
        self._precision_corner_outbound_heading_rad: float | None = None
        self._precision_corner_turn_rad: float | None = None
        self._stationary_pivot_active = False
        # A runtime heading probe can disprove the saved/minimap direction
        # after the first natural stride.  Keep one explicit latch so the
        # next decision releases W and turns in place before moving again.
        self._forced_stationary_pivot = False
        self._persistent_off_corridor_ticks = 0
        self._active_strafe: str | None = None
        self._pending_strafe: str | None = None
        self._pending_strafe_ticks = 0
        self._strafe_cooldown_ticks = 0
        self._trajectory_loop_guard = TrajectoryLoopGuard()

    def request_stationary_pivot(self) -> None:
        """Force the next correction to rotate with forward motion released.

        This is a bounded steering request from the runtime calibration layer;
        it does not send input by itself.  The latch clears only once the
        controller has reached its normal pivot-resume heading tolerance.
        """

        self._forced_stationary_pivot = True

    def decide(self, state: SteeringState, corridor: NavCorridor) -> SteeringIntent:
        values = (state.x, state.y, state.speed_world_per_s, state.no_progress_s)
        if any(not isfinite(value) for value in values) or state.speed_world_per_s <= 0:
            raise ValueError("steering state is invalid")
        if state.heading_rad is not None and not isfinite(state.heading_rad):
            raise ValueError("steering heading is invalid")
        remaining = hypot(corridor.stop.x - state.x, corridor.stop.y - state.y)
        if remaining <= self._arrival_radius_world:
            return SteeringIntent(
                "ARRIVED", 0, 0, None, "corridor_goal_reached",
                self._progress_world, 0.0, corridor.stop.z,
            )
        loop_evidence = self._trajectory_loop_guard.observe(
            x=state.x, y=state.y, goal_distance_world=remaining,
        )
        if loop_evidence is not None:
            self._previous_mouse_delta = 0
            self._desired_heading_rad = None
            return SteeringIntent(
                "REPLAN", 0, 0, None, "trajectory_loop_detected",
                self._progress_world, 0.0, self._projected_z_world,
            )
        (
            progress,
            cross_track,
            projected_z,
            signed_cross_track,
            tangent_heading,
        ) = self._project_progress(state, corridor)
        self._progress_world = max(self._progress_world, progress)
        self._projected_z_world = projected_z
        if state.no_progress_s >= 1.8:
            return SteeringIntent(
                "REPLAN", 0, 0, None, "stuck_progress_gate",
                self._progress_world, cross_track, self._projected_z_world,
            )
        recovery_profile = self._recovery_profile(corridor)
        recovery_start, recovery_full, _, hard_recenter = recovery_profile
        confined_profile = (
            hard_recenter == self.CONFINED_HARD_RECENTER_WORLD
        )
        if (
            confined_profile
            and state.no_progress_s >= self.CONFINED_FORWARD_STALL_REALIGN_S
        ):
            return SteeringIntent(
                "REPLAN", 0, 0, None, "confined_forward_stall_realign",
                self._progress_world, cross_track, self._projected_z_world,
            )
        lookahead = self._select_lookahead(
            state, corridor, self._progress_world, cross_track,
            recovery_profile=recovery_profile,
        )
        if state.heading_rad is None:
            self._previous_heading_rad = None
            self._filtered_heading_delta_rad = 0.0
            return SteeringIntent(
                "CALIBRATE_HEADING", 300, 0, lookahead,
                "one_natural_forward_stride_establishes_client_visible_heading",
                self._progress_world, cross_track, self._projected_z_world,
            )
        heading_delta = self._observe_heading_delta(state.heading_rad)
        raw_desired = atan2(lookahead.y - state.y, lookahead.x - state.x)
        raw_desired = self._curvature_preview_heading(
            corridor,
            progress_world=self._progress_world,
            cross_track_world=cross_track,
            base_heading_rad=raw_desired,
        )
        tangent_error = self._wrap(tangent_heading - state.heading_rad)
        locally_straight = self._corridor_is_locally_straight(
            corridor,
            progress_world=progress,
            tangent_heading_rad=tangent_heading,
        )
        awareness = corridor.start_awareness
        confined_wmo_strafe = (
            confined_profile
            and awareness is not None
            and "wmo" in awareness.physical_surfaces
            and corridor.complete
            and not self._curve_preview_active
            and locally_straight
            and not self._corner_precision_required
            and not corridor.doodad_avoidance_applied
            and abs(tangent_error)
            <= self.CAMERA_STABLE_STRAFE_MAX_TANGENT_ERROR_RAD
        )
        camera_stable_lateral_correction = (
            not self._curve_preview_active
            and locally_straight
            and not self._corner_precision_required
            and not corridor.doodad_avoidance_applied
            and (
                (
                    not confined_profile
                    and self.CAMERA_STABLE_STRAFE_STOP_WORLD
                    < cross_track
                    <= self.CAMERA_STABLE_STRAFE_MAX_WORLD
                )
                or (
                    confined_wmo_strafe
                    and self.CONFINED_STRAFE_START_WORLD
                    < cross_track
                    <= self.CONFINED_STRAFE_MAX_WORLD
                )
            )
            and abs(tangent_error)
            <= self.CAMERA_STABLE_STRAFE_MAX_TANGENT_ERROR_RAD
        )
        strafe = self._select_camera_stable_strafe(
            signed_cross_track_world=signed_cross_track,
            cross_track_world=cross_track,
            tangent_error_rad=tangent_error,
            allowed=(
                not self._curve_preview_active
                and locally_straight
                and not self._corner_precision_required
                and not corridor.doodad_avoidance_applied
                and (
                    not confined_profile
                    or confined_wmo_strafe
                )
            ),
            confined=confined_wmo_strafe,
        )
        if camera_stable_lateral_correction:
            # Keep the camera/facing on the path tangent. The lateral key, not
            # repeated RMB reversals, returns the capsule to the centreline.
            raw_desired = tangent_heading
        raw_error = self._wrap(raw_desired - state.heading_rad)
        # Being off the centreline while actively rotating toward it is not
        # divergence. Count only the case where the character is already facing
        # the re-entry bearing yet remains outside the corridor. A non-converging
        # pivot and a physically blocked forward move are independently proven
        # by the runner's heading/progress clocks.
        if (
            cross_track >= hard_recenter
            and abs(raw_error) < self.RECENTER_HEADING_THRESHOLD_RAD
        ):
            self._persistent_off_corridor_ticks += 1
        else:
            self._persistent_off_corridor_ticks = 0
        if (
            self._persistent_off_corridor_ticks
            >= self.PERSISTENT_OFF_CORRIDOR_REPLAN_TICKS
        ):
            return SteeringIntent(
                "REPLAN", 0, 0, None, "persistent_corridor_divergence",
                self._progress_world, cross_track, self._projected_z_world,
            )
        # A freestanding gate can be outdoors while still demanding indoor-
        # precision steering.  When the actor has consumed most of the local
        # portal's free half-width, stop treating a 60-100 degree correction
        # as a broad open-ground arc.  This is a late safety fallback; an actor
        # near the centreline still carves the verified curve continuously.
        portal_clearance_constrained = (
            self._curve_preview_active
            and self._curve_free_half_width_world is not None
            and cross_track >= max(
                0.50, self._curve_free_half_width_world * 0.55,
            )
        )
        # Detour's doodad path is already the clearance-inset centreline around
        # an object.  It must be tracked with capsule precision even when the
        # surrounding terrain is ordinary open ground.  Treating that short
        # section as an open-field arc lets steering round the inside of the
        # detour and put the actor back into the obstacle that navigation had
        # correctly avoided.
        precision_profile = (
            confined_profile
            or corridor.doodad_avoidance_applied
            or self._corner_precision_required
            or portal_clearance_constrained
        )
        pivot_threshold = (
            (
                self.PIVOT_THRESHOLD_RAD
                if cross_track < recovery_start
                else self.OFF_CORRIDOR_PIVOT_THRESHOLD_RAD
            )
            if precision_profile
            else self.OPEN_GROUND_PIVOT_THRESHOLD_RAD
        )
        desired = self._stabilize_desired_heading(
            raw_desired,
            pivot=abs(raw_error) >= pivot_threshold,
            precision=precision_profile,
        )
        error = self._wrap(desired - state.heading_rad)
        heading_preview = max(
            -self.MAX_HEADING_BRAKE_PREVIEW_RAD,
            min(
                self.MAX_HEADING_BRAKE_PREVIEW_RAD,
                heading_delta * self.HEADING_BRAKE_PREVIEW_TICKS,
            ),
        )
        control_error = self._wrap(
            desired - self._wrap(state.heading_rad + heading_preview),
        )
        # WoW's RMB relative-motion convention turns right for positive mouse
        # X, which decreases a standard mathematical world yaw.
        # Stop forward pressure for corners the character cannot physically
        # carve at its current turn rate.  Smaller errors remain one closed-loop
        # tick so the next fresh pose can correct them without visible pulsing.
        recenter_required = (
            cross_track >= hard_recenter
            and (
                abs(raw_error) >= self.RECENTER_HEADING_THRESHOLD_RAD
            )
        )
        running_recenter_allowed = (
            confined_profile
            and recenter_required
            and corridor.complete
            and cross_track < hard_recenter + self.RUNNING_RECENTER_MARGIN_WORLD
            and abs(raw_error) < self.RUNNING_RECENTER_MAX_ERROR_RAD
        )
        stationary_recenter_required = (
            recenter_required and not running_recenter_allowed
        )
        # Bearing error describes where the path goes; it does not prove that
        # moving is unsafe. Continue carving the turn while the capsule is
        # inside the verified corridor. Only a real recenter condition, or a
        # precision section already outside its ordinary recovery envelope,
        # stops W. This removes robotic stop-turn-go behavior without allowing
        # a wall-adjacent recovery to charge forward.
        # A normal recovery-envelope crossing is not evidence that forward
        # motion is unsafe.  Releasing W there created the observed 0.2-1.0 s
        # stop/start pulses through stairs, bridges and S-shaped portals.  A
        # player keeps W held and uses RMB through those corrections.  Stop
        # only after the capsule has actually crossed the hard recenter limit;
        # the verified inset corridor remains the collision authority.
        extreme_precision_hairpin = (
            self._corner_precision_required
            and self._precision_corner_turn_rad is not None
            and self._precision_corner_turn_rad >= self.OPEN_GROUND_PIVOT_THRESHOLD_RAD
            and abs(raw_error) >= self.PIVOT_THRESHOLD_RAD
            and (
                self._curve_free_half_width_world is None
                or self._curve_free_half_width_world
                < self.MINIMUM_RUNNING_CURVE_FREE_HALF_WIDTH_WORLD
            )
        )
        pivot_entry_required = (
            stationary_recenter_required
            or extreme_precision_hairpin
            or abs(raw_error) >= self.OPEN_GROUND_PIVOT_THRESHOLD_RAD
        )
        if self._forced_stationary_pivot:
            if abs(error) <= self.PIVOT_RESUME_THRESHOLD_RAD:
                self._forced_stationary_pivot = False
            else:
                self._stationary_pivot_active = True
        if self._stationary_pivot_active:
            if (
                not self._forced_stationary_pivot
                and not stationary_recenter_required
                and not extreme_precision_hairpin
                and abs(error) <= self.PIVOT_RESUME_THRESHOLD_RAD
            ):
                self._stationary_pivot_active = False
        elif pivot_entry_required:
            self._stationary_pivot_active = True
        forward_ms = 0 if self._stationary_pivot_active else self.CONTROL_TICK_MS
        state_name = "PIVOT" if forward_ms == 0 else "FOLLOW"
        yaw_gain_per_s = (
            self.PIVOT_YAW_GAIN_PER_S
            if state_name == "PIVOT"
            else self.FOLLOW_YAW_GAIN_PER_S
        )
        maximum_delta = (
            self.PIVOT_MAX_MOUSE_DELTA
            if state_name == "PIVOT"
            else self.FOLLOW_MAX_MOUSE_DELTA
        )
        requested_delta = (
            0
            if state_name == "FOLLOW"
            and abs(error) <= self.FOLLOW_HEADING_DEADBAND_RAD
            else round(
                -control_error
                * yaw_gain_per_s
                / (
                    self.MOUSE_YAW_RAD_PER_PIXEL
                    * self.MOUSE_COMMAND_VELOCITY_SCALE_HZ
                )
            )
        )
        requested_delta = max(
            -maximum_delta,
            min(maximum_delta, requested_delta),
        )
        # A camera cannot jump from a full left pivot to a full right pivot in
        # one observation. Brake through zero first, accelerate gradually, and
        # allow a faster stop than start so the visible yaw does not overshoot.
        slew_target = requested_delta
        if self._previous_mouse_delta * requested_delta < 0:
            slew_target = 0
        accelerating_slew = (
            self.CURVE_MOUSE_ACCEL_SLEW_PER_TICK
            if self._curve_preview_active or precision_profile
            else self.MOUSE_ACCEL_SLEW_PER_TICK
        )
        braking_slew = (
            self.CURVE_MOUSE_BRAKE_SLEW_PER_TICK
            if self._curve_preview_active or precision_profile
            else self.MOUSE_BRAKE_SLEW_PER_TICK
        )
        slew = (
            braking_slew
            if abs(slew_target) < abs(self._previous_mouse_delta)
            else accelerating_slew
        )
        mouse_delta = max(
            self._previous_mouse_delta - slew,
            min(self._previous_mouse_delta + slew, slew_target),
        )
        if state_name == "PIVOT":
            # A completed stationary alignment starts a new running arc. Do
            # not compare its first FOLLOW command with a stale pre-pivot sign.
            self._last_nonzero_follow_delta = 0
        if state_name == "FOLLOW" and mouse_delta:
            if self._follow_reversal_settle_ticks > 0:
                self._follow_reversal_settle_ticks -= 1
            prior_nonzero = self._last_nonzero_follow_delta
            settled_straight_reversal = (
                locally_straight
                and abs(mouse_delta)
                <= self.FOLLOW_REVERSAL_HYSTERESIS_MAX_DELTA
                and abs(prior_nonzero)
                <= self.STRAIGHT_REVERSAL_HYSTERESIS_MAX_PRIOR_DELTA
                and abs(raw_error)
                <= self.STRAIGHT_REVERSAL_HYSTERESIS_MAX_ERROR_RAD
            )
            settled_open_reversal = (
                not precision_profile
                and not locally_straight
                and abs(mouse_delta)
                <= self.FOLLOW_REVERSAL_HYSTERESIS_MAX_DELTA
                and abs(prior_nonzero)
                <= self.FOLLOW_REVERSAL_HYSTERESIS_MAX_PRIOR_DELTA
                and abs(raw_error)
                <= self.FOLLOW_REVERSAL_HYSTERESIS_MAX_ERROR_RAD
                and cross_track <= min(recovery_full, 2.0)
            )
            settled_precision_micro_reversal = (
                abs(mouse_delta) < 2
                and abs(prior_nonzero) < 4
                and cross_track
                <= self.OFF_CORRIDOR_RECOVERY_START_WORLD
                and not locally_straight
            )
            settling_counter_pulse = (
                prior_nonzero * mouse_delta < 0
                and self._follow_reversal_settle_ticks > 0
                and abs(raw_error) <= self.FOLLOW_REVERSAL_SETTLE_MAX_ERROR_RAD
                and cross_track <= hard_recenter
            )
            if (
                prior_nonzero * mouse_delta < 0
                and (
                    settled_straight_reversal
                    or settled_open_reversal
                    or settled_precision_micro_reversal
                    or settling_counter_pulse
                )
            ):
                # Do not balance small left/right pulses around a settled
                # corridor bearing, even when a neutral slew tick separates
                # them. Larger corrections, departures and pivots are never
                # filtered by this rule.
                mouse_delta = 0
            else:
                if prior_nonzero * mouse_delta < 0:
                    self._follow_reversal_settle_ticks = (
                        self.FOLLOW_REVERSAL_SETTLE_TICKS
                    )
                self._last_nonzero_follow_delta = mouse_delta
        self._previous_mouse_delta = mouse_delta
        return SteeringIntent(
            state_name, forward_ms, mouse_delta, lookahead,
            (
                "topology_camera_stable_strafe_correction"
                if camera_stable_lateral_correction
                else "topology_continuous_projection_with_yaw_momentum_braking"
            ),
            self._progress_world, cross_track, self._projected_z_world, strafe,
        )

    def _observe_heading_delta(self, heading_rad: float) -> float:
        """Estimate bounded yaw momentum from consecutive client observations.

        The estimate deliberately lives in the controller rather than the
        Windows input sink.  Replays and every future client adapter therefore
        exercise the same closed-loop braking behavior.
        """

        if self._previous_heading_rad is None:
            self._previous_heading_rad = heading_rad
            self._filtered_heading_delta_rad = 0.0
            return 0.0
        observed = self._wrap(heading_rad - self._previous_heading_rad)
        observed = max(
            -self.MAX_OBSERVED_HEADING_DELTA_RAD,
            min(self.MAX_OBSERVED_HEADING_DELTA_RAD, observed),
        )
        weight = self.HEADING_DELTA_FILTER_CURRENT_WEIGHT
        self._filtered_heading_delta_rad = (
            observed * weight
            + self._filtered_heading_delta_rad * (1.0 - weight)
        )
        self._previous_heading_rad = heading_rad
        return self._filtered_heading_delta_rad

    def _reset_for_corridor(self, corridor: NavCorridor) -> None:
        guidance = corridor.guidance_points()
        # Equal XY does not imply the same surface: stairs and stacked floors
        # may replace only Z. Retaining that cache mixes the new corridor with
        # old projection/lookahead heights. This tracks plan identity, not an
        # observation or confirmation of the actor's physical floor.
        signature = tuple((point.x, point.y, point.z) for point in guidance)
        if signature != self._corridor_signature:
            self._corridor_signature = signature
            self._guidance_points_cache = guidance
            self._progress_world = 0.0
            self._projected_z_world = corridor.start.z
            self._projection_initialized = False
            self._persistent_off_corridor_ticks = 0
            self._active_strafe = None
            self._pending_strafe = None
            self._pending_strafe_ticks = 0
            self._strafe_cooldown_ticks = 0
            self._trajectory_loop_guard.reset()
            self._precision_corner_progress_world = None
            self._precision_corner_outbound_heading_rad = None
            self._precision_corner_turn_rad = None
            self._stationary_pivot_active = False
            # A rolling semantic horizon changes corridor identity while the
            # same physical turn is still in progress. Preserve actuator
            # velocity across that hand-off; sign-change braking in decide()
            # already prevents an instantaneous reversal.

    def _project_progress(
        self, state: SteeringState, corridor: NavCorridor
    ) -> tuple[float, float, float, float, float]:
        self._reset_for_corridor(corridor)
        best_distance = float("inf")
        best_progress = self._progress_world
        best_z = (
            corridor.start.z
            if self._projected_z_world is None
            else self._projected_z_world
        )
        best_signed_cross_track = 0.0
        best_tangent_heading = 0.0
        cumulative = 0.0
        if self._projection_initialized:
            minimum_progress = max(
                0.0, self._progress_world - self.PROJECTION_BACKTRACK_WORLD,
            )
            maximum_progress = self._progress_world + max(
                self.MIN_PROJECTION_ADVANCE_WORLD,
                min(
                    self.MAX_PROJECTION_ADVANCE_WORLD,
                    state.speed_world_per_s * self.PROJECTION_ADVANCE_TIME_S,
                ),
            )
            maximum_progress = self._extend_projection_for_outbound_corner(
                state,
                corridor,
                maximum_progress=maximum_progress,
            )
        else:
            # A newly planned corridor starts at the current observed pose, but
            # fixtures and resume callers can enter at any proven point.  One
            # global projection establishes the anchor; every subsequent frame
            # is topology-windowed so overlapping floors cannot steal it.
            minimum_progress = 0.0
            maximum_progress = float("inf")
        guidance = self._guidance_points(corridor)
        for start, stop in zip(guidance, guidance[1:]):
            dx, dy = stop.x - start.x, stop.y - start.y
            length_squared = dx * dx + dy * dy
            if length_squared == 0:
                continue
            segment_length = length_squared ** 0.5
            segment_start_progress = cumulative
            segment_stop_progress = cumulative + segment_length
            cumulative = segment_stop_progress
            if (
                segment_stop_progress < minimum_progress
                or segment_start_progress > maximum_progress
            ):
                continue
            t = max(
                0.0,
                min(1.0, ((state.x - start.x) * dx + (state.y - start.y) * dy) / length_squared),
            )
            candidate_progress = segment_start_progress + t * segment_length
            if candidate_progress < minimum_progress:
                t = (minimum_progress - segment_start_progress) / segment_length
                t = max(0.0, min(1.0, t))
                candidate_progress = segment_start_progress + t * segment_length
            elif candidate_progress > maximum_progress:
                t = (maximum_progress - segment_start_progress) / segment_length
                t = max(0.0, min(1.0, t))
                candidate_progress = segment_start_progress + t * segment_length
            projected_x, projected_y = start.x + t * dx, start.y + t * dy
            distance = hypot(state.x - projected_x, state.y - projected_y)
            if distance < best_distance:
                best_distance = distance
                best_progress = candidate_progress
                best_z = start.z + (stop.z - start.z) * t
                best_signed_cross_track = (
                    dx * (state.y - projected_y)
                    - dy * (state.x - projected_x)
                ) / segment_length
                best_tangent_heading = atan2(dy, dx)
        self._projection_initialized = True
        return (
            best_progress,
            best_distance,
            best_z,
            best_signed_cross_track,
            best_tangent_heading,
        )

    def _extend_projection_for_outbound_corner(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        *,
        maximum_progress: float,
    ) -> float:
        """Reach a locally proven corner's outbound strip after a late sample.

        The normal projection window is deliberately time-bounded to prevent
        an overlapping upper/lower floor from stealing progress.  A narrow
        hairpin is a different observation pattern: the actor may already be
        turning toward the outbound tangent while the window still ends just
        before the apex.  Extend only that existing window when client
        geometry identifies a sharp corner, a nearby portal, a nearby actor,
        and an outbound-facing observation.  No point is selected here; the
        regular nearest-segment and monotonic projection checks remain the
        authority.
        """

        if not corridor.geometry_aware:
            return maximum_progress
        if state.heading_rad is None:
            return maximum_progress
        awareness = corridor.start_awareness
        if awareness is not None and awareness.environment_class != "OPEN_GROUND":
            # Confined/WMO corridors keep the stricter temporal projection;
            # their doorway/stair precision logic must not be bypassed by an
            # outbound-facing sample.
            return maximum_progress
        corner_progress = self._first_sharp_corner_progress(
            corridor,
            progress_world=self._progress_world,
            scan_distance_world=self.MAX_PROJECTION_ADVANCE_WORLD
            + self.CORNER_SAMPLE_WORLD,
        )
        if corner_progress is None or corner_progress > (
            maximum_progress + self.CORNER_SAMPLE_WORLD
        ):
            return maximum_progress
        if self._local_corner_portal_width(
            corridor, corner_progress=corner_progress,
        ) is None:
            return maximum_progress
        corner = self._point_at_progress(corridor, corner_progress)
        if hypot(state.x - corner.x, state.y - corner.y) > (
            self.PROJECTION_CORNER_MAX_DISTANCE_WORLD
        ):
            return maximum_progress
        outbound_start = self._point_at_progress(
            corridor, corner_progress + self.CORNER_SAMPLE_WORLD,
        )
        outbound_stop = self._point_at_progress(
            corridor, corner_progress + 2.0 * self.CORNER_SAMPLE_WORLD,
        )
        outbound_heading = atan2(
            outbound_stop.y - outbound_start.y,
            outbound_stop.x - outbound_start.x,
        )
        if abs(self._wrap(state.heading_rad - outbound_heading)) > (
            self.PROJECTION_CORNER_MAX_HEADING_ERROR_RAD
        ):
            return maximum_progress
        return min(
            self._progress_world + self.MAX_PROJECTION_ADVANCE_WORLD,
            max(maximum_progress, corner_progress + self.MAX_PROJECTION_ADVANCE_WORLD),
        )

    def _select_camera_stable_strafe(
        self,
        *,
        signed_cross_track_world: float,
        cross_track_world: float,
        tangent_error_rad: float,
        allowed: bool,
        confined: bool = False,
    ) -> str | None:
        start_world = (
            self.CONFINED_STRAFE_START_WORLD
            if confined else self.CAMERA_STABLE_STRAFE_START_WORLD
        )
        max_world = (
            self.CONFINED_STRAFE_MAX_WORLD
            if confined else self.CAMERA_STABLE_STRAFE_MAX_WORLD
        )
        confirmation_ticks = (
            self.CONFINED_STRAFE_REVERSAL_CONFIRMATION_TICKS
            if confined else self.CAMERA_STABLE_STRAFE_REVERSAL_CONFIRMATION_TICKS
        )
        cooldown_ticks = (
            self.CONFINED_STRAFE_COOLDOWN_TICKS
            if confined else self.CAMERA_STABLE_STRAFE_COOLDOWN_TICKS
        )
        if (
            not allowed
            or cross_track_world > max_world
            or abs(tangent_error_rad)
            > self.CAMERA_STABLE_STRAFE_MAX_TANGENT_ERROR_RAD
        ):
            self._active_strafe = None
            self._pending_strafe = None
            self._pending_strafe_ticks = 0
            self._strafe_cooldown_ticks = 0
            return None
        if cross_track_world <= (
            self.CAMERA_STABLE_STRAFE_STOP_WORLD
            if not confined else 0.12
        ):
            self._active_strafe = None
            self._pending_strafe = None
            self._pending_strafe_ticks = 0
            self._strafe_cooldown_ticks = 0
            return None

        desired = (
            "STRAFE_RIGHT"
            if signed_cross_track_world > 0.0
            else "STRAFE_LEFT"
        )
        # A full strafe key has much more lateral authority than a tiny RMB
        # correction. Emit one observed-frame tap, then reassess the exact
        # client pose after a short neutral interval instead of holding A/D
        # long enough to cross the centreline and start another oscillation.
        if self._strafe_cooldown_ticks > 0:
            self._active_strafe = None
            self._strafe_cooldown_ticks -= 1
            return None
        if cross_track_world < start_world:
            return None
        if self._pending_strafe != desired:
            self._active_strafe = None
            self._pending_strafe = desired
            self._pending_strafe_ticks = 1
            return None
        self._pending_strafe_ticks += 1
        if (
            self._pending_strafe_ticks
            < confirmation_ticks
        ):
            return None
        self._active_strafe = desired
        self._pending_strafe = None
        self._pending_strafe_ticks = 0
        self._strafe_cooldown_ticks = cooldown_ticks
        return desired

    def _corridor_is_locally_straight(
        self,
        corridor: NavCorridor,
        *,
        progress_world: float,
        tangent_heading_rad: float,
    ) -> bool:
        previous = self._point_at_progress(corridor, progress_world)
        sample = progress_world + self.CORNER_SCAN_STEP_WORLD
        stop = progress_world + self.CAMERA_STABLE_STRAFE_PREVIEW_WORLD
        while sample <= stop:
            current = self._point_at_progress(corridor, sample)
            dx, dy = current.x - previous.x, current.y - previous.y
            if hypot(dx, dy) > 1.0e-6:
                heading = atan2(dy, dx)
                if abs(self._wrap(heading - tangent_heading_rad)) > (
                    self.CAMERA_STABLE_STRAFE_MAX_PATH_BEND_RAD
                ):
                    return False
                previous = current
            sample += self.CORNER_SCAN_STEP_WORLD
        return True

    def _select_lookahead(
        self,
        state: SteeringState,
        corridor: NavCorridor,
        progress_world: float,
        cross_track_world: float,
        *,
        recovery_profile: tuple[float, float, float, float],
    ) -> NavPoint:
        distance = self._fixed_lookahead_world
        if distance is None:
            distance = max(
                self._min_lookahead_world,
                min(
                    self._max_lookahead_world,
                    state.speed_world_per_s * self._lookahead_time_s,
                ),
            )
        recovery_start, recovery_full, recovery_lookahead, _ = recovery_profile
        if cross_track_world >= recovery_start:
            speed_horizon = max(
                recovery_lookahead,
                min(
                    distance,
                    state.speed_world_per_s
                    * self.MINIMUM_RECOVERY_LOOKAHEAD_TIME_S,
                ),
            )
            speed_blend = min(
                1.0,
                max(
                    0.0,
                    (cross_track_world - recovery_full)
                    / self.RECOVERY_SPEED_HORIZON_BLEND_WORLD,
                ),
            )
            speed_blend = (
                speed_blend * speed_blend * (3.0 - 2.0 * speed_blend)
            )
            recovery_lookahead += (
                speed_horizon - recovery_lookahead
            ) * speed_blend
            # Start shortening the pursuit horizon inside the safe band and
            # reach the full recovery horizon at the corridor threshold.  The
            # former recovery ramp started *after* that threshold and did not
            # fully engage until 3 yd away.  In a WMO doorway/stair corridor a
            # 0.91 yd deviation therefore kept a roughly 5 yd carrot directly
            # ahead, producing zero yaw while the client capsule hit a wall.
            # Smoothstep keeps the steering bearing continuous while making
            # the centerline authoritative before physical clearance is lost.
            recovery_span = (
                recovery_full - recovery_start
            )
            recovery_blend = min(
                1.0,
                (cross_track_world - recovery_start)
                / recovery_span,
            )
            recovery_blend = (
                recovery_blend
                * recovery_blend
                * (3.0 - 2.0 * recovery_blend)
            )
            distance = distance + (
                recovery_lookahead - distance
            ) * recovery_blend
        corner_progress = self._first_sharp_corner_progress(
            corridor, progress_world=progress_world, scan_distance_world=distance,
        )
        target_progress = progress_world + distance
        if corner_progress is not None:
            target_progress = min(target_progress, corner_progress)
        return self._point_at_progress(corridor, target_progress)

    def _recovery_profile(
        self, corridor: NavCorridor,
    ) -> tuple[float, float, float, float]:
        """Choose precision from client geometry, not a named location.

        Covered WMO/doodad space needs a short centreline correction before a
        doorway or stair edge is lost.  Open ground and roads need a longer
        pursuit horizon so ordinary one-yard drift remains a smooth arc.  The
        distinction is supplied by the worker's local client-asset awareness;
        no zone, crypt, road, or coordinate is special-cased.
        """

        awareness = corridor.start_awareness
        confined = corridor.doodad_avoidance_applied or (
            awareness is not None and (
                not awareness.overhead_clear
                or bool(awareness.physical_surfaces.intersection({"wmo", "doodad"}))
                or awareness.environment_class == "CONFINED_STATIC_SPACE"
            )
        )
        if confined:
            return (
                self.CONFINED_RECOVERY_START_WORLD,
                self.CONFINED_RECOVERY_FULL_WORLD,
                self.CONFINED_REENTRY_LOOKAHEAD_WORLD,
                self.CONFINED_HARD_RECENTER_WORLD,
            )
        return (
            self.OFF_CORRIDOR_RECOVERY_START_WORLD,
            self.OFF_CORRIDOR_THRESHOLD_WORLD,
            self.OFF_CORRIDOR_REENTRY_LOOKAHEAD_WORLD,
            self.OFF_CORRIDOR_HARD_RECENTER_WORLD,
        )

    def _first_sharp_corner_progress(
        self,
        corridor: NavCorridor,
        *,
        progress_world: float,
        scan_distance_world: float,
    ) -> float | None:
        scan_start = progress_world + self.CORNER_SAMPLE_WORLD
        scan_stop = progress_world + scan_distance_world
        sample = scan_start
        while sample <= scan_stop:
            before = self._point_at_progress(
                corridor, sample - self.CORNER_SAMPLE_WORLD,
            )
            center = self._point_at_progress(corridor, sample)
            after = self._point_at_progress(
                corridor, sample + self.CORNER_SAMPLE_WORLD,
            )
            inbound = atan2(center.y - before.y, center.x - before.x)
            outbound = atan2(after.y - center.y, after.x - center.x)
            corner_threshold = (
                self.DOODAD_CORNER_THRESHOLD_RAD
                if corridor.doodad_avoidance_applied
                else self.CORNER_THRESHOLD_RAD
            )
            if abs(self._wrap(outbound - inbound)) >= corner_threshold:
                return sample
            sample += self.CORNER_SCAN_STEP_WORLD
        return None

    def _curvature_preview_heading(
        self,
        corridor: NavCorridor,
        *,
        progress_world: float,
        cross_track_world: float,
        base_heading_rad: float,
    ) -> float:
        """Blend toward an upcoming portal turn before reaching its apex.

        The look-ahead point remains capped at a sharp corner, so steering can
        never claim a straight chord through a wall.  On a geometry-aware
        corridor, portal width provides a bounded turning radius: the actor
        begins the RMB arc early enough to look human, but never earlier than
        its capsule plus clearance margin can fit inside the passage.
        """

        self._curve_preview_active = False
        self._curve_free_half_width_world = None
        self._corner_precision_required = False
        # A doodad detour is not a cosmetic polyline bend: its apex encodes an
        # actor-sized collision envelope.  Without the obstacle geometry here,
        # a generic corner fillet can only cut toward the forbidden interior.
        # Follow the proven inset corridor; future obstacle-aware fillets may
        # replace this once their complete swept capsule is verified.
        if corridor.doodad_avoidance_applied:
            return base_heading_rad

        committed_progress = self._precision_corner_progress_world
        committed_outbound = self._precision_corner_outbound_heading_rad
        if committed_progress is not None and committed_outbound is not None:
            if progress_world <= (
                committed_progress + self.NARROW_CORNER_RELEASE_AFTER_WORLD
            ):
                self._corner_precision_required = True
                if progress_world >= (
                    committed_progress - self.NARROW_CORNER_COMMIT_BEFORE_WORLD
                ):
                    return committed_outbound
            else:
                self._precision_corner_progress_world = None
                self._precision_corner_outbound_heading_rad = None
                self._precision_corner_turn_rad = None
        corner_progress = self._first_sharp_corner_progress(
            corridor,
            progress_world=progress_world,
            scan_distance_world=(
                self.CURVE_PREVIEW_MAX_WORLD + self.CORNER_SAMPLE_WORLD
            ),
        )
        if corner_progress is None:
            return base_heading_rad
        local_width = self._local_corner_portal_width(
            corridor, corner_progress=corner_progress,
        )
        if local_width is None:
            return base_heading_rad
        free_half_width = (
            local_width * 0.5
            - self.CURVE_PREVIEW_CAPSULE_AND_MARGIN_WORLD
        )
        # A turn whose portal cannot hold even the minimum actor-centre fillet
        # is not open-ground steering merely because it is outdoors.  Mark it
        # as a precision corner so W remains released until the RMB correction
        # is genuinely aligned.  The live 128-degree, 2.20 yd road hairpin
        # exposed the former 99-degree resume threshold.
        if free_half_width <= self.MINIMUM_CURVE_FREE_HALF_WIDTH_WORLD:
            self._corner_precision_required = True
            # ``corner_progress`` is a sampled detection point and can sit
            # slightly before the actual polyline vertex.  Measuring from that
            # point mixes the inbound and outbound segments and produced a
            # false ~45-degree tangent for a real 128-degree hairpin.  Sample
            # wholly beyond the detection window to obtain the exit tangent.
            outbound_start = self._point_at_progress(
                corridor, corner_progress + self.CORNER_SAMPLE_WORLD,
            )
            outbound_stop = self._point_at_progress(
                corridor, corner_progress + 2.0 * self.CORNER_SAMPLE_WORLD,
            )
            outbound = atan2(
                outbound_stop.y - outbound_start.y,
                outbound_stop.x - outbound_start.x,
            )
            inbound_start = self._point_at_progress(
                corridor, max(0.0, corner_progress - 2.0 * self.CORNER_SAMPLE_WORLD),
            )
            inbound_stop = self._point_at_progress(
                corridor, max(0.0, corner_progress - self.CORNER_SAMPLE_WORLD),
            )
            inbound = atan2(
                inbound_stop.y - inbound_start.y,
                inbound_stop.x - inbound_start.x,
            )
            self._precision_corner_progress_world = corner_progress
            self._precision_corner_outbound_heading_rad = outbound
            self._precision_corner_turn_rad = abs(self._wrap(outbound - inbound))
            if progress_world >= (
                corner_progress - self.NARROW_CORNER_COMMIT_BEFORE_WORLD
            ):
                return outbound
        # A rounded path legitimately leaves the zero-width funnel polyline.
        # Keep anticipating while the complete actor capsule remains inside
        # the locally proven portal clearance; a generic 1.25 yd cutoff used
        # to disable the curve half-way through a wide, valid gateway.
        if cross_track_world >= free_half_width:
            return base_heading_rad
        preview_world = min(
            self.CURVE_PREVIEW_MAX_WORLD,
            free_half_width * self.CURVE_PREVIEW_FREE_HALF_WIDTH_MULTIPLIER,
        )
        if preview_world <= self.MINIMUM_CURVE_FREE_HALF_WIDTH_WORLD:
            return base_heading_rad
        distance_to_corner = max(0.0, corner_progress - progress_world)
        if distance_to_corner >= preview_world:
            return base_heading_rad
        outbound_start = self._point_at_progress(
            corridor, corner_progress + self.CORNER_SAMPLE_WORLD,
        )
        outbound_stop = self._point_at_progress(
            corridor, corner_progress + 2.0 * self.CORNER_SAMPLE_WORLD,
        )
        outbound = atan2(
            outbound_stop.y - outbound_start.y,
            outbound_stop.x - outbound_start.x,
        )
        # Begin visibly committing while there is still room to carve the
        # corner.  Smoothstep was almost flat at the preview boundary: at
        # running speed the actor spent most of the available clearance still
        # correcting toward the old straight, then chased the apex from its
        # far side.  The square-root profile is deliberately early; the
        # desired-heading slew remains the actuator-continuity bound.
        blend = sqrt(1.0 - distance_to_corner / preview_world)
        self._curve_preview_active = True
        self._curve_free_half_width_world = free_half_width
        # Blend the actual pursuit bearing toward the outbound tangent.  The
        # former ``base + path_turn`` expression was only geometrically exact
        # while the actor sat on the inbound centerline.  With ordinary
        # lateral error it retained a recentering bias and delayed the curve.
        outbound_error = self._wrap(outbound - base_heading_rad)
        return self._wrap(base_heading_rad + outbound_error * blend)

    def _local_corner_portal_width(
        self, corridor: NavCorridor, *, corner_progress: float,
    ) -> float | None:
        """Return clearance evidence local to one funnel-path corner.

        Portal order describes topology, while funnel points describe the
        executable center path; they do not have a one-to-one index.  Spatial
        association is therefore deliberate.  If no portal is close enough,
        anticipation stays disabled rather than assuming free space.
        """

        if not corridor.geometry_aware:
            return None
        corner = self._point_at_progress(corridor, corner_progress)
        candidates: list[tuple[float, float]] = []
        for portal in corridor.portals:
            midpoint_x = (portal.left.x + portal.right.x) * 0.5
            midpoint_y = (portal.left.y + portal.right.y) * 0.5
            distance = hypot(corner.x - midpoint_x, corner.y - midpoint_y)
            if distance <= self.CURVE_PORTAL_ASSOCIATION_MAX_WORLD:
                candidates.append((distance, portal.width))
        if not candidates:
            return None
        nearest_distance = min(item[0] for item in candidates)
        # Adjacent triangulation edges can share the same physical gateway.
        # Keep the narrowest equally-near edge instead of cherry-picking room.
        return min(
            width for distance, width in candidates
            if distance <= nearest_distance + 0.25
        )

    def _guidance_points(self, corridor: NavCorridor) -> tuple[NavPoint, ...]:
        cached = self._guidance_points_cache
        if cached is None:
            cached = corridor.guidance_points()
            self._guidance_points_cache = cached
        return cached

    def _point_at_progress(
        self, corridor: NavCorridor, progress_world: float,
    ) -> NavPoint:
        target = max(0.0, progress_world)
        cumulative = 0.0
        guidance = self._guidance_points(corridor)
        for start, stop in zip(guidance, guidance[1:]):
            segment_length = start.distance_2d(stop)
            if segment_length == 0:
                continue
            if cumulative + segment_length >= target:
                t = (target - cumulative) / segment_length
                return NavPoint(
                    start.x + (stop.x - start.x) * t,
                    start.y + (stop.y - start.y) * t,
                    start.z + (stop.z - start.z) * t,
                )
            cumulative += segment_length
        return guidance[-1]

    @staticmethod
    def _wrap(angle: float) -> float:
        while angle > pi:
            angle -= 2 * pi
        while angle < -pi:
            angle += 2 * pi
        return angle

    def _stabilize_desired_heading(
        self, desired: float, *, pivot: bool, precision: bool = False,
    ) -> float:
        """Advance a desired bearing by a bounded amount per control tick.

        This is deliberately a target-side filter, rather than filtering the
        observed facing.  Position and facing remain fresh client observations;
        only the controller's own future-point preference is made continuous.
        """

        if self._desired_heading_rad is None:
            self._desired_heading_rad = desired
            return desired
        maximum_step = (
            self.PIVOT_DESIRED_HEADING_SLEW_RAD_PER_TICK
            if pivot
            else (
                self.CURVE_DESIRED_HEADING_SLEW_RAD_PER_TICK
                if self._curve_preview_active or precision
                else self.FOLLOW_DESIRED_HEADING_SLEW_RAD_PER_TICK
            )
        )
        delta = self._wrap(desired - self._desired_heading_rad)
        delta = max(-maximum_step, min(maximum_step, delta))
        self._desired_heading_rad = self._wrap(
            self._desired_heading_rad + delta,
        )
        return self._desired_heading_rad
