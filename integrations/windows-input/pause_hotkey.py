from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from threading import Event, Thread
from typing import Callable


MOD_NOREPEAT = 0x4000
VK_PAUSE = 0x13
WM_HOTKEY = 0x0312
WM_APP_STOP = 0x8001
HOTKEY_ID = 0xB351


class PauseHotkeyError(RuntimeError):
    pass


class PauseHotkeySource:
    """Thread-bound RegisterHotKey source; no keyboard hook is installed."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Pause hotkey is available only on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure()

    def _configure(self) -> None:
        self._user32.RegisterHotKey.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.GetMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.GetMessageW.restype = ctypes.c_int
        self._user32.PostThreadMessageW.argtypes = (
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._user32.PostThreadMessageW.restype = wintypes.BOOL
        self._kernel32.GetCurrentThreadId.argtypes = ()
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def arm(self, callback: Callable[[], bool]) -> Callable[[], None]:
        if not callable(callback):
            raise ValueError("Pause takeover callback must be callable")
        ready = Event()
        stopped = Event()
        state: dict[str, object] = {}

        def worker() -> None:
            thread_id = int(self._kernel32.GetCurrentThreadId())
            state["thread_id"] = thread_id
            if not self._user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_PAUSE):
                state["error"] = PauseHotkeyError(
                    f"RegisterHotKey(Pause) failed with Win32 {ctypes.get_last_error()}"
                )
                ready.set()
                stopped.set()
                return
            state["registered"] = True
            ready.set()
            message = wintypes.MSG()
            try:
                while True:
                    result = int(self._user32.GetMessageW(ctypes.byref(message), None, 0, 0))
                    if result == -1:
                        state["error"] = PauseHotkeyError(
                            f"Pause hotkey message loop failed with Win32 {ctypes.get_last_error()}"
                        )
                        break
                    if result == 0 or int(message.message) == WM_APP_STOP:
                        break
                    if int(message.message) == WM_HOTKEY and int(message.wParam) == HOTKEY_ID:
                        try:
                            callback()
                        except Exception:
                            # Takeover callbacks fail closed internally; the message
                            # source must remain alive long enough to unregister.
                            pass
            finally:
                self._user32.UnregisterHotKey(None, HOTKEY_ID)
                stopped.set()

        thread = Thread(target=worker, name="pa-f3a-pause-hotkey", daemon=False)
        thread.start()
        if not ready.wait(1.0):
            raise PauseHotkeyError("Pause hotkey thread did not initialize in time")
        if "error" in state:
            thread.join(1.0)
            raise state["error"]  # type: ignore[misc]

        def disarm() -> None:
            thread_id = state.get("thread_id")
            if type(thread_id) is not int or not self._user32.PostThreadMessageW(
                thread_id, WM_APP_STOP, 0, 0
            ):
                raise PauseHotkeyError("Pause hotkey stop signal failed")
            if not stopped.wait(1.0):
                raise PauseHotkeyError("Pause hotkey thread did not stop in time")
            thread.join(1.0)
            if thread.is_alive():
                raise PauseHotkeyError("Pause hotkey thread remained alive")
            if "error" in state:
                raise state["error"]  # type: ignore[misc]

        return disarm
