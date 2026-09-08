from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from perfect_assassin.domain.motion import (
    CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S,
    HELD_MOVEMENT_CONTROLS,
    ContinuousMotionFrame,
)

__all__ = [
    "CONTINUOUS_MOUSE_VELOCITY_LIMIT_PX_S",
    "HELD_MOVEMENT_CONTROLS",
    "ContinuousInputStateMachine",
    "ContinuousInputTransition",
    "ContinuousMotionFrame",
]


@dataclass(frozen=True, slots=True)
class ContinuousInputTransition:
    key_up: tuple[str, ...]
    key_down: tuple[str, ...]
    mouse_look_up: bool
    mouse_look_down: bool
    mouse_delta_x: int
    mouse_delta_y: int
    mouse_velocity_x_px_s: float
    mouse_velocity_y_px_s: float

    @property
    def state_changed(self) -> bool:
        return bool(
            self.key_up
            or self.key_down
            or self.mouse_look_up
            or self.mouse_look_down
        )


class ContinuousInputStateMachine:
    """Pure transition compiler for humanlike held movement controls."""

    _ORDER: ClassVar[dict[str, int]] = {
        "MOVE_FORWARD": 0,
        "MOVE_BACKWARD": 1,
        "STRAFE_LEFT": 2,
        "STRAFE_RIGHT": 3,
    }

    def __init__(self) -> None:
        self._held_controls: frozenset[str] = frozenset()
        self._mouse_look = False

    @property
    def held_controls(self) -> frozenset[str]:
        return self._held_controls

    @property
    def mouse_look(self) -> bool:
        return self._mouse_look

    def step(self, frame: ContinuousMotionFrame) -> ContinuousInputTransition:
        if not isinstance(frame, ContinuousMotionFrame):
            raise ValueError("continuous input frame type is invalid")
        desired = frame.held_controls
        released = tuple(
            sorted(self._held_controls - desired, key=self._ORDER.__getitem__)
        )
        pressed = tuple(sorted(desired - self._held_controls, key=self._ORDER.__getitem__))
        mouse_up = self._mouse_look and not frame.mouse_look
        mouse_down = frame.mouse_look and not self._mouse_look
        self._held_controls = desired
        self._mouse_look = frame.mouse_look
        return ContinuousInputTransition(
            key_up=released,
            key_down=pressed,
            mouse_look_up=mouse_up,
            mouse_look_down=mouse_down,
            mouse_delta_x=frame.mouse_delta_x,
            mouse_delta_y=frame.mouse_delta_y,
            mouse_velocity_x_px_s=float(frame.mouse_velocity_x_px_s),
            mouse_velocity_y_px_s=float(frame.mouse_velocity_y_px_s),
        )

    def release(self) -> ContinuousInputTransition:
        frame = ContinuousMotionFrame(observed_monotonic_s=0.0)
        return self.step(frame)
