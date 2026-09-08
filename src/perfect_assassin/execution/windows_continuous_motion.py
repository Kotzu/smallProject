from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from threading import Condition, RLock, Thread
import time
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

from perfect_assassin.execution.continuous_motion import (
    ContinuousInputStateMachine,
    ContinuousMotionFrame,
)
from perfect_assassin.execution.ports import CooperativeCancellation, InputCancelledError, MonotonicClock
from perfect_assassin.execution.windows_mouse_turn import WindowsCursorPlacement
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsInputSinkError,
    WindowsInputTargetBinding,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)


CONTINUOUS_CONTROL_VIRTUAL_KEYS: Mapping[str, int] = MappingProxyType(
    {
        "MOVE_FORWARD": 0x57,
        "MOVE_BACKWARD": 0x53,
        "STRAFE_LEFT": 0x41,
        "STRAFE_RIGHT": 0x44,
    }
)
# Navigation capture is bounded at 300 ms.  Keep the frame lease aligned with
# that bound so a valid client frame is not rejected merely because DXGI and
# the local navmesh planner consumed one capture interval.  The independent
# actuator watchdog remains shorter than a stale-input hazard window.
CONTINUOUS_FRAME_MAX_AGE_MS = 300.0
# The full perception + policy loop can legitimately take about 300 ms on the
# bound 4K LAB client.  A 220 ms lease therefore released RMB between fresh
# frames and turned continuous tracking back into repeated button impulses.
# Keep one held state across that measured gap while remaining fail-safe well
# below one second if perception or the runner stalls.
CONTINUOUS_LEASE_TIMEOUT_MS = 450
MOUSE_VELOCITY_HZ = 120.0
MOUSE_VELOCITY_TICK_S = 1.0 / MOUSE_VELOCITY_HZ
# Eight-pixel relative steps at 120 Hz permit a humanlike bounded pivot while
# remaining temporally smooth. Normal corridor corrections are much smaller;
# this is the actuator ceiling, not the ordinary command size.
MOUSE_VELOCITY_MAX_STEP_PX = 8
MOUSE_LOOK_SETTLE_S = 0.020
MOUSE_UP_SETTLE_S = 0.050


class WindowsContinuousMotionBackend(Protocol):
    def map_virtual_key(self, virtual_key: int) -> int: ...

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt: ...

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot: ...

    def send_scan_code(self, scan_code: int, *, key_up: bool) -> int: ...

    def send_turn_mode_key(self, *, key_up: bool) -> int: ...

    def prepare_world_drag_cursor(self, *, hwnd: int) -> WindowsCursorPlacement: ...

    def restore_cursor_position(self, placement: WindowsCursorPlacement) -> int: ...

    def send_relative_mouse(self, *, delta_x: int, delta_y: int) -> int: ...

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ContinuousMotionReceipt:
    held_controls: tuple[str, ...]
    mouse_look_held: bool
    state_changed: bool
    mouse_delta_x: int
    mouse_delta_y: int
    mouse_velocity_x_px_s: float
    mouse_velocity_y_px_s: float
    lease_deadline_monotonic_ms: float


class WindowsContinuousMotionSession:
    """Exact-target held W/A/S/D + RMB transport refreshed by 20 Hz frames.

    The session emits key/button transitions only when desired state changes.
    A local watchdog is release-only: if fresh frames stop, every owned key and
    RMB is released without waiting for the planner, capture loop, or model.
    """

    supports_cooperative_cancellation = True
    max_apply_block_ms = 75

    def __init__(
        self,
        *,
        target: WindowsInputTargetBinding,
        backend: WindowsContinuousMotionBackend,
        clock: MonotonicClock,
        expires_at_monotonic_ms: float,
        lease_timeout_ms: int = CONTINUOUS_LEASE_TIMEOUT_MS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(target, WindowsInputTargetBinding):
            raise ValueError("continuous motion target binding is invalid")
        if (
            not isfinite(expires_at_monotonic_ms)
            or expires_at_monotonic_ms <= clock.now_ms()
        ):
            raise ValueError("continuous motion authority expiry is invalid")
        if type(lease_timeout_ms) is not int or not 120 <= lease_timeout_ms <= 500:
            raise ValueError("continuous motion lease timeout is invalid")
        if not callable(sleeper):
            raise ValueError("continuous motion sleeper is invalid")
        receipt = backend.prevalidate_target(target)
        if not isinstance(receipt, WindowsTargetIdentityReceipt) or receipt.target != target:
            if isinstance(receipt, WindowsTargetIdentityReceipt):
                backend.release_identity_receipt(receipt)
            raise WindowsTargetBindingError("continuous motion receipt target diverges")
        scan_codes: dict[str, int] = {}
        for control, virtual_key in CONTINUOUS_CONTROL_VIRTUAL_KEYS.items():
            scan_code = backend.map_virtual_key(virtual_key)
            if type(scan_code) is not int or not 1 <= scan_code <= 0xFF:
                backend.release_identity_receipt(receipt)
                raise WindowsInputSinkError("continuous motion scan code is invalid")
            scan_codes[control] = scan_code
        if len(set(scan_codes.values())) != len(scan_codes):
            backend.release_identity_receipt(receipt)
            raise WindowsInputSinkError("continuous motion scan codes collide")

        self._target = target
        self._backend = backend
        self._clock = clock
        self._expires_at_ms = float(expires_at_monotonic_ms)
        self._lease_timeout_ms = lease_timeout_ms
        self._sleeper = sleeper
        self._receipt = receipt
        self._scan_codes = MappingProxyType(scan_codes)
        self._machine = ContinuousInputStateMachine()
        self._owned_controls: set[str] = set()
        self._mouse_owned = False
        self._cursor_placement: WindowsCursorPlacement | None = None
        self._lease_deadline_ms = 0.0
        self._mouse_velocity_x = 0.0
        self._mouse_velocity_y = 0.0
        self._mouse_fraction_x = 0.0
        self._mouse_fraction_y = 0.0
        self._closed = False
        self._lock = RLock()
        self._watchdog_condition = Condition(self._lock)
        self._watchdog_thread = Thread(
            target=self._watchdog_loop,
            name="perfect-assassin-continuous-motion-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()
        self._velocity_thread = Thread(
            target=self._mouse_velocity_loop,
            name="perfect-assassin-mouse-velocity-actuator",
            daemon=True,
        )
        self._velocity_thread.start()

    @property
    def held_controls(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._owned_controls))

    @property
    def mouse_look_held(self) -> bool:
        with self._lock:
            return self._mouse_owned

    def renew_authority_expiry(self, expires_at_monotonic_ms: float) -> bool:
        """Extend the same reviewed session without releasing held controls."""

        with self._lock:
            if self._closed:
                raise WindowsInputSinkError("continuous motion session is closed")
            now_ms = self._read_now()
            if (
                not isfinite(expires_at_monotonic_ms)
                or expires_at_monotonic_ms <= now_ms
            ):
                raise WindowsInputSinkError(
                    "renewed continuous motion authority expiry is invalid"
                )
            if expires_at_monotonic_ms <= self._expires_at_ms:
                return False
            self._expires_at_ms = float(expires_at_monotonic_ms)
            if self._lease_deadline_ms > 0.0:
                self._lease_deadline_ms = min(
                    now_ms + self._lease_timeout_ms,
                    self._expires_at_ms,
                )
                self._arm_watchdog()
            return True

    def apply_frame(
        self,
        frame: ContinuousMotionFrame,
        cancellation: CooperativeCancellation,
    ) -> ContinuousMotionReceipt:
        if not isinstance(frame, ContinuousMotionFrame):
            raise ValueError("continuous motion frame type is invalid")
        if not isinstance(cancellation, CooperativeCancellation):
            raise ValueError("continuous motion cancellation type is invalid")
        with self._lock:
            try:
                if self._closed:
                    raise WindowsInputSinkError("continuous motion session is closed")
                if cancellation.is_cancelled:
                    raise InputCancelledError("continuous motion was cancelled")
                now_ms = self._read_now()
                if now_ms >= self._expires_at_ms:
                    raise WindowsInputSinkError("continuous motion authority expired")
                age_ms = now_ms - frame.observed_monotonic_s * 1000.0
                if age_ms < -5.0 or age_ms > CONTINUOUS_FRAME_MAX_AGE_MS:
                    raise WindowsInputSinkError("continuous motion frame is stale")
                self._assert_exact_hot()
                transition = self._machine.step(frame)

                for control in transition.key_up:
                    self._release_control(control)
                if transition.mouse_look_up:
                    self._release_mouse_look()
                for control in transition.key_down:
                    self._press_control(control)
                if transition.mouse_look_down:
                    self._press_mouse_look()
                if transition.mouse_delta_x or transition.mouse_delta_y:
                    if not self._mouse_owned:
                        raise WindowsInputSinkError("mouse correction lost RMB ownership")
                    submitted = self._backend.send_relative_mouse(
                        delta_x=transition.mouse_delta_x,
                        delta_y=transition.mouse_delta_y,
                    )
                    if type(submitted) is not int or submitted != 1:
                        raise WindowsInputSinkError("continuous relative mouse input was not exact")
                self._set_mouse_velocity(
                    transition.mouse_velocity_x_px_s,
                    transition.mouse_velocity_y_px_s,
                )

                self._lease_deadline_ms = min(
                    now_ms + self._lease_timeout_ms,
                    self._expires_at_ms,
                )
                self._arm_watchdog()
                return ContinuousMotionReceipt(
                    held_controls=self.held_controls,
                    mouse_look_held=self._mouse_owned,
                    state_changed=transition.state_changed,
                    mouse_delta_x=transition.mouse_delta_x,
                    mouse_delta_y=transition.mouse_delta_y,
                    mouse_velocity_x_px_s=transition.mouse_velocity_x_px_s,
                    mouse_velocity_y_px_s=transition.mouse_velocity_y_px_s,
                    lease_deadline_monotonic_ms=self._lease_deadline_ms,
                )
            except BaseException:
                self._release_all_locked()
                raise

    def release_all(self) -> None:
        with self._lock:
            self._release_all_locked()

    def close(self) -> None:
        watchdog = self._watchdog_thread
        velocity = self._velocity_thread
        with self._lock:
            if self._closed:
                return
            self._closed = True
            release_error: BaseException | None = None
            try:
                self._release_all_locked()
            except BaseException as error:
                release_error = error
            try:
                self._backend.release_identity_receipt(self._receipt)
            except BaseException as error:
                if release_error is None:
                    release_error = error
            self._watchdog_condition.notify_all()
        if watchdog.is_alive():
            watchdog.join(timeout=0.5)
        if velocity.is_alive():
            velocity.join(timeout=0.5)
        if watchdog.is_alive() and release_error is None:
            release_error = WindowsInputSinkError(
                "continuous motion watchdog did not stop"
            )
        if velocity.is_alive() and release_error is None:
            release_error = WindowsInputSinkError(
                "continuous mouse velocity actuator did not stop"
            )
        if release_error is not None:
            raise WindowsInputSinkError("continuous motion close failed safely") from release_error

    def _press_control(self, control: str) -> None:
        self._owned_controls.add(control)
        submitted = self._backend.send_scan_code(self._scan_codes[control], key_up=False)
        if type(submitted) is not int or submitted != 1:
            raise WindowsInputSinkError("continuous key-down was not exact")

    def _release_control(self, control: str) -> None:
        if control not in self._owned_controls:
            return
        submitted = self._backend.send_scan_code(self._scan_codes[control], key_up=True)
        if type(submitted) is not int or submitted != 1:
            raise WindowsInputSinkError("continuous key-up was not exact")
        self._owned_controls.discard(control)

    def _press_mouse_look(self) -> None:
        if self._mouse_owned:
            return
        placement = self._backend.prepare_world_drag_cursor(hwnd=self._target.hwnd)
        if not isinstance(placement, WindowsCursorPlacement):
            raise WindowsInputSinkError("continuous mouse cursor placement is invalid")
        self._cursor_placement = placement
        self._mouse_owned = True
        submitted = self._backend.send_turn_mode_key(key_up=False)
        if type(submitted) is not int or submitted != 1:
            raise WindowsInputSinkError("continuous RMB-down was not exact")
        # RMB-down on verified world space is sufficient to enter mouselook.
        # A former vertical anti-click excursion changed camera pitch and made
        # a valid selected target disappear before the horizontal servo ran.
        self._sleeper(MOUSE_LOOK_SETTLE_S)

    def _release_mouse_look(self) -> None:
        if not self._mouse_owned:
            return
        submitted = self._backend.send_turn_mode_key(key_up=True)
        if type(submitted) is not int or submitted != 1:
            raise WindowsInputSinkError("continuous RMB-up was not exact")
        self._mouse_owned = False
        placement = self._cursor_placement
        self._cursor_placement = None
        if placement is not None:
            self._sleeper(MOUSE_UP_SETTLE_S)
            restored = self._backend.restore_cursor_position(placement)
            if type(restored) is not int or restored != 1:
                raise WindowsInputSinkError("continuous cursor restore was not exact")

    def _release_all_locked(self) -> None:
        self._set_mouse_velocity(0.0, 0.0)
        failures: list[BaseException] = []
        for control in tuple(sorted(self._owned_controls)):
            try:
                self._release_control(control)
            except BaseException as error:
                failures.append(error)
        try:
            self._release_mouse_look()
        except BaseException as error:
            failures.append(error)
        self._machine = ContinuousInputStateMachine()
        self._lease_deadline_ms = 0.0
        self._watchdog_condition.notify_all()
        if failures:
            raise WindowsInputSinkError("continuous input release was incomplete") from failures[0]

    def _set_mouse_velocity(self, x_px_s: float, y_px_s: float) -> None:
        x = float(x_px_s)
        y = float(y_px_s)
        if (x > 0) != (self._mouse_velocity_x > 0) or (x < 0) != (self._mouse_velocity_x < 0):
            self._mouse_fraction_x = 0.0
        if (y > 0) != (self._mouse_velocity_y > 0) or (y < 0) != (self._mouse_velocity_y < 0):
            self._mouse_fraction_y = 0.0
        self._mouse_velocity_x = x
        self._mouse_velocity_y = y
        self._watchdog_condition.notify_all()

    def _mouse_velocity_loop(self) -> None:
        last_tick = time.monotonic()
        last_hot_check = 0.0
        with self._lock:
            while not self._closed:
                active = (
                    self._mouse_owned
                    and self._lease_deadline_ms > self._read_now()
                    and (self._mouse_velocity_x or self._mouse_velocity_y)
                )
                if not active:
                    last_tick = time.monotonic()
                    self._watchdog_condition.wait(timeout=MOUSE_VELOCITY_TICK_S)
                    continue
                now = time.monotonic()
                elapsed = min(0.025, max(0.0, now - last_tick))
                last_tick = now
                self._mouse_fraction_x += self._mouse_velocity_x * elapsed
                self._mouse_fraction_y += self._mouse_velocity_y * elapsed
                delta_x = max(-MOUSE_VELOCITY_MAX_STEP_PX, min(MOUSE_VELOCITY_MAX_STEP_PX, int(self._mouse_fraction_x)))
                delta_y = max(-MOUSE_VELOCITY_MAX_STEP_PX, min(MOUSE_VELOCITY_MAX_STEP_PX, int(self._mouse_fraction_y)))
                self._mouse_fraction_x -= delta_x
                self._mouse_fraction_y -= delta_y
                if delta_x or delta_y:
                    try:
                        if now - last_hot_check >= 0.05:
                            self._assert_exact_hot()
                            last_hot_check = now
                        submitted = self._backend.send_relative_mouse(
                            delta_x=delta_x, delta_y=delta_y,
                        )
                        if type(submitted) is not int or submitted != 1:
                            raise WindowsInputSinkError(
                                "interpolated relative mouse input was not exact"
                            )
                    except BaseException:
                        try:
                            self._release_all_locked()
                        finally:
                            self._lease_deadline_ms = 0.0
                self._watchdog_condition.wait(timeout=MOUSE_VELOCITY_TICK_S)

    def _arm_watchdog(self) -> None:
        # One persistent release-only worker owns the lease deadline.  Refreshing
        # a 20 Hz frame only updates state and wakes that worker; it never creates
        # a timer/thread per frame.
        self._watchdog_condition.notify_all()

    def _watchdog_loop(self) -> None:
        with self._lock:
            while not self._closed:
                if self._lease_deadline_ms <= 0.0:
                    self._watchdog_condition.wait()
                    continue
                remaining_s = (
                    self._lease_deadline_ms - self._read_now()
                ) / 1000.0
                if remaining_s > 0.001:
                    self._watchdog_condition.wait(timeout=remaining_s)
                    continue
                try:
                    self._release_all_locked()
                except BaseException:
                    # Fail closed already attempted every owned key/button up.
                    # A later explicit close still reports backend failures.
                    self._lease_deadline_ms = 0.0

    def _assert_exact_hot(self) -> None:
        hot = self._backend.inspect_hot(self._receipt)
        target = self._target
        if (
            not isinstance(hot, WindowsHotTargetSnapshot)
            or hot.hwnd != target.hwnd
            or hot.foreground_hwnd != target.hwnd
            or hot.owner_pid != target.pid
            or hot.process_creation_time_100ns != target.process_creation_time_100ns
            or not hot.process_alive
            or not hot.visible
            or hot.minimized
        ):
            raise WindowsTargetBindingError("continuous motion target is not exact and hot")

    def _read_now(self) -> float:
        value = self._clock.now_ms()
        if not isfinite(value):
            raise WindowsInputSinkError("continuous motion clock is non-finite")
        return value
