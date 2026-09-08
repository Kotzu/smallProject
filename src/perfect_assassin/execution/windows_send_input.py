from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from pathlib import PureWindowsPath
from threading import Lock, RLock
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

from perfect_assassin.execution.contracts import (
    MAX_EXECUTION_ENVELOPE_MS,
    MIN_EXECUTION_SLACK_MS,
    AuthorityBinding,
    MovementPrimitive,
)
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    InputCancelledError,
    MonotonicClock,
    SinkExecutionBudget,
)


CANCELLATION_POLL_MS = 5
HOLD_CLOCK_TOLERANCE_MS = 1e-6

DEFAULT_CONTROL_VIRTUAL_KEYS: Mapping[str, int] = MappingProxyType(
    {
        "MOVE_FORWARD": 0x57,  # W
        "MOVE_BACKWARD": 0x53,  # S
        "STRAFE_LEFT": 0x41,  # A
        "STRAFE_RIGHT": 0x44,  # D
        "JUMP": 0x20,  # SPACE
        "TARGET_NEAREST_HOSTILE": 0x09,  # TAB
        "TARGET_LAST_HOSTILE": 0x47,  # G
        "INTERACT_TARGET": 0x59,  # Y / TURNORACTION
        "ACTION_SLOT_1": 0x31,  # 1
        "ACTION_SLOT_2": 0x32,  # 2
        "ACTION_SLOT_3": 0x33,  # 3
    }
)


class WindowsInputSinkError(RuntimeError):
    """Base failure for the isolated Win32 keyboard sink."""


class WindowsTargetBindingError(WindowsInputSinkError):
    """The current foreground window/process is not the exact bound target."""


class WindowsInputDeadlineError(WindowsInputSinkError):
    """The absolute execution envelope is no longer safe to use."""


@dataclass(frozen=True, slots=True)
class WindowsInputTargetBinding:
    """Exact OS identity paired with, but not replacing, F1 authorization."""

    authority_binding: AuthorityBinding
    pid: int
    hwnd: int
    process_creation_time_100ns: int
    executable_path: str
    executable_sha256: str
    window_class_exact: str
    window_title_exact: str

    def __post_init__(self) -> None:
        if not isinstance(self.authority_binding, AuthorityBinding):
            raise ValueError("authority_binding must be an F1 AuthorityBinding")
        for name in ("pid", "hwnd", "process_creation_time_100ns"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            not isinstance(self.executable_path, str)
            or not self.executable_path
            or len(self.executable_path) > 32_767
            or not PureWindowsPath(self.executable_path).is_absolute()
        ):
            raise ValueError("executable_path must be a bounded absolute Windows path")
        if (
            not isinstance(self.executable_sha256, str)
            or len(self.executable_sha256) != 64
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in self.executable_sha256
            )
        ):
            raise ValueError("executable_sha256 must be a SHA-256 digest")
        for name in ("window_class_exact", "window_title_exact"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError(f"{name} must be a bounded non-empty string")
        object.__setattr__(
            self, "executable_sha256", self.executable_sha256.upper()
        )


@dataclass(frozen=True, slots=True)
class WindowsTargetIdentityReceipt:
    """Cold-path proof returned after path/hash/window/process validation."""

    receipt_id: str
    target: WindowsInputTargetBinding

    def __post_init__(self) -> None:
        if (
            not isinstance(self.receipt_id, str)
            or not self.receipt_id
            or len(self.receipt_id) > 128
        ):
            raise ValueError("receipt_id must be a bounded non-empty string")
        if not isinstance(self.target, WindowsInputTargetBinding):
            raise ValueError("receipt target must be an exact Windows binding")


@dataclass(frozen=True, slots=True)
class WindowsHotTargetSnapshot:
    """Cheap hot-path state; executable hashing is deliberately absent."""

    hwnd: int
    foreground_hwnd: int
    owner_pid: int
    process_creation_time_100ns: int
    process_alive: bool
    visible: bool
    minimized: bool

    def __post_init__(self) -> None:
        for name in (
            "hwnd",
            "foreground_hwnd",
            "owner_pid",
            "process_creation_time_100ns",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if any(
            not isinstance(value, bool)
            for value in (self.process_alive, self.visible, self.minimized)
        ):
            raise ValueError("hot target state flags must be boolean")


@dataclass(frozen=True, slots=True)
class KeyHoldTiming:
    """Measured F2 semantics: first accepted down to first up submission."""

    primitive_id: str
    clock_id: str
    first_key_down_at_monotonic_ms: float
    first_key_up_started_at_monotonic_ms: float
    completed_at_monotonic_ms: float
    requested_hold_duration_ms: int
    observed_hold_duration_ms: float
    absolute_deadline_monotonic_ms: float


class WindowsKeyboardBackend(Protocol):
    """Injected boundary; only its external implementation imports ctypes."""

    def map_virtual_key(self, virtual_key: int) -> int: ...

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt: ...

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot: ...

    def send_scan_code(self, scan_code: int, *, key_up: bool) -> int: ...

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None: ...


def _default_wait(
    cancellation: CooperativeCancellation, timeout_ms: int
) -> bool:
    return cancellation.wait(timeout_ms)


class WindowsSendInputSink:
    """F2 scan-code sink behind F1; this module contains no native runner."""

    max_apply_block_ms = MAX_EXECUTION_ENVELOPE_MS
    supports_cooperative_cancellation = True

    def __init__(
        self,
        *,
        target: WindowsInputTargetBinding,
        backend: WindowsKeyboardBackend,
        clock: MonotonicClock,
        control_virtual_keys: Mapping[str, int] = DEFAULT_CONTROL_VIRTUAL_KEYS,
        waiter: Callable[[CooperativeCancellation, int], bool] = _default_wait,
    ) -> None:
        if not callable(waiter):
            raise ValueError("waiter must be callable")
        try:
            clock_id = clock.clock_id
        except Exception as error:
            raise ValueError("clock must expose a stable clock_id") from error
        if not isinstance(clock_id, str) or not clock_id or len(clock_id) > 128:
            raise ValueError("clock_id must be a bounded non-empty string")
        if not isinstance(control_virtual_keys, Mapping):
            raise ValueError("control_virtual_keys must be a mapping")
        if dict(control_virtual_keys) != dict(DEFAULT_CONTROL_VIRTUAL_KEYS):
            raise ValueError(
                "v1 accepts only the exact default non-extended virtual-key mapping"
            )

        resolved: dict[str, int] = {}
        for control, virtual_key in control_virtual_keys.items():
            if type(virtual_key) is not int or not 1 <= virtual_key <= 0xFF:
                raise ValueError(f"{control} virtual key is invalid")
            scan_code = backend.map_virtual_key(virtual_key)
            if type(scan_code) is not int or not 1 <= scan_code <= 0xFF:
                raise WindowsInputSinkError(
                    f"{control} requires a non-extended one-byte scan code"
                )
            resolved[control] = scan_code
        if len(set(resolved.values())) != len(resolved):
            raise ValueError("movement controls must map to unique scan codes")

        receipt = backend.prevalidate_target(target)
        if (
            not isinstance(receipt, WindowsTargetIdentityReceipt)
            or receipt.target != target
        ):
            if isinstance(receipt, WindowsTargetIdentityReceipt):
                try:
                    backend.release_identity_receipt(receipt)
                except Exception:
                    pass
            raise WindowsTargetBindingError(
                "backend did not return the exact immutable target receipt"
            )

        self._target = target
        self._receipt = receipt
        self._backend = backend
        self._clock = clock
        self._clock_id = clock_id
        self._waiter = waiter
        self._scan_codes = MappingProxyType(resolved)
        self._apply_lock = Lock()
        self._submission_lock = Lock()
        self._state_lock = RLock()
        self._owned_order: list[int] = []
        self._owned: set[int] = set()
        self._releasing: set[int] = set()
        self._pending_down: tuple[int, int] | None = None
        self._release_generation = 0
        self._active_generation: int | None = None
        self._closed = False
        self._last_timing: KeyHoldTiming | None = None

    @property
    def owned_scan_codes(self) -> tuple[int, ...]:
        with self._state_lock:
            combined = list(self._owned_order)
            combined.extend(
                scan_code
                for scan_code in self._releasing
                if scan_code not in self._owned
            )
            return tuple(combined)

    @property
    def last_timing(self) -> KeyHoldTiming | None:
        with self._state_lock:
            return self._last_timing

    def inspect_hot_target(self) -> WindowsHotTargetSnapshot:
        """Read the exact bound target state without submitting input.

        This is used by a preflight to separate a foreground/focus failure
        from a visual-observation failure.  It deliberately exposes only the
        metadata-only hot snapshot already required immediately before every
        input primitive; it never grants authority or changes state.
        """

        with self._state_lock:
            if self._closed:
                raise WindowsTargetBindingError(
                    "Windows input sink is closed"
                )
        snapshot = self._backend.inspect_hot(self._receipt)
        if not isinstance(snapshot, WindowsHotTargetSnapshot):
            raise WindowsTargetBindingError(
                "backend returned an invalid hot target snapshot"
            )
        return snapshot

    def apply_bounded(
        self,
        primitive: MovementPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if not self._apply_lock.acquire(blocking=False):
            raise WindowsInputSinkError("concurrent movement primitives are forbidden")

        with self._state_lock:
            if self._closed:
                self._apply_lock.release()
                raise WindowsInputSinkError("Windows input sink is closed")
            if self._active_generation is not None:
                self._apply_lock.release()
                raise WindowsInputSinkError("an active movement generation already exists")
            execution_generation = self._release_generation
            self._active_generation = execution_generation
            self._last_timing = None

        first_down_at: float | None = None
        try:
            # The active generation is registered before validation so any
            # concurrent release during a slow/failing dependency revokes it.
            self._validate_envelope(primitive, cancellation, budget)
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )
            self._assert_exact_hot()
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )

            if any(control not in self._scan_codes for control in primitive.controls):
                raise WindowsInputSinkError(
                    "control has no keyboard transport in the strafe-first profile"
                )
            for control in primitive.controls:
                down_at = self._press_scan_code(
                    self._scan_codes[control],
                    cancellation=cancellation,
                    budget=budget,
                    execution_generation=execution_generation,
                )
                if first_down_at is None:
                    first_down_at = down_at

            assert first_down_at is not None
            requested_up_at = first_down_at + primitive.hold_duration_ms
            if (
                requested_up_at + MIN_EXECUTION_SLACK_MS
                > budget.absolute_deadline_monotonic_ms
            ):
                raise WindowsInputDeadlineError(
                    "remaining envelope cannot preserve the requested key hold"
                )
            self._hold_until(
                requested_up_at=requested_up_at,
                cancellation=cancellation,
                budget=budget,
                execution_generation=execution_generation,
            )

            up_started, completed = self._release_owned(revoke_active=False)
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )
            if up_started is None:
                raise WindowsInputSinkError("no owned key reached key-up")
            observed_hold = up_started - first_down_at
            if observed_hold + HOLD_CLOCK_TOLERANCE_MS < primitive.hold_duration_ms:
                raise WindowsInputDeadlineError(
                    "measured key hold was shorter than requested"
                )
            if completed > budget.absolute_deadline_monotonic_ms:
                raise WindowsInputDeadlineError(
                    "movement primitive exceeded its total execution envelope"
                )

            timing = KeyHoldTiming(
                primitive_id=primitive.primitive_id,
                clock_id=self._clock_id,
                first_key_down_at_monotonic_ms=first_down_at,
                first_key_up_started_at_monotonic_ms=up_started,
                completed_at_monotonic_ms=completed,
                requested_hold_duration_ms=primitive.hold_duration_ms,
                observed_hold_duration_ms=observed_hold,
                absolute_deadline_monotonic_ms=budget.absolute_deadline_monotonic_ms,
            )
            with self._state_lock:
                if not self._generation_is_current_locked(
                    cancellation, execution_generation
                ):
                    raise InputCancelledError(
                        "release or cancellation won before sink completion"
                    )
                self._last_timing = timing
                self._active_generation = None
        except BaseException:
            try:
                self._release_owned(revoke_active=False)
            finally:
                with self._state_lock:
                    if self._active_generation == execution_generation:
                        self._active_generation = None
            raise
        finally:
            self._apply_lock.release()

    def release_all(self) -> None:
        self._release_owned(revoke_active=True)

    def close(self) -> None:
        """Revoke work, release owned keys, then close the native receipt."""

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
            raise WindowsInputSinkError("sink close could not finish safely") from release_error

    def _validate_envelope(
        self,
        primitive: MovementPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        if primitive.binding != self._target.authority_binding:
            raise WindowsTargetBindingError(
                "primitive F1 binding does not match the Win32 target binding"
            )
        if primitive.clock_id != self._clock_id or budget.clock_id != self._clock_id:
            raise WindowsInputDeadlineError("sink clock identity mismatch")
        if (
            budget.hold_duration_ms != primitive.hold_duration_ms
            or budget.max_execution_envelope_ms
            != primitive.max_execution_envelope_ms
            or abs(
                budget.remaining_ms - primitive.max_execution_envelope_ms
            )
            > HOLD_CLOCK_TOLERANCE_MS
        ):
            raise WindowsInputDeadlineError(
                "primitive hold/envelope does not match the gateway-owned budget"
            )
        if (
            primitive.max_execution_envelope_ms - primitive.hold_duration_ms
            < MIN_EXECUTION_SLACK_MS
        ):
            raise WindowsInputDeadlineError(
                "execution envelope has insufficient explicit input overhead"
            )
        if cancellation.is_cancelled:
            raise InputCancelledError("movement cancelled before key-down")
        now = self._read_now()
        actual_remaining = budget.absolute_deadline_monotonic_ms - now
        if (
            now < budget.started_at_monotonic_ms
            or actual_remaining
            < primitive.hold_duration_ms + MIN_EXECUTION_SLACK_MS
        ):
            raise WindowsInputDeadlineError("sink execution budget is not current")

    def _press_scan_code(
        self,
        scan_code: int,
        *,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        execution_generation: int,
    ) -> float:
        self._assert_execution_current(cancellation, budget, execution_generation)
        self._assert_exact_hot()
        self._assert_execution_current(cancellation, budget, execution_generation)
        send_error: BaseException | None = None
        with self._submission_lock:
            # Hot inspection may have consumed part of the envelope.  Recheck
            # the complete hold-plus-release requirement at the submission
            # linearization point so an already-stale primitive emits no down.
            now = self._read_now()
            if (
                budget.absolute_deadline_monotonic_ms - now
                < budget.hold_duration_ms + MIN_EXECUTION_SLACK_MS
            ):
                raise WindowsInputDeadlineError(
                    "remaining envelope is insufficient immediately pre-down"
                )
            with self._state_lock:
                if not self._generation_is_current_locked(
                    cancellation, execution_generation
                ):
                    raise InputCancelledError(
                        "movement generation was revoked pre-down"
                    )
                self._pending_down = (execution_generation, scan_code)
            try:
                submitted = self._backend.send_scan_code(scan_code, key_up=False)
            except BaseException as error:
                submitted = None
                send_error = error
            if type(submitted) is not int or submitted != 1:
                if send_error is None:
                    send_error = WindowsInputSinkError(
                        "backend key-down result must be exact integer 1"
                    )
            with self._state_lock:
                self._pending_down = None
                # Any ambiguous backend outcome is conservatively unwound.
                if scan_code not in self._owned:
                    self._owned.add(scan_code)
                    self._owned_order.append(scan_code)
        if send_error is not None:
            self._release_owned(revoke_active=False)
            raise send_error

        down_at = self._read_now()
        with self._state_lock:
            generation_current = self._generation_is_current_locked(
                cancellation, execution_generation
            )
        if not generation_current:
            self._release_owned(revoke_active=False)
            raise InputCancelledError("movement generation was revoked during key-down")
        try:
            self._assert_exact_hot()
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )
        except BaseException:
            self._release_owned(revoke_active=False)
            raise
        return down_at

    def _hold_until(
        self,
        *,
        requested_up_at: float,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        execution_generation: int,
    ) -> None:
        while True:
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )
            self._assert_exact_hot()
            self._assert_execution_current(
                cancellation, budget, execution_generation
            )
            now = self._read_now()
            remaining = requested_up_at - now
            if remaining <= 0:
                return
            timeout_ms = min(CANCELLATION_POLL_MS, max(1, ceil(remaining)))
            if self._waiter(cancellation, timeout_ms) is not False:
                if cancellation.is_cancelled:
                    raise InputCancelledError(
                        "movement cancelled while keys were owned"
                    )
                raise WindowsInputSinkError("cooperative waiter returned a non-false result")

    def _release_owned(
        self, *, revoke_active: bool
    ) -> tuple[float | None, float]:
        if revoke_active:
            # This lock is held only around the bounded SendInput submission
            # linearization point, never around cold or hot identity checks.
            with self._submission_lock:
                claimed = self._claim_owned(revoke_active=True)
        else:
            claimed = self._claim_owned(revoke_active=False)

        # An idempotent no-op release must not depend on the clock or backend.
        # This also keeps revocation responsive when another caller has already
        # claimed every sink-owned key for release.
        if not claimed:
            return None, 0.0

        failures: list[Exception] = []
        first_up_started: float | None = None
        for scan_code in claimed:
            try:
                self._assert_exact_hot()
            except Exception as error:
                failures.append(error)

            # Timing is evidence, not authority to strand a key.  If the clock
            # fails during cleanup, still attempt every key-up and report the
            # combined safety failure only after those submissions.
            try:
                up_started = self._read_now()
            except Exception as error:
                up_started = None
                failures.append(error)
            if first_up_started is None and up_started is not None:
                first_up_started = up_started
            submitted: object
            try:
                submitted = self._backend.send_scan_code(scan_code, key_up=True)
            except Exception as error:
                submitted = None
                failures.append(error)
            if type(submitted) is not int or submitted != 1:
                if submitted is not None:
                    failures.append(
                        WindowsInputSinkError(
                            "backend key-up result must be exact integer 1"
                        )
                    )
                with self._state_lock:
                    self._releasing.discard(scan_code)
                    if scan_code not in self._owned:
                        self._owned.add(scan_code)
                        self._owned_order.append(scan_code)
            else:
                with self._state_lock:
                    self._releasing.discard(scan_code)

            try:
                self._assert_exact_hot()
            except Exception as error:
                failures.append(error)

        try:
            completed = self._read_now()
        except Exception as error:
            completed = 0.0
            failures.append(error)
        if failures:
            raise WindowsInputSinkError(
                "one or more owned key-up safety checks failed"
            ) from failures[0]
        return first_up_started, completed

    def _claim_owned(self, *, revoke_active: bool) -> tuple[int, ...]:
        with self._state_lock:
            if revoke_active:
                self._release_generation += 1
            claimed = tuple(reversed(self._owned_order))
            for scan_code in claimed:
                self._owned.discard(scan_code)
                self._releasing.add(scan_code)
            self._owned_order.clear()
            return claimed

    def _assert_execution_current(
        self,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
        execution_generation: int,
    ) -> None:
        with self._state_lock:
            if not self._generation_is_current_locked(
                cancellation, execution_generation
            ):
                raise InputCancelledError("movement primitive was revoked")
        if self._read_now() >= budget.absolute_deadline_monotonic_ms:
            raise WindowsInputDeadlineError("absolute sink deadline reached")

    def _generation_is_current_locked(
        self,
        cancellation: CooperativeCancellation,
        execution_generation: int,
    ) -> bool:
        return (
            not self._closed
            and not cancellation.is_cancelled
            and self._active_generation == execution_generation
            and self._release_generation == execution_generation
        )

    def _assert_exact_hot(self) -> None:
        snapshot = self._backend.inspect_hot(self._receipt)
        if not isinstance(snapshot, WindowsHotTargetSnapshot):
            raise WindowsTargetBindingError("backend returned an invalid hot snapshot")
        expected = self._target
        if (
            snapshot.hwnd != expected.hwnd
            or snapshot.foreground_hwnd != expected.hwnd
            or snapshot.owner_pid != expected.pid
            or snapshot.process_creation_time_100ns
            != expected.process_creation_time_100ns
            or not snapshot.process_alive
            or not snapshot.visible
            or snapshot.minimized
        ):
            raise WindowsTargetBindingError(
                "foreground HWND/PID/live-process identity no longer matches"
            )

    def _read_now(self) -> float:
        try:
            now = self._clock.now_ms()
        except Exception as error:
            raise WindowsInputDeadlineError("sink monotonic clock failed") from error
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not isfinite(now)
            or now < 0
        ):
            raise WindowsInputDeadlineError(
                "sink monotonic clock returned an invalid value"
            )
        return float(now)
