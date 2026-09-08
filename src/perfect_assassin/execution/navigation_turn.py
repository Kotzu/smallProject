from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from perfect_assassin.execution.contracts import (
    MOVEMENT_EXECUTION_CAPABILITY, MOVEMENT_MODE, AuthorityBinding,
)


NAVIGATION_TURN_DELTA_TO_HOLD_MS = {
    1: 25, 2: 25, 3: 25, 4: 25,
    5: 25, 6: 25, 7: 25, 8: 30,
    14: 35, 28: 50,
}


@dataclass(frozen=True, slots=True)
class NavigationTurnPrimitive:
    primitive_id: str
    lease_id: str
    binding: AuthorityBinding
    owner_id: str
    runtime_arm_nonce: str
    mode: str
    capability: str
    sequence: int
    controls: tuple[str, ...]
    hold_duration_ms: int
    max_execution_envelope_ms: int
    mouse_delta_x: int
    clock_id: str
    issued_at_monotonic_ms: float
    expires_at_monotonic_ms: float

    def __post_init__(self) -> None:
        if self.mode != MOVEMENT_MODE or self.capability != MOVEMENT_EXECUTION_CAPABILITY:
            raise ValueError("navigation turn mode/capability mismatch")
        if self.controls not in {("TURN_LEFT",), ("TURN_RIGHT",)}:
            raise ValueError("navigation turn control is invalid")
        expected = NAVIGATION_TURN_DELTA_TO_HOLD_MS.get(abs(self.mouse_delta_x))
        if expected is None or self.hold_duration_ms != expected:
            raise ValueError("navigation mouse delta/timing is invalid")
        if self.max_execution_envelope_ms != self.hold_duration_ms + 100:
            raise ValueError("navigation turn envelope is invalid")
        if self.sequence <= 0 or not all(
            isinstance(value, str) and value
            for value in (
                self.primitive_id, self.lease_id, self.owner_id,
                self.runtime_arm_nonce, self.clock_id,
            )
        ):
            raise ValueError("navigation turn identity is invalid")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
            for value in (self.issued_at_monotonic_ms, self.expires_at_monotonic_ms)
        ):
            raise ValueError("navigation turn time is invalid")
        if (
            self.issued_at_monotonic_ms < 0
            or self.expires_at_monotonic_ms
            < self.issued_at_monotonic_ms + self.max_execution_envelope_ms
            or self.expires_at_monotonic_ms - self.issued_at_monotonic_ms > 2_000
        ):
            raise ValueError("navigation turn lifetime is invalid")
