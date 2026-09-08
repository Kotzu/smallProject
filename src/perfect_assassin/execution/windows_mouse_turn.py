from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from threading import Lock, RLock
from typing import Callable, Protocol

from perfect_assassin.execution.combat_gateway import CombatInputPrimitive
from perfect_assassin.execution.contracts import MIN_EXECUTION_SLACK_MS
from perfect_assassin.execution.navigation_turn import (
    NAVIGATION_TURN_DELTA_TO_HOLD_MS,
    NavigationTurnPrimitive,
)
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    InputCancelledError,
    MonotonicClock,
    SinkExecutionBudget,
)
from perfect_assassin.execution.windows_send_input import (
    CANCELLATION_POLL_MS,
    WindowsHotTargetSnapshot,
    WindowsInputDeadlineError,
    WindowsInputSinkError,
    WindowsInputTargetBinding,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)


TURN_DELTA_TO_HOLD_MS = {
    1: 25, 2: 25, 3: 25, 4: 25,
    5: 25, 6: 25, 7: 25, 8: 25,
    14: 35, 28: 50, 24: 200,
}
TURN_EXECUTION_SLACK_MS = 150
TURN_PRE_DRAG_SETTLE_MS = 10
TURN_POST_DRAG_SETTLE_MS = 50
# WoW 2.4.3 can still classify an eight-pixel RMB path as a world click.
# Use a clearly intentional, equal-and-opposite drag excursion before the
# horizontal camera delta so button-up cannot retarget a unit under the cursor.
TURN_ANTI_CLICK_EXCURSION_PX = 32
# SendInput calls issued back-to-back can be coalesced by the client into their
# net displacement.  Keep the outward leg visible for at least one 50 Hz frame
# so WoW unambiguously enters drag mode before the cursor returns.
TURN_ANTI_CLICK_SETTLE_MS = 20
INTERACT_POST_CLICK_SETTLE_MS = 20


class WindowsMouseTurnBackend(Protocol):
    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt: ...

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot: ...

    def send_turn_mode_key(self, *, key_up: bool) -> int: ...

    def send_target_select_key(self, *, key_up: bool) -> int: ...

    def prepare_world_drag_cursor(self, *, hwnd: int) -> WindowsCursorPlacement: ...

    def prepare_client_point_cursor(
        self, *, hwnd: int, x_normalized: float, y_normalized: float
    ) -> WindowsCursorPlacement: ...

    def restore_cursor_position(self, placement: WindowsCursorPlacement) -> int: ...

    def send_relative_mouse(self, *, delta_x: int, delta_y: int) -> int: ...

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None: ...


def _default_wait(cancellation: CooperativeCancellation, timeout_ms: int) -> bool:
    return cancellation.wait(timeout_ms)


@dataclass(frozen=True, slots=True)
class WindowsCursorPlacement:
    original_x: int
    original_y: int
    placed_x: int
    placed_y: int


@dataclass(frozen=True, slots=True)
class MouseTurnTiming:
    primitive_id: str
    clock_id: str
    turn_mode_down_at_monotonic_ms: float
    move_submitted_at_monotonic_ms: float
    turn_mode_up_started_at_monotonic_ms: float
    completed_at_monotonic_ms: float
    delta_x: int
    requested_hold_duration_ms: int
    absolute_deadline_monotonic_ms: float


class WindowsMouseTurnSink:
    """Exact foreground-bound right-button plus mouse-delta turn transport."""

    max_apply_block_ms = 350
    supports_cooperative_cancellation = True

    def __init__(
        self,
        *,
        target: WindowsInputTargetBinding,
        backend: WindowsMouseTurnBackend,
        clock: MonotonicClock,
        waiter: Callable[[CooperativeCancellation, int], bool] = _default_wait,
    ) -> None:
        if not isinstance(target, WindowsInputTargetBinding):
            raise ValueError("target must be an exact Windows input binding")
        if not callable(waiter):
            raise ValueError("waiter must be callable")
        if not isinstance(clock.clock_id, str) or not clock.clock_id:
            raise ValueError("clock must expose a stable clock_id")
        self._target = target
        self._backend = backend
        self._clock = clock
        self._clock_id = clock.clock_id
        self._waiter = waiter
        self._receipt = backend.prevalidate_target(target)
        if self._receipt.target != target:
            try:
                backend.release_identity_receipt(self._receipt)
            finally:
                raise WindowsTargetBindingError(
                    "mouse receipt does not bind the requested target"
                )
        self._state_lock = RLock()
        self._apply_lock = Lock()
        self._submission_lock = Lock()
        self._release_generation = 0
        self._active_generation: int | None = None
        self._turn_mode_owned = False
        self._select_mode_owned = False
        self._closed = False
        self._last_timing: MouseTurnTiming | None = None

    @property
    def turn_mode_owned(self) -> bool:
        with self._state_lock:
            return self._turn_mode_owned

    @property
    def last_timing(self) -> MouseTurnTiming | None:
        with self._state_lock:
            return self._last_timing

    def apply_bounded(
        self,
        primitive: CombatInputPrimitive | NavigationTurnPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if (
            isinstance(primitive, CombatInputPrimitive)
            and primitive.controls
            in {("INTERACT_TARGET",), ("TARGET_VISIBLE_HOSTILE",)}
        ):
            self._apply_visible_click(primitive, cancellation, budget)
            return
        if not self._apply_lock.acquire(blocking=False):
            raise WindowsInputSinkError("concurrent mouse turns are forbidden")
        with self._state_lock:
            if self._closed:
                self._apply_lock.release()
                raise WindowsInputSinkError("mouse turn sink is closed")
            if self._active_generation is not None:
                self._apply_lock.release()
                raise WindowsInputSinkError("a mouse turn is already active")
            generation = self._release_generation
            self._active_generation = generation
            self._last_timing = None
        down_at: float | None = None
        move_at: float | None = None
        cursor_placement: WindowsCursorPlacement | None = None
        try:
            self._validate(primitive, cancellation, budget)
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            self._assert_current(cancellation, budget, generation)
            cursor_placement = self._backend.prepare_world_drag_cursor(
                hwnd=self._target.hwnd
            )
            if not isinstance(cursor_placement, WindowsCursorPlacement):
                raise WindowsInputSinkError(
                    "mouse backend did not return an exact cursor placement"
                )
            down_at = self._turn_mode_down(cancellation, budget, generation)
            requested_up_at = down_at + primitive.hold_duration_ms
            self._hold_until(
                requested_up_at=min(
                    down_at + TURN_PRE_DRAG_SETTLE_MS,
                    requested_up_at,
                ),
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            move_at = self._relative_move(
                primitive.mouse_delta_x,
                primitive.mouse_delta_y or 0,
                cancellation,
                budget,
                generation,
            )
            self._hold_until(
                requested_up_at=requested_up_at,
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            up_started, completed = self._release_turn_mode(revoke_active=False)
            # WoW consumes the RMB-up asynchronously.  Moving the OS cursor
            # back immediately can be observed by the client as one final,
            # enormous drag and changes camera pitch.  Let the exact target
            # consume button-up before restoring the operator's cursor.
            self._hold_until(
                requested_up_at=completed + TURN_POST_DRAG_SETTLE_MS,
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            restored = self._backend.restore_cursor_position(cursor_placement)
            if type(restored) is not int or restored != 1:
                raise WindowsInputSinkError("world-drag cursor restore was not exact")
            cursor_placement = None
            self._assert_current(cancellation, budget, generation)
            if up_started is None:
                raise WindowsInputSinkError("TURNORACTION never reached key-up")
            if completed > budget.absolute_deadline_monotonic_ms:
                raise WindowsInputDeadlineError(
                    "mouse turn exceeded its execution envelope"
                )
            timing = MouseTurnTiming(
                primitive_id=primitive.primitive_id,
                clock_id=self._clock_id,
                turn_mode_down_at_monotonic_ms=down_at,
                move_submitted_at_monotonic_ms=move_at,
                turn_mode_up_started_at_monotonic_ms=up_started,
                completed_at_monotonic_ms=completed,
                delta_x=primitive.mouse_delta_x,
                requested_hold_duration_ms=primitive.hold_duration_ms,
                absolute_deadline_monotonic_ms=budget.absolute_deadline_monotonic_ms,
            )
            with self._state_lock:
                if not self._is_current_locked(cancellation, generation):
                    raise InputCancelledError("mouse turn was revoked before commit")
                self._last_timing = timing
                self._active_generation = None
        except BaseException:
            try:
                self._release_turn_mode(revoke_active=False)
            finally:
                try:
                    if cursor_placement is not None:
                        self._backend.restore_cursor_position(cursor_placement)
                finally:
                    with self._state_lock:
                        if self._active_generation == generation:
                            self._active_generation = None
            raise
        finally:
            self._apply_lock.release()

    def _apply_visible_click(
        self,
        primitive: CombatInputPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if not self._apply_lock.acquire(blocking=False):
            raise WindowsInputSinkError("concurrent mouse actions are forbidden")
        with self._state_lock:
            if self._closed or self._active_generation is not None:
                self._apply_lock.release()
                raise WindowsInputSinkError("mouse action sink is unavailable")
            generation = self._release_generation
            self._active_generation = generation
        placement: WindowsCursorPlacement | None = None
        try:
            if primitive.binding != self._target.authority_binding:
                raise WindowsTargetBindingError("mouse primitive target binding diverges")
            if (
                primitive.mouse_click_x_normalized is None
                or primitive.mouse_click_y_normalized is None
                or primitive.mouse_delta_x is not None
                or primitive.hold_duration_ms != 25
                or primitive.max_execution_envelope_ms != 125
            ):
                raise WindowsInputSinkError("visible click primitive is not exact")
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            placement = self._backend.prepare_client_point_cursor(
                hwnd=self._target.hwnd,
                x_normalized=primitive.mouse_click_x_normalized,
                y_normalized=primitive.mouse_click_y_normalized,
            )
            selecting = primitive.controls == ("TARGET_VISIBLE_HOSTILE",)
            down_at = (
                self._select_mode_down(cancellation, budget, generation)
                if selecting
                else self._turn_mode_down(cancellation, budget, generation)
            )
            self._hold_until(
                requested_up_at=down_at + primitive.hold_duration_ms,
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            _up_started, completed = (
                self._release_select_mode(revoke_active=False)
                if selecting
                else self._release_turn_mode(revoke_active=False)
            )
            self._hold_until(
                requested_up_at=completed + INTERACT_POST_CLICK_SETTLE_MS,
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            restored = self._backend.restore_cursor_position(placement)
            if type(restored) is not int or restored != 1:
                raise WindowsInputSinkError("visible click cursor restore was not exact")
            placement = None
            self._assert_current(cancellation, budget, generation)
            with self._state_lock:
                if not self._is_current_locked(cancellation, generation):
                    raise InputCancelledError("visible click was revoked")
                self._active_generation = None
        except BaseException:
            try:
                if primitive.controls == ("TARGET_VISIBLE_HOSTILE",):
                    self._release_select_mode(revoke_active=False)
                else:
                    self._release_turn_mode(revoke_active=False)
            finally:
                try:
                    if placement is not None:
                        self._backend.restore_cursor_position(placement)
                finally:
                    with self._state_lock:
                        if self._active_generation == generation:
                            self._active_generation = None
            raise
        finally:
            self._apply_lock.release()

    def release_all(self) -> None:
        turn_error: BaseException | None = None
        try:
            self._release_turn_mode(revoke_active=True)
        except BaseException as error:
            turn_error = error
        try:
            self._release_select_mode(revoke_active=True)
        except BaseException:
            if turn_error is None:
                raise
        if turn_error is not None:
            raise turn_error

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        release_error: Exception | None = None
        try:
            self.release_all()
        except Exception as error:
            release_error = error
        try:
            self._backend.release_identity_receipt(self._receipt)
        except Exception as error:
            if release_error is None:
                release_error = error
        if release_error is not None:
            raise WindowsInputSinkError("mouse sink close could not finish safely") from release_error

    def _validate(
        self,
        primitive: CombatInputPrimitive | NavigationTurnPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if not isinstance(primitive, (CombatInputPrimitive, NavigationTurnPrimitive)):
            raise WindowsInputSinkError("mouse turns require an exact reviewed primitive")
        if primitive.binding != self._target.authority_binding:
            raise WindowsTargetBindingError("mouse primitive target binding diverges")
        if primitive.controls not in {("TURN_LEFT",), ("TURN_RIGHT",)}:
            raise WindowsInputSinkError("mouse sink accepts only exact turn controls")
        delta = primitive.mouse_delta_x
        timing_profile = (
            NAVIGATION_TURN_DELTA_TO_HOLD_MS
            if isinstance(primitive, NavigationTurnPrimitive)
            else TURN_DELTA_TO_HOLD_MS
        )
        if type(delta) is not int or abs(delta) not in timing_profile:
            raise WindowsInputSinkError("mouse turn delta is not exact")
        if primitive.hold_duration_ms < TURN_PRE_DRAG_SETTLE_MS:
            raise WindowsInputDeadlineError("mouse turn cannot settle before drag")
        execution_slack_ms = (
            100 if isinstance(primitive, NavigationTurnPrimitive)
            else TURN_EXECUTION_SLACK_MS
        )
        if (
            timing_profile[abs(delta)] != primitive.hold_duration_ms
            or primitive.max_execution_envelope_ms
            != primitive.hold_duration_ms + execution_slack_ms
            or budget.hold_duration_ms != primitive.hold_duration_ms
            or budget.max_execution_envelope_ms
            != primitive.max_execution_envelope_ms
        ):
            raise WindowsInputDeadlineError("mouse turn timing profile diverges")
        if primitive.clock_id != self._clock_id or budget.clock_id != self._clock_id:
            raise WindowsInputDeadlineError("mouse sink clock identity mismatch")
        if cancellation.is_cancelled:
            raise InputCancelledError("mouse turn cancelled before TURNORACTION down")
        now = self._read_now()
        if (
            now < budget.started_at_monotonic_ms
            or budget.absolute_deadline_monotonic_ms - now
            < primitive.hold_duration_ms + MIN_EXECUTION_SLACK_MS
        ):
            raise WindowsInputDeadlineError("mouse turn budget is not current")

    def _turn_mode_down(
        self,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        generation: int,
    ) -> float:
        with self._submission_lock:
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            self._assert_current(cancellation, budget, generation)
            if (
                budget.absolute_deadline_monotonic_ms - self._read_now()
                < budget.hold_duration_ms + MIN_EXECUTION_SLACK_MS
            ):
                raise WindowsInputDeadlineError(
                    "mouse envelope is insufficient immediately pre-down"
                )
            submitted: object = None
            send_error: BaseException | None = None
            try:
                submitted = self._backend.send_turn_mode_key(key_up=False)
            except BaseException as error:
                send_error = error
            with self._state_lock:
                # A partial/native exception is ambiguous; own the binding key
                # and force an up before surfacing the failure.
                self._turn_mode_owned = True
            if type(submitted) is not int or submitted != 1:
                self._release_turn_mode(revoke_active=False)
                if send_error is not None:
                    raise send_error
                raise WindowsInputSinkError("TURNORACTION down result must be exact integer 1")
        down_at = self._read_now()
        self._assert_current(cancellation, budget, generation)
        return down_at

    def _select_mode_down(
        self,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        generation: int,
    ) -> float:
        with self._submission_lock:
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            self._assert_current(cancellation, budget, generation)
            if (
                budget.absolute_deadline_monotonic_ms - self._read_now()
                < budget.hold_duration_ms + MIN_EXECUTION_SLACK_MS
            ):
                raise WindowsInputDeadlineError(
                    "mouse envelope is insufficient immediately pre-select"
                )
            submitted: object = None
            send_error: BaseException | None = None
            try:
                submitted = self._backend.send_target_select_key(key_up=False)
            except BaseException as error:
                send_error = error
            with self._state_lock:
                self._select_mode_owned = True
            if type(submitted) is not int or submitted != 1:
                self._release_select_mode(revoke_active=False)
                if send_error is not None:
                    raise send_error
                raise WindowsInputSinkError(
                    "target-select down result must be exact integer 1"
                )
        down_at = self._read_now()
        self._assert_current(cancellation, budget, generation)
        return down_at

    def _relative_move(
        self,
        delta_x: int,
        delta_y: int,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        generation: int,
    ) -> float:
        with self._submission_lock:
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            self._assert_current(cancellation, budget, generation)
            # A tiny horizontal correction can remain below Windows' drag
            # threshold and WoW then interprets RMB-up as a world right-click,
            # accidentally replacing the selected target.  Keep the equal and
            # opposite vertical events separate from the horizontal event.
            # Windows mouse acceleration is magnitude-sensitive, so combining
            # the return excursion with delta_x can accumulate camera pitch.
            excursion = self._backend.send_relative_mouse(
                delta_x=0, delta_y=TURN_ANTI_CLICK_EXCURSION_PX
            )
            if type(excursion) is not int or excursion != 1:
                raise WindowsInputSinkError("relative mouse excursion must be exact integer 1")
            self._hold_until(
                requested_up_at=self._read_now() + TURN_ANTI_CLICK_SETTLE_MS,
                cancellation=cancellation,
                budget=budget,
                generation=generation,
            )
            excursion_return = self._backend.send_relative_mouse(
                delta_x=0, delta_y=-TURN_ANTI_CLICK_EXCURSION_PX
            )
            if type(excursion_return) is not int or excursion_return != 1:
                raise WindowsInputSinkError(
                    "relative mouse excursion return must be exact integer 1"
                )
            submitted = self._backend.send_relative_mouse(
                delta_x=delta_x, delta_y=delta_y
            )
            if type(submitted) is not int or submitted != 1:
                raise WindowsInputSinkError("relative mouse result must be exact integer 1")
        moved_at = self._read_now()
        self._assert_current(cancellation, budget, generation)
        return moved_at

    def _hold_until(
        self,
        *,
        requested_up_at: float,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        generation: int,
    ) -> None:
        while True:
            self._assert_current(cancellation, budget, generation)
            self._assert_exact_hot()
            self._assert_current(cancellation, budget, generation)
            remaining = requested_up_at - self._read_now()
            if remaining <= 0:
                return
            timeout_ms = min(CANCELLATION_POLL_MS, max(1, ceil(remaining)))
            waited = self._waiter(cancellation, timeout_ms)
            if waited is not False:
                if cancellation.is_cancelled:
                    raise InputCancelledError("mouse turn cancelled while TURNORACTION was owned")
                raise WindowsInputSinkError("mouse waiter returned a non-false result")

    def _release_turn_mode(self, *, revoke_active: bool) -> tuple[float | None, float]:
        if revoke_active:
            with self._submission_lock:
                with self._state_lock:
                    self._release_generation += 1
                    owned = self._turn_mode_owned
                    self._turn_mode_owned = False
        else:
            with self._state_lock:
                owned = self._turn_mode_owned
                self._turn_mode_owned = False
        if not owned:
            return None, 0.0
        try:
            up_started = self._read_now()
        except Exception:
            up_started = 0.0
        submitted: object = None
        send_error: BaseException | None = None
        try:
            submitted = self._backend.send_turn_mode_key(key_up=True)
        except BaseException as error:
            send_error = error
        if type(submitted) is not int or submitted != 1:
            with self._state_lock:
                self._turn_mode_owned = True
            if send_error is not None:
                raise send_error
            raise WindowsInputSinkError("TURNORACTION up result must be exact integer 1")
        completed = self._read_now()
        return up_started, completed

    def _release_select_mode(self, *, revoke_active: bool) -> tuple[float | None, float]:
        if revoke_active:
            with self._submission_lock:
                with self._state_lock:
                    self._release_generation += 1
                    owned = self._select_mode_owned
                    self._select_mode_owned = False
        else:
            with self._state_lock:
                owned = self._select_mode_owned
                self._select_mode_owned = False
        if not owned:
            return None, 0.0
        try:
            up_started = self._read_now()
        except Exception:
            up_started = 0.0
        submitted: object = None
        send_error: BaseException | None = None
        try:
            submitted = self._backend.send_target_select_key(key_up=True)
        except BaseException as error:
            send_error = error
        if type(submitted) is not int or submitted != 1:
            with self._state_lock:
                self._select_mode_owned = True
            if send_error is not None:
                raise send_error
            raise WindowsInputSinkError(
                "target-select up result must be exact integer 1"
            )
        completed = self._read_now()
        return up_started, completed

    def _assert_exact_hot(self) -> None:
        snapshot = self._backend.inspect_hot(self._receipt)
        target = self._target
        if (
            snapshot.hwnd != target.hwnd
            or snapshot.foreground_hwnd != target.hwnd
            or snapshot.owner_pid != target.pid
            or snapshot.process_creation_time_100ns
            != target.process_creation_time_100ns
            or not snapshot.process_alive
            or not snapshot.visible
            or snapshot.minimized
        ):
            raise WindowsTargetBindingError("mouse hot target binding is not exact")

    def _assert_current(
        self,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        generation: int,
    ) -> None:
        with self._state_lock:
            if not self._is_current_locked(cancellation, generation):
                raise InputCancelledError("mouse turn generation was revoked")
        if self._read_now() >= budget.absolute_deadline_monotonic_ms:
            raise WindowsInputDeadlineError("mouse turn absolute deadline reached")

    def _is_current_locked(
        self, cancellation: CooperativeCancellation, generation: int
    ) -> bool:
        return (
            not self._closed
            and not cancellation.is_cancelled
            and self._active_generation == generation
            and self._release_generation == generation
        )

    def _read_now(self) -> float:
        value = self._clock.now_ms()
        if not isfinite(value):
            raise WindowsInputDeadlineError("mouse sink clock is non-finite")
        return value


class WindowsCombatInputSink:
    """Routes combat keys to the keyboard sink and turns to binding plus mouse."""

    max_apply_block_ms = 250
    supports_cooperative_cancellation = True

    def __init__(self, *, keyboard_sink: object, mouse_turn_sink: WindowsMouseTurnSink) -> None:
        for sink in (keyboard_sink, mouse_turn_sink):
            if not callable(getattr(sink, "apply_bounded", None)) or not callable(
                getattr(sink, "release_all", None)
            ):
                raise ValueError("combat sink delegates must implement the input port")
        self._keyboard_sink = keyboard_sink
        self._mouse_turn_sink = mouse_turn_sink

    def apply_bounded(
        self,
        primitive: CombatInputPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if primitive.controls in {
            ("TURN_LEFT",),
            ("TURN_RIGHT",),
            ("INTERACT_TARGET",),
            ("TARGET_VISIBLE_HOSTILE",),
        }:
            self._mouse_turn_sink.apply_bounded(primitive, cancellation, budget)
            return
        self._keyboard_sink.apply_bounded(primitive, cancellation, budget)

    def release_all(self) -> None:
        failures: list[Exception] = []
        for sink in (self._mouse_turn_sink, self._keyboard_sink):
            try:
                sink.release_all()
            except Exception as error:
                failures.append(error)
        if failures:
            raise WindowsInputSinkError("combat input release did not fully succeed") from failures[0]

    def close(self) -> None:
        failures: list[Exception] = []
        for sink in (self._mouse_turn_sink, self._keyboard_sink):
            try:
                sink.close()
            except Exception as error:
                failures.append(error)
        if failures:
            raise WindowsInputSinkError("combat input close did not fully succeed") from failures[0]
