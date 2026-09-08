from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from threading import Event, Lock, Thread
import time
from typing import Callable


WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

# Record controls that can affect movement/camera only.  This intentionally
# excludes letters unrelated to movement so chat and credentials cannot be
# reconstructed from a demonstration trace.
RECORDED_VIRTUAL_KEYS = frozenset({
    0x20,  # Space / jump
    0x25, 0x26, 0x27, 0x28,  # arrows
    0x41, 0x44, 0x45, 0x51, 0x53, 0x57,  # A/D/E/Q/S/W
    0x90,  # NumLock / autorun in the current client profile
})


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    )


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    )


class Win32OperatorInputObserver:
    """Observe physical Win32 input without blocking or synthesizing it."""

    def __init__(self, target_hwnd: int, publish: Callable[..., object]) -> None:
        if os.name != "nt":
            raise OSError("Win32 input observation is available only on Windows")
        if type(target_hwnd) is not int or target_hwnd <= 0:
            raise ValueError("target HWND is invalid")
        self.target_hwnd = target_hwnd
        self.publish = publish
        self._thread: Thread | None = None
        self._ready = Event()
        self._thread_id = 0
        self._keyboard_hook = None
        self._mouse_hook = None
        self._last_mouse: tuple[int, int] | None = None
        self._keyboard_callback = None
        self._mouse_callback = None
        self._state_lock = Lock()
        self._held_virtual_keys: set[int] = set()
        self._held_mouse_buttons: set[str] = set()
        self._cumulative_mouse_x = 0
        self._cumulative_mouse_y = 0
        self._cumulative_wheel = 0

    def snapshot(self) -> dict[str, object]:
        with self._state_lock:
            return {
                "held_virtual_keys": sorted(self._held_virtual_keys),
                "held_mouse_buttons": sorted(self._held_mouse_buttons),
                "cumulative_mouse_x": self._cumulative_mouse_x,
                "cumulative_mouse_y": self._cumulative_mouse_y,
                "cumulative_wheel": self._cumulative_wheel,
            }

    def window_metrics(self) -> dict[str, object]:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        rect = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not user32.GetClientRect(self.target_hwnd, ctypes.byref(rect)):
            raise OSError(ctypes.get_last_error(), "cannot read target client rectangle")
        if not user32.ClientToScreen(self.target_hwnd, ctypes.byref(origin)):
            raise OSError(ctypes.get_last_error(), "cannot map target client rectangle")
        dpi = (
            int(user32.GetDpiForWindow(self.target_hwnd))
            if hasattr(user32, "GetDpiForWindow") else None
        )
        return {
            "client_left": int(origin.x),
            "client_top": int(origin.y),
            "client_width": int(rect.right - rect.left),
            "client_height": int(rect.bottom - rect.top),
            "dpi": dpi,
        }

    def _foreground_matches(self, user32: object) -> bool:
        return int(user32.GetForegroundWindow() or 0) == self.target_hwnd

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="operator-input-observer", daemon=True)
        self._thread.start()
        if not self._ready.wait(2.0):
            raise RuntimeError("input observer did not start")
        if self._keyboard_hook is None or self._mouse_hook is None:
            raise RuntimeError("Windows refused the read-only input hooks")

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_proc = ctypes.WINFUNCTYPE(
            wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int, hook_proc, wintypes.HINSTANCE, wintypes.DWORD,
        )
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = (
            wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
        )
        user32.CallNextHookEx.restype = wintypes.LPARAM
        user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.GetCurrentThreadId.argtypes = ()
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        def keyboard(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION and int(w_param) in {
                WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
            }:
                data = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                matches = self._foreground_matches(user32)
                if matches and int(data.vkCode) in RECORDED_VIRTUAL_KEYS:
                    state = (
                        "DOWN" if int(w_param) in {WM_KEYDOWN, WM_SYSKEYDOWN}
                        else "UP"
                    )
                    with self._state_lock:
                        if state == "DOWN":
                            self._held_virtual_keys.add(int(data.vkCode))
                        else:
                            self._held_virtual_keys.discard(int(data.vkCode))
                    self.publish(
                        "KEY",
                        monotonic_ns=time.perf_counter_ns(),
                        foreground_matches_target=True,
                        payload={
                            "virtual_key": int(data.vkCode),
                            "scan_code": int(data.scanCode),
                            "state": state,
                            "extended": bool(int(data.flags) & 0x01),
                            "injected": bool(int(data.flags) & 0x10),
                        },
                    )
            return int(user32.CallNextHookEx(None, n_code, w_param, l_param))

        mouse_names = {
            WM_LBUTTONDOWN: ("LEFT", "DOWN"), WM_LBUTTONUP: ("LEFT", "UP"),
            WM_RBUTTONDOWN: ("RIGHT", "DOWN"), WM_RBUTTONUP: ("RIGHT", "UP"),
            WM_MBUTTONDOWN: ("MIDDLE", "DOWN"), WM_MBUTTONUP: ("MIDDLE", "UP"),
        }

        def mouse(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == HC_ACTION:
                data = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                current = (int(data.pt.x), int(data.pt.y))
                previous = self._last_mouse
                self._last_mouse = current
                matches = self._foreground_matches(user32)
                message = int(w_param)
                if matches and message == WM_MOUSEMOVE and previous is not None:
                    dx, dy = current[0] - previous[0], current[1] - previous[1]
                    if dx or dy:
                        with self._state_lock:
                            self._cumulative_mouse_x += dx
                            self._cumulative_mouse_y += dy
                        self.publish(
                            "MOUSE_MOVE",
                            monotonic_ns=time.perf_counter_ns(),
                            foreground_matches_target=True,
                            payload={
                                "screen_x": current[0], "screen_y": current[1],
                                "delta_x": dx, "delta_y": dy,
                                "injected": bool(int(data.flags) & 0x01),
                            },
                        )
                elif matches and message in mouse_names:
                    button, state = mouse_names[message]
                    with self._state_lock:
                        if state == "DOWN":
                            self._held_mouse_buttons.add(button)
                        else:
                            self._held_mouse_buttons.discard(button)
                    self.publish(
                        "MOUSE_BUTTON",
                        monotonic_ns=time.perf_counter_ns(),
                        foreground_matches_target=True,
                        payload={"button": button, "state": state},
                    )
                elif matches and message == WM_MOUSEWHEEL:
                    wheel = ctypes.c_short((int(data.mouseData) >> 16) & 0xFFFF).value
                    with self._state_lock:
                        self._cumulative_wheel += int(wheel)
                    self.publish(
                        "MOUSE_WHEEL",
                        monotonic_ns=time.perf_counter_ns(),
                        foreground_matches_target=True,
                        payload={"delta": int(wheel)},
                    )
            return int(user32.CallNextHookEx(None, n_code, w_param, l_param))

        self._keyboard_callback = hook_proc(keyboard)
        self._mouse_callback = hook_proc(mouse)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._keyboard_callback, None, 0
        )
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_callback, None, 0
        )
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if self._keyboard_hook:
                user32.UnhookWindowsHookEx(self._keyboard_hook)
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
            self._keyboard_hook = None
            self._mouse_hook = None

    def close(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(2.0)
        self._thread = None

    def __enter__(self) -> "Win32OperatorInputObserver":
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
