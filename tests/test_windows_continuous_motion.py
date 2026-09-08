from __future__ import annotations

import time
import unittest

from perfect_assassin.execution.continuous_motion import ContinuousMotionFrame
from perfect_assassin.execution.ports import CooperativeCancellation
from perfect_assassin.execution.windows_continuous_motion import (
    MOUSE_VELOCITY_MAX_STEP_PX,
    WindowsContinuousMotionSession,
)
from perfect_assassin.execution.windows_mouse_turn import WindowsCursorPlacement
from perfect_assassin.execution.windows_send_input import (
    WindowsHotTargetSnapshot,
    WindowsTargetIdentityReceipt,
)
from tests.test_windows_send_input_sink import FakeClock, target_binding


class FakeContinuousBackend:
    def __init__(self) -> None:
        target = target_binding()
        self.target = target
        self.events: list[tuple[str, object]] = []
        self.hot = WindowsHotTargetSnapshot(
            hwnd=target.hwnd,
            foreground_hwnd=target.hwnd,
            owner_pid=target.pid,
            process_creation_time_100ns=target.process_creation_time_100ns,
            process_alive=True,
            visible=True,
            minimized=False,
        )
        self.released_receipt = False

    def map_virtual_key(self, virtual_key: int) -> int:
        return virtual_key

    def prevalidate_target(self, target):
        return WindowsTargetIdentityReceipt("receipt:continuous:fixture", target)

    def inspect_hot(self, receipt):
        self.events.append(("inspect", receipt.receipt_id))
        return self.hot

    def send_scan_code(self, scan_code: int, *, key_up: bool) -> int:
        self.events.append(("key_up" if key_up else "key_down", scan_code))
        return 1

    def send_turn_mode_key(self, *, key_up: bool) -> int:
        self.events.append(("rmb_up" if key_up else "rmb_down", 0))
        return 1

    def prepare_world_drag_cursor(self, *, hwnd: int) -> WindowsCursorPlacement:
        self.events.append(("prepare", hwnd))
        return WindowsCursorPlacement(10, 20, 500, 400)

    def restore_cursor_position(self, placement: WindowsCursorPlacement) -> int:
        self.events.append(("restore", placement))
        return 1

    def send_relative_mouse(self, *, delta_x: int, delta_y: int) -> int:
        self.events.append(("move", (delta_x, delta_y)))
        return 1

    def release_identity_receipt(self, receipt) -> None:
        self.released_receipt = True


class WindowsContinuousMotionSessionTests(unittest.TestCase):
    def make_session(self, *, lease_timeout_ms: int = 220):
        clock = FakeClock(current_ms=1_000.0)
        backend = FakeContinuousBackend()
        session = WindowsContinuousMotionSession(
            target=backend.target,
            backend=backend,
            clock=clock,
            expires_at_monotonic_ms=20_000.0,
            lease_timeout_ms=lease_timeout_ms,
            sleeper=lambda _seconds: None,
        )
        backend.events.clear()
        return session, backend, clock

    def test_repeated_20hz_frames_do_not_tap_w_or_rmb(self) -> None:
        session, backend, clock = self.make_session()
        cancellation = CooperativeCancellation()
        first = ContinuousMotionFrame(
            1.0, movement="MOVE_FORWARD", mouse_look=True, mouse_delta_x=2
        )
        session.apply_frame(first, cancellation)
        clock.current_ms = 1_050.0
        session.apply_frame(
            ContinuousMotionFrame(
                1.05, movement="MOVE_FORWARD", mouse_look=True, mouse_delta_x=1
            ),
            cancellation,
        )

        names = [event[0] for event in backend.events]
        self.assertEqual(names.count("key_down"), 1)
        self.assertEqual(names.count("key_up"), 0)
        self.assertEqual(names.count("rmb_down"), 1)
        self.assertEqual(names.count("rmb_up"), 0)
        self.assertEqual(session.held_controls, ("MOVE_FORWARD",))
        self.assertTrue(session.mouse_look_held)
        session.release_all()

    def test_authority_expiry_renews_without_releasing_w_or_rmb(self) -> None:
        clock = FakeClock(current_ms=1_000.0)
        backend = FakeContinuousBackend()
        session = WindowsContinuousMotionSession(
            target=backend.target,
            backend=backend,
            clock=clock,
            expires_at_monotonic_ms=2_000.0,
            sleeper=lambda _seconds: None,
        )
        backend.events.clear()
        cancellation = CooperativeCancellation()
        session.apply_frame(
            ContinuousMotionFrame(
                1.0, movement="MOVE_FORWARD", mouse_look=True
            ),
            cancellation,
        )
        clock.current_ms = 1_500.0
        self.assertTrue(session.renew_authority_expiry(20_000.0))
        clock.current_ms = 2_500.0
        session.apply_frame(
            ContinuousMotionFrame(
                2.5, movement="MOVE_FORWARD", mouse_look=True
            ),
            cancellation,
        )

        names = [name for name, _ in backend.events]
        self.assertEqual(names.count("key_down"), 1)
        self.assertEqual(names.count("key_up"), 0)
        self.assertEqual(names.count("rmb_down"), 1)
        self.assertEqual(names.count("rmb_up"), 0)
        session.close()

    def test_velocity_is_interpolated_into_bounded_mouse_steps(self) -> None:
        session, backend, clock = self.make_session(lease_timeout_ms=450)
        cancellation = CooperativeCancellation()
        session.apply_frame(
            ContinuousMotionFrame(
                1.0, mouse_look=True, mouse_velocity_x_px_s=120.0
            ),
            cancellation,
        )
        time.sleep(0.045)
        moves = [value for name, value in backend.events if name == "move"]
        self.assertTrue(moves)
        self.assertTrue(
            all(0 < x <= MOUSE_VELOCITY_MAX_STEP_PX and y == 0 for x, y in moves)
        )
        self.assertEqual(
            [name for name, _ in backend.events].count("rmb_down"), 1
        )
        session.close()

    def test_two_hundred_frames_hold_one_w_and_one_rmb_transition(self) -> None:
        session, backend, clock = self.make_session()
        cancellation = CooperativeCancellation()

        for index in range(200):
            observed_s = 1.0 + index * 0.05
            clock.current_ms = observed_s * 1000.0
            session.apply_frame(
                ContinuousMotionFrame(
                    observed_s,
                    movement="MOVE_FORWARD",
                    mouse_look=True,
                    mouse_delta_x=1 if index % 3 == 0 else 0,
                ),
                cancellation,
            )

        names = [event[0] for event in backend.events]
        self.assertEqual(names.count("key_down"), 1)
        self.assertEqual(names.count("key_up"), 0)
        self.assertEqual(names.count("rmb_down"), 1)
        self.assertEqual(names.count("rmb_up"), 0)
        self.assertEqual(session.held_controls, ("MOVE_FORWARD",))
        self.assertTrue(session.mouse_look_held)
        session.close()

    def test_strafe_swap_is_one_release_then_one_press_without_rmb_chatter(self) -> None:
        session, backend, clock = self.make_session()
        cancellation = CooperativeCancellation()
        session.apply_frame(
            ContinuousMotionFrame(1.0, strafe="STRAFE_LEFT", mouse_look=True),
            cancellation,
        )
        backend.events.clear()
        clock.current_ms = 1_050.0
        session.apply_frame(
            ContinuousMotionFrame(1.05, strafe="STRAFE_RIGHT", mouse_look=True),
            cancellation,
        )

        self.assertEqual(
            [event[0] for event in backend.events if event[0] != "inspect"],
            ["key_up", "key_down"],
        )
        self.assertTrue(session.mouse_look_held)
        session.release_all()

    def test_manual_cancellation_releases_every_owned_input(self) -> None:
        session, backend, clock = self.make_session()
        cancellation = CooperativeCancellation()
        session.apply_frame(
            ContinuousMotionFrame(
                1.0, movement="MOVE_FORWARD", strafe="STRAFE_LEFT", mouse_look=True
            ),
            cancellation,
        )
        backend.events.clear()
        cancellation.cancel()
        clock.current_ms = 1_050.0

        with self.assertRaisesRegex(Exception, "cancelled"):
            session.apply_frame(ContinuousMotionFrame(1.05), cancellation)

        names = [event[0] for event in backend.events]
        self.assertEqual(names.count("key_up"), 2)
        self.assertEqual(names.count("rmb_up"), 1)
        self.assertFalse(session.mouse_look_held)
        self.assertEqual(session.held_controls, ())

    def test_watchdog_releases_if_fresh_frames_stop(self) -> None:
        session, backend, clock = self.make_session(lease_timeout_ms=120)
        session.apply_frame(
            ContinuousMotionFrame(1.0, movement="MOVE_FORWARD", mouse_look=True),
            CooperativeCancellation(),
        )
        backend.events.clear()
        clock.current_ms = 1_121.0
        time.sleep(0.14)

        names = [event[0] for event in backend.events]
        self.assertIn("key_up", names)
        self.assertIn("rmb_up", names)
        self.assertEqual(session.held_controls, ())
        self.assertFalse(session.mouse_look_held)
        session.close()

    def test_focus_change_fails_closed_and_releases_previous_hold(self) -> None:
        session, backend, clock = self.make_session()
        cancellation = CooperativeCancellation()
        session.apply_frame(
            ContinuousMotionFrame(1.0, movement="MOVE_FORWARD", mouse_look=True),
            cancellation,
        )
        backend.hot = WindowsHotTargetSnapshot(
            hwnd=backend.target.hwnd,
            foreground_hwnd=0x9999,
            owner_pid=backend.target.pid,
            process_creation_time_100ns=backend.target.process_creation_time_100ns,
            process_alive=True,
            visible=True,
            minimized=False,
        )
        backend.events.clear()
        clock.current_ms = 1_050.0

        with self.assertRaisesRegex(Exception, "not exact and hot"):
            session.apply_frame(
                ContinuousMotionFrame(1.05, movement="MOVE_FORWARD", mouse_look=True),
                cancellation,
            )

        names = [event[0] for event in backend.events]
        self.assertIn("key_up", names)
        self.assertIn("rmb_up", names)


if __name__ == "__main__":
    unittest.main()
