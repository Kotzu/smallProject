from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from threading import Event, RLock
from time import monotonic_ns
from typing import Callable, Protocol

from perfect_assassin.execution.contracts import (
    MAX_EXECUTION_ENVELOPE_MS,
    MAX_EXECUTION_SLACK_MS,
    MAX_HOLD_DURATION_MS,
    MIN_EXECUTION_ENVELOPE_MS,
    MIN_EXECUTION_SLACK_MS,
    MovementPrimitive,
    RuntimeArmSnapshot,
)


class MonotonicClock(Protocol):
    @property
    def clock_id(self) -> str: ...

    def now_ms(self) -> float: ...


class RuntimeArmProvider(Protocol):
    def snapshot(self) -> RuntimeArmSnapshot: ...

    def subscribe_revocation(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]: ...


class WatchdogWaiter(Protocol):
    def wait(self, completion: Event, timeout_ms: float) -> bool: ...


class InputSink(Protocol):
    """Bounded cooperative port. PA-024F1 ships no native adapter.

    Implementations must bound ``apply_bounded`` by ``max_apply_block_ms``, poll
    cancellation, and keep every effect inside that call (no detached input
    worker may outlive it). ``release_all`` must be non-blocking and safe to call
    concurrently with ``apply_bounded``. The gateway cannot hard-kill a Python
    thread; after watchdog timeout it tracks the late worker and calls
    ``release_all`` again when that worker finally returns.
    """

    @property
    def max_apply_block_ms(self) -> int: ...

    @property
    def supports_cooperative_cancellation(self) -> bool: ...

    def apply_bounded(
        self,
        primitive: MovementPrimitive,
        cancellation: "CooperativeCancellation",
        budget: "SinkExecutionBudget",
    ) -> None: ...

    def release_all(self) -> None: ...


@dataclass(slots=True)
class SystemMonotonicClock:
    clock_id: str

    def now_ms(self) -> float:
        return monotonic_ns() / 1_000_000.0


@dataclass(slots=True)
class ManualMonotonicClock:
    """Deterministic clock seam for contract and gateway tests."""

    clock_id: str
    current_ms: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.current_ms, bool)
            or not isinstance(self.current_ms, (int, float))
            or not isfinite(self.current_ms)
            or self.current_ms < 0
        ):
            raise ValueError("current_ms must be a finite non-negative number")

    def now_ms(self) -> float:
        return self.current_ms

    def advance(self, milliseconds: float) -> None:
        if (
            isinstance(milliseconds, bool)
            or not isinstance(milliseconds, (int, float))
            or not isfinite(milliseconds)
            or milliseconds < 0
        ):
            raise ValueError("A monotonic test clock needs a finite non-negative advance")
        self.current_ms += milliseconds


class InputCancelledError(RuntimeError):
    """Raised by a cooperative sink after manual takeover or gateway close."""


@dataclass(frozen=True, slots=True)
class SinkExecutionBudget:
    """Gateway-owned hold interval and total start-through-release envelope."""

    clock_id: str
    started_at_monotonic_ms: float
    absolute_deadline_monotonic_ms: float
    remaining_ms: float
    hold_duration_ms: int
    max_execution_envelope_ms: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.clock_id, str)
            or not self.clock_id
            or len(self.clock_id) > 128
        ):
            raise ValueError("Sink execution budget needs a bounded clock_id")
        values = (
            self.started_at_monotonic_ms,
            self.absolute_deadline_monotonic_ms,
            self.remaining_ms,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in values
        ):
            raise ValueError("Sink execution budget values must be finite numbers")
        if (
            self.started_at_monotonic_ms < 0
            or self.remaining_ms <= 0
            or self.remaining_ms > MAX_EXECUTION_ENVELOPE_MS
        ):
            raise ValueError("Sink execution budget must be positive")
        if (
            isinstance(self.hold_duration_ms, bool)
            or not isinstance(self.hold_duration_ms, int)
            or not 1 <= self.hold_duration_ms <= MAX_HOLD_DURATION_MS
        ):
            raise ValueError("Sink hold duration must be a bounded integer")
        if (
            isinstance(self.max_execution_envelope_ms, bool)
            or not isinstance(self.max_execution_envelope_ms, int)
            or not (
                MIN_EXECUTION_ENVELOPE_MS
                <= self.max_execution_envelope_ms
                <= MAX_EXECUTION_ENVELOPE_MS
            )
        ):
            raise ValueError("Sink execution envelope must be a bounded integer")
        execution_slack = self.max_execution_envelope_ms - self.hold_duration_ms
        if execution_slack < MIN_EXECUTION_SLACK_MS:
            raise ValueError("Sink execution envelope has insufficient release slack")
        if execution_slack > MAX_EXECUTION_SLACK_MS:
            raise ValueError("Sink execution envelope slack exceeds its bound")
        expected = self.absolute_deadline_monotonic_ms - self.started_at_monotonic_ms
        if (
            expected <= 0
            or abs(expected - self.remaining_ms) > 1e-9
            or abs(self.remaining_ms - self.max_execution_envelope_ms) > 1e-9
        ):
            raise ValueError("Sink execution budget deadline and remainder disagree")


class CooperativeCancellation:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def wait(self, timeout_ms: int) -> bool:
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer")
        return self._event.wait(timeout_ms / 1_000.0)


class EventWatchdogWaiter:
    """Wall-clock watchdog used only to bound the isolated sink call."""

    def wait(self, completion: Event, timeout_ms: float) -> bool:
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, (int, float))
            or not isfinite(timeout_ms)
            or timeout_ms <= 0
            or timeout_ms > MAX_EXECUTION_ENVELOPE_MS
        ):
            raise ValueError("Watchdog timeout must be finite and bounded")
        return completion.wait(timeout_ms / 1_000.0)


@dataclass(slots=True)
class InMemoryRuntimeArm:
    """Revocable in-memory arm seam; it does not inspect a client or server."""

    current: RuntimeArmSnapshot
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _revocation_callbacks: dict[int, Callable[[], None]] = field(
        default_factory=dict, init=False, repr=False
    )
    _next_callback_id: int = field(default=0, init=False, repr=False)

    def snapshot(self) -> RuntimeArmSnapshot:
        with self._lock:
            return self.current

    def subscribe_revocation(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        if not callable(callback):
            raise ValueError("Runtime-arm revocation callback must be callable")
        with self._lock:
            self._next_callback_id += 1
            callback_id = self._next_callback_id
            self._revocation_callbacks[callback_id] = callback

        def unsubscribe() -> None:
            with self._lock:
                self._revocation_callbacks.pop(callback_id, None)

        return unsubscribe

    def disarm(self) -> None:
        with self._lock:
            if not self.current.active:
                return
            self.current = replace(self.current, active=False)
            callbacks = tuple(self._revocation_callbacks.values())
        for callback in callbacks:
            try:
                callback()
            except Exception:
                # One observer must not prevent the arm from notifying others.
                continue


class FakeInputSink:
    """Deterministic non-I/O sink. No Win32, HID, process, or native input."""

    max_apply_block_ms = 1_000
    supports_cooperative_cancellation = True

    def __init__(
        self,
        *,
        fail_on_apply: bool = False,
        fail_on_release: bool = False,
        wait_for_cancellation: bool = False,
    ):
        self.fail_on_apply = fail_on_apply
        self.fail_on_release = fail_on_release
        self.wait_for_cancellation = wait_for_cancellation
        self.apply_attempts: list[str] = []
        self.applied: list[MovementPrimitive] = []
        self.release_count = 0
        self.apply_started = Event()
        self.budgets: list[SinkExecutionBudget] = []

    def apply_bounded(
        self,
        primitive: MovementPrimitive,
        cancellation: CooperativeCancellation,
        budget: SinkExecutionBudget,
    ) -> None:
        self.apply_attempts.append(primitive.primitive_id)
        self.budgets.append(budget)
        self.apply_started.set()
        if self.wait_for_cancellation:
            cancellation.wait(self.max_apply_block_ms)
        if cancellation.is_cancelled:
            raise InputCancelledError("fake sink observed cooperative cancellation")
        if self.fail_on_apply:
            raise RuntimeError("fake sink apply failure")
        self.applied.append(primitive)

    def release_all(self) -> None:
        self.release_count += 1
        if self.fail_on_release:
            raise RuntimeError("fake sink release failure")
