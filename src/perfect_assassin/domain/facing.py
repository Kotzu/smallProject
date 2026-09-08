from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from perfect_assassin.domain.combat import TargetBearingState


@dataclass(frozen=True, slots=True)
class FacingIntent:
    control: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class FacingServoIntent:
    """One fresh-frame correction for a camera-coupled facing servo."""

    state: str
    mouse_delta_x: int
    hold_turn_mode: bool
    aligned: bool
    error_x_normalized: float | None
    target_identity_crc16: int | None
    reason: str


class ContinuousMagneticFacingController:
    """Target-relative visual servo; it never owns input or combat authority.

    Positive screen error means the selected target is to the right.  The
    returned delta is a logical yaw command (positive means yaw right), not a
    raw transport delta.  The live-input adapter owns the client-specific
    mapping between logical yaw and Win32 relative mouse-X.
    Hysteresis prevents chatter on the center line.  The controller predicts
    where the target will be after the measured capture/input latency and
    starts braking before the rendered marker crosses the center line.
    """

    def __init__(
        self,
        *,
        engage_tolerance: float = 0.075,
        release_tolerance: float = 0.030,
        proportional_gain_px: float = 90.0,
        prediction_horizon_s: float = 0.18,
        prediction_coast_tolerance: float = 0.012,
        max_delta_px: int = 16,
        filter_alpha: float = 0.65,
        derivative_filter_alpha: float = 1.0,
        acceleration_slew_px: int = 3,
        braking_slew_px: int = 6,
    ) -> None:
        if not 0 < release_tolerance < engage_tolerance < 0.25:
            raise ValueError("facing servo tolerances are invalid")
        if not 1 <= max_delta_px <= 16:
            raise ValueError("facing servo delta limit is invalid")
        if not 0 < filter_alpha <= 1:
            raise ValueError("facing servo filter is invalid")
        if not 0 < derivative_filter_alpha <= 1:
            raise ValueError("facing servo derivative filter is invalid")
        if proportional_gain_px <= 0:
            raise ValueError("facing servo gains are invalid")
        if not 0 <= prediction_horizon_s <= 0.45:
            raise ValueError("facing servo prediction horizon is invalid")
        if not 0 <= prediction_coast_tolerance < release_tolerance:
            raise ValueError("facing servo coast tolerance is invalid")
        if not 1 <= acceleration_slew_px <= max_delta_px:
            raise ValueError("facing servo acceleration slew is invalid")
        if not acceleration_slew_px <= braking_slew_px <= max_delta_px:
            raise ValueError("facing servo braking slew is invalid")
        self._engage_tolerance = float(engage_tolerance)
        self._release_tolerance = float(release_tolerance)
        self._kp = float(proportional_gain_px)
        self._prediction_horizon_s = float(prediction_horizon_s)
        self._prediction_coast_tolerance = float(prediction_coast_tolerance)
        self._max_delta_px = int(max_delta_px)
        self._alpha = float(filter_alpha)
        self._derivative_alpha = float(derivative_filter_alpha)
        self._acceleration_slew_px = int(acceleration_slew_px)
        self._braking_slew_px = int(braking_slew_px)
        self.reset()

    def reset(self) -> None:
        self._target_identity_crc16: int | None = None
        self._filtered_error: float | None = None
        self._previous_error: float | None = None
        self._previous_observed_s: float | None = None
        self._filtered_derivative = 0.0
        self._previous_command_px = 0
        self._aligned = False

    def decide(self, bearing: TargetBearingState) -> FacingServoIntent:
        if bearing.tracking_state != "VISIBLE":
            self.reset()
            return FacingServoIntent(
                "LOST", 0, False, False, None,
                bearing.target_identity_crc16,
                "selected_target_visual_lock_unavailable",
            )
        error = bearing.offset_x_normalized
        if error is None or not isfinite(error):
            raise ValueError("visible target bearing has no finite offset")
        if bearing.target_identity_crc16 != self._target_identity_crc16:
            self.reset()
            self._target_identity_crc16 = bearing.target_identity_crc16

        filtered = (
            error
            if self._filtered_error is None
            else self._alpha * error + (1.0 - self._alpha) * self._filtered_error
        )
        threshold = (
            self._engage_tolerance if self._aligned else self._release_tolerance
        )
        aligned = abs(filtered) <= threshold
        self._aligned = aligned

        derivative = 0.0
        if (
            self._previous_error is not None
            and self._previous_observed_s is not None
        ):
            dt = bearing.observed_monotonic_s - self._previous_observed_s
            if 0.005 <= dt <= 0.45:
                derivative = (filtered - self._previous_error) / dt
        self._filtered_error = filtered
        self._previous_error = filtered
        self._previous_observed_s = bearing.observed_monotonic_s

        if aligned:
            self._previous_command_px = 0
            return FacingServoIntent(
                "ALIGNED", 0, False, True, filtered,
                bearing.target_identity_crc16,
                "selected_target_inside_magnetic_deadband",
            )

        self._filtered_derivative = (
            self._derivative_alpha * derivative
            + (1.0 - self._derivative_alpha) * self._filtered_derivative
        )
        projected = (
            filtered
            + self._filtered_derivative * self._prediction_horizon_s
        )
        if abs(projected) <= self._prediction_coast_tolerance:
            self._previous_command_px = 0
            return FacingServoIntent(
                "COAST", 0, True, False, filtered,
                bearing.target_identity_crc16,
                "latency_compensated_center_crossing_brake",
            )
        requested = self._kp * projected
        magnitude = max(1, min(self._max_delta_px, round(abs(requested))))
        requested_delta = magnitude if requested > 0 else -magnitude
        # A human RMB turn brakes before it reverses.  Jumping directly from a
        # full left correction to a full right correction is the visible
        # frame-by-frame wobble we are explicitly trying to remove.
        slew_target = requested_delta
        if self._previous_command_px * requested_delta < 0:
            slew_target = 0
        slew = (
            self._braking_slew_px
            if abs(slew_target) < abs(self._previous_command_px)
            else self._acceleration_slew_px
        )
        delta = max(
            self._previous_command_px - slew,
            min(self._previous_command_px + slew, slew_target),
        )
        self._previous_command_px = delta
        return FacingServoIntent(
            "TRACK", delta, True, False, filtered,
            bearing.target_identity_crc16,
            "fresh_frame_latency_compensated_correction",
        )


def bearing_refinement_is_compatible(
    coarse: TargetBearingState,
    refined: TargetBearingState,
    *,
    conflict_threshold: float = 0.12,
) -> bool:
    """Reject colour geometry that contradicts the exact selected nameplate.

    The addon bearing is bound to the target's exact name and selected state.
    Pixel geometry may refine its coarse bucket, but an unrelated coloured arc
    on the opposite half of the screen must never reverse that trusted axis.
    A narrow center-line disagreement remains valid to remove bucket chatter.
    """

    if not 0 < conflict_threshold < 0.25:
        raise ValueError("bearing refinement conflict threshold is invalid")
    if (
        coarse.tracking_state != "VISIBLE"
        or refined.tracking_state != "VISIBLE"
        or coarse.target_identity_crc16 != refined.target_identity_crc16
    ):
        return False
    coarse_offset = coarse.offset_x_normalized
    refined_offset = refined.offset_x_normalized
    if coarse_offset is None or refined_offset is None:
        return False
    opposing_halves = coarse_offset * refined_offset < 0
    material_conflict = (
        abs(coarse_offset) >= conflict_threshold
        and abs(refined_offset) >= conflict_threshold
    )
    return not (opposing_halves and material_conflict)


class MagneticFacingController:
    """Compatibility policy for the categorical combat decision layer."""

    def decide(self, bearing: TargetBearingState) -> FacingIntent:
        if bearing.tracking_state != "VISIBLE":
            return FacingIntent("TURN_RIGHT", "selected_target_not_visible")
        if bearing.direction == "LEFT":
            return FacingIntent("TURN_LEFT", "selected_target_visible_left")
        if bearing.direction == "RIGHT":
            return FacingIntent("TURN_RIGHT", "selected_target_visible_right")
        if bearing.direction == "CENTER":
            return FacingIntent(None, "selected_target_centered")
        raise ValueError("visible target bearing has no exact direction")
