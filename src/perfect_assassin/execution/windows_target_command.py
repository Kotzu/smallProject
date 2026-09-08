from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from threading import Lock
from typing import Protocol

from perfect_assassin.brain.hunting import (
    compile_target_exact_command,
    validate_exact_target_name,
)
from perfect_assassin.execution.combat_runtime_arm import CombatRuntimeArm
from perfect_assassin.execution.ports import MonotonicClock
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsInputTargetBinding,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)


TARGET_COMMAND_EXECUTION_BUDGET_MS = 1_000


class ExactTargetCommandError(RuntimeError):
    """The allowlisted exact-name probe could not complete safely."""


class ExactTargetCommandBackend(Protocol):
    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt: ...

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot: ...

    def send_exact_target_name(self, target_name: str) -> int: ...

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ExactTargetCommandReceipt:
    target_name: str
    command_preview: str
    submitted_events: int
    started_at_monotonic_ms: float
    completed_at_monotonic_ms: float
    authorization_sha256: str
    execution_authority: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "exact_target_command_receipt",
            "schema_version": "0.1",
            "target_name": self.target_name,
            "command_preview": self.command_preview,
            "submitted_events": self.submitted_events,
            "started_at_monotonic_ms": self.started_at_monotonic_ms,
            "completed_at_monotonic_ms": self.completed_at_monotonic_ms,
            "authorization_sha256": self.authorization_sha256,
            "execution_authority": self.execution_authority,
        }


class WindowsExactTargetCommandGateway:
    """One bounded `/targetexact` probe; it cannot emit arbitrary chat text."""

    def __init__(
        self,
        *,
        arm: CombatRuntimeArm,
        target: WindowsInputTargetBinding,
        backend: ExactTargetCommandBackend,
        clock: MonotonicClock,
    ) -> None:
        if "TARGET_EXACT_NAME" not in arm.policy.get("allowed_controls", ()):
            raise ExactTargetCommandError("runtime arm does not authorize exact targeting")
        if clock.clock_id != arm.clock_id:
            raise ExactTargetCommandError("runtime arm and exact-target clock do not match")
        if target.authority_binding.authorization_sha256 != arm.authorization_sha256:
            raise ExactTargetCommandError("target binding and runtime arm do not match")
        receipt = backend.prevalidate_target(target)
        if receipt.target != target:
            try:
                backend.release_identity_receipt(receipt)
            except Exception:
                pass
            raise WindowsTargetBindingError("exact-target receipt does not bind the target")
        self._arm = arm
        self._target = target
        self._backend = backend
        self._clock = clock
        self._receipt = receipt
        self._lock = Lock()
        self._closed = False

    def execute(self, target_name: str) -> ExactTargetCommandReceipt:
        name = validate_exact_target_name(target_name)
        command = compile_target_exact_command(name)
        if not self._lock.acquire(blocking=False):
            raise ExactTargetCommandError("concurrent exact-target probes are forbidden")
        try:
            if self._closed:
                raise ExactTargetCommandError("exact-target gateway is closed")
            started = self._now()
            deadline = min(
                self._arm.expires_at_monotonic_ms,
                started + TARGET_COMMAND_EXECUTION_BUDGET_MS,
            )
            if (
                started < self._arm.issued_at_monotonic_ms
                or deadline <= started
            ):
                raise ExactTargetCommandError("runtime arm is not active for the probe")
            self._assert_exact_hot()
            if self._now() >= deadline:
                raise ExactTargetCommandError("exact-target budget expired before submission")
            submitted = self._backend.send_exact_target_name(name)
            expected = 4 + 2 * len(command)
            if type(submitted) is not int or submitted != expected:
                raise ExactTargetCommandError("exact-target batch was not submitted completely")
            self._assert_exact_hot()
            completed = self._now()
            if completed > deadline:
                raise ExactTargetCommandError("exact-target command exceeded its deadline")
            return ExactTargetCommandReceipt(
                target_name=name,
                command_preview=command,
                submitted_events=submitted,
                started_at_monotonic_ms=started,
                completed_at_monotonic_ms=completed,
                authorization_sha256=self._arm.authorization_sha256,
            )
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._backend.release_identity_receipt(self._receipt)

    def _now(self) -> float:
        value = self._clock.now_ms()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value < 0
        ):
            raise ExactTargetCommandError("monotonic clock returned an invalid value")
        return float(value)

    def _assert_exact_hot(self) -> None:
        hot = self._backend.inspect_hot(self._receipt)
        if (
            hot.hwnd != self._target.hwnd
            or hot.foreground_hwnd != self._target.hwnd
            or hot.owner_pid != self._target.pid
            or hot.process_creation_time_100ns
            != self._target.process_creation_time_100ns
            or not hot.process_alive
            or not hot.visible
            or hot.minimized
        ):
            raise WindowsTargetBindingError("exact-target hot identity no longer matches")
