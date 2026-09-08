from __future__ import annotations

import ctypes
import importlib.util
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread, current_thread

from perfect_assassin.execution.contracts import (
    MOVEMENT_EXECUTION_CAPABILITY,
    MOVEMENT_MODE,
    AuthorityBinding,
    ExecutionAuthorization,
    ExecutionLease,
    ExecutionLeasePolicy,
    ExecutionPoseState,
    MovementPrimitive,
    RuntimeArmSnapshot,
)
from perfect_assassin.execution.gateway import ExecutionGateway
from perfect_assassin.execution.combat_gateway import CombatInputPrimitive
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    InMemoryRuntimeArm,
    InputCancelledError,
    SinkExecutionBudget,
)
from perfect_assassin.execution.windows_send_input import (
    CANCELLATION_POLL_MS,
    DEFAULT_CONTROL_VIRTUAL_KEYS,
    KeyHoldTiming,
    WindowsHotTargetSnapshot,
    WindowsInputDeadlineError,
    WindowsInputSinkError,
    WindowsInputTargetBinding,
    WindowsSendInputSink,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)


CLOCK_ID = "clock:test:windows-input"
WOW_PATH = r"E:\Games\WoW TBC 2.4.3\Wow.exe"
ROOT = Path(__file__).resolve().parents[1]


def authority_binding() -> AuthorityBinding:
    return AuthorityBinding(
        actor_id="actor:lab:predator",
        actor_instance_id="actor-instance:lab:predator:one",
        actor_role="lab_clone",
        decision_context="lab_clone",
        target_profile="target:tbc243:lab",
        target_instance_id="target-instance:wow:fixture",
        authorization_id="authorization:movement:fixture",
        authorization_sha256="A" * 64,
    )


def target_binding() -> WindowsInputTargetBinding:
    return WindowsInputTargetBinding(
        authority_binding=authority_binding(),
        pid=42,
        hwnd=0x1234,
        process_creation_time_100ns=132_000_000_000_000_000,
        executable_path=WOW_PATH,
        executable_sha256="B" * 64,
        window_class_exact="GxWindowClassD3d",
        window_title_exact="World of Warcraft",
    )


def hot_snapshot() -> WindowsHotTargetSnapshot:
    target = target_binding()
    return WindowsHotTargetSnapshot(
        hwnd=target.hwnd,
        foreground_hwnd=target.hwnd,
        owner_pid=target.pid,
        process_creation_time_100ns=target.process_creation_time_100ns,
        process_alive=True,
        visible=True,
        minimized=False,
    )


def movement_primitive(
    *,
    controls: tuple[str, ...] = ("MOVE_FORWARD",),
    hold_duration_ms: int = 20,
    max_execution_envelope_ms: int = 40,
    exact_binding: AuthorityBinding | None = None,
) -> MovementPrimitive:
    return MovementPrimitive(
        primitive_id="primitive:windows-input:one",
        lease_id="lease:movement:fixture",
        binding=exact_binding or authority_binding(),
        owner_id="controller:movement:fixture",
        runtime_arm_nonce="arm:movement:fixture",
        mode=MOVEMENT_MODE,
        capability=MOVEMENT_EXECUTION_CAPABILITY,
        sequence=1,
        controls=controls,
        hold_duration_ms=hold_duration_ms,
        max_execution_envelope_ms=max_execution_envelope_ms,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=990.0,
        expires_at_monotonic_ms=2_000.0,
    )


def combat_primitive(*, control: str) -> CombatInputPrimitive:
    return CombatInputPrimitive(
        primitive_id=f"primitive:windows-input:combat:{control.lower()}",
        lease_id="lease:combat:fixture",
        binding=authority_binding(),
        owner_id="controller:combat:fixture",
        runtime_arm_nonce="arm:combat:fixture",
        mode="COMBAT_ONLY",
        capability="COMBAT_EXECUTION",
        sequence=1,
        controls=(control,),
        hold_duration_ms=25,
        max_execution_envelope_ms=75,
        mouse_delta_x=None,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=990.0,
        expires_at_monotonic_ms=2_000.0,
    )


def execution_budget(
    *,
    started_at: float = 1_000.0,
    hold_duration_ms: int = 20,
    max_execution_envelope_ms: int = 40,
) -> SinkExecutionBudget:
    return SinkExecutionBudget(
        clock_id=CLOCK_ID,
        started_at_monotonic_ms=started_at,
        absolute_deadline_monotonic_ms=(
            started_at + max_execution_envelope_ms
        ),
        remaining_ms=float(max_execution_envelope_ms),
        hold_duration_ms=hold_duration_ms,
        max_execution_envelope_ms=max_execution_envelope_ms,
    )


def execution_policy() -> ExecutionLeasePolicy:
    return ExecutionLeasePolicy(
        mode=MOVEMENT_MODE,
        capability=MOVEMENT_EXECUTION_CAPABILITY,
        allowed_controls=(
            "JUMP",
            "MOVE_BACKWARD",
            "MOVE_FORWARD",
            "STRAFE_LEFT",
            "STRAFE_RIGHT",
            "TURN_LEFT",
            "TURN_RIGHT",
        ),
        max_primitives=4_096,
        max_hold_duration_ms=1_000,
        max_execution_envelope_ms=1_250,
        max_queue_depth=8,
        min_pose_confidence=0.0,
        required_pose_components=(),
        position_coordinate_space=None,
        max_position_radius_95=None,
        max_yaw_error_95_deg=None,
    )


def authorization() -> ExecutionAuthorization:
    return ExecutionAuthorization(
        binding=authority_binding(),
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=900.0,
        expires_at_monotonic_ms=2_000.0,
        permitted_modes=frozenset({MOVEMENT_MODE}),
        permitted_capabilities=frozenset({MOVEMENT_EXECUTION_CAPABILITY}),
        lease_policy=execution_policy(),
    )


def execution_lease() -> ExecutionLease:
    return ExecutionLease(
        lease_id="lease:movement:fixture",
        binding=authority_binding(),
        owner_id="controller:movement:fixture",
        runtime_arm_nonce="arm:movement:fixture",
        mode=MOVEMENT_MODE,
        capability=MOVEMENT_EXECUTION_CAPABILITY,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=900.0,
        expires_at_monotonic_ms=2_000.0,
        first_sequence=1,
        max_hold_duration_ms=250,
        max_execution_envelope_ms=500,
        max_queue_depth=1,
        min_pose_confidence=0.9,
        required_pose_components=("POSITION_2D", "YAW"),
        position_coordinate_space="world_map_2d",
        max_position_radius_95=0.05,
        max_yaw_error_95_deg=5.0,
    )


def runtime_arm() -> InMemoryRuntimeArm:
    return InMemoryRuntimeArm(
        RuntimeArmSnapshot(
            binding=authority_binding(),
            arm_nonce="arm:movement:fixture",
            clock_id=CLOCK_ID,
            issued_at_monotonic_ms=900.0,
            expires_at_monotonic_ms=2_000.0,
            allowed_modes=frozenset({MOVEMENT_MODE}),
            allowed_capabilities=frozenset({MOVEMENT_EXECUTION_CAPABILITY}),
            lease_policy=execution_policy(),
            active=True,
        )
    )


def execution_pose() -> ExecutionPoseState:
    binding = authority_binding()
    return ExecutionPoseState(
        pose_id="pose:windows-input:one",
        actor_id=binding.actor_id,
        actor_instance_id=binding.actor_instance_id,
        actor_role=binding.actor_role,
        decision_context=binding.decision_context,
        target_profile=binding.target_profile,
        target_instance_id=binding.target_instance_id,
        authorization_id=binding.authorization_id,
        authorization_sha256=binding.authorization_sha256,
        state="VALID",
        source_scope="lab_evaluation_only",
        source_id="pose-source:fixture",
        capability="POSE_ESTIMATE",
        source_origins=("window_capture",),
        evidence_refs=("capture:fixture:one",),
        confidence=0.95,
        freshness_status="FRESH",
        available_pose_components=("POSITION_2D", "YAW"),
        position_coordinate_space="world_map_2d",
        position_radius_95=0.04,
        yaw_error_95_deg=4.0,
        clock_id=CLOCK_ID,
        observed_at_monotonic_ms=990.0,
        expires_at_monotonic_ms=2_000.0,
    )


class FakeClock:
    clock_id = CLOCK_ID

    def __init__(self, current_ms: float = 1_000.0) -> None:
        self.current_ms = current_ms
        self.fail_reads = False
        self.block_next = False
        self.block_thread_name: str | None = None
        self.read_started = Event()
        self.allow_read = Event()

    def now_ms(self) -> float:
        if self.fail_reads:
            raise RuntimeError("clock fixture failed")
        if self.block_next and (
            self.block_thread_name is None
            or self.block_thread_name == current_thread().name
        ):
            self.block_next = False
            self.read_started.set()
            if not self.allow_read.wait(timeout=1.0):
                raise RuntimeError("blocking clock fixture timed out")
        return self.current_ms

    def advance(self, milliseconds: int) -> None:
        self.current_ms += milliseconds


class FakeKeyboardBackend:
    def __init__(self) -> None:
        self.hot_snapshot = hot_snapshot()
        self.receipt_target: WindowsInputTargetBinding | None = None
        self.events: list[tuple[str, object]] = []
        self.prevalidate_count = 0
        self.inspect_count = 0
        self.release_receipt_count = 0
        self.down_outcomes: list[object] = []
        self.up_outcomes: list[object] = []
        self.block_hot_on_call: int | None = None
        self.hot_started = Event()
        self.allow_hot = Event()
        self.block_down = False
        self.down_started = Event()
        self.allow_down = Event()
        self.block_up = False
        self.up_started = Event()
        self.allow_up = Event()
        self.map_result = None

    def map_virtual_key(self, virtual_key: int) -> int:
        self.events.append(("map", virtual_key))
        return virtual_key if self.map_result is None else self.map_result

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt:
        self.prevalidate_count += 1
        self.events.append(("prevalidate", target.hwnd))
        return WindowsTargetIdentityReceipt(
            receipt_id="receipt:windows-input:fixture",
            target=self.receipt_target or target,
        )

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot:
        self.inspect_count += 1
        self.events.append(("inspect", receipt.receipt_id))
        if self.block_hot_on_call == self.inspect_count:
            self.hot_started.set()
            if not self.allow_hot.wait(timeout=1.0):
                raise RuntimeError("blocking hot inspection fixture timed out")
        return self.hot_snapshot

    def send_scan_code(self, scan_code: int, *, key_up: bool) -> int:
        direction = "up" if key_up else "down"
        self.events.append((direction, scan_code))
        if key_up and self.block_up:
            self.up_started.set()
            if not self.allow_up.wait(timeout=1.0):
                raise RuntimeError("blocking key-up fixture timed out")
        if not key_up and self.block_down:
            self.down_started.set()
            if not self.allow_down.wait(timeout=1.0):
                raise RuntimeError("blocking key-down fixture timed out")
        outcomes = self.up_outcomes if key_up else self.down_outcomes
        outcome = outcomes.pop(0) if outcomes else 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None:
        self.release_receipt_count += 1
        self.events.append(("release_receipt", receipt.receipt_id))


class AdvancingWaiter:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.timeouts: list[int] = []
        self.on_wait = None

    def __call__(
        self, cancellation: CooperativeCancellation, timeout_ms: int
    ) -> bool:
        self.timeouts.append(timeout_ms)
        self.clock.advance(timeout_ms)
        if self.on_wait is not None:
            self.on_wait(cancellation)
        return cancellation.is_cancelled


def make_sink(
    *,
    backend: FakeKeyboardBackend | None = None,
    clock: FakeClock | None = None,
    waiter=None,
) -> tuple[WindowsSendInputSink, FakeKeyboardBackend, FakeClock, AdvancingWaiter]:
    exact_backend = backend or FakeKeyboardBackend()
    exact_clock = clock or FakeClock()
    exact_waiter = waiter or AdvancingWaiter(exact_clock)
    sink = WindowsSendInputSink(
        target=target_binding(),
        backend=exact_backend,
        clock=exact_clock,
        waiter=exact_waiter,
    )
    return sink, exact_backend, exact_clock, exact_waiter


class WindowsSendInputSinkTests(unittest.TestCase):
    def test_inspect_hot_target_is_read_only(self) -> None:
        sink, backend, _, _ = make_sink()
        backend.events.clear()

        snapshot = sink.inspect_hot_target()

        self.assertEqual(snapshot, hot_snapshot())
        self.assertEqual(backend.inspect_count, 1)
        self.assertEqual(
            [event for event in backend.events if event[0] in {"down", "up"}],
            [],
        )

    def test_sink_composes_with_f1_gateway_without_a_live_runner(self) -> None:
        sink, backend, clock, _ = make_sink()
        gate = ExecutionGateway(
            authorization=authorization(),
            lease=execution_lease(),
            runtime_arm=runtime_arm(),
            clock=clock,
            sink=sink,
        )

        result = gate.execute(movement_primitive(), execution_pose())

        self.assertEqual((result.status, result.reason_code), ("EXECUTED", "EXECUTED"))
        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_hold_duration_is_measured_without_hidden_release_reserve(self) -> None:
        sink, backend, _, waiter = make_sink()
        backend.events.clear()

        sink.apply_bounded(
            movement_primitive(controls=("MOVE_FORWARD", "STRAFE_RIGHT")),
            CooperativeCancellation(),
            execution_budget(),
        )

        self.assertEqual(
            [event for event in backend.events if event[0] in {"down", "up"}],
            [
                ("down", DEFAULT_CONTROL_VIRTUAL_KEYS["MOVE_FORWARD"]),
                ("down", DEFAULT_CONTROL_VIRTUAL_KEYS["STRAFE_RIGHT"]),
                ("up", DEFAULT_CONTROL_VIRTUAL_KEYS["STRAFE_RIGHT"]),
                ("up", DEFAULT_CONTROL_VIRTUAL_KEYS["MOVE_FORWARD"]),
            ],
        )
        timing = sink.last_timing
        self.assertIsInstance(timing, KeyHoldTiming)
        assert timing is not None
        self.assertEqual(timing.first_key_down_at_monotonic_ms, 1_000.0)
        self.assertEqual(timing.first_key_up_started_at_monotonic_ms, 1_020.0)
        self.assertEqual(timing.observed_hold_duration_ms, 20.0)
        self.assertEqual(timing.requested_hold_duration_ms, 20)
        self.assertLessEqual(timing.completed_at_monotonic_ms, 1_040.0)
        self.assertTrue(waiter.timeouts)
        self.assertLessEqual(max(waiter.timeouts), CANCELLATION_POLL_MS)

    def test_strafe_first_profile_maps_a_d_and_has_no_keyboard_turn_transport(self) -> None:
        self.assertEqual(DEFAULT_CONTROL_VIRTUAL_KEYS["STRAFE_LEFT"], 0x41)
        self.assertEqual(DEFAULT_CONTROL_VIRTUAL_KEYS["STRAFE_RIGHT"], 0x44)
        self.assertNotIn("TURN_LEFT", DEFAULT_CONTROL_VIRTUAL_KEYS)
        self.assertNotIn("TURN_RIGHT", DEFAULT_CONTROL_VIRTUAL_KEYS)
        sink, backend, _, _ = make_sink()
        backend.events.clear()
        with self.assertRaisesRegex(
            WindowsInputSinkError, "no keyboard transport"
        ):
            sink.apply_bounded(
                movement_primitive(controls=("TURN_LEFT",)),
                CooperativeCancellation(),
                execution_budget(),
            )
        self.assertEqual(
            [event for event in backend.events if event[0] in {"map", "down", "up"}],
            [],
        )

    def test_exact_combat_keys_share_the_same_non_extended_scan_code_transport(self) -> None:
        expected_virtual_keys = {
            "TARGET_NEAREST_HOSTILE": 0x09,
            "ACTION_SLOT_1": 0x31,
            "ACTION_SLOT_2": 0x32,
            "ACTION_SLOT_3": 0x33,
        }
        self.assertEqual(
            {
                control: DEFAULT_CONTROL_VIRTUAL_KEYS[control]
                for control in expected_virtual_keys
            },
            expected_virtual_keys,
        )
        for control, virtual_key in expected_virtual_keys.items():
            with self.subTest(control=control):
                sink, backend, _, _ = make_sink()
                backend.events.clear()
                sink.apply_bounded(
                    combat_primitive(control=control),
                    CooperativeCancellation(),
                    execution_budget(
                        hold_duration_ms=25,
                        max_execution_envelope_ms=75,
                    ),
                )
                self.assertEqual(
                    [event for event in backend.events if event[0] in {"down", "up"}],
                    [("down", virtual_key), ("up", virtual_key)],
                )
                self.assertEqual(sink.owned_scan_codes, ())

    def test_cold_identity_is_prevalidated_once_and_hot_checks_have_no_hash_data(self) -> None:
        sink, backend, _, _ = make_sink()
        self.assertEqual(backend.prevalidate_count, 1)

        sink.apply_bounded(
            movement_primitive(), CooperativeCancellation(), execution_budget()
        )

        self.assertEqual(backend.prevalidate_count, 1)
        self.assertGreaterEqual(backend.inspect_count, 4)
        self.assertNotIn("executable_path", WindowsHotTargetSnapshot.__dataclass_fields__)
        self.assertNotIn("executable_sha256", WindowsHotTargetSnapshot.__dataclass_fields__)

    def test_invalid_cold_receipt_is_released_and_constructor_fails(self) -> None:
        backend = FakeKeyboardBackend()
        backend.receipt_target = replace(
            target_binding(), executable_sha256="C" * 64
        )

        with self.assertRaises(WindowsTargetBindingError):
            make_sink(backend=backend)

        self.assertEqual(backend.prevalidate_count, 1)
        self.assertEqual(backend.release_receipt_count, 1)

    def test_each_hot_foreground_pid_hwnd_and_liveness_pin_fails_closed(self) -> None:
        valid = hot_snapshot()
        variants = (
            replace(valid, hwnd=0x9999),
            replace(valid, foreground_hwnd=0x9999),
            replace(valid, owner_pid=43),
            replace(
                valid,
                process_creation_time_100ns=valid.process_creation_time_100ns + 1,
            ),
            replace(valid, process_alive=False),
            replace(valid, visible=False),
            replace(valid, minimized=True),
        )
        for snapshot in variants:
            with self.subTest(snapshot=snapshot):
                backend = FakeKeyboardBackend()
                backend.hot_snapshot = snapshot
                sink, _, _, _ = make_sink(backend=backend)

                with self.assertRaises(WindowsTargetBindingError):
                    sink.apply_bounded(
                        movement_primitive(),
                        CooperativeCancellation(),
                        execution_budget(),
                    )

                self.assertNotIn("down", self._directions(backend))
                self.assertEqual(sink.owned_scan_codes, ())

    def test_generation_registered_before_blocking_validation(self) -> None:
        clock = FakeClock()
        sink, backend, _, _ = make_sink(clock=clock)
        clock.block_next = True
        errors: list[BaseException] = []
        worker = Thread(
            target=lambda: self._capture_error(
                errors,
                lambda: sink.apply_bounded(
                    movement_primitive(),
                    CooperativeCancellation(),
                    execution_budget(),
                ),
            )
        )
        worker.start()
        self.assertTrue(clock.read_started.wait(timeout=1.0))

        sink.release_all()
        clock.allow_read.set()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InputCancelledError)
        self.assertNotIn("down", self._directions(backend))

    def test_release_does_not_block_behind_hot_identity_inspection(self) -> None:
        backend = FakeKeyboardBackend()
        backend.block_hot_on_call = 1
        sink, _, _, _ = make_sink(backend=backend)
        apply_errors: list[BaseException] = []
        apply_worker = Thread(
            target=lambda: self._capture_error(
                apply_errors,
                lambda: sink.apply_bounded(
                    movement_primitive(),
                    CooperativeCancellation(),
                    execution_budget(),
                ),
            )
        )
        apply_worker.start()
        self.assertTrue(backend.hot_started.wait(timeout=1.0))

        release_errors: list[BaseException] = []
        release_worker = Thread(
            target=lambda: self._capture_error(release_errors, sink.release_all)
        )
        release_worker.start()
        release_worker.join(timeout=0.2)
        self.assertFalse(release_worker.is_alive())
        self.assertEqual(release_errors, [])

        backend.allow_hot.set()
        apply_worker.join(timeout=1.0)
        self.assertFalse(apply_worker.is_alive())
        self.assertIsInstance(apply_errors[0], InputCancelledError)
        self.assertNotIn("down", self._directions(backend))

    def test_release_linearizes_with_inflight_down_and_unwinds_it(self) -> None:
        backend = FakeKeyboardBackend()
        backend.block_down = True
        clock = FakeClock()
        sink, _, _, _ = make_sink(backend=backend, clock=clock)
        apply_errors: list[BaseException] = []
        apply_worker = Thread(
            target=lambda: self._capture_error(
                apply_errors,
                lambda: sink.apply_bounded(
                    movement_primitive(),
                    CooperativeCancellation(),
                    execution_budget(),
                ),
            ),
            name="f2-apply-inflight",
        )
        apply_worker.start()
        self.assertTrue(backend.down_started.wait(timeout=1.0))

        release_worker = Thread(target=sink.release_all)
        release_worker.start()
        release_worker.join(timeout=0.05)
        self.assertTrue(release_worker.is_alive())
        clock.block_next = True
        clock.block_thread_name = "f2-apply-inflight"
        backend.allow_down.set()
        self.assertTrue(clock.read_started.wait(timeout=1.0))
        release_worker.join(timeout=1.0)
        clock.allow_read.set()
        apply_worker.join(timeout=1.0)

        self.assertFalse(release_worker.is_alive())
        self.assertFalse(apply_worker.is_alive())
        self.assertIsInstance(apply_errors[0], InputCancelledError)
        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_tail_release_wins_after_key_up_before_completion_commit(self) -> None:
        backend = FakeKeyboardBackend()
        backend.block_up = True
        sink, _, _, _ = make_sink(backend=backend)
        errors: list[BaseException] = []
        worker = Thread(
            target=lambda: self._capture_error(
                errors,
                lambda: sink.apply_bounded(
                    movement_primitive(),
                    CooperativeCancellation(),
                    execution_budget(),
                ),
            )
        )
        worker.start()
        self.assertTrue(backend.up_started.wait(timeout=1.0))

        sink.release_all()
        backend.allow_up.set()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertIsInstance(errors[0], InputCancelledError)
        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertIsNone(sink.last_timing)

    def test_exact_integer_send_count_is_required_in_both_directions(self) -> None:
        for outcome in (True, False, 1.0, 0.0, OSError("down fixture")):
            with self.subTest(direction="down", outcome=outcome):
                backend = FakeKeyboardBackend()
                backend.down_outcomes = [outcome]
                sink, _, _, _ = make_sink(backend=backend)
                with self.assertRaises(Exception):
                    sink.apply_bounded(
                        movement_primitive(),
                        CooperativeCancellation(),
                        execution_budget(),
                    )
                self.assertEqual(self._directions(backend), ["down", "up"])
                self.assertEqual(sink.owned_scan_codes, ())

        for outcome in (True, False, 1.0, 0.0, OSError("up fixture")):
            with self.subTest(direction="up", outcome=outcome):
                backend = FakeKeyboardBackend()
                backend.up_outcomes = [outcome, 1]
                sink, _, _, _ = make_sink(backend=backend)
                with self.assertRaises(WindowsInputSinkError):
                    sink.apply_bounded(
                        movement_primitive(),
                        CooperativeCancellation(),
                        execution_budget(),
                    )
                self.assertEqual(self._directions(backend), ["down", "up", "up"])
                self.assertEqual(sink.owned_scan_codes, ())

    def test_clock_failure_after_down_cannot_prevent_emergency_key_up(self) -> None:
        clock = FakeClock()

        class FailClockAfterDownBackend(FakeKeyboardBackend):
            def send_scan_code(self, scan_code: int, *, key_up: bool) -> int:
                submitted = super().send_scan_code(scan_code, key_up=key_up)
                if not key_up:
                    clock.fail_reads = True
                return submitted

        backend = FailClockAfterDownBackend()
        sink, _, _, _ = make_sink(backend=backend, clock=clock)

        with self.assertRaises(WindowsInputSinkError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_insufficient_actual_remaining_time_is_rejected_before_down(self) -> None:
        clock = FakeClock(current_ms=1_016.0)
        sink, backend, _, _ = make_sink(clock=clock)

        with self.assertRaises(WindowsInputDeadlineError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

        self.assertNotIn("down", self._directions(backend))

    def test_hot_check_budget_loss_is_rejected_at_linearized_pre_down_gate(self) -> None:
        clock = FakeClock()

        class BudgetConsumingHotBackend(FakeKeyboardBackend):
            def inspect_hot(
                self, receipt: WindowsTargetIdentityReceipt
            ) -> WindowsHotTargetSnapshot:
                snapshot = super().inspect_hot(receipt)
                clock.advance(8)
                return snapshot

        backend = BudgetConsumingHotBackend()
        sink, _, _, _ = make_sink(backend=backend, clock=clock)

        with self.assertRaises(WindowsInputDeadlineError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

        self.assertEqual(self._directions(backend), [])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_budget_hold_and_envelope_must_match_primitive_exactly(self) -> None:
        sink, backend, _, _ = make_sink()
        mismatches = (
            execution_budget(hold_duration_ms=19),
            execution_budget(hold_duration_ms=20, max_execution_envelope_ms=39),
        )
        for budget in mismatches:
            with self.subTest(budget=budget):
                with self.assertRaises(WindowsInputDeadlineError):
                    sink.apply_bounded(
                        movement_primitive(), CooperativeCancellation(), budget
                    )
        self.assertNotIn("down", self._directions(backend))

    def test_cancellation_is_observed_with_at_most_five_ms_polling(self) -> None:
        sink, backend, _, waiter = make_sink()

        def cancel(cancellation: CooperativeCancellation) -> None:
            cancellation.cancel()

        waiter.on_wait = cancel
        with self.assertRaises(InputCancelledError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

        self.assertLessEqual(max(waiter.timeouts), CANCELLATION_POLL_MS)
        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_focus_loss_during_hold_emits_only_owned_emergency_key_up(self) -> None:
        sink, backend, _, waiter = make_sink()

        def lose_focus(_cancellation: CooperativeCancellation) -> None:
            backend.hot_snapshot = replace(
                backend.hot_snapshot, foreground_hwnd=0x9999
            )

        waiter.on_wait = lose_focus
        with self.assertRaises(WindowsInputSinkError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

        self.assertEqual(self._directions(backend), ["down", "up"])
        self.assertEqual(sink.owned_scan_codes, ())

    def test_default_transport_rejects_extended_or_non_integer_scan_codes(self) -> None:
        for value in (0x100, True, 1.0, 0):
            with self.subTest(value=value):
                backend = FakeKeyboardBackend()
                backend.map_result = value
                with self.assertRaises(WindowsInputSinkError):
                    make_sink(backend=backend)
                self.assertEqual(backend.prevalidate_count, 0)

    def test_v1_rejects_configurable_extended_virtual_keys_before_mapping(self) -> None:
        backend = FakeKeyboardBackend()
        extended_mapping = dict(DEFAULT_CONTROL_VIRTUAL_KEYS)
        extended_mapping["JUMP"] = 0xA3  # VK_RCONTROL requires an E0 prefix.

        with self.assertRaises(ValueError):
            WindowsSendInputSink(
                target=target_binding(),
                backend=backend,
                clock=FakeClock(),
                control_virtual_keys=extended_mapping,
            )

        self.assertEqual(backend.events, [])

    def test_external_backend_uses_exactly_one_scan_code_input_abi(self) -> None:
        native = self._load_native_backend()
        captures: list[tuple[int, int, int, int, int, int]] = []

        class FakeSendInput:
            def __call__(self, count, pointer, input_size):
                event = ctypes.cast(
                    pointer, ctypes.POINTER(native._INPUT)
                ).contents
                captures.append(
                    (
                        int(count),
                        int(input_size),
                        int(event.type),
                        int(event.ki.wVk),
                        int(event.ki.wScan),
                        int(event.ki.dwFlags),
                    )
                )
                return 1

        class FakeUser32:
            SendInput = FakeSendInput()

        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._user32 = FakeUser32()
        with self.assertRaises(ValueError):
            backend.map_virtual_key(0xA3)  # VK_RCONTROL / E0 1D
        self.assertEqual(backend.send_scan_code(0x11, key_up=False), 1)
        self.assertEqual(backend.send_scan_code(0x11, key_up=True), 1)

        expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(
            captures,
            [
                (1, expected_size, 1, 0, 0x11, native.KEYEVENTF_SCANCODE),
                (
                    1,
                    expected_size,
                    1,
                    0,
                    0x11,
                    native.KEYEVENTF_SCANCODE | native.KEYEVENTF_KEYUP,
                ),
            ],
        )

        for invalid_count in (True, False, 1.0, 0.0):
            with self.subTest(invalid_count=invalid_count):
                class InvalidCountSendInput:
                    def __call__(self, count, pointer, input_size):
                        return invalid_count

                class InvalidCountUser32:
                    SendInput = InvalidCountSendInput()

                invalid_backend = object.__new__(
                    native.CtypesWin32KeyboardBackend
                )
                invalid_backend._user32 = InvalidCountUser32()
                with self.assertRaises(OSError):
                    invalid_backend.send_scan_code(0x11, key_up=False)

    def test_native_metadata_open_uses_exact_legacy_fallback_rights(self) -> None:
        native = self._load_native_backend()
        pid = 76_276
        fallback_handle = 0xBEEF
        self.assertEqual(
            native.PROCESS_QUERY_LIMITED_INFORMATION | native.SYNCHRONIZE,
            0x00101000,
        )
        self.assertEqual(
            native.PROCESS_QUERY_INFORMATION | native.SYNCHRONIZE,
            0x00100400,
        )

        class FakeKernel32:
            def __init__(self) -> None:
                self.calls: list[tuple[int, bool, int]] = []

            def OpenProcess(self, access, inherit, requested_pid):
                self.calls.append((access, inherit, requested_pid))
                if len(self.calls) == 1:
                    ctypes.set_last_error(native.ERROR_ACCESS_DENIED)
                    return 0
                ctypes.set_last_error(0)
                return fallback_handle

        kernel32 = FakeKernel32()
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._kernel32 = kernel32

        self.assertEqual(backend._open_metadata_process(pid), fallback_handle)
        self.assertEqual(
            kernel32.calls,
            [
                (
                    native.PROCESS_QUERY_LIMITED_INFORMATION
                    | native.SYNCHRONIZE,
                    False,
                    pid,
                ),
                (
                    native.PROCESS_QUERY_INFORMATION | native.SYNCHRONIZE,
                    False,
                    pid,
                ),
            ],
        )
        forbidden_vm_rights = 0x0008 | 0x0010 | 0x0020
        self.assertTrue(
            all(access & forbidden_vm_rights == 0 for access, _, _ in kernel32.calls)
        )

    def test_native_metadata_open_prefers_limited_rights_without_fallback(self) -> None:
        native = self._load_native_backend()
        preferred_handle = 0xABCD

        class FakeKernel32:
            def __init__(self) -> None:
                self.calls: list[tuple[int, bool, int]] = []

            def OpenProcess(self, access, inherit, requested_pid):
                self.calls.append((access, inherit, requested_pid))
                return preferred_handle

        kernel32 = FakeKernel32()
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._kernel32 = kernel32

        self.assertEqual(backend._open_metadata_process(76_276), preferred_handle)
        self.assertEqual(
            kernel32.calls,
            [(0x00101000, False, 76_276)],
        )

    def test_native_metadata_open_never_falls_back_on_other_errors(self) -> None:
        native = self._load_native_backend()

        class FakeKernel32:
            def __init__(self) -> None:
                self.calls: list[tuple[int, bool, int]] = []

            def OpenProcess(self, access, inherit, requested_pid):
                self.calls.append((access, inherit, requested_pid))
                ctypes.set_last_error(87)
                return 0

        kernel32 = FakeKernel32()
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._kernel32 = kernel32

        with self.assertRaises(OSError):
            backend._open_metadata_process(76_276)

        self.assertEqual(
            kernel32.calls,
            [
                (
                    native.PROCESS_QUERY_LIMITED_INFORMATION
                    | native.SYNCHRONIZE,
                    False,
                    76_276,
                )
            ],
        )

    def test_failed_cold_validation_closes_legacy_fallback_handle(self) -> None:
        native = self._load_native_backend()
        fallback_handle = 0xCAFE
        close_calls: list[int] = []

        class FakeUser32:
            @staticmethod
            def IsWindow(hwnd):
                return 1

            @staticmethod
            def GetWindowThreadProcessId(hwnd, pid_pointer):
                ctypes.cast(
                    pid_pointer, ctypes.POINTER(ctypes.wintypes.DWORD)
                ).contents.value = 76_276
                return 1

        class FakeKernel32:
            def __init__(self) -> None:
                self.open_calls = 0

            def OpenProcess(self, access, inherit, requested_pid):
                self.open_calls += 1
                if self.open_calls == 1:
                    ctypes.set_last_error(native.ERROR_ACCESS_DENIED)
                    return 0
                return fallback_handle

            @staticmethod
            def QueryFullProcessImageNameW(process, flags, buffer, size_pointer):
                ctypes.set_last_error(87)
                return 0

            @staticmethod
            def CloseHandle(process):
                close_calls.append(process)
                return 1

        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._user32 = FakeUser32()
        backend._kernel32 = FakeKernel32()

        with self.assertRaises(OSError):
            backend.prevalidate_target(replace(target_binding(), pid=76_276))

        self.assertEqual(close_calls, [fallback_handle])

    def test_native_receipt_release_closes_retained_handle_once(self) -> None:
        native = self._load_native_backend()
        retained_handle = 0xD00D
        close_calls: list[int] = []

        class FakeKernel32:
            @staticmethod
            def CloseHandle(process):
                close_calls.append(process)
                return 1

        receipt = WindowsTargetIdentityReceipt(
            receipt_id="receipt:native:legacy-fixture",
            target=target_binding(),
        )
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._kernel32 = FakeKernel32()
        backend._receipt_lock = native.RLock()
        backend._process_handles = {receipt.receipt_id: retained_handle}

        backend.release_identity_receipt(receipt)
        backend.release_identity_receipt(receipt)

        self.assertEqual(close_calls, [retained_handle])

    def test_close_releases_receipt_once_and_rejects_future_apply(self) -> None:
        sink, backend, _, _ = make_sink()
        sink.close()
        sink.close()
        self.assertEqual(backend.release_receipt_count, 1)
        with self.assertRaises(WindowsInputSinkError):
            sink.apply_bounded(
                movement_primitive(), CooperativeCancellation(), execution_budget()
            )

    def test_camera_snapshot_is_one_exact_native_view_command(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(backend.send_camera_view_snapshot(view_index=3), 99)
        self.assertEqual(calls, [(
            "/run SaveView(3)",
            "camera-view-snapshot",
        )])
        for invalid in (1, 6, True):
            with self.subTest(view_index=invalid):
                with self.assertRaises(ValueError):
                    backend.send_camera_view_snapshot(view_index=invalid)

    def test_camera_home_restores_operator_view_without_rebuilding_it(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(
            backend.send_camera_home_command(view_index=3),
            99,
        )
        self.assertEqual(calls, [(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            'SetCVar("cameraPivot","0");'
            'SetCVar("rotateMinimap","0");'
            "SetView(3)",
            "camera-home",
        )])
        command = calls[0][0]
        self.assertNotIn("ResetView", command)
        self.assertNotIn("CameraZoom", command)
        for invalid in (1, 6, True):
            with self.subTest(view_index=invalid):
                with self.assertRaises(ValueError):
                    backend.send_camera_home_command(view_index=invalid)
        with self.assertRaises(ValueError):
            backend.send_camera_home_command(view_index=3, smart_pivot="true")

    def test_camera_home_can_explicitly_enable_smart_pivot_for_wmo(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(
            backend.send_camera_home_command(view_index=3, smart_pivot=True),
            99,
        )
        self.assertIn('SetCVar("cameraPivot","1");', calls[0][0])

    def test_navigation_camera_preferences_preserve_pitch_zoom_and_view(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(backend.send_navigation_camera_preferences(), 99)
        self.assertEqual(calls, [(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            'SetCVar("cameraPivot","0");'
            'SetCVar("rotateMinimap","0")',
            "navigation-camera-preferences",
        )])
        command = calls[0][0]
        self.assertNotIn("ResetView", command)
        self.assertNotIn("SetView", command)
        self.assertNotIn("CameraZoom", command)

    def test_camera_pivot_profile_can_disable_outdoor_smart_pivot(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(
            backend.send_camera_pivot_profile(
                camera_distance_max_factor=2.0,
                smart_pivot=False,
            ),
            99,
        )
        self.assertEqual(calls, [(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            'SetCVar("cameraPivot","0");'
            'SetCVar("cameraDistanceMaxFactor","2");'
            'SetCVar("rotateMinimap","0")',
            "camera-pivot-profile",
        )])
        for invalid in (1, 0, "false"):
            with self.subTest(smart_pivot=invalid):
                with self.assertRaises(ValueError):
                    backend.send_camera_pivot_profile(
                        camera_distance_max_factor=2.0,
                        smart_pivot=invalid,
                    )

    def test_stand_is_one_exact_non_toggle_command(self) -> None:
        native = self._load_native_backend()
        calls: list[tuple[str, str]] = []
        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._send_fixed_chat_command = lambda command, failure_label: (
            calls.append((command, failure_label)) or 99
        )

        self.assertEqual(backend.send_stand_command(), 99)
        self.assertEqual(calls, [("/stand", "stand")])

    @staticmethod
    def _directions(backend: FakeKeyboardBackend) -> list[str]:
        return [
            str(event[0])
            for event in backend.events
            if event[0] in {"down", "up"}
        ]

    @staticmethod
    def _capture_error(errors: list[BaseException], action) -> None:
        try:
            action()
        except BaseException as error:
            errors.append(error)

    @staticmethod
    def _load_native_backend():
        path = ROOT / "integrations" / "windows-input" / "send_input_backend.py"
        spec = importlib.util.spec_from_file_location(
            "pa_test_win32_send_input_backend", path
        )
        if spec is None or spec.loader is None:
            raise AssertionError("native backend test module cannot be loaded")
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        return native


if __name__ == "__main__":
    unittest.main()
