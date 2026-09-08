from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "windows-input"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))

import predator_codex_driver as driver


class PredatorCodexDriverTests(unittest.TestCase):
    def _fake_step(self, stack: ExitStack):
        target = driver.DriverTarget(pid=1, hwnd=2, owner_pid=3)
        events = []
        backend = MagicMock()
        backend.prepare_world_drag_cursor.side_effect = lambda **kw: events.append("place") or "placement"
        backend.restore_cursor_position.side_effect = lambda receipt: events.append("restore")
        user32 = MagicMock()
        user32.GetForegroundWindow.return_value = target.hwnd
        stack.enter_context(patch.object(driver.ctypes, "windll", SimpleNamespace(user32=user32), create=True))
        stack.enter_context(patch.object(driver, "armed_target", return_value=target))
        stack.enter_context(patch.object(driver, "_focus_target"))
        stack.enter_context(patch.object(driver, "CtypesWin32KeyboardBackend", return_value=backend))
        guard = stack.enter_context(patch.object(driver, "_assert_drag_target", side_effect=lambda t: events.append("guard")))
        mouse = stack.enter_context(patch.object(driver, "_send_mouse", side_effect=lambda **kw: events.append(kw["flags"])))
        key = stack.enter_context(patch.object(driver, "_send_key"))
        stack.enter_context(patch.object(driver.time, "sleep"))
        return events, backend, user32, guard, mouse, key

    def test_camera_places_and_checks_cursor_before_rmb_then_restores(self):
        with ExitStack() as stack:
            events, backend, _, _, _, key = self._fake_step(stack)
            result = driver.drive_step(keys=(), duration_ms=20, hold_rmb=True, mouse_dy=5)
            self.assertEqual(events, ["place", "guard", 8, 1, 16, "restore"])
            backend.prepare_world_drag_cursor.assert_called_once_with(hwnd=2)
            backend.restore_cursor_position.assert_called_once_with("placement")
            key.assert_not_called()
            self.assertEqual(result["status"], "EXECUTED")

    def test_occluded_cursor_refuses_all_input_and_restores(self):
        with ExitStack() as stack:
            events, _, _, guard, mouse, key = self._fake_step(stack)
            guard.side_effect = RuntimeError("occluded")
            with self.assertRaisesRegex(RuntimeError, "occluded"):
                driver.drive_step(keys=("W",), duration_ms=20, hold_rmb=True)
            mouse.assert_not_called()
            key.assert_not_called()
            self.assertEqual(events, ["place", "restore"])

    def test_focus_loss_still_releases_rmb_and_restores(self):
        with ExitStack() as stack:
            events, _, user32, _, _, _ = self._fake_step(stack)
            user32.GetForegroundWindow.return_value = 99
            with self.assertRaisesRegex(RuntimeError, "lost focus"):
                driver.drive_step(keys=(), duration_ms=20, hold_rmb=True, mouse_dy=5)
            self.assertEqual(events, ["place", "guard", 8, 16, "restore"])

    def test_placement_failure_sends_no_keys_or_button_events(self):
        with ExitStack() as stack:
            _, backend, _, _, mouse, key = self._fake_step(stack)
            backend.prepare_world_drag_cursor.side_effect = RuntimeError("placement failed")
            with self.assertRaisesRegex(RuntimeError, "placement failed"):
                driver.drive_step(keys=("W",), duration_ms=20, hold_rmb=True)
            mouse.assert_not_called()
            key.assert_not_called()
            backend.restore_cursor_position.assert_not_called()

    def test_keyboard_only_does_not_reposition_cursor(self):
        with ExitStack() as stack:
            _, backend, _, guard, _, key = self._fake_step(stack)
            driver.drive_step(keys=("W",), duration_ms=20)
            backend.prepare_world_drag_cursor.assert_not_called()
            guard.assert_not_called()
            self.assertEqual(key.call_count, 2)

    def test_changed_arm_refuses_input_and_restores_cursor(self):
        with ExitStack() as stack:
            events, _, _, guard, mouse, key = self._fake_step(stack)
            driver.armed_target.side_effect = [
                driver.DriverTarget(pid=1, hwnd=2, owner_pid=3),
                driver.DriverTarget(pid=4, hwnd=5, owner_pid=6),
            ]
            with self.assertRaisesRegex(RuntimeError, "authorization changed"):
                driver.drive_step(keys=(), duration_ms=20, hold_rmb=True, mouse_dy=5)
            guard.assert_not_called()
            mouse.assert_not_called()
            key.assert_not_called()
            self.assertEqual(events, ["place", "restore"])

    def test_release_failure_does_not_warp_cursor_while_rmb_may_be_down(self):
        with ExitStack() as stack:
            _, backend, _, _, mouse, _ = self._fake_step(stack)
            mouse.side_effect = [None, None, OSError("release failed")]
            with self.assertRaisesRegex(OSError, "release failed"):
                driver.drive_step(keys=(), duration_ms=20, hold_rmb=True, mouse_dy=5)
            backend.restore_cursor_position.assert_not_called()

    def test_rmb_settles_before_motion_and_before_cursor_restore(self):
        with ExitStack() as stack:
            events, _, _, _, _, _ = self._fake_step(stack)
            driver.time.sleep.side_effect = lambda seconds: events.append(("sleep", seconds))
            driver.drive_step(keys=(), duration_ms=20, hold_rmb=True, mouse_dy=5)
            down = events.index(8)
            movement = events.index(1)
            up = events.index(16)
            self.assertEqual(events[down + 1], ("sleep", driver.MOUSE_LOOK_SETTLE_S))
            self.assertLess(down + 1, movement)
            self.assertEqual(events[up + 1], ("sleep", driver.MOUSE_UP_SETTLE_S))
            self.assertEqual(events[up + 2], "restore")

    def test_drag_guard_requires_foreground_and_exact_window_under_cursor(self):
        target = driver.DriverTarget(pid=1, hwnd=2, owner_pid=3)
        for foreground, cursor_read, hit in ((99, 1, 2), (2, 0, 2), (2, 1, 99), (2, 1, 2)):
            with self.subTest(foreground=foreground, cursor_read=cursor_read, hit=hit):
                user32 = MagicMock()
                user32.GetForegroundWindow.return_value = foreground
                user32.GetCursorPos.return_value = cursor_read
                user32.WindowFromPoint.return_value = hit
                with patch.object(driver.ctypes, "windll", SimpleNamespace(user32=user32), create=True):
                    if foreground == 2 and cursor_read and hit == 2:
                        driver._assert_drag_target(target)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "cursor is not over"):
                            driver._assert_drag_target(target)

    def test_driver_exposes_the_normal_wow_keyboard_but_not_os_keys(self) -> None:
        self.assertTrue({"W", "A", "S", "D", "P", "B", "1", "F12"} <= set(
            driver.ALLOWED_KEYS
        ))
        self.assertNotIn("WIN", driver.ALLOWED_KEYS)
        self.assertNotIn("PRINTSCREEN", driver.ALLOWED_KEYS)

    def test_driver_rejects_unbounded_step_before_touching_wow(self) -> None:
        with self.assertRaisesRegex(ValueError, "bounded control envelope"):
            driver.drive_step(keys=("W",), duration_ms=3001)

    def test_driver_rejects_os_key_before_touching_wow(self) -> None:
        with self.assertRaisesRegex(ValueError, "bounded control envelope"):
            driver.drive_step(keys=("WIN",), duration_ms=100)

    def test_control_center_arm_is_scoped_to_its_process_and_exact_window(self) -> None:
        source = (
            INTEGRATION / "run_movement_engine_client.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"control_center_pid": os.getpid()', source)
        self.assertIn('"target_hwnd": f"0x{target_hwnd:X}"', source)
        self.assertIn('self.codex_driver_enabled.set(False)', source)
        self.assertIn(
            'text="Codex AI poate folosi tastatura și mouse-ul"', source,
        )
        self.assertIn('text="Codex AI — control manual"', source)
        self.assertIn(
            '"Oprit: Codex AI nu trimite comenzi. Funcționează doar în WoW."',
            source,
        )

    def test_control_center_invalidates_stale_driver_arm_on_startup(self) -> None:
        source = (
            INTEGRATION / "run_movement_engine_client.py"
        ).read_text(encoding="utf-8")
        readiness = source.index(
            'self._apply_autonomous_start_readiness(update_status=True)'
        )
        startup_disarm = source.index('self._codex_driver_changed()', readiness)
        window_protocol = source.index(
            'self.root.protocol("WM_DELETE_WINDOW", self.close)', startup_disarm
        )
        self.assertLess(readiness, startup_disarm)
        self.assertLess(startup_disarm, window_protocol)

    def test_driver_uses_bounded_focus_handoff_for_the_validated_wow_hwnd(self) -> None:
        source = (INTEGRATION / "predator_codex_driver.py").read_text(
            encoding="utf-8"
        )
        focus = source[source.index("def _focus_target") : source.index("def release_all")]
        self.assertIn("AttachThreadInput", focus)
        self.assertIn("BringWindowToTop(target.hwnd)", focus)
        self.assertIn("finally:", focus)
        self.assertIn("AttachThreadInput(current_thread, thread_id, False)", focus)
        self.assertGreaterEqual(source.count("_focus_target(target)"), 2)


if __name__ == "__main__":
    unittest.main()
