from __future__ import annotations

import ctypes
import importlib.util
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
import unittest

from perfect_assassin.execution.combat_gateway import CombatInputPrimitive
from perfect_assassin.execution.ports import (
    CooperativeCancellation,
    InputCancelledError,
    SinkExecutionBudget,
)
from perfect_assassin.execution.windows_mouse_turn import (
    TURN_DELTA_TO_HOLD_MS,
    TURN_ANTI_CLICK_EXCURSION_PX,
    TURN_ANTI_CLICK_SETTLE_MS,
    TURN_PRE_DRAG_SETTLE_MS,
    TURN_EXECUTION_SLACK_MS,
    WindowsCursorPlacement,
    WindowsCombatInputSink,
    WindowsMouseTurnSink,
)
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsInputDeadlineError,
    WindowsInputSinkError,
    WindowsInputTargetBinding,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)
from tests.test_windows_send_input_sink import CLOCK_ID, FakeClock, AdvancingWaiter, target_binding


ROOT = Path(__file__).resolve().parents[1]


def turn_primitive(
    *,
    direction: str = "TURN_RIGHT",
    delta_x: int = 14,
    hold_ms: int = 35,
) -> CombatInputPrimitive:
    # The bound TBC client follows native Win32 relative mouse-X while RMB is
    # held: negative turns left and positive turns right.
    signed_delta = -abs(delta_x) if direction == "TURN_LEFT" else abs(delta_x)
    return CombatInputPrimitive(
        primitive_id=f"primitive:mouse:{direction.lower()}:{abs(delta_x)}",
        lease_id="lease:combat:fixture",
        binding=target_binding().authority_binding,
        owner_id="controller:combat:fixture",
        runtime_arm_nonce="arm:combat:fixture",
        mode="COMBAT_ONLY",
        capability="COMBAT_EXECUTION",
        sequence=1,
        controls=(direction,),
        hold_duration_ms=hold_ms,
        max_execution_envelope_ms=hold_ms + TURN_EXECUTION_SLACK_MS,
        mouse_delta_x=signed_delta,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=990.0,
        expires_at_monotonic_ms=2_000.0,
    )


def execution_budget(*, hold_ms: int = 35) -> SinkExecutionBudget:
    envelope_ms = hold_ms + TURN_EXECUTION_SLACK_MS
    return SinkExecutionBudget(
        clock_id=CLOCK_ID,
        started_at_monotonic_ms=1_000.0,
        absolute_deadline_monotonic_ms=1_000.0 + envelope_ms,
        remaining_ms=float(envelope_ms),
        hold_duration_ms=hold_ms,
        max_execution_envelope_ms=envelope_ms,
    )


def visible_select_primitive() -> CombatInputPrimitive:
    return CombatInputPrimitive(
        primitive_id="primitive:mouse:visible-select",
        lease_id="lease:combat:fixture",
        binding=target_binding().authority_binding,
        owner_id="controller:combat:fixture",
        runtime_arm_nonce="arm:combat:fixture",
        mode="COMBAT_ONLY",
        capability="COMBAT_EXECUTION",
        sequence=1,
        controls=("TARGET_VISIBLE_HOSTILE",),
        hold_duration_ms=25,
        max_execution_envelope_ms=125,
        mouse_delta_x=None,
        clock_id=CLOCK_ID,
        issued_at_monotonic_ms=990.0,
        expires_at_monotonic_ms=2_000.0,
        mouse_click_x_normalized=0.31,
        mouse_click_y_normalized=0.42,
    )


def visible_click_budget() -> SinkExecutionBudget:
    return SinkExecutionBudget(
        clock_id=CLOCK_ID,
        started_at_monotonic_ms=1_000.0,
        absolute_deadline_monotonic_ms=1_125.0,
        remaining_ms=125.0,
        hold_duration_ms=25,
        max_execution_envelope_ms=125,
    )


def exact_hot() -> WindowsHotTargetSnapshot:
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


class FakeMouseBackend:
    def __init__(self) -> None:
        self.hot_snapshot = exact_hot()
        self.receipt_target: WindowsInputTargetBinding | None = None
        self.events: list[tuple[str, object]] = []
        self.turn_mode_down_outcomes: list[object] = []
        self.turn_mode_up_outcomes: list[object] = []
        self.select_mode_down_outcomes: list[object] = []
        self.select_mode_up_outcomes: list[object] = []
        self.move_outcomes: list[object] = []
        self.release_receipt_count = 0
        self.cursor_placement = WindowsCursorPlacement(20, 30, 500, 400)
        self.block_move = False
        self.move_started = Event()
        self.allow_move = Event()

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt:
        self.events.append(("prevalidate", target.hwnd))
        return WindowsTargetIdentityReceipt(
            receipt_id="receipt:mouse:fixture",
            target=self.receipt_target or target,
        )

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot:
        self.events.append(("inspect", receipt.receipt_id))
        return self.hot_snapshot

    def send_turn_mode_key(self, *, key_up: bool) -> int:
        direction = "turn_mode_up" if key_up else "turn_mode_down"
        self.events.append((direction, 0))
        outcomes = self.turn_mode_up_outcomes if key_up else self.turn_mode_down_outcomes
        outcome = outcomes.pop(0) if outcomes else 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]

    def send_target_select_key(self, *, key_up: bool) -> int:
        direction = "select_mode_up" if key_up else "select_mode_down"
        self.events.append((direction, 0))
        outcomes = (
            self.select_mode_up_outcomes
            if key_up
            else self.select_mode_down_outcomes
        )
        outcome = outcomes.pop(0) if outcomes else 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]

    def send_relative_mouse(self, *, delta_x: int, delta_y: int) -> int:
        self.events.append(("move", (delta_x, delta_y)))
        if self.block_move:
            self.move_started.set()
            if not self.allow_move.wait(timeout=1.0):
                raise RuntimeError("blocking mouse fixture timed out")
        outcome = self.move_outcomes.pop(0) if self.move_outcomes else 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]

    def prepare_world_drag_cursor(self, *, hwnd: int) -> WindowsCursorPlacement:
        self.events.append(("prepare_cursor", hwnd))
        return self.cursor_placement

    def prepare_client_point_cursor(
        self, *, hwnd: int, x_normalized: float, y_normalized: float
    ) -> WindowsCursorPlacement:
        self.events.append(
            ("prepare_client_point", (hwnd, x_normalized, y_normalized))
        )
        return self.cursor_placement

    def restore_cursor_position(self, placement: WindowsCursorPlacement) -> int:
        self.events.append(("restore_cursor", placement))
        return 1

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None:
        self.release_receipt_count += 1
        self.events.append(("release_receipt", receipt.receipt_id))


def make_sink(
    *, backend: FakeMouseBackend | None = None, clock: FakeClock | None = None
) -> tuple[WindowsMouseTurnSink, FakeMouseBackend, FakeClock, AdvancingWaiter]:
    exact_backend = backend or FakeMouseBackend()
    exact_clock = clock or FakeClock()
    waiter = AdvancingWaiter(exact_clock)
    sink = WindowsMouseTurnSink(
        target=target_binding(),
        backend=exact_backend,
        clock=exact_clock,
        waiter=waiter,
    )
    return sink, exact_backend, exact_clock, waiter


class RecordingDelegate:
    max_apply_block_ms = 250
    supports_cooperative_cancellation = True

    def __init__(self) -> None:
        self.applied: list[CombatInputPrimitive] = []
        self.release_count = 0
        self.close_count = 0

    def apply_bounded(self, primitive, cancellation, budget) -> None:
        self.applied.append(primitive)

    def release_all(self) -> None:
        self.release_count += 1

    def close(self) -> None:
        self.close_count += 1


class WindowsMouseTurnSinkTests(unittest.TestCase):
    def test_visible_hostile_selection_uses_one_left_click_without_camera_turn(self) -> None:
        sink, backend, _, _ = make_sink()
        backend.events.clear()

        sink.apply_bounded(
            visible_select_primitive(),
            CooperativeCancellation(),
            visible_click_budget(),
        )

        self.assertEqual(
            [
                event
                for event in backend.events
                if event[0]
                in {
                    "select_mode_down",
                    "select_mode_up",
                    "turn_mode_down",
                    "turn_mode_up",
                    "move",
                }
            ],
            [("select_mode_down", 0), ("select_mode_up", 0)],
        )
        self.assertIn(
            (
                "prepare_client_point",
                (target_binding().hwnd, 0.31, 0.42),
            ),
            backend.events,
        )

    def test_small_dispatch_delay_does_not_invalidate_full_execution_envelope(self) -> None:
        clock = FakeClock(current_ms=1_001.0)
        sink, backend, _, _ = make_sink(clock=clock)
        backend.events.clear()

        sink.apply_bounded(
            turn_primitive(),
            CooperativeCancellation(),
            execution_budget(),
        )

        self.assertEqual(
            [event[0] for event in backend.events if event[0] in {"turn_mode_down", "move", "turn_mode_up"}],
            ["turn_mode_down", "move", "move", "move", "turn_mode_up"],
        )
        self.assertFalse(sink.turn_mode_owned)

    def test_reviewed_latency_slack_covers_post_drag_cursor_cleanup(self) -> None:
        clock = FakeClock(current_ms=1_040.0)
        sink, backend, _, _ = make_sink(clock=clock)
        backend.events.clear()

        sink.apply_bounded(
            turn_primitive(),
            CooperativeCancellation(),
            execution_budget(),
        )

        self.assertEqual(
            [
                event[0]
                for event in backend.events
                if event[0]
                in {"turn_mode_down", "move", "turn_mode_up", "restore_cursor"}
            ],
            [
                "turn_mode_down",
                "move",
                "move",
                "move",
                "turn_mode_up",
                "restore_cursor",
            ],
        )
        self.assertFalse(sink.turn_mode_owned)

    def test_each_reviewed_profile_is_exact_turn_binding_plus_mouse_delta(self) -> None:
        for delta, hold_ms in TURN_DELTA_TO_HOLD_MS.items():
            for direction in ("TURN_LEFT", "TURN_RIGHT"):
                with self.subTest(delta=delta, direction=direction):
                    sink, backend, _, _ = make_sink()
                    backend.events.clear()
                    primitive = turn_primitive(
                        direction=direction, delta_x=delta, hold_ms=hold_ms
                    )
                    sink.apply_bounded(
                        primitive,
                        CooperativeCancellation(),
                        execution_budget(hold_ms=hold_ms),
                    )
                    expected_delta = -delta if direction == "TURN_LEFT" else delta
                    expected_moves = [
                        ("move", (0, TURN_ANTI_CLICK_EXCURSION_PX)),
                        ("move", (0, -TURN_ANTI_CLICK_EXCURSION_PX)),
                        ("move", (expected_delta, 0)),
                    ]
                    self.assertEqual(
                        [event for event in backend.events if event[0] in {"turn_mode_down", "move", "turn_mode_up"}],
                        [
                            ("turn_mode_down", 0),
                            *expected_moves,
                            ("turn_mode_up", 0),
                        ],
                    )
                    self.assertEqual(
                        [event[0] for event in backend.events if event[0] in {"prepare_cursor", "restore_cursor"}],
                        ["prepare_cursor", "restore_cursor"],
                    )
                    self.assertFalse(sink.turn_mode_owned)
                    self.assertEqual(sink.last_timing.delta_x, expected_delta)
                    self.assertEqual(
                        sink.last_timing.requested_hold_duration_ms, hold_ms
                    )
                    self.assertGreaterEqual(
                        sink.last_timing.move_submitted_at_monotonic_ms
                        - sink.last_timing.turn_mode_down_at_monotonic_ms,
                        TURN_PRE_DRAG_SETTLE_MS + TURN_ANTI_CLICK_SETTLE_MS,
                    )
                    sink.close()

    def test_focus_identity_or_deadline_failure_emits_no_mouse_input(self) -> None:
        cases = (
            replace(exact_hot(), foreground_hwnd=0x9999),
            replace(exact_hot(), owner_pid=777),
            replace(exact_hot(), minimized=True),
        )
        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                backend = FakeMouseBackend()
                backend.hot_snapshot = snapshot
                sink, backend, _, _ = make_sink(backend=backend)
                backend.events.clear()
                with self.assertRaises(WindowsTargetBindingError):
                    sink.apply_bounded(
                        turn_primitive(),
                        CooperativeCancellation(),
                        execution_budget(),
                    )
                self.assertEqual(
                    [event for event in backend.events if event[0] in {"turn_mode_down", "move", "turn_mode_up"}],
                    [],
                )

        sink, backend, clock, _ = make_sink()
        backend.events.clear()
        clock.current_ms = 1_186.0
        expired = execution_budget()
        with self.assertRaises(WindowsInputDeadlineError):
            sink.apply_bounded(
                turn_primitive(), CooperativeCancellation(), expired
            )
        self.assertEqual(
            [event for event in backend.events if event[0] in {"turn_mode_down", "move", "turn_mode_up"}],
            [],
        )

    def test_cancellation_and_move_failure_always_release_turn_mode(self) -> None:
        sink, backend, _, waiter = make_sink()
        cancellation = CooperativeCancellation()
        waiter.on_wait = lambda token: token.cancel()
        with self.assertRaises(InputCancelledError):
            sink.apply_bounded(
                turn_primitive(), cancellation, execution_budget()
            )
        self.assertEqual(
            [event[0] for event in backend.events if event[0].startswith("turn_mode_")],
            ["turn_mode_down", "turn_mode_up"],
        )
        self.assertFalse(sink.turn_mode_owned)

        failing_backend = FakeMouseBackend()
        failing_backend.move_outcomes = [0]
        sink, failing_backend, _, _ = make_sink(backend=failing_backend)
        with self.assertRaisesRegex(WindowsInputSinkError, "relative mouse"):
            sink.apply_bounded(
                turn_primitive(),
                CooperativeCancellation(),
                execution_budget(),
            )
        self.assertEqual(
            [event[0] for event in failing_backend.events if event[0] in {"turn_mode_down", "move", "turn_mode_up"}],
            ["turn_mode_down", "move", "turn_mode_up"],
        )
        self.assertFalse(sink.turn_mode_owned)

    def test_release_all_during_hold_revokes_and_releases_once(self) -> None:
        backend = FakeMouseBackend()
        clock = FakeClock()
        wait_started = Event()
        allow_wait = Event()

        def blocking_waiter(
            _cancellation: CooperativeCancellation, timeout_ms: int
        ) -> bool:
            wait_started.set()
            if not allow_wait.wait(timeout=1.0):
                raise RuntimeError("blocking waiter fixture timed out")
            clock.advance(timeout_ms)
            return False

        sink = WindowsMouseTurnSink(
            target=target_binding(),
            backend=backend,
            clock=clock,
            waiter=blocking_waiter,
        )
        errors: list[BaseException] = []

        def run_turn() -> None:
            try:
                sink.apply_bounded(
                    turn_primitive(),
                    CooperativeCancellation(),
                    execution_budget(),
                )
            except BaseException as error:
                errors.append(error)

        worker = Thread(target=run_turn, name="mouse-turn-worker")
        worker.start()
        self.assertTrue(wait_started.wait(timeout=1.0))
        sink.release_all()
        allow_wait.set()
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InputCancelledError)
        self.assertEqual(
            [event[0] for event in backend.events if event[0].startswith("turn_mode_")],
            ["turn_mode_down", "turn_mode_up"],
        )
        self.assertFalse(sink.turn_mode_owned)

    def test_composite_routes_turns_only_to_mouse_and_keys_only_to_keyboard(self) -> None:
        keyboard = RecordingDelegate()
        mouse = RecordingDelegate()
        composite = WindowsCombatInputSink(
            keyboard_sink=keyboard,
            mouse_turn_sink=mouse,  # type: ignore[arg-type]
        )
        cancellation = CooperativeCancellation()
        budget = execution_budget()
        turn = turn_primitive()
        key = replace(
            turn,
            primitive_id="primitive:key:slot-one",
            controls=("ACTION_SLOT_1",),
            hold_duration_ms=25,
            max_execution_envelope_ms=75,
            mouse_delta_x=None,
        )
        composite.apply_bounded(turn, cancellation, budget)
        visible_select = visible_select_primitive()
        composite.apply_bounded(
            visible_select,
            cancellation,
            visible_click_budget(),
        )
        composite.apply_bounded(
            key,
            cancellation,
            replace(
                budget,
                hold_duration_ms=25,
                max_execution_envelope_ms=75,
                absolute_deadline_monotonic_ms=1_075.0,
                remaining_ms=75.0,
            ),
        )
        self.assertEqual(mouse.applied, [turn, visible_select])
        self.assertEqual(keyboard.applied, [key])
        composite.release_all()
        composite.close()
        self.assertEqual((mouse.release_count, keyboard.release_count), (1, 1))
        self.assertEqual((mouse.close_count, keyboard.close_count), (1, 1))

    def test_close_is_idempotent_and_releases_identity_receipt_once(self) -> None:
        sink, backend, _, _ = make_sink()
        sink.close()
        sink.close()
        self.assertEqual(backend.release_receipt_count, 1)
        with self.assertRaisesRegex(WindowsInputSinkError, "closed"):
            sink.apply_bounded(
                turn_primitive(),
                CooperativeCancellation(),
                execution_budget(),
            )

    def test_native_turn_transport_uses_right_button_and_one_relative_input(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "perfect_assassin_test_native_mouse_backend",
            ROOT / "integrations" / "windows-input" / "send_input_backend.py",
        )
        assert spec is not None and spec.loader is not None
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        captures: list[tuple[int, int, int, int, int]] = []

        class FakeSendInput:
            def __call__(self, count, pointer, input_size):
                event = ctypes.cast(pointer, ctypes.POINTER(native._INPUT)).contents
                if int(event.type) == native.INPUT_KEYBOARD:
                    captures.append((
                        int(count), int(input_size), int(event.type),
                        int(event.ki.wScan), int(event.ki.dwFlags),
                    ))
                else:
                    captures.append((
                        int(count), int(input_size), int(event.type),
                        int(event.mi.dx), int(event.mi.dwFlags),
                    ))
                return 1

        class FakeUser32:
            SendInput = FakeSendInput()

        backend = object.__new__(native.CtypesWin32KeyboardBackend)
        backend._user32 = FakeUser32()
        self.assertEqual(backend.send_target_select_key(key_up=False), 1)
        self.assertEqual(backend.send_target_select_key(key_up=True), 1)
        self.assertEqual(backend.send_turn_mode_key(key_up=False), 1)
        self.assertEqual(backend.send_relative_mouse(delta_x=-28, delta_y=0), 1)
        self.assertEqual(backend.send_turn_mode_key(key_up=True), 1)
        expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(
            captures,
            [
                (1, expected_size, native.INPUT_MOUSE, 0, native.MOUSEEVENTF_LEFTDOWN),
                (1, expected_size, native.INPUT_MOUSE, 0, native.MOUSEEVENTF_LEFTUP),
                (1, expected_size, native.INPUT_MOUSE, 0, native.MOUSEEVENTF_RIGHTDOWN),
                (1, expected_size, native.INPUT_MOUSE, -28, native.MOUSEEVENTF_MOVE),
                (
                    1,
                    expected_size,
                    native.INPUT_MOUSE,
                    0,
                    native.MOUSEEVENTF_RIGHTUP,
                ),
            ],
        )
        for invalid in (True, 1.0, 0, 32_768):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    backend.send_relative_mouse(delta_x=invalid, delta_y=0)


if __name__ == "__main__":
    unittest.main()
