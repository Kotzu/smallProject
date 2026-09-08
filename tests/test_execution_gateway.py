from __future__ import annotations

import copy
from dataclasses import replace
from math import nan
from threading import Event, Lock, Thread
import unittest
from pathlib import Path

from perfect_assassin.contract_validation import ContractValidationError, ContractValidator
from perfect_assassin.execution import (
    AuthorityBinding,
    ExecutionAuthorization,
    ExecutionGateway,
    ExecutionLease,
    ExecutionLeasePolicy,
    ExecutionPoseState,
    FakeInputSink,
    InMemoryRuntimeArm,
    ManualMonotonicClock,
    MovementPrimitive,
    RuntimeArmSnapshot,
    SinkExecutionBudget,
    WatchdogWaiter,
    validate_execution_record_semantics,
)


ROOT = Path(__file__).resolve().parents[1]
CLOCK_ID = "clock:test:execution"
ARM_NONCE = "arm:test:one"
AUTH_SHA = "A" * 64


def binding(**changes: str) -> AuthorityBinding:
    values = {
        "actor_id": "actor:predator:lab",
        "actor_instance_id": "instance:predator:lab:one",
        "actor_role": "lab_clone",
        "decision_context": "lab_clone",
        "target_profile": "tbc_243_lab",
        "target_instance_id": "client:fixture:one",
        "authorization_id": "authorization:fixture:movement",
        "authorization_sha256": AUTH_SHA,
    }
    values.update(changes)
    return AuthorityBinding(**values)


def authority_policy(**changes) -> ExecutionLeasePolicy:
    values = {
        "mode": "MOVEMENT_ONLY",
        "capability": "MOVEMENT_EXECUTION",
        "allowed_controls": (
            "JUMP",
            "MOVE_BACKWARD",
            "MOVE_FORWARD",
            "STRAFE_LEFT",
            "STRAFE_RIGHT",
            "TURN_LEFT",
            "TURN_RIGHT",
        ),
        "max_primitives": 4_096,
        "max_hold_duration_ms": 1_000,
        "max_execution_envelope_ms": 1_250,
        "max_queue_depth": 8,
        "min_pose_confidence": 0.0,
        "required_pose_components": (),
        "position_coordinate_space": None,
        "max_position_radius_95": None,
        "max_yaw_error_95_deg": None,
    }
    values.update(changes)
    return ExecutionLeasePolicy(**values)


def authorization(
    *,
    exact_binding: AuthorityBinding | None = None,
    expires_at: float = 20_000,
    modes: frozenset[str] = frozenset({"MOVEMENT_ONLY"}),
    capabilities: frozenset[str] = frozenset({"MOVEMENT_EXECUTION"}),
    lease_policy: ExecutionLeasePolicy | None = None,
) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        binding=exact_binding or binding(),
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=900,
        expires_at_monotonic_ms=expires_at,
        permitted_modes=modes,
        permitted_capabilities=capabilities,
        lease_policy=lease_policy or authority_policy(),
    )


def lease(
    *,
    exact_binding: AuthorityBinding | None = None,
    expires_at: float = 10_000,
    max_queue_depth: int = 4,
    max_hold_duration_ms: int = 500,
    max_execution_envelope_ms: int = 750,
    required_pose_components: tuple[str, ...] = ("POSITION_2D", "YAW"),
    position_coordinate_space: str | None = "world_map_2d",
    max_position_radius_95: float | None = 0.05,
    max_yaw_error_95_deg: float | None = 5.0,
) -> ExecutionLease:
    return ExecutionLease(
        lease_id="lease:test:one",
        binding=exact_binding or binding(),
        owner_id="controller:movement:one",
        runtime_arm_nonce=ARM_NONCE,
        mode="MOVEMENT_ONLY",
        capability="MOVEMENT_EXECUTION",
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=950,
        expires_at_monotonic_ms=expires_at,
        first_sequence=1,
        max_hold_duration_ms=max_hold_duration_ms,
        max_execution_envelope_ms=max_execution_envelope_ms,
        max_queue_depth=max_queue_depth,
        min_pose_confidence=0.9,
        required_pose_components=required_pose_components,
        position_coordinate_space=position_coordinate_space,
        max_position_radius_95=max_position_radius_95,
        max_yaw_error_95_deg=max_yaw_error_95_deg,
    )


def arm(
    *,
    exact_binding: AuthorityBinding | None = None,
    active: bool = True,
    expires_at: float = 10_000,
    lease_policy: ExecutionLeasePolicy | None = None,
) -> InMemoryRuntimeArm:
    return InMemoryRuntimeArm(
        RuntimeArmSnapshot(
            binding=exact_binding or binding(),
            arm_nonce=ARM_NONCE,
            clock_id=CLOCK_ID,
            issued_at_monotonic_ms=975,
            expires_at_monotonic_ms=expires_at,
            allowed_modes=frozenset({"MOVEMENT_ONLY"}),
            allowed_capabilities=frozenset({"MOVEMENT_EXECUTION"}),
            lease_policy=lease_policy or authority_policy(),
            active=active,
        )
    )


def primitive(
    sequence: int = 1,
    *,
    exact_binding: AuthorityBinding | None = None,
    primitive_id: str | None = None,
    owner_id: str = "controller:movement:one",
    issued_at: float = 990,
    expires_at: float = 1_500,
    hold_duration_ms: int = 100,
    max_execution_envelope_ms: int = 150,
) -> MovementPrimitive:
    return MovementPrimitive(
        primitive_id=primitive_id or f"primitive:test:{sequence}",
        lease_id="lease:test:one",
        binding=exact_binding or binding(),
        owner_id=owner_id,
        runtime_arm_nonce=ARM_NONCE,
        mode="MOVEMENT_ONLY",
        capability="MOVEMENT_EXECUTION",
        sequence=sequence,
        controls=("MOVE_FORWARD",),
        hold_duration_ms=hold_duration_ms,
        max_execution_envelope_ms=max_execution_envelope_ms,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=issued_at,
        expires_at_monotonic_ms=expires_at,
    )


def pose(
    *,
    state: str = "VALID",
    actor_id: str = "actor:predator:lab",
    target_instance_id: str = "client:fixture:one",
    authorization_sha256: str = AUTH_SHA,
    expires_at: float = 1_250,
    confidence: float = 0.95,
    available_pose_components: tuple[str, ...] = ("POSITION_2D", "YAW"),
    position_coordinate_space: str | None = "world_map_2d",
    position_radius_95: float | None = 0.01,
    yaw_error_95_deg: float | None = 2.0,
) -> ExecutionPoseState:
    return ExecutionPoseState(
        pose_id="pose:test:one",
        actor_id=actor_id,
        actor_instance_id="instance:predator:lab:one",
        actor_role="lab_clone",
        decision_context="lab_clone",
        target_profile="tbc_243_lab",
        target_instance_id=target_instance_id,
        authorization_id="authorization:fixture:movement",
        authorization_sha256=authorization_sha256,
        state=state,
        source_scope="lab_evaluation_only",
        source_id="fixture:pose:fusion",
        capability="pose_estimate",
        source_origins=("fused_client_observations",),
        evidence_refs=("frame:fixture:one",),
        confidence=confidence,
        freshness_status="FRESH",
        available_pose_components=available_pose_components,
        position_coordinate_space=position_coordinate_space,
        position_radius_95=position_radius_95,
        yaw_error_95_deg=yaw_error_95_deg,
        clock_id=CLOCK_ID,
        observed_at_monotonic_ms=995,
        expires_at_monotonic_ms=expires_at,
    )


def gateway(
    *,
    exact_authorization: ExecutionAuthorization | None = None,
    exact_lease: ExecutionLease | None = None,
    exact_arm: InMemoryRuntimeArm | None = None,
    clock: ManualMonotonicClock | None = None,
    sink: FakeInputSink | None = None,
    watchdog_waiter: WatchdogWaiter | None = None,
    before_sink_start=None,
) -> tuple[ExecutionGateway, ManualMonotonicClock, FakeInputSink, InMemoryRuntimeArm]:
    test_clock = clock or ManualMonotonicClock(CLOCK_ID, 1_000)
    test_sink = sink or FakeInputSink()
    test_arm = exact_arm or arm()
    return (
        ExecutionGateway(
            authorization=exact_authorization or authorization(),
            lease=exact_lease or lease(),
            runtime_arm=test_arm,
            clock=test_clock,
            sink=test_sink,
            watchdog_waiter=watchdog_waiter,
            before_sink_start=before_sink_start,
        ),
        test_clock,
        test_sink,
        test_arm,
    )


class ExecutionGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ContractValidator(
            ROOT / "contracts" / "execution-gateway.schema.json"
        )

    def test_contract_records_are_versioned_bounded_and_valid(self) -> None:
        gate, _, _, _ = gateway()
        result = gate.execute(primitive(), pose())

        for record in (lease().to_record(), primitive().to_record(), pose().to_record(), result.to_record()):
            with self.subTest(record_type=record["record_type"]):
                self.validator.validate(record)
                self.assertEqual(record["schema_version"], "1.0")
                self.assertIn("expires_at_monotonic_ms", record)

    def test_valid_exactly_bound_primitive_reaches_only_fake_sink(self) -> None:
        gate, _, sink, _ = gateway()
        result = gate.execute(primitive(), pose())

        self.assertEqual(result.status, "EXECUTED")
        self.assertEqual([item.primitive_id for item in sink.applied], ["primitive:test:1"])
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.READY)

    def test_expired_primitive_fails_closed_and_releases(self) -> None:
        gate, clock, sink, _ = gateway()
        clock.current_ms = 1_500

        result = gate.execute(primitive(), pose(expires_at=1_900))

        self.assertEqual((result.status, result.reason_code), ("REJECTED", "PRIMITIVE_EXPIRED"))
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.FAULTED)

    def test_expired_lease_fails_before_input(self) -> None:
        exact_lease = lease(expires_at=1_100)
        gate, clock, sink, _ = gateway(exact_lease=exact_lease)
        clock.current_ms = 1_100

        result = gate.execute(
            primitive(expires_at=1_150),
            pose(expires_at=1_150),
        )

        self.assertEqual(result.reason_code, "LEASE_EXPIRED")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_full_execution_envelope_must_fit_every_expiry_preflight(self) -> None:
        cases = (
            (
                "primitive",
                {},
                primitive(expires_at=1_149),
                pose(),
            ),
            (
                "pose",
                {},
                primitive(),
                pose(expires_at=1_149),
            ),
            (
                "lease",
                {"exact_lease": lease(expires_at=1_149)},
                primitive(expires_at=1_149),
                pose(),
            ),
            (
                "runtime_arm",
                {"exact_arm": arm(expires_at=1_149)},
                primitive(),
                pose(),
            ),
            (
                "authorization",
                {"exact_authorization": authorization(expires_at=1_149)},
                primitive(),
                pose(),
            ),
        )
        for name, gateway_changes, command, current_pose in cases:
            with self.subTest(expiry=name):
                gate, _, sink, _ = gateway(**gateway_changes)
                result = gate.execute(command, current_pose)
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("REJECTED", "TEMPORAL_BUDGET_INSUFFICIENT"),
                )
                self.assertEqual(sink.apply_attempts, [])
                self.assertEqual(sink.release_count, 1)

    def test_gateway_passes_absolute_deadline_and_remaining_budget_to_sink(self) -> None:
        gate, _, sink, _ = gateway()

        result = gate.execute(
            primitive(hold_duration_ms=100, max_execution_envelope_ms=150),
            pose(),
        )

        self.assertEqual(result.status, "EXECUTED")
        self.assertEqual(len(sink.budgets), 1)
        budget = sink.budgets[0]
        self.assertIsInstance(budget, SinkExecutionBudget)
        self.assertEqual(budget.clock_id, CLOCK_ID)
        self.assertEqual(budget.started_at_monotonic_ms, 1_000)
        self.assertEqual(budget.absolute_deadline_monotonic_ms, 1_150)
        self.assertEqual(budget.remaining_ms, 150)
        self.assertEqual(budget.hold_duration_ms, 100)
        self.assertEqual(budget.max_execution_envelope_ms, 150)

        with self.assertRaisesRegex(ValueError, "deadline and remainder disagree"):
            SinkExecutionBudget(
                clock_id=CLOCK_ID,
                started_at_monotonic_ms=1_000,
                absolute_deadline_monotonic_ms=1_150,
                remaining_ms=100,
                hold_duration_ms=100,
                max_execution_envelope_ms=150,
            )
        with self.assertRaisesRegex(ValueError, "insufficient release slack"):
            SinkExecutionBudget(
                clock_id=CLOCK_ID,
                started_at_monotonic_ms=1_000,
                absolute_deadline_monotonic_ms=1_099,
                remaining_ms=99,
                hold_duration_ms=100,
                max_execution_envelope_ms=99,
            )

    def test_post_apply_temporal_overrun_is_never_committed_as_executed(self) -> None:
        test_clock = ManualMonotonicClock(CLOCK_ID, 1_000)

        class OverrunFakeSink(FakeInputSink):
            def apply_bounded(self, primitive, cancellation, budget) -> None:
                super().apply_bounded(primitive, cancellation, budget)
                test_clock.advance(budget.remaining_ms + 1)

        sink = OverrunFakeSink()
        gate, _, _, _ = gateway(clock=test_clock, sink=sink)

        result = gate.execute(
            primitive(hold_duration_ms=100, max_execution_envelope_ms=150),
            pose(),
        )

        self.assertEqual((result.status, result.reason_code), ("FAILED", "TEMPORAL_OVERRUN"))
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.FAULTED)

    def test_slow_mandatory_release_is_inside_execution_envelope(self) -> None:
        test_clock = ManualMonotonicClock(CLOCK_ID, 1_000)

        class SlowReleaseFakeSink(FakeInputSink):
            def release_all(self) -> None:
                super().release_all()
                test_clock.advance(151)

        sink = SlowReleaseFakeSink()
        gate, _, _, _ = gateway(clock=test_clock, sink=sink)

        result = gate.execute(primitive(), pose())

        self.assertEqual(
            (result.status, result.reason_code),
            ("FAILED", "TEMPORAL_OVERRUN"),
        )
        self.assertEqual(result.completed_at_monotonic_ms, 1_151)
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.FAULTED)

    def test_takeover_between_queue_pop_and_worker_start_never_calls_sink(self) -> None:
        gap_entered = Event()
        allow_worker_start = Event()

        def hold_before_worker_start() -> None:
            gap_entered.set()
            if not allow_worker_start.wait(timeout=2.0):
                raise RuntimeError("start-gap fixture was not released")

        sink = FakeInputSink()
        gate, _, _, _ = gateway(
            sink=sink,
            before_sink_start=hold_before_worker_start,
        )
        results = []
        worker = Thread(target=lambda: results.append(gate.execute(primitive(), pose())))
        worker.start()
        self.assertTrue(gap_entered.wait(timeout=1.0))
        self.assertEqual(gate.queue_depth, 0)

        self.assertTrue(gate.cancel_for_manual_takeover())
        allow_worker_start.set()
        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(
            (results[0].status, results[0].reason_code),
            ("CANCELLED", "MANUAL_TAKEOVER"),
        )
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(gate.state, ExecutionGateway.MANUAL_TAKEOVER)

    def test_deadline_crossed_before_worker_start_never_calls_sink(self) -> None:
        test_clock = ManualMonotonicClock(CLOCK_ID, 1_000)
        sink = FakeInputSink()

        def cross_deadline_before_worker_start() -> None:
            test_clock.advance(150)

        gate, _, _, _ = gateway(
            clock=test_clock,
            sink=sink,
            before_sink_start=cross_deadline_before_worker_start,
        )

        result = gate.execute(primitive(), pose())

        self.assertEqual(
            (result.status, result.reason_code),
            ("REJECTED", "TEMPORAL_BUDGET_INSUFFICIENT"),
        )
        self.assertEqual(result.completed_at_monotonic_ms, 1_150)
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_actor_target_and_authorization_mismatches_are_denied(self) -> None:
        variants = {
            "actor": binding(actor_id="actor:other"),
            "target": binding(target_instance_id="client:fixture:other"),
            "authorization": binding(authorization_sha256="B" * 64),
        }
        for name, wrong_binding in variants.items():
            with self.subTest(mismatch=name):
                gate, _, sink, _ = gateway()
                result = gate.execute(
                    primitive(exact_binding=wrong_binding),
                    pose(),
                )
                self.assertEqual(result.reason_code, "PRIMITIVE_BINDING_MISMATCH")
                self.assertEqual(sink.apply_attempts, [])
                self.assertEqual(sink.release_count, 1)

        gate, _, sink, _ = gateway()
        pose_mismatch = gate.execute(
            primitive(),
            pose(authorization_sha256="B" * 64),
        )
        self.assertEqual(pose_mismatch.reason_code, "POSE_BINDING_MISMATCH")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_lease_must_match_separate_authorization_exactly(self) -> None:
        wrong = binding(authorization_id="authorization:fixture:other")
        gate, _, sink, _ = gateway(exact_lease=lease(exact_binding=wrong))

        result = gate.execute(primitive(exact_binding=wrong), pose())

        self.assertEqual(result.reason_code, "LEASE_BINDING_MISMATCH")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_mode_and_capability_are_allowlisted_by_authorization(self) -> None:
        for name, exact_authorization, reason in (
            ("mode", authorization(modes=frozenset()), "MODE_DENIED"),
            (
                "capability",
                authorization(capabilities=frozenset()),
                "CAPABILITY_DENIED",
            ),
        ):
            with self.subTest(denied=name):
                gate, _, sink, _ = gateway(exact_authorization=exact_authorization)
                result = gate.execute(primitive(), pose())
                self.assertEqual(result.reason_code, reason)
                self.assertEqual(sink.apply_attempts, [])
                self.assertEqual(sink.release_count, 1)

    def test_authorization_policy_rejects_every_widened_lease_dimension(self) -> None:
        exact_lease = lease(
            max_queue_depth=1,
            max_hold_duration_ms=100,
            max_execution_envelope_ms=150,
            required_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            max_position_radius_95=2.0 / 65_535.0,
            max_yaw_error_95_deg=None,
        )
        exact_lease = replace(
            exact_lease,
            allowed_controls=("MOVE_FORWARD",),
            max_primitives=1,
        )
        exact_policy = exact_lease.execution_policy()
        widened_leases = (
            replace(
                exact_lease,
                allowed_controls=("MOVE_FORWARD", "MOVE_BACKWARD"),
            ),
            replace(exact_lease, max_primitives=2),
            replace(exact_lease, max_hold_duration_ms=101),
            replace(exact_lease, max_execution_envelope_ms=151),
            replace(exact_lease, max_queue_depth=2),
            replace(exact_lease, min_pose_confidence=0.899_999),
            replace(
                exact_lease,
                required_pose_components=("YAW",),
                position_coordinate_space=None,
                max_position_radius_95=None,
                max_yaw_error_95_deg=1.0,
            ),
            replace(
                exact_lease,
                position_coordinate_space="world_map_2d",
            ),
            replace(
                exact_lease,
                max_position_radius_95=(2.0 / 65_535.0) + 1e-9,
            ),
        )
        for widened in widened_leases:
            with self.subTest(policy=widened.execution_policy().to_record()):
                gate, _, sink, _ = gateway(
                    exact_authorization=authorization(lease_policy=exact_policy),
                    exact_lease=widened,
                    exact_arm=arm(lease_policy=authority_policy()),
                )
                result = gate.execute(primitive(), pose())
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("REJECTED", "LEASE_POLICY_DENIED"),
                )
                self.assertEqual(sink.apply_attempts, [])

    def test_runtime_arm_policy_is_rechecked_before_every_sink_call(self) -> None:
        exact_lease = lease()
        exact_policy = exact_lease.execution_policy()
        runtime_provider = arm(lease_policy=exact_policy)
        gate, _, sink, _ = gateway(
            exact_authorization=authorization(lease_policy=exact_policy),
            exact_lease=exact_lease,
            exact_arm=runtime_provider,
        )
        runtime_provider.current = replace(
            runtime_provider.current,
            lease_policy=replace(exact_policy, max_hold_duration_ms=499),
        )

        result = gate.execute(primitive(), pose())

        self.assertEqual(
            (result.status, result.reason_code),
            ("REJECTED", "RUNTIME_ARM_POLICY_MISMATCH"),
        )
        self.assertEqual(sink.apply_attempts, [])

    def test_lease_independently_caps_hold_and_total_execution_envelope(self) -> None:
        cases = (
            (
                "hold",
                lease(max_hold_duration_ms=99),
                primitive(hold_duration_ms=100, max_execution_envelope_ms=150),
            ),
            (
                "envelope",
                lease(max_execution_envelope_ms=149),
                primitive(hold_duration_ms=100, max_execution_envelope_ms=150),
            ),
        )
        for name, exact_lease, command in cases:
            with self.subTest(cap=name):
                gate, _, sink, _ = gateway(exact_lease=exact_lease)
                result = gate.execute(command, pose())
                self.assertEqual(result.reason_code, "DURATION_DENIED")
                self.assertEqual(sink.apply_attempts, [])

    def test_lost_pose_never_reaches_sink(self) -> None:
        gate, _, sink, _ = gateway()

        result = gate.execute(primitive(), pose(state="LOST"))

        self.assertEqual(result.reason_code, "POSE_NOT_VALID")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_pose_contract_cannot_carry_server_only_fact_origins(self) -> None:
        record = pose().to_record()
        record["source_origins"] = ["server_ground_truth"]
        with self.assertRaises(ContractValidationError):
            self.validator.validate(record)

        with self.assertRaisesRegex(ValueError, "non-client fact origin"):
            replace(pose(), source_origins=("server_ground_truth",))

    def test_lab_pose_scope_cannot_be_laundered_into_champion_scope(self) -> None:
        record = pose().to_record()
        record["source_scope"] = "champion_eligible"
        with self.assertRaises(ContractValidationError):
            self.validator.validate(record)

        with self.assertRaisesRegex(ValueError, "cross decision contexts"):
            replace(pose(), source_scope="champion_eligible")

    def test_pose_requires_provenance_confidence_uncertainty_and_freshness(self) -> None:
        for name, changes in (
            ("evidence", {"evidence_refs": ()}),
            ("confidence", {"confidence": nan}),
            ("uncertainty", {"yaw_error_95_deg": nan}),
        ):
            with self.subTest(field=name):
                with self.assertRaises(ValueError):
                    replace(pose(), **changes)

        gate, _, sink, _ = gateway()
        result = gate.execute(
            primitive(),
            replace(pose(), freshness_status="STALE"),
        )
        self.assertEqual(result.reason_code, "POSE_NOT_VALID")
        self.assertEqual(sink.apply_attempts, [])

    def test_lease_owned_pose_thresholds_are_enforced_before_sink(self) -> None:
        for name, pose_changes in (
            ("position", {"position_radius_95": 0.050_001}),
            ("yaw", {"yaw_error_95_deg": 5.000_001}),
        ):
            with self.subTest(threshold=name):
                gate, _, sink, _ = gateway()
                result = gate.execute(primitive(), pose(**pose_changes))
                self.assertEqual(result.reason_code, "POSE_UNCERTAINTY_EXCEEDED")
                self.assertEqual(sink.apply_attempts, [])
                self.assertEqual(sink.release_count, 1)

        gate, _, sink, _ = gateway()
        boundary = gate.execute(
            primitive(),
            pose(
                confidence=0.9,
                position_radius_95=0.05,
                yaw_error_95_deg=5.0,
            ),
        )
        self.assertEqual(boundary.status, "EXECUTED")
        self.assertEqual(len(sink.applied), 1)

        gate, _, sink, _ = gateway()
        below = gate.execute(primitive(), pose(confidence=0.899_999))
        self.assertEqual(below.reason_code, "POSE_CONFIDENCE_BELOW_MINIMUM")
        self.assertEqual(sink.apply_attempts, [])

    def test_f3a_position_only_normalized_pose_executes_without_invented_yaw(self) -> None:
        f3a_lease = lease(
            required_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            max_position_radius_95=2.0 / 65_535.0,
            max_yaw_error_95_deg=None,
        )
        f3a_pose = pose(
            available_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            position_radius_95=1.0 / 65_535.0,
            yaw_error_95_deg=None,
        )
        gate, _, sink, _ = gateway(exact_lease=f3a_lease)

        result = gate.execute(primitive(), f3a_pose)

        self.assertEqual((result.status, result.reason_code), ("EXECUTED", "EXECUTED"))
        self.assertEqual(len(sink.applied), 1)
        self.assertIsNone(f3a_lease.to_record()["max_yaw_error_95_deg"])
        self.assertIsNone(f3a_pose.to_record()["yaw_error_95_deg"])
        self.validator.validate(f3a_lease.to_record())
        self.validator.validate(f3a_pose.to_record())
        validate_execution_record_semantics(f3a_lease.to_record())
        validate_execution_record_semantics(f3a_pose.to_record())

    def test_gateway_requires_pose_component_subset_and_matching_space(self) -> None:
        cases = (
            (
                "missing_yaw",
                pose(
                    available_pose_components=("POSITION_2D",),
                    yaw_error_95_deg=None,
                ),
                "POSE_COMPONENTS_MISSING",
            ),
            (
                "coordinate_space",
                pose(position_coordinate_space="normalized_current_zone_map"),
                "POSE_COORDINATE_SPACE_MISMATCH",
            ),
        )
        for name, exact_pose, reason in cases:
            with self.subTest(case=name):
                gate, _, sink, _ = gateway()
                result = gate.execute(primitive(), exact_pose)
                self.assertEqual((result.status, result.reason_code), ("REJECTED", reason))
                self.assertEqual(sink.apply_attempts, [])
                self.assertEqual(sink.release_count, 1)
                self.validator.validate(result.to_record())
                validate_execution_record_semantics(result.to_record())

    def test_gateway_checks_uncertainty_only_for_required_components(self) -> None:
        position_only_lease = lease(
            required_pose_components=("POSITION_2D",),
            max_yaw_error_95_deg=None,
        )
        gate, _, sink, _ = gateway(exact_lease=position_only_lease)

        result = gate.execute(
            primitive(),
            pose(yaw_error_95_deg=180.0),
        )

        self.assertEqual(result.status, "EXECUTED")
        self.assertEqual(len(sink.applied), 1)

    def test_pose_component_contract_has_strict_three_layer_parity(self) -> None:
        f3a_lease = lease(
            required_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            max_yaw_error_95_deg=None,
        )
        f3a_pose = pose(
            available_pose_components=("POSITION_2D",),
            position_coordinate_space="normalized_current_zone_map",
            yaw_error_95_deg=None,
        )
        for source, changes in (
            (f3a_lease.to_record(), {"required_pose_components": []}),
            (
                f3a_lease.to_record(),
                {"required_pose_components": ["POSITION_2D", "POSITION_2D"]},
            ),
            (f3a_lease.to_record(), {"required_pose_components": ["ALTITUDE"]}),
            (f3a_lease.to_record(), {"position_coordinate_space": None}),
            (f3a_lease.to_record(), {"max_position_radius_95": None}),
            (f3a_lease.to_record(), {"max_yaw_error_95_deg": 1.0}),
            (f3a_pose.to_record(), {"available_pose_components": ["ALTITUDE"]}),
            (
                f3a_pose.to_record(),
                {"available_pose_components": ["POSITION_2D", "POSITION_2D"]},
            ),
            (f3a_pose.to_record(), {"position_coordinate_space": None}),
            (f3a_pose.to_record(), {"position_radius_95": None}),
            (f3a_pose.to_record(), {"yaw_error_95_deg": 1.0}),
        ):
            with self.subTest(record_type=source["record_type"], changes=changes):
                record = copy.deepcopy(source)
                record.update(changes)
                with self.assertRaises(ContractValidationError):
                    self.validator.validate(record)
                with self.assertRaises(ValueError):
                    validate_execution_record_semantics(record)

        for source, field in (
            (f3a_lease.to_record(), "position_coordinate_space"),
            (f3a_lease.to_record(), "max_yaw_error_95_deg"),
            (f3a_pose.to_record(), "position_radius_95"),
            (f3a_pose.to_record(), "yaw_error_95_deg"),
        ):
            with self.subTest(record_type=source["record_type"], missing=field):
                record = copy.deepcopy(source)
                del record[field]
                with self.assertRaises(ContractValidationError):
                    self.validator.validate(record)
                with self.assertRaisesRegex(ValueError, "required and must be explicit"):
                    validate_execution_record_semantics(record)

        for source, changes in (
            (f3a_lease, {"required_pose_components": ()}),
            (f3a_lease, {"required_pose_components": ("POSITION_2D", "POSITION_2D")}),
            (f3a_lease, {"required_pose_components": ("ALTITUDE",)}),
            (f3a_lease, {"position_coordinate_space": None}),
            (f3a_lease, {"max_position_radius_95": None}),
            (f3a_lease, {"max_yaw_error_95_deg": 1.0}),
            (f3a_pose, {"available_pose_components": ("ALTITUDE",)}),
            (f3a_pose, {"available_pose_components": ("POSITION_2D", "POSITION_2D")}),
            (f3a_pose, {"position_coordinate_space": None}),
            (f3a_pose, {"position_radius_95": None}),
            (f3a_pose, {"yaw_error_95_deg": 1.0}),
        ):
            with self.subTest(record_type=type(source).__name__, changes=changes):
                with self.assertRaises(ValueError):
                    replace(source, **changes)

    def test_v01_execution_records_are_rejected_by_breaking_v1_contract(self) -> None:
        gate, _, _, _ = gateway()
        records = (
            lease().to_record(),
            primitive().to_record(),
            pose().to_record(),
            gate.execute(primitive(), pose()).to_record(),
        )
        for source in records:
            with self.subTest(record_type=source["record_type"]):
                legacy = copy.deepcopy(source)
                legacy["schema_version"] = "0.1"
                with self.assertRaises(ContractValidationError):
                    self.validator.validate(legacy)
                with self.assertRaisesRegex(ValueError, "schema_version must be 1.0"):
                    validate_execution_record_semantics(legacy)

    def test_lease_pose_thresholds_reject_nonfinite_bool_and_absolute_overflow(self) -> None:
        for field, value in (
            ("min_pose_confidence", nan),
            ("min_pose_confidence", True),
            ("max_position_radius_95", nan),
            ("max_position_radius_95", True),
            ("max_position_radius_95", 100.000_001),
            ("max_yaw_error_95_deg", nan),
            ("max_yaw_error_95_deg", True),
            ("max_yaw_error_95_deg", 90.000_001),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    replace(lease(), **{field: value})

    def test_replay_and_sequence_gap_are_denied(self) -> None:
        gate, _, sink, _ = gateway()
        first = primitive()
        self.assertEqual(gate.execute(first, pose()).status, "EXECUTED")

        replay = gate.execute(first, pose())

        self.assertEqual(replay.reason_code, "PRIMITIVE_REPLAY")
        self.assertEqual(len(sink.applied), 1)
        self.assertEqual(sink.release_count, 2)

        other_gate, _, other_sink, _ = gateway()
        gap = other_gate.execute(primitive(sequence=2), pose())
        self.assertEqual(gap.reason_code, "SEQUENCE_GAP")
        self.assertEqual(other_sink.release_count, 1)

    def test_execute_never_consumes_a_different_queued_head(self) -> None:
        gate, _, sink, _ = gateway()
        queued = primitive()
        requested = primitive(sequence=2, primitive_id="primitive:test:execute:two")
        self.assertIsNone(gate.enqueue(queued))

        result = gate.execute(requested, pose())

        self.assertEqual(result.primitive_id, requested.primitive_id)
        self.assertEqual(result.sequence, requested.sequence)
        self.assertEqual((result.status, result.reason_code), ("REJECTED", "SEQUENCE_GAP"))
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(gate.queue_depth, 0)

    def test_concurrent_execute_calls_are_strictly_single_flight(self) -> None:
        class SerializedSink(FakeInputSink):
            def __init__(self) -> None:
                super().__init__()
                self.counter_lock = Lock()
                self.active = 0
                self.max_active = 0
                self.first_started = Event()
                self.second_started = Event()
                self.allow_first = Event()

            def apply_bounded(self, command, cancellation, budget) -> None:
                with self.counter_lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    self.apply_attempts.append(command.primitive_id)
                    if command.sequence == 1:
                        self.first_started.set()
                        if not self.allow_first.wait(timeout=0.5):
                            raise RuntimeError("single-flight fixture timed out")
                    else:
                        self.second_started.set()
                    self.applied.append(command)
                finally:
                    with self.counter_lock:
                        self.active -= 1

        sink = SerializedSink()
        gate, _, _, _ = gateway(sink=sink)
        results = []
        second_call_started = Event()
        first = primitive(
            hold_duration_ms=400,
            max_execution_envelope_ms=500,
            expires_at=1_500,
        )
        second = primitive(
            sequence=2,
            primitive_id="primitive:test:concurrent:two",
            hold_duration_ms=400,
            max_execution_envelope_ms=500,
            expires_at=1_500,
        )
        first_worker = Thread(
            target=lambda: results.append(gate.execute(first, pose(expires_at=1_500)))
        )

        def execute_second() -> None:
            second_call_started.set()
            results.append(gate.execute(second, pose(expires_at=1_500)))

        second_worker = Thread(target=execute_second)
        first_worker.start()
        self.assertTrue(sink.first_started.wait(timeout=1.0))
        second_worker.start()
        self.assertTrue(second_call_started.wait(timeout=1.0))
        self.assertFalse(sink.second_started.wait(timeout=0.05))

        sink.allow_first.set()
        first_worker.join(timeout=1.0)
        second_worker.join(timeout=1.0)

        self.assertFalse(first_worker.is_alive())
        self.assertFalse(second_worker.is_alive())
        self.assertEqual([result.status for result in results], ["EXECUTED", "EXECUTED"])
        self.assertEqual(sink.max_active, 1)
        self.assertEqual(
            sink.apply_attempts,
            [first.primitive_id, second.primitive_id],
        )

    def test_wrong_owner_is_denied(self) -> None:
        gate, _, sink, _ = gateway()
        result = gate.execute(
            primitive(owner_id="controller:movement:other"),
            pose(),
        )
        self.assertEqual(result.reason_code, "OWNER_MISMATCH")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_manual_takeover_cancels_queue_and_every_future_execution(self) -> None:
        gate, _, sink, _ = gateway()
        self.assertIsNone(gate.enqueue(primitive()))
        gate.cancel_for_manual_takeover()

        self.assertEqual(gate.queue_depth, 0)
        self.assertEqual(gate.state, ExecutionGateway.MANUAL_TAKEOVER)
        self.assertEqual(sink.release_count, 1)

        cancelled = gate.execute(primitive(sequence=2), pose())
        self.assertEqual((cancelled.status, cancelled.reason_code), ("CANCELLED", "MANUAL_TAKEOVER"))
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 2)

    def test_manual_takeover_has_a_cooperative_inflight_interrupt_seam(self) -> None:
        sink = FakeInputSink(wait_for_cancellation=True)
        gate, _, _, _ = gateway(sink=sink)
        results = []
        worker = Thread(target=lambda: results.append(gate.execute(primitive(), pose())))
        worker.start()
        self.assertTrue(sink.apply_started.wait(timeout=1.0))

        gate.cancel_for_manual_takeover()
        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "CANCELLED")
        self.assertEqual(results[0].reason_code, "MANUAL_TAKEOVER")
        self.assertEqual(gate.state, ExecutionGateway.MANUAL_TAKEOVER)
        self.assertGreaterEqual(sink.release_count, 2)

    def test_takeover_after_apply_before_commit_wins_deterministically(self) -> None:
        post_apply_read = Event()
        allow_commit = Event()

        class CommitRaceClock:
            clock_id = CLOCK_ID

            def __init__(self) -> None:
                self.calls = 0

            def now_ms(self) -> float:
                self.calls += 1
                if self.calls == 4:
                    post_apply_read.set()
                    self.assert_unblocked()
                return 1_000.0

            @staticmethod
            def assert_unblocked() -> None:
                if not allow_commit.wait(timeout=2.0):
                    raise RuntimeError("commit race test was not released")

        sink = FakeInputSink()
        gate = ExecutionGateway(
            authorization=authorization(),
            lease=lease(),
            runtime_arm=arm(),
            clock=CommitRaceClock(),
            sink=sink,
        )
        results = []
        worker = Thread(target=lambda: results.append(gate.execute(primitive(), pose())))
        worker.start()
        self.assertTrue(post_apply_read.wait(timeout=1.0))

        gate.cancel_for_manual_takeover()
        allow_commit.set()
        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0].status, results[0].reason_code), ("CANCELLED", "MANUAL_TAKEOVER"))
        self.assertEqual(gate.state, ExecutionGateway.MANUAL_TAKEOVER)

    def test_runtime_arm_is_rechecked_immediately_before_result_commit(self) -> None:
        runtime_arm = arm()

        class DisarmingFakeSink(FakeInputSink):
            def apply_bounded(self, primitive, cancellation, budget) -> None:
                super().apply_bounded(primitive, cancellation, budget)
                runtime_arm.disarm()

        sink = DisarmingFakeSink()
        gate, _, _, _ = gateway(exact_arm=runtime_arm, sink=sink)

        result = gate.execute(primitive(), pose())

        self.assertNotEqual(result.status, "EXECUTED")
        self.assertEqual(result.reason_code, "RUNTIME_ARM_INACTIVE")
        self.assertGreaterEqual(sink.release_count, 2)

    def test_runtime_disarm_is_observed_at_execution_time(self) -> None:
        gate, _, sink, runtime_arm = gateway()
        self.assertIsNone(gate.enqueue(primitive()))
        runtime_arm.disarm()

        self.assertEqual(gate.queue_depth, 0)
        result = gate.execute(
            primitive(sequence=2, primitive_id="primitive:test:disarmed:two"),
            pose(),
        )

        self.assertEqual(result.reason_code, "RUNTIME_ARM_INACTIVE")
        self.assertEqual(sink.apply_attempts, [])
        self.assertGreaterEqual(sink.release_count, 2)

    def test_sink_exception_is_contained_and_release_all_is_attempted(self) -> None:
        sink = FakeInputSink(fail_on_apply=True)
        gate, _, _, _ = gateway(sink=sink)

        result = gate.execute(primitive(), pose())

        self.assertEqual((result.status, result.reason_code), ("FAILED", "SINK_EXCEPTION"))
        self.assertEqual(result.error_type, "SINK_APPLY_FAILURE")
        self.assertFalse(sink.applied)
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.FAULTED)

    def test_apply_exceptions_are_normalized_and_never_escape(self) -> None:
        class CustomApplyError(Exception):
            pass

        for raised in (OSError("fixture os apply"), CustomApplyError("fixture custom apply")):
            with self.subTest(exception_type=type(raised).__name__):
                class ExceptionalApplySink(FakeInputSink):
                    def apply_bounded(self, primitive, cancellation, budget) -> None:
                        self.apply_attempts.append(primitive.primitive_id)
                        raise raised

                sink = ExceptionalApplySink()
                gate, _, _, _ = gateway(sink=sink)

                result = gate.execute(primitive(), pose())

                self.assertEqual((result.status, result.reason_code), ("FAILED", "SINK_EXCEPTION"))
                self.assertEqual(result.error_type, "SINK_APPLY_FAILURE")
                self.assertEqual(sink.release_count, 1)
                self.validator.validate(result.to_record())
                validate_execution_record_semantics(result.to_record())

    def test_release_exceptions_are_normalized_and_never_escape(self) -> None:
        class CustomReleaseError(Exception):
            pass

        for raised in (OSError("fixture os release"), CustomReleaseError("fixture custom release")):
            with self.subTest(exception_type=type(raised).__name__):
                class ExceptionalReleaseSink(FakeInputSink):
                    def release_all(self) -> None:
                        self.release_count += 1
                        raise raised

                sink = ExceptionalReleaseSink()
                gate, _, _, _ = gateway(sink=sink)

                result = gate.execute(primitive(), pose())

                self.assertEqual(
                    (result.status, result.reason_code),
                    ("FAILED", "RELEASE_ALL_EXCEPTION"),
                )
                self.assertEqual(result.error_type, "SINK_RELEASE_FAILURE")
                self.assertFalse(result.sink_release_succeeded)
                self.validator.validate(result.to_record())
                validate_execution_record_semantics(result.to_record())

    def test_runtime_disarm_interrupts_inflight_before_primitive_deadline(self) -> None:
        runtime_arm = arm()
        sink = FakeInputSink(wait_for_cancellation=True)
        gate, _, _, _ = gateway(exact_arm=runtime_arm, sink=sink)
        results = []
        worker = Thread(target=lambda: results.append(gate.execute(primitive(), pose())))
        worker.start()
        self.assertTrue(sink.apply_started.wait(timeout=1.0))

        runtime_arm.disarm()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertNotEqual(result.status, "EXECUTED")
        self.assertEqual(result.reason_code, "RUNTIME_ARM_INACTIVE")
        self.assertEqual(result.error_type, "COOPERATIVE_CANCELLATION")
        self.assertLess(result.completed_at_monotonic_ms, 1_150)
        self.assertEqual(sink.applied, [])
        self.assertGreaterEqual(sink.release_count, 2)

    def test_sink_without_bounded_cooperative_contract_is_denied(self) -> None:
        class UnsafeFakeSink(FakeInputSink):
            supports_cooperative_cancellation = False

        sink = UnsafeFakeSink()
        gate, _, _, _ = gateway(sink=sink)

        result = gate.execute(primitive(), pose())

        self.assertEqual(result.reason_code, "SINK_SAFETY_CONTRACT_DENIED")
        self.assertEqual(sink.apply_attempts, [])
        self.assertEqual(sink.release_count, 1)

    def test_watchdog_cancels_and_releases_sink_that_ignores_deadline(self) -> None:
        class DeadlineIgnoringSink(FakeInputSink):
            def __init__(self) -> None:
                super().__init__()
                self.unblock = Event()
                self.late_effect_released = Event()
                self.observed_cancellation = None
                self.effect_lock = Lock()
                self.effect_active = False

            def apply_bounded(self, command, cancellation, budget) -> None:
                self.apply_attempts.append(command.primitive_id)
                self.observed_cancellation = cancellation
                self.apply_started.set()
                self.unblock.wait(timeout=1.0)
                with self.effect_lock:
                    self.effect_active = True

            def release_all(self) -> None:
                with self.effect_lock:
                    self.release_count += 1
                    if self.effect_active:
                        self.effect_active = False
                        self.late_effect_released.set()

        class DeterministicTimeoutWaiter:
            def __init__(self, exact_sink: DeadlineIgnoringSink) -> None:
                self.sink = exact_sink
                self.timeout_ms = None

            def wait(self, completion, timeout_ms) -> bool:
                self.timeout_ms = timeout_ms
                if not self.sink.apply_started.wait(timeout=1.0):
                    raise RuntimeError("watchdog fixture sink never started")
                return False

        sink = DeadlineIgnoringSink()
        waiter = DeterministicTimeoutWaiter(sink)
        gate, _, _, _ = gateway(sink=sink, watchdog_waiter=waiter)

        result = gate.execute(primitive(), pose())

        self.assertEqual((result.status, result.reason_code), ("FAILED", "TEMPORAL_OVERRUN"))
        self.assertEqual(waiter.timeout_ms, 150)
        self.assertIsNotNone(sink.observed_cancellation)
        self.assertTrue(sink.observed_cancellation.is_cancelled)
        self.assertGreaterEqual(sink.release_count, 1)
        self.assertEqual(gate.state, ExecutionGateway.FAULTED)

        denied_while_worker_is_still_blocked = gate.execute(
            primitive(sequence=2, primitive_id="primitive:test:watchdog:two"),
            pose(),
        )
        self.assertEqual(
            denied_while_worker_is_still_blocked.reason_code,
            "GATEWAY_FAULTED",
        )
        self.assertEqual(sink.apply_attempts, ["primitive:test:1"])
        sink.unblock.set()
        self.assertTrue(sink.late_effect_released.wait(timeout=1.0))
        with sink.effect_lock:
            self.assertFalse(sink.effect_active)
        self.assertGreaterEqual(sink.release_count, 3)

    def test_takeover_and_close_expose_release_failure(self) -> None:
        takeover_sink = FakeInputSink(fail_on_release=True)
        takeover_gate, _, _, _ = gateway(sink=takeover_sink)

        takeover_release_succeeded = takeover_gate.cancel_for_manual_takeover()

        self.assertFalse(takeover_release_succeeded)
        self.assertTrue(takeover_gate.release_faulted)
        self.assertEqual(takeover_gate.state, ExecutionGateway.FAULTED)

        close_sink = FakeInputSink(fail_on_release=True)
        close_gate, _, _, _ = gateway(sink=close_sink)

        close_release_succeeded = close_gate.close()

        self.assertFalse(close_release_succeeded)
        self.assertTrue(close_gate.release_faulted)
        self.assertEqual(close_gate.state, ExecutionGateway.CLOSED)

    def test_clock_that_becomes_nonfinite_after_apply_fails_closed(self) -> None:
        class AdversarialClock:
            clock_id = CLOCK_ID

            def __init__(self) -> None:
                self.values = iter((1_000.0, 1_000.0, 1_000.0, nan))

            def now_ms(self) -> float:
                return next(self.values)

        sink = FakeInputSink()
        gate = ExecutionGateway(
            authorization=authorization(),
            lease=lease(),
            runtime_arm=arm(),
            clock=AdversarialClock(),
            sink=sink,
        )

        result = gate.execute(primitive(), pose())

        self.assertEqual((result.status, result.reason_code), ("FAILED", "CLOCK_INVALID"))
        self.assertEqual(len(sink.applied), 1)
        self.assertEqual(sink.release_count, 1)

    def test_duration_and_queue_have_absolute_and_lease_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "hold_duration_ms"):
            primitive(hold_duration_ms=1_001, max_execution_envelope_ms=1_200, expires_at=1_900)

        with self.assertRaisesRegex(ValueError, "hold_duration_ms"):
            primitive(hold_duration_ms=True)

        with self.assertRaisesRegex(ValueError, "max_execution_envelope_ms"):
            primitive(max_execution_envelope_ms=1_251, expires_at=2_000)

        with self.assertRaisesRegex(ValueError, "insufficient release slack"):
            primitive(hold_duration_ms=100, max_execution_envelope_ms=99)

        with self.assertRaisesRegex(ValueError, "insufficient release slack"):
            primitive(hold_duration_ms=100, max_execution_envelope_ms=104)

        with self.assertRaisesRegex(ValueError, "slack exceeds"):
            primitive(hold_duration_ms=100, max_execution_envelope_ms=351)

        test_clock = ManualMonotonicClock(CLOCK_ID, 1_000)
        with self.assertRaisesRegex(ValueError, "finite non-negative advance"):
            test_clock.advance(nan)

        gate, _, sink, _ = gateway(exact_lease=lease(max_queue_depth=1))
        self.assertIsNone(gate.enqueue(primitive()))
        rejected = gate.enqueue(
            primitive(sequence=2, primitive_id="primitive:test:queue:two")
        )
        self.assertIsNotNone(rejected)
        assert rejected is not None
        self.assertEqual(rejected.reason_code, "QUEUE_FULL")
        self.assertEqual(gate.queue_depth, 0)
        self.assertEqual(sink.release_count, 1)

    def test_close_always_clears_queue_and_releases_all(self) -> None:
        gate, _, sink, _ = gateway()
        self.assertIsNone(gate.enqueue(primitive()))

        gate.close()

        self.assertEqual(gate.state, ExecutionGateway.CLOSED)
        self.assertEqual(gate.queue_depth, 0)
        self.assertEqual(sink.release_count, 1)
        self.assertEqual(sink.apply_attempts, [])

    def test_raw_contradictory_controls_fail_schema_and_semantic_validation(self) -> None:
        record = primitive().to_record()
        record["controls"] = ["MOVE_FORWARD", "MOVE_BACKWARD"]

        with self.assertRaises(ContractValidationError):
            self.validator.validate(record)
        with self.assertRaisesRegex(ValueError, "contradictory"):
            validate_execution_record_semantics(record)

    def test_raw_hold_and_envelope_semantics_reject_ambiguity_and_excess_slack(self) -> None:
        valid = primitive().to_record()
        self.assertNotIn("duration_ms", valid)

        legacy = copy.deepcopy(valid)
        legacy["duration_ms"] = 100
        with self.assertRaises(ContractValidationError):
            self.validator.validate(legacy)

        for changes, message in (
            (
                {"hold_duration_ms": 100, "max_execution_envelope_ms": 99},
                "insufficient release slack",
            ),
            (
                {"hold_duration_ms": 100, "max_execution_envelope_ms": 104},
                "insufficient release slack",
            ),
            (
                {"hold_duration_ms": 100, "max_execution_envelope_ms": 351},
                "slack exceeds",
            ),
        ):
            with self.subTest(changes=changes):
                record = copy.deepcopy(valid)
                record.update(changes)
                self.validator.validate(record)
                with self.assertRaisesRegex(ValueError, message):
                    validate_execution_record_semantics(record)

    def test_raw_unordered_lifetimes_require_mandatory_semantic_validation(self) -> None:
        records = (
            (lease().to_record(), "issued_at_monotonic_ms"),
            (primitive().to_record(), "issued_at_monotonic_ms"),
            (pose().to_record(), "observed_at_monotonic_ms"),
        )
        for source, start_field in records:
            with self.subTest(record_type=source["record_type"]):
                record = copy.deepcopy(source)
                record["expires_at_monotonic_ms"] = record[start_field]
                self.validator.validate(record)
                with self.assertRaisesRegex(ValueError, "invalid lifetime"):
                    validate_execution_record_semantics(record)

        gate, _, _, _ = gateway()
        result_record = gate.execute(primitive(), pose()).to_record()
        result_record["expires_at_monotonic_ms"] = result_record[
            "completed_at_monotonic_ms"
        ]
        self.validator.validate(result_record)
        with self.assertRaisesRegex(ValueError, "invalid lifetime"):
            validate_execution_record_semantics(result_record)

    def test_raw_result_contradictions_and_arbitrary_fields_are_denied(self) -> None:
        gate, _, _, _ = gateway()
        valid = gate.execute(primitive(), pose()).to_record()
        variants = (
            {"sink_release_succeeded": False, "error_type": "RuntimeError"},
            {"reason_code": "ARBITRARY_REASON"},
            {
                "status": "FAILED",
                "reason_code": "SINK_EXCEPTION",
                "error_type": "ArbitraryError",
            },
            {"error_type": "RuntimeError"},
        )
        for changes in variants:
            with self.subTest(changes=changes):
                record = copy.deepcopy(valid)
                record.update(changes)
                with self.assertRaises(ContractValidationError):
                    self.validator.validate(record)
                with self.assertRaises(ValueError):
                    validate_execution_record_semantics(record)

    def test_sequence_and_pose_radius_limits_have_full_contract_parity(self) -> None:
        too_large_sequence = 2**63
        gate, _, _, _ = gateway()
        valid_result = gate.execute(primitive(), pose())
        for source, field in (
            (lease().to_record(), "first_sequence"),
            (primitive().to_record(), "sequence"),
            (valid_result.to_record(), "sequence"),
        ):
            with self.subTest(record_type=source["record_type"]):
                record = copy.deepcopy(source)
                record[field] = too_large_sequence
                with self.assertRaises(ContractValidationError):
                    self.validator.validate(record)
                with self.assertRaises(ValueError):
                    validate_execution_record_semantics(record)

        with self.assertRaises(ValueError):
            replace(lease(), first_sequence=too_large_sequence)
        with self.assertRaises(ValueError):
            replace(primitive(), sequence=too_large_sequence)
        with self.assertRaises(ValueError):
            replace(valid_result, sequence=too_large_sequence)

        boundary = replace(pose(), position_radius_95=1_000_000.0)
        self.validator.validate(boundary.to_record())
        validate_execution_record_semantics(boundary.to_record())
        raw_pose = boundary.to_record()
        raw_pose["position_radius_95"] = 1_000_000.000_001
        with self.assertRaises(ContractValidationError):
            self.validator.validate(raw_pose)
        with self.assertRaises(ValueError):
            validate_execution_record_semantics(raw_pose)
        with self.assertRaises(ValueError):
            replace(pose(), position_radius_95=1_000_000.000_001)

    def test_pose_evidence_refs_have_schema_dataclass_and_semantic_bound(self) -> None:
        boundary_refs = tuple(f"evidence:fixture:{index}" for index in range(64))
        boundary = replace(pose(), evidence_refs=boundary_refs)
        self.validator.validate(boundary.to_record())
        validate_execution_record_semantics(boundary.to_record())

        overflow_refs = tuple(f"evidence:fixture:{index}" for index in range(65))
        with self.assertRaisesRegex(ValueError, "cannot exceed 64"):
            replace(pose(), evidence_refs=overflow_refs)

        raw = pose().to_record()
        raw["evidence_refs"] = list(overflow_refs)
        with self.assertRaises(ContractValidationError):
            self.validator.validate(raw)
        with self.assertRaisesRegex(ValueError, "bounded unique"):
            validate_execution_record_semantics(raw)

    def test_execution_result_release_contradictions_fail_in_post_init(self) -> None:
        gate, _, _, _ = gateway()
        valid = gate.execute(primitive(), pose())

        with self.assertRaisesRegex(ValueError, "Release failure result contradicts"):
            replace(
                valid,
                status="FAILED",
                reason_code="RELEASE_ALL_EXCEPTION",
                sink_release_succeeded=True,
                error_type="SINK_RELEASE_FAILURE",
            )

    def test_release_failure_is_an_explicit_failed_result(self) -> None:
        sink = FakeInputSink(fail_on_release=True)
        gate, _, _, _ = gateway(sink=sink)

        result = gate.execute(primitive(), pose())
        record = result.to_record()

        self.assertEqual((result.status, result.reason_code), ("FAILED", "RELEASE_ALL_EXCEPTION"))
        self.assertFalse(result.sink_release_succeeded)
        self.validator.validate(record)
        validate_execution_record_semantics(record)


if __name__ == "__main__":
    unittest.main()
