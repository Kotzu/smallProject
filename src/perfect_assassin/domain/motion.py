from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


HELD_MOVEMENT_CONTROLS = frozenset(
    {"MOVE_FORWARD", "MOVE_BACKWARD", "STRAFE_LEFT", "STRAFE_RIGHT"}
)
CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S = 960.0


@dataclass(frozen=True, slots=True)
class ContinuousMotionFrame:
    """A non-authoritative desired held-input state for one control frame."""

    observed_monotonic_s: float
    movement: str | None = None
    strafe: str | None = None
    mouse_look: bool = False
    mouse_delta_x: int = 0
    mouse_delta_y: int = 0
    mouse_velocity_x_px_s: float = 0.0
    mouse_velocity_y_px_s: float = 0.0
    reason: str = "closed_loop_hold_state"

    def __post_init__(self) -> None:
        if not isfinite(self.observed_monotonic_s) or self.observed_monotonic_s < 0:
            raise ValueError("continuous motion observation time is invalid")
        if self.movement not in {None, "MOVE_FORWARD", "MOVE_BACKWARD"}:
            raise ValueError("continuous motion longitudinal state is invalid")
        if self.strafe not in {None, "STRAFE_LEFT", "STRAFE_RIGHT"}:
            raise ValueError("continuous motion strafe state is invalid")
        if not isinstance(self.mouse_look, bool):
            raise ValueError("continuous motion mouse-look state is invalid")
        for name in ("mouse_delta_x", "mouse_delta_y"):
            value = getattr(self, name)
            if type(value) is not int or not -16 <= value <= 16:
                raise ValueError(f"{name} is outside the continuous correction bound")
        for name in ("mouse_velocity_x_px_s", "mouse_velocity_y_px_s"):
            value = getattr(self, name)
            if (
                type(value) not in {int, float}
                or not isfinite(value)
                or not -CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S
                <= value
                <= CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S
            ):
                raise ValueError(f"{name} is outside the continuous velocity bound")
        if (self.mouse_delta_x or self.mouse_delta_y) and (
            self.mouse_velocity_x_px_s or self.mouse_velocity_y_px_s
        ):
            raise ValueError("mouse impulse and velocity are mutually exclusive")
        if not self.mouse_look and (
            self.mouse_delta_x
            or self.mouse_delta_y
            or self.mouse_velocity_x_px_s
            or self.mouse_velocity_y_px_s
        ):
            raise ValueError("mouse correction requires held mouse-look")
        if not isinstance(self.reason, str) or not self.reason or len(self.reason) > 160:
            raise ValueError("continuous motion reason is invalid")

    @property
    def held_controls(self) -> frozenset[str]:
        return frozenset(
            control for control in (self.movement, self.strafe) if control is not None
        )


__all__ = [
    "CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S",
    "ContinuousMotionFrame",
    "HELD_MOVEMENT_CONTROLS",
]
