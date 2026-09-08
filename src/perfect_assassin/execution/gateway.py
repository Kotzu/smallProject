from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from threading import Event, Lock, RLock, Thread
from typing import Callable, Final

from perfect_assassin.execution.contracts import (
    ERROR_TYPE_COOPERATIVE_CANCELLATION,
    ERROR_TYPE_SINK_APPLY_FAILURE,
    ERROR_TYPE_SINK_RELEASE_FAILURE,
    MAX_EXECUTION_ENVELOPE_MS,
    MIN_EXECUTION_SLACK_MS,
    POSITION_2D_COMPONENT,
    RESULT_LIFETIME_MS,
    YAW_COMPONENT,
    ExecutionAuthorization,
    ExecutionLease,
    ExecutionPoseState,
    ExecutionResult,
    MovementPrimitive,
    RuntimeArmSnapshot,
)
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    EventWatchdogWaiter,
    InputCancelledError,
    InputSink,
    MonotonicClock,
    RuntimeArmProvider,
    SinkExecutionBudget,
    WatchdogWaiter,
)


@dataclass(frozen=True, slots=True)
class _GateFailure:
    status: str
    reason_code: str


@dataclass(slots=True)
class _SinkInvocation:
    completion: Event
    final_release_required: Event
    start_resolved: Event
    worker: Thread | None = None
    start_failure: _GateFailure | None = None
    start_observed_at: float | None = None
    watchdog_timeout_ms: float | None = None
    outcome: str | None = None


@dataclass(frozen=True, slots=True)
class _ApplyOutcome:
    kind: str
    failure: _GateFailure | None = None
    observed_at: float | None = None


class ExecutionGateway:
    """Pure, synchronous, deny-by-default movement execution policy gateway.

    The gateway can only call the injected ``InputSink`` port. PA-024F1 provides
    a fake sink, so this module cannot affect a game client by itself.
    """

    READY: Final = "READY"
    FAULTED: Final = "FAULTED"
    MANUAL_TAKEOVER: Final = "MANUAL_TAKEOVER"
    CLOSED: Final = "CLOSED"

    def __init__(
        self,
        *,
        authorization: ExecutionAuthorization,
        lease: ExecutionLease,
        runtime_arm: RuntimeArmProvider,
        clock: MonotonicClock,
        sink: InputSink,
        watchdog_waiter: WatchdogWaiter | None = None,
        before_sink_start: Callable[[], None] | None = None,
    ) -> None:
        self._authorization = authorization
        self._lease = lease
        # Freeze the authorization-side policy decision during construction.
        # The runtime arm is intentionally sampled again at every session gate
        # because it is revocable and may narrow independently.
        self._lease_policy_authorized = lease.execution_policy().is_effective_subset_of(
            authorization.lease_policy
        )
        self._runtime_arm = runtime_arm
        self._clock = clock
        self._sink = sink
        self._watchdog_waiter = watchdog_waiter or EventWatchdogWaiter()
        self._before_sink_start = before_sink_start
        self._queue: deque[MovementPrimitive] = deque()
        self._next_sequence = lease.first_sequence
        self._seen_primitive_ids: set[str] = set()
        self._result_counter = 0
        self._state = self.READY
        self._state_epoch = 0
        self._lock = RLock()
        self._execution_lock = Lock()
        self._cancellation = CooperativeCancellation()
        self._runtime_arm_revoked = False
        self._active_sink_invocation: _SinkInvocation | None = None
        self._release_faulted = False
        self._arm_subscription_valid = False
        self._unsubscribe_runtime_arm = None
        try:
            unsubscribe = self._runtime_arm.subscribe_revocation(
                self._on_runtime_arm_revoked
            )
        except Exception:
            unsubscribe = None
        if callable(unsubscribe):
            self._unsubscribe_runtime_arm = unsubscribe
            self._arm_subscription_valid = True

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def release_faulted(self) -> bool:
        with self._lock:
            return self._release_faulted

    def enqueue(self, primitive: MovementPrimitive) -> ExecutionResult | None:
        with self._lock:
            now = self._read_now()
            if now is None:
                return self._fail_closed(
                    primitive,
                    _GateFailure("REJECTED", "CLOCK_INVALID"),
                    0.0,
                )
            failure, _ = self._session_gate(now)
            if failure is None:
                failure = self._primitive_failure(primitive, now)
            if failure is not None:
                return self._fail_closed(primitive, failure, now)

            if len(self._seen_primitive_ids) >= self._lease.max_primitives:
                return self._fail_closed(
                    primitive,
                    _GateFailure("REJECTED", "PRIMITIVE_BUDGET_EXHAUSTED"),
                    now,
                )

            if len(self._queue) >= self._lease.max_queue_depth:
                return self._fail_closed(
                    primitive,
                    _GateFailure("REJECTED", "QUEUE_FULL"),
                    now,
                )

            self._queue.append(primitive)
            self._seen_primitive_ids.add(primitive.primitive_id)
            self._next_sequence += 1
            return None

    def run_next(self, pose: ExecutionPoseState) -> ExecutionResult | None:
        with self._execution_lock:
            return self._run_next(pose)

    def _run_next(
        self,
        pose: ExecutionPoseState,
        *,
        expected_primitive: MovementPrimitive | None = None,
    ) -> ExecutionResult | None:
        with self._lock:
            if not self._queue:
                return None
            primitive = self._queue[0]
            if (
                expected_primitive is not None
                and primitive != expected_primitive
            ):
                now = self._read_now()
                return self._fail_closed(
                    expected_primitive,
                    _GateFailure("REJECTED", "SEQUENCE_GAP"),
                    now if now is not None else 0.0,
                )
            now = self._read_now()
            if now is None:
                return self._fail_closed(
                    primitive,
                    _GateFailure("REJECTED", "CLOCK_INVALID"),
                    0.0,
                )
            failure, runtime_arm = self._session_gate(now)
            if failure is None:
                failure = self._primitive_runtime_failure(primitive, now)
            if failure is None:
                failure = self._pose_failure(pose, now)
            if failure is not None:
                return self._fail_closed(primitive, failure, now)
            assert runtime_arm is not None
            temporal_failure, budget = self._execution_budget_failure(
                primitive,
                pose,
                runtime_arm,
                now,
            )
            if temporal_failure is not None:
                return self._fail_closed(primitive, temporal_failure, now)
            assert budget is not None
            if not self._sink_contract_is_safe():
                return self._fail_closed(
                    primitive,
                    _GateFailure("REJECTED", "SINK_SAFETY_CONTRACT_DENIED"),
                    now,
                )
            if self._active_sink_invocation is not None:
                return self._fail_closed(
                    primitive,
                    _GateFailure("FAILED", "SINK_EXCEPTION"),
                    now,
                    error_type=ERROR_TYPE_SINK_APPLY_FAILURE,
                )
            invocation = _SinkInvocation(
                completion=Event(),
                final_release_required=Event(),
                start_resolved=Event(),
            )
            # Registration and queue ownership transfer are one linearized
            # operation. Takeover/close/revocation can therefore always find
            # and cancel work after the head is consumed, even before a worker
            # thread exists.
            self._active_sink_invocation = invocation
            self._queue.popleft()
            execution_epoch = self._state_epoch

        apply_outcome = self._apply_with_watchdog(
            primitive,
            pose,
            budget,
            invocation,
            execution_epoch,
        )
        if apply_outcome.kind == "START_REJECTED":
            failure = apply_outcome.failure or _GateFailure(
                "FAILED", "SINK_EXCEPTION"
            )
            completed = (
                apply_outcome.observed_at
                if apply_outcome.observed_at is not None
                else self._bounded_post_apply_now(now)
            )
            error_type = (
                ERROR_TYPE_COOPERATIVE_CANCELLATION
                if failure.reason_code
                in {"MANUAL_TAKEOVER", "GATEWAY_CLOSED", "RUNTIME_ARM_INACTIVE"}
                and self._cancellation.is_cancelled
                else None
            )
            return self._fail_closed(
                primitive,
                failure,
                completed,
                error_type=error_type,
            )
        if apply_outcome.kind == "CANCELLED":
            completed = self._bounded_post_apply_now(now)
            failure, error_type = self._cooperative_cancellation_failure()
            return self._fail_closed(
                primitive,
                failure,
                completed,
                error_type=error_type,
            )
        if apply_outcome.kind == "EXCEPTION":
            completed = self._bounded_post_apply_now(now)
            return self._fail_closed(
                primitive,
                _GateFailure("FAILED", "SINK_EXCEPTION"),
                completed,
                error_type=ERROR_TYPE_SINK_APPLY_FAILURE,
            )
        if apply_outcome.kind == "TIMEOUT":
            self._cancellation.cancel()
            completed = self._bounded_post_apply_now(now)
            return self._fail_closed(
                primitive,
                _GateFailure("FAILED", "TEMPORAL_OVERRUN"),
                completed,
            )

        # Releasing all controls is part of the execution envelope. The audit
        # timestamp and commit decision must therefore be measured afterwards.
        release_succeeded, release_error = self._release_all()
        completed_raw = self._read_now()
        completion_clock_valid = completed_raw is not None and completed_raw >= now
        completed = completed_raw if completion_clock_valid else now
        return self._commit_after_apply(
            primitive=primitive,
            completed_at=completed,
            deadline=budget.absolute_deadline_monotonic_ms,
            execution_epoch=execution_epoch,
            release_succeeded=release_succeeded,
            release_error=release_error,
            completion_clock_valid=completion_clock_valid,
        )

    def execute(
        self,
        primitive: MovementPrimitive,
        pose: ExecutionPoseState,
    ) -> ExecutionResult:
        with self._execution_lock:
            with self._lock:
                if self._queue:
                    now = self._read_now()
                    return self._fail_closed(
                        primitive,
                        _GateFailure("REJECTED", "SEQUENCE_GAP"),
                        now if now is not None else 0.0,
                    )
                rejection = self.enqueue(primitive)
            if rejection is not None:
                return rejection
            result = self._run_next(pose, expected_primitive=primitive)
            if result is None:  # defensive: the atomic enqueue must own the head
                with self._lock:
                    if self._state == self.MANUAL_TAKEOVER:
                        failure = _GateFailure("CANCELLED", "MANUAL_TAKEOVER")
                    elif self._state == self.CLOSED:
                        failure = _GateFailure("CANCELLED", "GATEWAY_CLOSED")
                    else:
                        failure = _GateFailure("FAILED", "INTERNAL_EMPTY_QUEUE")
                return self._fail_closed(
                    primitive,
                    failure,
                    self._bounded_post_apply_now(0.0),
                )
            return result

    def cancel_for_manual_takeover(self) -> bool:
        """Cancel authority and report whether the immediate release succeeded."""

        with self._lock:
            invocation = self._active_sink_invocation
            if invocation is not None:
                invocation.final_release_required.set()
            self._cancellation.cancel()
            if self._state != self.CLOSED:
                self._state = self.MANUAL_TAKEOVER
                self._state_epoch += 1
                self._queue.clear()
        self._drop_runtime_arm_subscription()
        release_succeeded, _ = self._release_all()
        return release_succeeded

    def close(self) -> bool:
        """Close permanently and report whether the immediate release succeeded."""

        with self._lock:
            invocation = self._active_sink_invocation
            if invocation is not None:
                invocation.final_release_required.set()
            self._cancellation.cancel()
            self._state = self.CLOSED
            self._state_epoch += 1
            self._queue.clear()
        self._drop_runtime_arm_subscription()
        release_succeeded, _ = self._release_all()
        return release_succeeded

    def _session_gate(
        self, now: float
    ) -> tuple[_GateFailure | None, RuntimeArmSnapshot | None]:
        if self._state == self.CLOSED:
            return _GateFailure("CANCELLED", "GATEWAY_CLOSED"), None
        if self._state == self.MANUAL_TAKEOVER:
            return _GateFailure("CANCELLED", "MANUAL_TAKEOVER"), None
        if self._runtime_arm_revoked:
            return _GateFailure("REJECTED", "RUNTIME_ARM_INACTIVE"), None
        if self._state == self.FAULTED:
            return _GateFailure("REJECTED", "GATEWAY_FAULTED"), None
        if not self._arm_subscription_valid:
            return _GateFailure("FAILED", "RUNTIME_ARM_PROVIDER_EXCEPTION"), None
        try:
            clock_id = self._clock.clock_id
        except Exception:
            return _GateFailure("REJECTED", "CLOCK_MISMATCH"), None
        if clock_id != self._authorization.clock_id:
            return _GateFailure("REJECTED", "CLOCK_MISMATCH"), None
        if not self._authorization.active:
            return _GateFailure("REJECTED", "AUTHORIZATION_INACTIVE"), None
        if now < self._authorization.issued_at_monotonic_ms:
            return _GateFailure("REJECTED", "AUTHORIZATION_NOT_YET_VALID"), None
        if now >= self._authorization.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "AUTHORIZATION_EXPIRED"), None
        if self._lease.clock_id != self._authorization.clock_id:
            return _GateFailure("REJECTED", "CLOCK_MISMATCH"), None
        if self._lease.binding != self._authorization.binding:
            return _GateFailure("REJECTED", "LEASE_BINDING_MISMATCH"), None
        if self._lease.mode not in self._authorization.permitted_modes:
            return _GateFailure("REJECTED", "MODE_DENIED"), None
        if self._lease.capability not in self._authorization.permitted_capabilities:
            return _GateFailure("REJECTED", "CAPABILITY_DENIED"), None
        current_lease_policy = self._lease.execution_policy()
        if (
            not self._lease_policy_authorized
            or not current_lease_policy.is_effective_subset_of(
                self._authorization.lease_policy
            )
        ):
            return _GateFailure("REJECTED", "LEASE_POLICY_DENIED"), None
        if now < self._lease.issued_at_monotonic_ms:
            return _GateFailure("REJECTED", "LEASE_NOT_YET_VALID"), None
        if now >= self._lease.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "LEASE_EXPIRED"), None

        try:
            arm = self._runtime_arm.snapshot()
        except Exception:
            return _GateFailure("FAILED", "RUNTIME_ARM_PROVIDER_EXCEPTION"), None
        if not isinstance(arm, RuntimeArmSnapshot):
            return _GateFailure("FAILED", "RUNTIME_ARM_PROVIDER_EXCEPTION"), None
        if not arm.active:
            return _GateFailure("REJECTED", "RUNTIME_ARM_INACTIVE"), None
        if arm.clock_id != self._authorization.clock_id:
            return _GateFailure("REJECTED", "RUNTIME_ARM_MISMATCH"), None
        if now < arm.issued_at_monotonic_ms or now >= arm.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "RUNTIME_ARM_EXPIRED"), None
        if arm.binding != self._authorization.binding:
            return _GateFailure("REJECTED", "RUNTIME_ARM_MISMATCH"), None
        if arm.arm_nonce != self._lease.runtime_arm_nonce:
            return _GateFailure("REJECTED", "RUNTIME_ARM_MISMATCH"), None
        if self._lease.mode not in arm.allowed_modes:
            return _GateFailure("REJECTED", "MODE_DENIED"), None
        if self._lease.capability not in arm.allowed_capabilities:
            return _GateFailure("REJECTED", "CAPABILITY_DENIED"), None
        if not current_lease_policy.is_effective_subset_of(arm.lease_policy):
            return _GateFailure("REJECTED", "RUNTIME_ARM_POLICY_MISMATCH"), None
        return None, arm

    def _primitive_failure(
        self, primitive: MovementPrimitive, now: float
    ) -> _GateFailure | None:
        failure = self._primitive_runtime_failure(primitive, now)
        if failure is not None:
            return failure
        if primitive.primitive_id in self._seen_primitive_ids:
            return _GateFailure("REJECTED", "PRIMITIVE_REPLAY")
        if primitive.sequence < self._next_sequence:
            return _GateFailure("REJECTED", "SEQUENCE_REPLAY")
        if primitive.sequence > self._next_sequence:
            return _GateFailure("REJECTED", "SEQUENCE_GAP")
        return None

    def _execution_budget_failure(
        self,
        primitive: MovementPrimitive,
        pose: ExecutionPoseState,
        runtime_arm: RuntimeArmSnapshot,
        now: float,
    ) -> tuple[_GateFailure | None, SinkExecutionBudget | None]:
        absolute_deadline = now + primitive.max_execution_envelope_ms
        expiry_limits = (
            primitive.expires_at_monotonic_ms,
            pose.expires_at_monotonic_ms,
            self._lease.expires_at_monotonic_ms,
            runtime_arm.expires_at_monotonic_ms,
            self._authorization.expires_at_monotonic_ms,
        )
        if not self._valid_now(absolute_deadline) or any(
            absolute_deadline > limit for limit in expiry_limits
        ):
            return (
                _GateFailure("REJECTED", "TEMPORAL_BUDGET_INSUFFICIENT"),
                None,
            )
        return (
            None,
            SinkExecutionBudget(
                clock_id=self._authorization.clock_id,
                started_at_monotonic_ms=now,
                absolute_deadline_monotonic_ms=absolute_deadline,
                remaining_ms=float(primitive.max_execution_envelope_ms),
                hold_duration_ms=primitive.hold_duration_ms,
                max_execution_envelope_ms=primitive.max_execution_envelope_ms,
            ),
        )

    def _primitive_runtime_failure(
        self, primitive: MovementPrimitive, now: float
    ) -> _GateFailure | None:
        if primitive.clock_id != self._authorization.clock_id:
            return _GateFailure("REJECTED", "CLOCK_MISMATCH")
        if primitive.lease_id != self._lease.lease_id:
            return _GateFailure("REJECTED", "PRIMITIVE_LEASE_MISMATCH")
        if primitive.binding != self._lease.binding:
            return _GateFailure("REJECTED", "PRIMITIVE_BINDING_MISMATCH")
        if primitive.owner_id != self._lease.owner_id:
            return _GateFailure("REJECTED", "OWNER_MISMATCH")
        if primitive.runtime_arm_nonce != self._lease.runtime_arm_nonce:
            return _GateFailure("REJECTED", "RUNTIME_ARM_MISMATCH")
        if primitive.mode != self._lease.mode:
            return _GateFailure("REJECTED", "MODE_DENIED")
        if primitive.capability != self._lease.capability:
            return _GateFailure("REJECTED", "CAPABILITY_DENIED")
        if not set(primitive.controls) <= set(self._lease.allowed_controls):
            return _GateFailure("REJECTED", "CONTROL_DENIED")
        if primitive.hold_duration_ms > self._lease.max_hold_duration_ms:
            return _GateFailure("REJECTED", "DURATION_DENIED")
        if (
            primitive.max_execution_envelope_ms
            > self._lease.max_execution_envelope_ms
        ):
            return _GateFailure("REJECTED", "DURATION_DENIED")
        if now < primitive.issued_at_monotonic_ms:
            return _GateFailure("REJECTED", "PRIMITIVE_NOT_YET_VALID")
        if now >= primitive.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "PRIMITIVE_EXPIRED")
        if primitive.expires_at_monotonic_ms > self._lease.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "PRIMITIVE_OUTLIVES_LEASE")
        return None

    def _pose_failure(
        self, pose: ExecutionPoseState, now: float
    ) -> _GateFailure | None:
        if pose.clock_id != self._authorization.clock_id:
            return _GateFailure("REJECTED", "CLOCK_MISMATCH")
        if pose.state != "VALID":
            return _GateFailure("REJECTED", "POSE_NOT_VALID")
        binding = self._lease.binding
        if (
            pose.actor_id != binding.actor_id
            or pose.actor_instance_id != binding.actor_instance_id
            or pose.actor_role != binding.actor_role
            or pose.decision_context != binding.decision_context
            or pose.target_profile != binding.target_profile
            or pose.target_instance_id != binding.target_instance_id
            or pose.authorization_id != binding.authorization_id
            or pose.authorization_sha256 != binding.authorization_sha256
        ):
            return _GateFailure("REJECTED", "POSE_BINDING_MISMATCH")
        expected_scope = (
            "lab_evaluation_only"
            if binding.decision_context == "lab_clone"
            else "champion_eligible"
        )
        if pose.source_scope != expected_scope:
            return _GateFailure("REJECTED", "POSE_SCOPE_MISMATCH")
        if pose.freshness_status != "FRESH":
            return _GateFailure("REJECTED", "POSE_NOT_VALID")
        if pose.confidence < self._lease.min_pose_confidence:
            return _GateFailure("REJECTED", "POSE_CONFIDENCE_BELOW_MINIMUM")
        required_components = frozenset(self._lease.required_pose_components)
        available_components = frozenset(pose.available_pose_components)
        if not required_components <= available_components:
            return _GateFailure("REJECTED", "POSE_COMPONENTS_MISSING")
        if POSITION_2D_COMPONENT in required_components:
            if (
                pose.position_coordinate_space
                != self._lease.position_coordinate_space
            ):
                return _GateFailure(
                    "REJECTED", "POSE_COORDINATE_SPACE_MISMATCH"
                )
            if (
                pose.position_radius_95 is None
                or self._lease.max_position_radius_95 is None
                or pose.position_radius_95
                > self._lease.max_position_radius_95
            ):
                return _GateFailure("REJECTED", "POSE_UNCERTAINTY_EXCEEDED")
        if YAW_COMPONENT in required_components and (
            pose.yaw_error_95_deg is None
            or self._lease.max_yaw_error_95_deg is None
            or pose.yaw_error_95_deg > self._lease.max_yaw_error_95_deg
        ):
            return _GateFailure("REJECTED", "POSE_UNCERTAINTY_EXCEEDED")
        if now < pose.observed_at_monotonic_ms or now >= pose.expires_at_monotonic_ms:
            return _GateFailure("REJECTED", "POSE_EXPIRED")
        return None

    def _fail_closed(
        self,
        primitive: MovementPrimitive,
        failure: _GateFailure,
        completed_at: float,
        *,
        error_type: str | None = None,
    ) -> ExecutionResult:
        with self._lock:
            if self._state not in {self.CLOSED, self.MANUAL_TAKEOVER}:
                self._state = self.FAULTED
                self._state_epoch += 1
            self._queue.clear()
        release_succeeded, release_error = self._release_all()
        if not release_succeeded:
            failure = _GateFailure("FAILED", "RELEASE_ALL_EXCEPTION")
            error_type = release_error
        with self._lock:
            return self._result(
                primitive,
                status=failure.status,
                reason_code=failure.reason_code,
                completed_at=completed_at,
                release_succeeded=release_succeeded,
                error_type=error_type,
            )

    def _commit_after_apply(
        self,
        *,
        primitive: MovementPrimitive,
        completed_at: float,
        deadline: float,
        execution_epoch: int,
        release_succeeded: bool,
        release_error: str | None,
        completion_clock_valid: bool,
    ) -> ExecutionResult:
        with self._lock:
            if not release_succeeded:
                self._state = self.FAULTED
                self._state_epoch += 1
                self._queue.clear()
                return self._result(
                    primitive,
                    status="FAILED",
                    reason_code="RELEASE_ALL_EXCEPTION",
                    completed_at=completed_at,
                    release_succeeded=False,
                    error_type=release_error,
                )
            if (
                self._cancellation.is_cancelled
                or self._state_epoch != execution_epoch
                or self._state != self.READY
            ):
                failure = self._cancellation_failure_locked()
                return self._result(
                    primitive,
                    status=failure.status,
                    reason_code=failure.reason_code,
                    completed_at=completed_at,
                    release_succeeded=True,
                )
            if not completion_clock_valid:
                self._state = self.FAULTED
                self._state_epoch += 1
                self._queue.clear()
                return self._result(
                    primitive,
                    status="FAILED",
                    reason_code="CLOCK_INVALID",
                    completed_at=completed_at,
                    release_succeeded=True,
                )
            if completed_at > deadline:
                self._state = self.FAULTED
                self._state_epoch += 1
                self._queue.clear()
                return self._result(
                    primitive,
                    status="FAILED",
                    reason_code="TEMPORAL_OVERRUN",
                    completed_at=completed_at,
                    release_succeeded=True,
                )
            failure, current_arm = self._session_gate(completed_at)
            if failure is not None or current_arm is None:
                selected = failure or _GateFailure(
                    "FAILED", "RUNTIME_ARM_PROVIDER_EXCEPTION"
                )
                if self._state not in {self.CLOSED, self.MANUAL_TAKEOVER}:
                    self._state = self.FAULTED
                    self._state_epoch += 1
                self._queue.clear()
                return self._result(
                    primitive,
                    status=selected.status,
                    reason_code=selected.reason_code,
                    completed_at=completed_at,
                    release_succeeded=True,
                )
            return self._result(
                primitive,
                status="EXECUTED",
                reason_code="EXECUTED",
                completed_at=completed_at,
                release_succeeded=True,
            )

    def _release_all(self) -> tuple[bool, str | None]:
        try:
            self._sink.release_all()
        except Exception:  # shutdown must remain non-throwing
            with self._lock:
                self._release_faulted = True
                if self._state != self.CLOSED:
                    self._state = self.FAULTED
                    self._state_epoch += 1
            return False, ERROR_TYPE_SINK_RELEASE_FAILURE
        return True, None

    def _apply_with_watchdog(
        self,
        primitive: MovementPrimitive,
        pose: ExecutionPoseState,
        budget: SinkExecutionBudget,
        invocation: _SinkInvocation,
        execution_epoch: int,
    ) -> _ApplyOutcome:

        def invoke_sink() -> None:
            try:
                with self._lock:
                    (
                        invocation.start_failure,
                        invocation.start_observed_at,
                        invocation.watchdog_timeout_ms,
                    ) = self._sink_start_gate_locked(
                        primitive=primitive,
                        pose=pose,
                        budget=budget,
                        invocation=invocation,
                        execution_epoch=execution_epoch,
                    )
                    invocation.start_resolved.set()
                if invocation.start_failure is not None:
                    invocation.outcome = "START_REJECTED"
                    return
                self._sink.apply_bounded(
                    primitive,
                    self._cancellation,
                    budget,
                )
            except InputCancelledError:
                invocation.outcome = "CANCELLED"
            except Exception:
                invocation.outcome = "EXCEPTION"
            else:
                invocation.outcome = "COMPLETED"
            finally:
                invocation.start_resolved.set()
                if invocation.final_release_required.is_set():
                    self._release_all()
                with self._lock:
                    if self._active_sink_invocation is invocation:
                        self._active_sink_invocation = None
                invocation.completion.set()

        invocation.worker = Thread(
            target=invoke_sink,
            name=f"pa-fake-sink-{primitive.sequence}",
            daemon=True,
        )
        worker_started = False
        try:
            if self._before_sink_start is not None:
                self._before_sink_start()
            invocation.worker.start()
            worker_started = True
            if not invocation.start_resolved.wait(budget.remaining_ms / 1_000.0):
                invocation.final_release_required.set()
                self._cancellation.cancel()
                return _ApplyOutcome("TIMEOUT")
            if invocation.start_failure is not None:
                if not invocation.completion.wait(budget.remaining_ms / 1_000.0):
                    invocation.final_release_required.set()
                    self._cancellation.cancel()
                    return _ApplyOutcome("TIMEOUT")
                return _ApplyOutcome(
                    "START_REJECTED",
                    invocation.start_failure,
                    invocation.start_observed_at,
                )
            timeout_ms = invocation.watchdog_timeout_ms
            if timeout_ms is None:
                raise RuntimeError("sink start did not publish a watchdog budget")
            completed = self._watchdog_waiter.wait(
                invocation.completion, timeout_ms
            )
        except Exception:
            invocation.final_release_required.set()
            self._cancellation.cancel()
            if not worker_started:
                with self._lock:
                    if self._active_sink_invocation is invocation:
                        self._active_sink_invocation = None
            return _ApplyOutcome("EXCEPTION")
        if completed is not True or not invocation.completion.is_set():
            invocation.final_release_required.set()
            self._cancellation.cancel()
            return _ApplyOutcome("TIMEOUT")
        if invocation.outcome is None:
            self._cancellation.cancel()
            return _ApplyOutcome("EXCEPTION")
        return _ApplyOutcome(invocation.outcome)

    def _sink_start_gate_locked(
        self,
        *,
        primitive: MovementPrimitive,
        pose: ExecutionPoseState,
        budget: SinkExecutionBudget,
        invocation: _SinkInvocation,
        execution_epoch: int,
    ) -> tuple[_GateFailure | None, float, float | None]:
        """Final linearized authority/deadline check immediately before apply."""

        observed = self._read_now()
        safe_observed = (
            observed
            if observed is not None
            and observed >= budget.started_at_monotonic_ms
            else budget.started_at_monotonic_ms
        )
        if self._active_sink_invocation is not invocation:
            return (
                _GateFailure("FAILED", "INTERNAL_EMPTY_QUEUE"),
                safe_observed,
                None,
            )
        if (
            invocation.final_release_required.is_set()
            or self._cancellation.is_cancelled
            or self._state_epoch != execution_epoch
            or self._state != self.READY
        ):
            if (
                self._cancellation.is_cancelled
                or self._state in {self.CLOSED, self.MANUAL_TAKEOVER}
                or self._runtime_arm_revoked
            ):
                failure = self._cancellation_failure_locked()
            else:
                failure = _GateFailure("REJECTED", "GATEWAY_FAULTED")
            return failure, safe_observed, None
        if observed is None or observed < budget.started_at_monotonic_ms:
            return _GateFailure("FAILED", "CLOCK_INVALID"), safe_observed, None

        failure, runtime_arm = self._session_gate(observed)
        if failure is None:
            failure = self._primitive_runtime_failure(primitive, observed)
        if failure is None:
            failure = self._pose_failure(pose, observed)
        if failure is not None or runtime_arm is None:
            return (
                failure
                or _GateFailure("FAILED", "RUNTIME_ARM_PROVIDER_EXCEPTION"),
                observed,
                None,
            )

        remaining_ms = budget.absolute_deadline_monotonic_ms - observed
        expiry_limits = (
            primitive.expires_at_monotonic_ms,
            pose.expires_at_monotonic_ms,
            self._lease.expires_at_monotonic_ms,
            runtime_arm.expires_at_monotonic_ms,
            self._authorization.expires_at_monotonic_ms,
        )
        if (
            observed >= budget.absolute_deadline_monotonic_ms
            or remaining_ms < primitive.hold_duration_ms + MIN_EXECUTION_SLACK_MS
            or any(
                budget.absolute_deadline_monotonic_ms > limit
                for limit in expiry_limits
            )
        ):
            return (
                _GateFailure("REJECTED", "TEMPORAL_BUDGET_INSUFFICIENT"),
                observed,
                None,
            )
        if not self._sink_contract_is_safe():
            return (
                _GateFailure("REJECTED", "SINK_SAFETY_CONTRACT_DENIED"),
                observed,
                None,
            )
        try:
            timeout_ms = min(float(self._sink.max_apply_block_ms), remaining_ms)
        except Exception:
            return (
                _GateFailure("REJECTED", "SINK_SAFETY_CONTRACT_DENIED"),
                observed,
                None,
            )
        return None, observed, timeout_ms

    def _on_runtime_arm_revoked(self) -> None:
        """Interrupt current work immediately when the arm revokes authority."""

        with self._lock:
            invocation = self._active_sink_invocation
            if invocation is not None:
                invocation.final_release_required.set()
            self._cancellation.cancel()
            self._runtime_arm_revoked = True
            if self._state not in {self.CLOSED, self.MANUAL_TAKEOVER}:
                self._state = self.FAULTED
            self._state_epoch += 1
            self._queue.clear()
        self._release_all()

    def _mark_active_sink_for_final_release(self) -> None:
        with self._lock:
            invocation = self._active_sink_invocation
            if invocation is not None:
                invocation.final_release_required.set()

    def _drop_runtime_arm_subscription(self) -> None:
        with self._lock:
            unsubscribe = self._unsubscribe_runtime_arm
            self._unsubscribe_runtime_arm = None
            self._arm_subscription_valid = False
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass

    def _cancellation_failure_locked(self) -> _GateFailure:
        if self._state == self.CLOSED:
            return _GateFailure("CANCELLED", "GATEWAY_CLOSED")
        if self._state == self.MANUAL_TAKEOVER:
            return _GateFailure("CANCELLED", "MANUAL_TAKEOVER")
        if self._runtime_arm_revoked:
            return _GateFailure("REJECTED", "RUNTIME_ARM_INACTIVE")
        return _GateFailure("CANCELLED", "MANUAL_TAKEOVER")

    def _cooperative_cancellation_failure(self) -> tuple[_GateFailure, str]:
        with self._lock:
            if self._cancellation.is_cancelled:
                return (
                    self._cancellation_failure_locked(),
                    ERROR_TYPE_COOPERATIVE_CANCELLATION,
                )
        return _GateFailure("FAILED", "SINK_EXCEPTION"), ERROR_TYPE_SINK_APPLY_FAILURE

    @staticmethod
    def _valid_now(value: float) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and isfinite(value)
            and value >= 0
        )

    def _bounded_post_apply_now(self, fallback: float) -> float:
        value = self._read_now()
        if value is None or value < fallback:
            return fallback
        return value

    def _read_now(self) -> float | None:
        try:
            value = self._clock.now_ms()
        except Exception:
            return None
        return value if self._valid_now(value) else None

    def _sink_contract_is_safe(self) -> bool:
        try:
            supports_cancellation = self._sink.supports_cooperative_cancellation
            maximum = self._sink.max_apply_block_ms
        except Exception:
            return False
        return (
            supports_cancellation is True
            and not isinstance(maximum, bool)
            and isinstance(maximum, int)
            and 1 <= maximum <= MAX_EXECUTION_ENVELOPE_MS
        )

    def _result(
        self,
        primitive: MovementPrimitive,
        *,
        status: str,
        reason_code: str,
        completed_at: float,
        release_succeeded: bool,
        error_type: str | None = None,
    ) -> ExecutionResult:
        self._result_counter += 1
        return ExecutionResult(
            result_id=f"result:{primitive.sequence}:{self._result_counter}",
            primitive_id=primitive.primitive_id,
            lease_id=primitive.lease_id,
            binding=primitive.binding,
            owner_id=primitive.owner_id,
            sequence=primitive.sequence,
            status=status,
            reason_code=reason_code,
            clock_id=self._authorization.clock_id,
            completed_at_monotonic_ms=completed_at,
            expires_at_monotonic_ms=completed_at + RESULT_LIFETIME_MS,
            sink_release_attempted=True,
            sink_release_succeeded=release_succeeded,
            error_type=error_type,
        )
