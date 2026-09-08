from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time

from send_input_backend import CtypesWin32KeyboardBackend
from perfect_assassin.execution.windows_continuous_motion import (
    MOUSE_LOOK_SETTLE_S,
    MOUSE_UP_SETTLE_S,
)


ROOT = Path(__file__).resolve().parents[2]
ARM_FILE = ROOT / "data" / "runtime" / "operator" / "predator-codex-driver-arm.json"
RECEIPT_FILE = ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
WOW_CLASS = "GxWindowClassD3d"
WOW_TITLE = "World of Warcraft"
# Every normal key WoW can consume is available while this exact, armed WoW
# HWND owns the foreground. OS-only keys (Windows key, Print Screen, Pause) are
# deliberately absent because they can escape the game-window boundary.
ALLOWED_KEYS = {
    **{chr(code): code for code in range(0x41, 0x5B)},
    **{str(number): 0x30 + number for number in range(10)},
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "CAPSLOCK": 0x14,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    **{f"F{number}": 0x6F + number for number in range(1, 13)},
    **{f"NUMPAD{number}": 0x60 + number for number in range(10)},
    "MULTIPLY": 0x6A,
    "ADD": 0x6B,
    "SUBTRACT": 0x6D,
    "DECIMAL": 0x6E,
    "DIVIDE": 0x6F,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "SEMICOLON": 0xBA,
    "EQUALS": 0xBB,
    "COMMA": 0xBC,
    "MINUS": 0xBD,
    "PERIOD": 0xBE,
    "SLASH": 0xBF,
    "GRAVE": 0xC0,
    "LBRACKET": 0xDB,
    "BACKSLASH": 0xDC,
    "RBRACKET": 0xDD,
    "APOSTROPHE": 0xDE,
}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT))


class _INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (("type", wintypes.DWORD), ("value", _INPUT_UNION))


@dataclass(frozen=True, slots=True)
class DriverTarget:
    pid: int
    hwnd: int
    owner_pid: int


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def _process_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def armed_target(path: Path = ARM_FILE) -> DriverTarget:
    record = _read_object(path)
    if (
        record.get("record_type") != "predator_codex_driver_arm"
        or record.get("schema_version") != "1.0"
        or record.get("enabled") is not True
        or record.get("allowed_controls") != sorted(ALLOWED_KEYS)
    ):
        raise RuntimeError("Codex Driver is not armed in Control Center")
    target = DriverTarget(
        pid=int(record["target_pid"]),
        hwnd=int(str(record["target_hwnd"]), 0),
        owner_pid=int(record["control_center_pid"]),
    )
    if not _process_alive(target.owner_pid):
        raise RuntimeError("the Control Center session which armed driving is closed")
    user32 = ctypes.windll.user32
    if not user32.IsWindow(target.hwnd):
        raise RuntimeError("the authorized WoW window no longer exists")
    actual_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(target.hwnd, ctypes.byref(actual_pid))
    class_name = ctypes.create_unicode_buffer(128)
    title = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(target.hwnd, class_name, len(class_name))
    user32.GetWindowTextW(target.hwnd, title, len(title))
    if (
        int(actual_pid.value) != target.pid
        or class_name.value != WOW_CLASS
        or title.value != WOW_TITLE
    ):
        raise RuntimeError("the authorization does not match the exact WoW window")
    return target


def _send_key(virtual_key: int, *, up: bool) -> None:
    item = _INPUT(type=1)
    item.ki = _KEYBDINPUT(
        wVk=virtual_key,
        wScan=0,
        dwFlags=0x0002 if up else 0,
        time=0,
        dwExtraInfo=None,
    )
    if ctypes.windll.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(_INPUT)) != 1:
        raise OSError(ctypes.get_last_error(), "SendInput keyboard event failed")


def _send_mouse(*, dx: int = 0, dy: int = 0, flags: int = 0) -> None:
    item = _INPUT(type=0)
    item.mi = _MOUSEINPUT(
        dx=dx, dy=dy, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None,
    )
    if ctypes.windll.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(_INPUT)) != 1:
        raise OSError(ctypes.get_last_error(), "SendInput mouse event failed")


def _focus_target(target: DriverTarget) -> None:
    """Bring only the already validated WoW HWND to the foreground.

    Windows may reject SetForegroundWindow from a background helper.  Attach
    the helper briefly to the current foreground and target input queues, as
    the production movement transport already does, then detach in all cases.
    This grants no new target: ``armed_target`` resolved and validated the
    exact PID/HWND before this function is called.
    """

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.ShowWindow(target.hwnd, 9)
    user32.SetForegroundWindow(target.hwnd)
    if int(user32.GetForegroundWindow() or 0) == target.hwnd:
        return

    target_thread = int(user32.GetWindowThreadProcessId(target.hwnd, None) or 0)
    foreground = int(user32.GetForegroundWindow() or 0)
    foreground_thread = int(
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )
    current_thread = int(kernel32.GetCurrentThreadId())
    attached: list[int] = []
    try:
        for thread_id in (foreground_thread, target_thread):
            if (
                thread_id
                and thread_id != current_thread
                and thread_id not in attached
                and user32.AttachThreadInput(current_thread, thread_id, True)
            ):
                attached.append(thread_id)
        user32.ShowWindowAsync(target.hwnd, 9)
        user32.BringWindowToTop(target.hwnd)
        user32.SetForegroundWindow(target.hwnd)
    finally:
        for thread_id in reversed(attached):
            user32.AttachThreadInput(current_thread, thread_id, False)
    time.sleep(0.04)
    if int(user32.GetForegroundWindow() or 0) != target.hwnd:
        raise RuntimeError("the exact WoW window did not accept foreground focus")


def release_all() -> None:
    target = armed_target()
    _focus_target(target)
    for virtual_key in ALLOWED_KEYS.values():
        _send_key(virtual_key, up=True)
    _send_mouse(flags=0x0010)  # right button up


def _assert_drag_target(target: DriverTarget) -> None:
    """Focus alone does not prove that an RMB press will land inside WoW."""
    user32 = ctypes.windll.user32
    point = wintypes.POINT()
    user32.WindowFromPoint.argtypes = (wintypes.POINT,)
    user32.WindowFromPoint.restype = wintypes.HWND
    if (
        int(user32.GetForegroundWindow() or 0) != target.hwnd
        or not user32.GetCursorPos(ctypes.byref(point))
        or int(user32.WindowFromPoint(point) or 0) != target.hwnd
    ):
        raise RuntimeError("camera drag cursor is not over the foreground WoW window")


def drive_step(
    *, keys: tuple[str, ...], duration_ms: int,
    mouse_dx: int = 0, mouse_dy: int = 0, hold_rmb: bool = False,
) -> dict[str, object]:
    normalized = tuple(dict.fromkeys(key.upper() for key in keys))
    if (
        not normalized
        and mouse_dx == 0 and mouse_dy == 0
        or any(key not in ALLOWED_KEYS for key in normalized)
        or not 20 <= duration_ms <= 3000
        or not -2000 <= mouse_dx <= 2000
        or not -1200 <= mouse_dy <= 1200
    ):
        raise ValueError("driver step is outside the bounded control envelope")
    target = armed_target()
    user32 = ctypes.windll.user32
    _focus_target(target)
    cursor_backend = None
    cursor_placement = None
    pressed_keys: list[str] = []
    rmb_attempted = False
    rmb_released = False
    try:
        if hold_rmb:
            cursor_backend = CtypesWin32KeyboardBackend()
            cursor_placement = cursor_backend.prepare_world_drag_cursor(hwnd=target.hwnd)
            # Revalidate after placement; never click an occluding window.
            if armed_target() != target:
                raise RuntimeError("WoW driving authorization changed before camera drag")
            _assert_drag_target(target)
        for key in normalized:
            pressed_keys.append(key)
            _send_key(ALLOWED_KEYS[key], up=False)
        if hold_rmb:
            rmb_attempted = True
            _send_mouse(flags=0x0008)  # right button down
            time.sleep(MOUSE_LOOK_SETTLE_S)
        started = time.monotonic()
        motion_steps = max(1, min(30, duration_ms // 16))
        sent_x = sent_y = 0
        for index in range(1, motion_steps + 1):
            if int(user32.GetForegroundWindow() or 0) != target.hwnd:
                raise RuntimeError("WoW lost focus during the drive step")
            next_x = round(mouse_dx * index / motion_steps)
            next_y = round(mouse_dy * index / motion_steps)
            _send_mouse(dx=next_x - sent_x, dy=next_y - sent_y, flags=0x0001)
            sent_x, sent_y = next_x, next_y
            remaining_s = duration_ms / 1000.0 - (time.monotonic() - started)
            if remaining_s > 0:
                time.sleep(min(remaining_s, duration_ms / 1000.0 / motion_steps))
    finally:
        try:
            try:
                if rmb_attempted:
                    _send_mouse(flags=0x0010)
                    rmb_released = True
                    # The client consumes RMB-up asynchronously. Restoring the
                    # OS cursor immediately can become one last enormous drag.
                    time.sleep(MOUSE_UP_SETTLE_S)
            finally:
                for key in reversed(pressed_keys):
                    _send_key(ALLOWED_KEYS[key], up=True)
        finally:
            if (
                cursor_backend is not None and cursor_placement is not None
                and (not rmb_attempted or rmb_released)
            ):
                cursor_backend.restore_cursor_position(cursor_placement)
    return {
        "status": "EXECUTED",
        "target_pid": target.pid,
        "keys": list(normalized),
        "duration_ms": duration_ms,
        "mouse_delta": [mouse_dx, mouse_dy],
        "rmb_held": hold_rmb,
    }


def capture_wow_png(receipt_path: Path = RECEIPT_FILE) -> bytes:
    receipt = _read_object(receipt_path)
    hwnd = int(str(receipt["hwnd"]), 0)
    pid = int(receipt["pid"])
    user32 = ctypes.windll.user32
    actual_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(actual_pid))
    if not user32.IsWindow(hwnd) or int(actual_pid.value) != pid:
        raise RuntimeError("the launch receipt does not match a live WoW window")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "gdigrab", "-i", f"title={WOW_TITLE}",
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=0x08000000,
        timeout=8.0,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.startswith(b"\x89PNG"):
        detail = completed.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"WoW window capture failed: {detail}")
    return completed.stdout
