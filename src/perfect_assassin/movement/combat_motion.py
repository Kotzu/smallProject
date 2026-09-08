from __future__ import annotations

from dataclasses import dataclass

from perfect_assassin.domain.combat import CombatObservationState, TargetBearingState
from perfect_assassin.domain.combat_range import ROGUE_MELEE_RANGE, RangeBand
from perfect_assassin.domain.facing import ContinuousMagneticFacingController
from perfect_assassin.domain.motion import ContinuousMotionFrame
from perfect_assassin.movement.target_tether import TargetTetherIntent


@dataclass(frozen=True, slots=True)
class CombatMotionIntent:
    frame: ContinuousMotionFrame
    state: str
    aligned: bool
    target_identity_crc16: int | None
    reason: str


class FacingTransferProbeController:
    """Bounded LAB controller that measures one signed RMB camera correction.

    It deliberately has no translation, strafe, target acquisition, or action
    capability.  Neutral frames before and after the single impulse make the
    observed screen-space transfer direction measurable without servo feedback.
    """

    def __init__(
        self,
        *,
        signed_delta_x: int,
        warmup_frames: int = 12,
        impulse_frames: int = 8,
    ) -> None:
        if type(signed_delta_x) is not int or signed_delta_x == 0 or abs(signed_delta_x) > 16:
            raise ValueError("facing transfer probe delta is invalid")
        if type(warmup_frames) is not int or not 8 <= warmup_frames <= 20:
            raise ValueError("facing transfer probe warmup is invalid")
        if type(impulse_frames) is not int or not 3 <= impulse_frames <= 8:
            raise ValueError("facing transfer probe impulse duration is invalid")
        self._signed_delta_x = signed_delta_x
        self._warmup_frames = warmup_frames
        self._impulse_frames = impulse_frames
        self.reset()

    def reset(self) -> None:
        self._frame_index = 0
        self._visible_frames = 0
        self._impulses_emitted = 0
        self._target_identity: int | None = None

    def decide(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ) -> CombatMotionIntent:
        target = observation.target
        if (
            not observation.player_alive
            or target is None
            or target.dead
            or target.is_player
            or bearing is None
            or not bearing.is_bound_to(observation)
        ):
            raise RuntimeError("facing transfer probe lost its exact NPC target")
        if self._target_identity is None:
            self._target_identity = target.identity_crc16
        elif target.identity_crc16 != self._target_identity:
            raise RuntimeError("facing transfer probe target continuity changed")

        self._frame_index += 1
        visible = bearing.tracking_state == "VISIBLE"
        if visible:
            self._visible_frames += 1
        impulse = (
            visible
            and self._visible_frames > self._warmup_frames
            and self._impulses_emitted < self._impulse_frames
        )
        if impulse:
            self._impulses_emitted += 1
        state = (
            "CALIBRATION_IMPULSE"
            if impulse
            else "CALIBRATION_OBSERVE"
            if visible
            else "CALIBRATION_OCCLUDED"
        )
        return CombatMotionIntent(
            frame=ContinuousMotionFrame(
                observed_monotonic_s=observation.observed_monotonic_s,
                mouse_look=True,
                mouse_delta_x=self._signed_delta_x if impulse else 0,
                reason=(
                    "single_signed_facing_transfer_impulse"
                    if impulse
                    else "facing_transfer_neutral_observation"
                ),
            ),
            state=state,
            aligned=False,
            target_identity_crc16=target.identity_crc16,
            reason=(
                "single_signed_facing_transfer_impulse"
                if impulse
                else "facing_transfer_neutral_observation"
            ),
        )


class CameraPitchProbeController:
    """One bounded continuous RMB pitch correction with no combat capability."""

    def __init__(self, *, signed_delta_y: int, frames: int = 8) -> None:
        if type(signed_delta_y) is not int or signed_delta_y == 0 or abs(signed_delta_y) > 16:
            raise ValueError("camera pitch probe delta is invalid")
        if type(frames) is not int or not 1 <= frames <= 8:
            raise ValueError("camera pitch probe frame count is invalid")
        self._signed_delta_y = signed_delta_y
        self._frames = frames
        self.reset()

    def reset(self) -> None:
        self._emitted = 0
        self._target_identity: int | None = None

    def decide(self, observation: CombatObservationState, bearing: TargetBearingState | None) -> CombatMotionIntent:
        target = observation.target
        if (
            not observation.player_alive
            or target is None
            or target.dead
            or target.is_player
            or bearing is None
            or not bearing.is_bound_to(observation)
        ):
            raise RuntimeError("camera pitch probe requires one exact live NPC target")
        if self._target_identity is None:
            self._target_identity = target.identity_crc16
        elif target.identity_crc16 != self._target_identity:
            raise RuntimeError("camera pitch probe target continuity changed")
        active = self._emitted < self._frames
        if active:
            self._emitted += 1
        return CombatMotionIntent(
            frame=ContinuousMotionFrame(
                observed_monotonic_s=observation.observed_monotonic_s,
                mouse_look=True,
                mouse_delta_y=self._signed_delta_y if active else 0,
                reason="bounded_continuous_camera_pitch_probe",
            ),
            state="CAMERA_PITCH" if active else "CAMERA_PITCH_SETTLE",
            aligned=False,
            target_identity_crc16=target.identity_crc16,
            reason="bounded_continuous_camera_pitch_probe",
        )
class HumanlikeCombatMotionController:
    """Continuous target-relative movement independent from the spell policy."""

    MOTION_ALIGN_ENTER = 0.08
    MOTION_ALIGN_EXIT = 0.16
    TRANSLATION_FACING_TOLERANCE = 0.08
    APPROACH_ALIGN_EXIT = 0.18
    APPROACH_STABLE_FRAMES = 3
    ORBIT_MOUSE_FEEDFORWARD_PX = 5
    ORBIT_MOUSE_MAX_DELTA_PX = 16
    NAV_GUIDANCE_GAIN_PX_PER_RAD = 28.0
    NAV_GUIDANCE_MAX_DELTA_PX = 12
    NAV_GUIDANCE_SLEW_PX = 3
    NAV_ALIGN_ENTER_RAD = 0.12
    NAV_ALIGN_EXIT_RAD = 0.28
    SERVO_FRAME_RATE_EQUIVALENT_HZ = 11.25
    # Live selected-nameplate probe 06fe1ddb established the TBC 2.4.3 client
    # transfer while RMB is owned: positive Win32 relative mouse-X moved a
    # target already on the right farther right.  Keep the facing controller
    # in logical yaw coordinates and calibrate only this transport boundary.
    LOGICAL_YAW_TO_ACTUATOR_X = -1.0
    # Live Deathknell hunt 355239e6 proved that 36 px/s could keep a valid,
    # selected level-safe NPC outside the frame until the acquisition deadline.
    # 120 px/s remains interpolated by the 120 Hz actuator (<=8 px/tick), while
    # completing a humanlike full-camera reacquisition inside the bounded gate.
    SEARCH_MOUSE_VELOCITY_PX_S = 120.0
    SEARCH_SWEEP_SECONDS = 0.75
    ORBIT_BURST_SECONDS = 0.30
    ORBIT_CYCLE_SECONDS = 1.50
    # A bridge or another narrow client-geometry corridor is not a place for
    # an automatic sideways orbit.  Keep the target-facing servo alive, but
    # wait for a fresh corridor witness when the actor is too close to an edge.
    COMBAT_MIN_EDGE_CLEARANCE_WORLD = 0.65

    TRANSIENT_LOSS_FRAMES = 4

    def __init__(
        self,
        *,
        translation_enabled: bool = True,
        require_tether_for_approach: bool = False,
        allow_non_attackable_npc: bool = False,
        initial_search_direction: str = "RIGHT",
    ) -> None:
        if initial_search_direction not in {"LEFT", "RIGHT"}:
            raise ValueError("initial_search_direction must be LEFT or RIGHT")
        self._facing = ContinuousMagneticFacingController()
        self._translation_enabled = bool(translation_enabled)
        self._require_tether_for_approach = bool(require_tether_for_approach)
        self._allow_non_attackable_npc = bool(allow_non_attackable_npc)
        # Search direction is stored as logical yaw.  Raw mouse-X polarity is
        # applied only when a ContinuousMotionFrame is produced.
        self._initial_search_delta = -4 if initial_search_direction == "LEFT" else 4
        self._target_identity: int | None = None
        self._orbit_control: str | None = None
        self._orbit_started_s: float | None = None
        self._motion_aligned = False
        self._lost_observations = 0
        self._last_movement: str | None = None
        self._last_strafe: str | None = None
        self._last_search_delta: int | None = None
        self._search_started_s: float | None = None
        self._approach_aligned_frames = 0
        self._approach_active = False
        self._tether_intent: TargetTetherIntent | None = None
        self._nav_aligned = False
        self._last_nav_delta_px = 0

    def reset(self) -> None:
        self._facing.reset()
        self._target_identity = None
        self._orbit_control = None
        self._orbit_started_s = None
        self._motion_aligned = False
        self._lost_observations = 0
        self._last_movement = None
        self._last_strafe = None
        self._last_search_delta = None
        self._search_started_s = None
        self._approach_aligned_frames = 0
        self._approach_active = False
        self._tether_intent = None
        self._nav_aligned = False
        self._last_nav_delta_px = 0

    def set_tether_guidance(self, intent: TargetTetherIntent | None) -> None:
        """Attach the latest CRC-bound local navmesh approach evidence."""

        self._tether_intent = intent

    @classmethod
    def _logical_yaw_velocity(cls, logical_delta_px: float) -> float:
        return (
            float(logical_delta_px)
            * cls.SERVO_FRAME_RATE_EQUIVALENT_HZ
            * cls.LOGICAL_YAW_TO_ACTUATOR_X
        )

    @classmethod
    def _logical_search_velocity(cls, logical_delta_px: int) -> float:
        logical_velocity = (
            cls.SEARCH_MOUSE_VELOCITY_PX_S
            if logical_delta_px > 0
            else -cls.SEARCH_MOUSE_VELOCITY_PX_S
        )
        return logical_velocity * cls.LOGICAL_YAW_TO_ACTUATOR_X

    def decide(
        self,
        observation: CombatObservationState,
        bearing: TargetBearingState | None,
    ) -> CombatMotionIntent:
        target = observation.target
        if (
            observation.player_alive
            and target is None
            and bearing is not None
            and bearing.is_bound_to(observation)
            and bearing.tracking_state == "VISIBLE"
        ):
            servo = self._facing.decide(bearing)
            return CombatMotionIntent(
                frame=ContinuousMotionFrame(
                    observed_monotonic_s=observation.observed_monotonic_s,
                    mouse_look=True,
                    mouse_velocity_x_px_s=self._logical_yaw_velocity(
                        servo.mouse_delta_x
                    ),
                    reason="continuous_visible_candidate_alignment",
                ),
                state="CANDIDATE_FACE",
                aligned=servo.aligned,
                target_identity_crc16=None,
                reason="visible_attackable_candidate_alignment",
            )
        if (
            not observation.player_alive
            or target is None
            or target.dead
            or target.is_player
            or (
                not target.attackable_npc
                and not self._allow_non_attackable_npc
            )
            or bearing is None
            or not bearing.is_bound_to(observation)
        ):
            self.reset()
            return CombatMotionIntent(
                ContinuousMotionFrame(observation.observed_monotonic_s),
                "RELEASED",
                False,
                None if target is None else target.identity_crc16,
                "no_exact_visible_npc_target",
            )

        if bearing.tracking_state != "VISIBLE":
            if target.identity_crc16 != self._target_identity:
                self._target_identity = target.identity_crc16
                self._lost_observations = 0
                self._last_movement = None
                self._last_strafe = None
                self._last_search_delta = None
                self._search_started_s = None
                self._approach_aligned_frames = 0
                self._approach_active = False
            self._lost_observations += 1
            if self._lost_observations <= self.TRANSIENT_LOSS_FRAMES:
                # Never coast blindly toward or around a target whose exact
                # screen bearing just disappeared. A human player releases
                # translation for this short visual pause while keeping RMB
                # held, then resumes from a fresh range+bearing frame.
                self._last_movement = None
                self._last_strafe = None
                self._approach_aligned_frames = 0
                self._approach_active = False
                return CombatMotionIntent(
                    frame=ContinuousMotionFrame(
                        observed_monotonic_s=observation.observed_monotonic_s,
                        mouse_look=True,
                        reason="transient_target_marker_occlusion_hold",
                    ),
                    state="HOLD_OCCLUSION",
                    aligned=False,
                    target_identity_crc16=target.identity_crc16,
                    reason="selected_target_marker_transiently_occluded",
                )
            if (
                self._require_tether_for_approach
                and self._tether_intent is not None
                and self._tether_intent.state
                in {
                    "WAITING_NAVMESH",
                    "PARTIAL_BLOCKED",
                    "PARTIAL_ADVANCE_DIRECT",
                    "PARTIAL_ADVANCE_LEFT",
                    "PARTIAL_ADVANCE_RIGHT",
                }
            ):
                # The last fresh visible frame already said that the local
                # target line had no confirmed traversable corridor.  Rotating
                # farther after the marker vanishes only buries the camera in
                # the wall.  Stop input and hand the situation to the world
                # navigation layer, which can choose a new vantage point.
                return CombatMotionIntent(
                    frame=ContinuousMotionFrame(
                        observed_monotonic_s=observation.observed_monotonic_s,
                        mouse_look=True,
                        reason="blocked_target_requires_world_reposition",
                    ),
                    state="HOLD_WORLD_REPOSITION",
                    aligned=False,
                    target_identity_crc16=target.identity_crc16,
                    reason="navmesh_blocked_target_marker_occluded",
                )
            # Keep one continuous mouse-look search instead of emitting turn
            # taps.  The deterministic CRC chooses a stable direction until
            # the selected-target marker re-enters the frame.
            search_delta = self._last_search_delta
            if search_delta is None:
                search_delta = self._initial_search_delta
            if self._search_started_s is None:
                self._search_started_s = observation.observed_monotonic_s
            search_elapsed_s = max(
                0.0,
                observation.observed_monotonic_s - self._search_started_s,
            )
            if search_elapsed_s > self.SEARCH_SWEEP_SECONDS:
                return CombatMotionIntent(
                    frame=ContinuousMotionFrame(
                        observed_monotonic_s=observation.observed_monotonic_s,
                        mouse_look=True,
                        reason="lost_target_requires_world_reposition",
                    ),
                    state="HOLD_LOST_TARGET",
                    aligned=False,
                    target_identity_crc16=target.identity_crc16,
                    reason="bounded_visual_sweep_exhausted",
                )
            search_velocity = self._logical_search_velocity(search_delta)
            return CombatMotionIntent(
                frame=ContinuousMotionFrame(
                    observed_monotonic_s=observation.observed_monotonic_s,
                    mouse_look=True,
                    mouse_velocity_x_px_s=search_velocity,
                    reason="continuous_selected_target_reacquisition",
                ),
                state="SEARCH",
                aligned=False,
                target_identity_crc16=target.identity_crc16,
                reason="selected_target_marker_not_visible",
            )

        self._lost_observations = 0
        self._search_started_s = None
        servo = self._facing.decide(bearing)
        if servo.mouse_delta_x:
            self._last_search_delta = servo.mouse_delta_x
        if target.identity_crc16 != self._target_identity:
            self._target_identity = target.identity_crc16
            self._motion_aligned = False
            self._approach_aligned_frames = 0
            self._approach_active = False
            self._orbit_control = (
                "STRAFE_LEFT" if target.identity_crc16 & 1 else "STRAFE_RIGHT"
            )
            self._orbit_started_s = None

        facing_error = abs(bearing.offset_x_normalized or 0.0)
        if self._motion_aligned:
            if facing_error >= self.MOTION_ALIGN_EXIT:
                self._motion_aligned = False
        elif facing_error <= self.MOTION_ALIGN_ENTER:
            self._motion_aligned = True

        known_ranges = tuple(
            action.in_range
            for action in (observation.attack, observation.sinister_strike)
            if action.in_range is not None
        )
        melee_witness = True if any(known_ranges) else False if known_ranges else None
        melee_band = ROGUE_MELEE_RANGE.classify(client_in_range=melee_witness)
        out_of_melee = melee_band is RangeBand.TOO_FAR
        in_melee = melee_band is RangeBand.IN_RANGE
        filtered_facing_error = abs(servo.error_x_normalized or 0.0)
        if not out_of_melee or not self._translation_enabled:
            self._approach_aligned_frames = 0
            self._approach_active = False
        elif self._approach_active:
            if filtered_facing_error >= self.APPROACH_ALIGN_EXIT:
                self._approach_active = False
                self._approach_aligned_frames = 0
        elif filtered_facing_error <= self.TRANSLATION_FACING_TOLERANCE:
            self._approach_aligned_frames += 1
            if self._approach_aligned_frames >= self.APPROACH_STABLE_FRAMES:
                self._approach_active = True
        else:
            self._approach_aligned_frames = 0
        # Screen-edge bearing is not a distance witness.  The former
        # MOVE_BACKWARD escape treated an off-centre target as physical model
        # overlap and produced a visibly robotic back-step.  Backward movement
        # stays disabled until a real too-close/proximity observation exists.
        overlap_escape = False
        tether = self._tether_intent
        tether_blocks_blind_forward = (
            out_of_melee
            and (
                (self._require_tether_for_approach and tether is None)
                or (
                    tether is not None
                    and tether.state in {"WAITING_NAVMESH", "PARTIAL_BLOCKED"}
                )
            )
        )
        tether_detour = (
            out_of_melee
            and tether is not None
            and tether.state in {
                "DETOUR_LEFT",
                "DETOUR_RIGHT",
                "PARTIAL_ADVANCE_DIRECT",
                "PARTIAL_ADVANCE_LEFT",
                "PARTIAL_ADVANCE_RIGHT",
            }
            and tether.guidance_error_rad is not None
        )
        tether_partial_advance = bool(
            tether is not None and tether.state.startswith("PARTIAL_ADVANCE_")
        )
        corridor_edge_limited = bool(
            tether is not None
            and tether.corridor_edge_clearance_world is not None
            and (
                tether.corridor_edge_safe is False
                or tether.corridor_edge_clearance_world
                < self.COMBAT_MIN_EDGE_CLEARANCE_WORLD
            )
        )
        if tether_detour:
            guidance_error = tether.guidance_error_rad or 0.0
            if self._nav_aligned:
                if abs(guidance_error) >= self.NAV_ALIGN_EXIT_RAD:
                    self._nav_aligned = False
            elif abs(guidance_error) <= self.NAV_ALIGN_ENTER_RAD:
                self._nav_aligned = True

            requested_nav_delta = max(
                -self.NAV_GUIDANCE_MAX_DELTA_PX,
                min(
                    self.NAV_GUIDANCE_MAX_DELTA_PX,
                    round(-guidance_error * self.NAV_GUIDANCE_GAIN_PX_PER_RAD),
                ),
            )
            self._last_nav_delta_px = max(
                self._last_nav_delta_px - self.NAV_GUIDANCE_SLEW_PX,
                min(
                    self._last_nav_delta_px + self.NAV_GUIDANCE_SLEW_PX,
                    requested_nav_delta,
                ),
            )
        else:
            self._nav_aligned = False
            self._last_nav_delta_px = 0
        movement = (
            "MOVE_BACKWARD"
            if overlap_escape
            else "MOVE_FORWARD" if (
                self._translation_enabled
                and out_of_melee
                and not tether_blocks_blind_forward
                and (
                    self._nav_aligned
                    if tether_detour
                    else self._approach_active
                )
            )
            else None
        )
        orbit_requested = (
            self._translation_enabled
            and observation.in_combat
            and in_melee
            and self._motion_aligned
        )
        lane_guard = orbit_requested and corridor_edge_limited
        orbit_ready = orbit_requested and not corridor_edge_limited
        if orbit_ready and self._orbit_started_s is None:
            self._orbit_started_s = observation.observed_monotonic_s
        if not orbit_ready:
            self._orbit_started_s = None
        orbit_phase_s = (
            None
            if self._orbit_started_s is None
            else (observation.observed_monotonic_s - self._orbit_started_s)
            % self.ORBIT_CYCLE_SECONDS
        )
        strafe = (
            None
            if tether_detour
            else self._orbit_control
            if orbit_phase_s is not None and orbit_phase_s < self.ORBIT_BURST_SECONDS
            else None
        )
        self._last_movement = movement
        self._last_strafe = strafe
        # A traversable detour is world navigation, not combat orbiting.  Face
        # the navmesh corridor while it is needed; otherwise the visual target
        # servo points through the obstacle and W walks directly into the wall.
        # Once the tether becomes direct, target-relative magnetic facing owns
        # yaw again without any route-specific hardcoded path.
        mouse_delta_x = (
            self._last_nav_delta_px if tether_detour else servo.mouse_delta_x
        )
        if strafe == "STRAFE_RIGHT":
            # A right strafe moves the target left on screen. Turn left at the
            # same instant instead of waiting for the next visual error frame.
            mouse_delta_x = max(
                -self.ORBIT_MOUSE_MAX_DELTA_PX,
                mouse_delta_x - self.ORBIT_MOUSE_FEEDFORWARD_PX,
            )
        elif strafe == "STRAFE_LEFT":
            mouse_delta_x = min(
                self.ORBIT_MOUSE_MAX_DELTA_PX,
                mouse_delta_x + self.ORBIT_MOUSE_FEEDFORWARD_PX,
            )
        state = (
            "OVERLAP_ESCAPE"
            if overlap_escape
            else "LANE_GUARD"
            if lane_guard
            else "TETHER_BLOCKED"
            if tether_blocks_blind_forward
            else "TETHER_DETOUR"
            if tether_detour and not tether_partial_advance
            else "TETHER_PARTIAL_ADVANCE"
            if tether_partial_advance
            else "APPROACH"
            if movement is not None
            else "ORBIT"
            if strafe is not None
            else "FACE"
            if not servo.aligned
            else "LOCK"
        )
        return CombatMotionIntent(
            frame=ContinuousMotionFrame(
                observed_monotonic_s=observation.observed_monotonic_s,
                movement=movement,
                strafe=strafe,
                # Keep RMB down even inside the deadband.  This is what makes
                # A/D true target-relative strafing rather than keyboard turn.
                mouse_look=True,
                mouse_velocity_x_px_s=(
                    self._logical_yaw_velocity(mouse_delta_x)
                ),
                reason="target_relative_mouse_look_and_held_movement",
            ),
            state=state,
            aligned=self._nav_aligned if tether_detour else servo.aligned,
            target_identity_crc16=target.identity_crc16,
            reason=(
                "combat_lane_edge_clearance_guard"
                if lane_guard
                else
                "navmesh_corridor_heading_control"
                if tether_detour
                else servo.reason
            ),
        )
