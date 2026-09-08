from __future__ import annotations

import ctypes
import hashlib
import ntpath
import os
from ctypes import wintypes
from pathlib import Path
from threading import RLock

from perfect_assassin.execution.windows_send_input import (
    DEFAULT_CONTROL_VIRTUAL_KEYS,
    WindowsHotTargetSnapshot,
    WindowsInputTargetBinding,
    WindowsInputSinkError,
    WindowsTargetBindingError,
    WindowsTargetIdentityReceipt,
)
from perfect_assassin.execution.windows_mouse_turn import WindowsCursorPlacement


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120
MAPVK_VK_TO_VSC = 0
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
ERROR_ACCESS_DENIED = 5
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
_V1_NON_EXTENDED_VIRTUAL_KEYS = frozenset(
    (*DEFAULT_CONTROL_VIRTUAL_KEYS.values(), VK_ESCAPE)
)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    )


class _INPUTUNION(ctypes.Union):
    # INPUT's native union is 32 bytes on x64 and 24 on x86. Padding keeps the
    # keyboard and narrowly reviewed mouse transports on the exact Win32 ABI.
    _fields_ = (
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        (
            "_native_abi_padding",
            ctypes.c_ubyte * (32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24),
        ),
    )


class _INPUT(ctypes.Structure):
    _anonymous_ = ("payload",)
    _fields_ = (("type", wintypes.DWORD), ("payload", _INPUTUNION))


class CtypesWin32KeyboardBackend:
    """Documented user-mode keyboard/mouse transport, not a native runner.

    Only this integration boundary imports ``ctypes``. The core execution
    package sees the injected ``WindowsKeyboardBackend`` protocol. There is no
    focus-steal, PostMessage, HID/kernel path, injection, or process-memory
    operation in this backend. Mouse support is limited to exact relative
    movement and exact right-button ownership for the reviewed combat turn adapter.
    Foreground handoff is limited to the already verified target HWND.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Win32 SendInput is available only on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._hash_cache: dict[tuple[str, int, int, int, int], str] = {}
        self._receipt_lock = RLock()
        self._receipt_counter = 0
        self._process_handles: dict[str, object] = {}
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        user32 = self._user32
        kernel32 = self._kernel32

        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.AttachThreadInput.argtypes = (
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.BOOL,
        )
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = (wintypes.HWND,)
        user32.BringWindowToTop.restype = wintypes.BOOL
        user32.ShowWindowAsync.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindowAsync.restype = wintypes.BOOL
        user32.IsWindow.argtypes = (wintypes.HWND,)
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = (wintypes.HWND,)
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        user32.GetClassNameW.restype = ctypes.c_int
        user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
        user32.MapVirtualKeyW.restype = wintypes.UINT
        user32.SendInput.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(_INPUT),
            ctypes.c_int,
        )
        user32.SendInput.restype = wintypes.UINT

        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetCurrentThreadId.argtypes = ()
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def prevalidate_target(
        self, target: WindowsInputTargetBinding
    ) -> WindowsTargetIdentityReceipt:
        """Cold path: hash once and retain a metadata-only liveness handle."""

        if not isinstance(target, WindowsInputTargetBinding):
            raise WindowsTargetBindingError("target binding type is invalid")
        hwnd = target.hwnd
        if not self._user32.IsWindow(hwnd):
            raise WindowsTargetBindingError("target HWND no longer exists")
        pid = wintypes.DWORD()
        if not self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise OSError(ctypes.get_last_error(), "cannot resolve target HWND owner")
        if int(pid.value) != target.pid:
            raise WindowsTargetBindingError("target HWND owner PID is not exact")

        process = self._open_metadata_process(pid.value)
        retained = False
        try:
            capacity = 32_768
            image_buffer = ctypes.create_unicode_buffer(capacity)
            image_size = wintypes.DWORD(capacity)
            if not self._kernel32.QueryFullProcessImageNameW(
                process, 0, image_buffer, ctypes.byref(image_size)
            ):
                raise OSError(
                    ctypes.get_last_error(), "cannot query target executable path"
                )
            creation_time = self._query_creation_time(process)
            executable_path = image_buffer.value
            executable_sha256 = self._sha256_cached(Path(executable_path))

            if not self._user32.IsWindow(hwnd):
                raise WindowsTargetBindingError(
                    "target HWND disappeared during cold validation"
                )
            final_pid = wintypes.DWORD()
            if not self._user32.GetWindowThreadProcessId(
                hwnd, ctypes.byref(final_pid)
            ):
                raise OSError(
                    ctypes.get_last_error(), "cannot recheck target HWND owner"
                )
            if int(final_pid.value) != target.pid:
                raise WindowsTargetBindingError(
                    "target HWND owner changed during cold validation"
                )

            window_class = ctypes.create_unicode_buffer(256)
            if not self._user32.GetClassNameW(
                hwnd, window_class, len(window_class)
            ):
                raise OSError(
                    ctypes.get_last_error(), "cannot query target window class"
                )
            title_length = self._user32.GetWindowTextLengthW(hwnd)
            window_title = ctypes.create_unicode_buffer(title_length + 1)
            if title_length and not self._user32.GetWindowTextW(
                hwnd, window_title, len(window_title)
            ):
                raise OSError(
                    ctypes.get_last_error(), "cannot query target window title"
                )

            path_matches = ntpath.normcase(ntpath.normpath(executable_path)) == ntpath.normcase(
                ntpath.normpath(target.executable_path)
            )
            wait_timeout = 0x00000102
            mismatches: list[str] = []
            if creation_time != target.process_creation_time_100ns:
                mismatches.append("creation_time")
            if not path_matches:
                mismatches.append("executable_path")
            if executable_sha256 != target.executable_sha256:
                mismatches.append("executable_sha256")
            if window_class.value != target.window_class_exact:
                mismatches.append("window_class")
            if window_title.value != target.window_title_exact:
                mismatches.append("window_title")
            if int(self._user32.GetForegroundWindow() or 0) != target.hwnd:
                mismatches.append("foreground_window")
            if not self._user32.IsWindowVisible(hwnd):
                mismatches.append("window_visible")
            if self._user32.IsIconic(hwnd):
                mismatches.append("window_minimized")
            if int(self._kernel32.WaitForSingleObject(process, 0)) != wait_timeout:
                mismatches.append("process_liveness")
            if mismatches:
                raise WindowsTargetBindingError(
                    "cold target identity does not match the exact binding: "
                    + ",".join(mismatches)
                )

            with self._receipt_lock:
                self._receipt_counter += 1
                receipt = WindowsTargetIdentityReceipt(
                    receipt_id=(
                        f"win32-receipt:{self._receipt_counter}:{target.pid}:"
                        f"{target.hwnd:X}"
                    ),
                    target=target,
                )
                self._process_handles[receipt.receipt_id] = process
                retained = True
                return receipt
        finally:
            if not retained:
                self._kernel32.CloseHandle(process)

    def _open_metadata_process(self, pid: int) -> object:
        """Open only a metadata/liveness handle, with a legacy-WoW fallback."""

        preferred_access = PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
        ctypes.set_last_error(0)
        process = self._kernel32.OpenProcess(preferred_access, False, pid)
        if process:
            return process

        preferred_error = ctypes.get_last_error()
        if preferred_error != ERROR_ACCESS_DENIED:
            raise OSError(
                preferred_error, "cannot open target metadata handle"
            )

        # Some legacy Windows processes deny QUERY_LIMITED_INFORMATION while
        # accepting the older QUERY_INFORMATION right.  This fallback remains
        # metadata/liveness-only: it never asks for any VM access right.
        fallback_access = PROCESS_QUERY_INFORMATION | SYNCHRONIZE
        ctypes.set_last_error(0)
        process = self._kernel32.OpenProcess(fallback_access, False, pid)
        if not process:
            raise OSError(
                ctypes.get_last_error(),
                "cannot open target legacy metadata handle",
            )
        return process

    def inspect_hot(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> WindowsHotTargetSnapshot:
        """Hot path: no file I/O, hashing, image query, or process-memory access."""

        if not isinstance(receipt, WindowsTargetIdentityReceipt):
            raise WindowsTargetBindingError("target receipt type is invalid")
        with self._receipt_lock:
            process = self._process_handles.get(receipt.receipt_id)
            if process is None:
                raise WindowsTargetBindingError("target receipt is no longer live")
            wait_result = int(self._kernel32.WaitForSingleObject(process, 0))
            creation_time = self._query_creation_time(process)

        target = receipt.target
        owner_pid = wintypes.DWORD()
        window_exists = bool(self._user32.IsWindow(target.hwnd))
        if window_exists:
            if not self._user32.GetWindowThreadProcessId(
                target.hwnd, ctypes.byref(owner_pid)
            ):
                raise OSError(
                    ctypes.get_last_error(), "cannot query hot target HWND owner"
                )
        wait_timeout = 0x00000102
        wait_failed = 0xFFFFFFFF
        if wait_result == wait_failed:
            raise OSError(ctypes.get_last_error(), "target liveness wait failed")
        return WindowsHotTargetSnapshot(
            hwnd=target.hwnd if window_exists else 0,
            foreground_hwnd=int(self._user32.GetForegroundWindow() or 0),
            owner_pid=int(owner_pid.value),
            process_creation_time_100ns=creation_time,
            process_alive=wait_result == wait_timeout,
            visible=window_exists and bool(self._user32.IsWindowVisible(target.hwnd)),
            minimized=(
                bool(self._user32.IsIconic(target.hwnd)) if window_exists else True
            ),
        )

    def release_identity_receipt(
        self, receipt: WindowsTargetIdentityReceipt
    ) -> None:
        if not isinstance(receipt, WindowsTargetIdentityReceipt):
            raise WindowsTargetBindingError("target receipt type is invalid")
        with self._receipt_lock:
            process = self._process_handles.pop(receipt.receipt_id, None)
        if process is not None:
            self._kernel32.CloseHandle(process)

    def _query_creation_time(self, process: object) -> int:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not self._kernel32.GetProcessTimes(
            process,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise OSError(
                ctypes.get_last_error(), "cannot query target process creation time"
            )
        return (int(creation.dwHighDateTime) << 32) | int(
            creation.dwLowDateTime
        )

    def map_virtual_key(self, virtual_key: int) -> int:
        if type(virtual_key) is not int or not 1 <= virtual_key <= 0xFF:
            raise ValueError("virtual key must be in [1, 255]")
        if virtual_key not in _V1_NON_EXTENDED_VIRTUAL_KEYS:
            raise ValueError(
                "v1 accepts only the exact default non-extended virtual keys"
            )
        scan_code = self._user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
        if type(scan_code) is not int or not 1 <= scan_code <= 0xFF:
            raise WindowsInputSinkError(
                "MapVirtualKeyW returned an unsupported extended scan code"
            )
        return scan_code

    def focus_bound_target(self, target: WindowsInputTargetBinding) -> int:
        """Focus the already-authorized HWND before any input sink is created."""

        if not isinstance(target, WindowsInputTargetBinding):
            raise WindowsTargetBindingError("focus target binding type is invalid")
        if not self._user32.IsWindow(target.hwnd):
            raise WindowsTargetBindingError("focus target HWND no longer exists")
        pid = wintypes.DWORD()
        target_thread = self._user32.GetWindowThreadProcessId(
            target.hwnd, ctypes.byref(pid)
        )
        if not target_thread:
            raise OSError(ctypes.get_last_error(), "cannot resolve focus HWND owner")
        if (
            int(pid.value) != target.pid
            or not self._user32.IsWindowVisible(target.hwnd)
            or self._user32.IsIconic(target.hwnd)
        ):
            raise WindowsTargetBindingError("focus target hot identity does not match")
        focused = bool(self._user32.SetForegroundWindow(target.hwnd))
        if not focused or int(self._user32.GetForegroundWindow() or 0) != target.hwnd:
            foreground = self._user32.GetForegroundWindow()
            foreground_thread = (
                self._user32.GetWindowThreadProcessId(foreground, None)
                if foreground
                else 0
            )
            current_thread = self._kernel32.GetCurrentThreadId()
            attached_threads: list[int] = []
            try:
                for thread_id in (foreground_thread, target_thread):
                    thread_id = int(thread_id)
                    if (
                        thread_id
                        and thread_id != int(current_thread)
                        and thread_id not in attached_threads
                        and self._user32.AttachThreadInput(
                            current_thread, thread_id, True
                        )
                    ):
                        attached_threads.append(thread_id)
                self._user32.ShowWindowAsync(target.hwnd, 9)
                self._user32.BringWindowToTop(target.hwnd)
                self._user32.SetForegroundWindow(target.hwnd)
            finally:
                for thread_id in reversed(attached_threads):
                    self._user32.AttachThreadInput(current_thread, thread_id, False)
        if int(self._user32.GetForegroundWindow() or 0) != target.hwnd:
            raise WindowsTargetBindingError("Windows refused the bound target focus")
        return 1

    def send_scan_code(self, scan_code: int, *, key_up: bool) -> int:
        if type(scan_code) is not int or not 1 <= scan_code <= 0xFF:
            raise ValueError("scan_code must be a non-extended byte")
        if type(key_up) is not bool:
            raise ValueError("key_up must be boolean")
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        event = _INPUT(
            type=INPUT_KEYBOARD,
            payload=_INPUTUNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=scan_code,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            1, ctypes.byref(event), ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != 1:
            raise OSError(
                ctypes.get_last_error(),
                "SendInput did not submit exactly one keyboard event",
            )
        return submitted

    def send_exact_target_name(self, target_name: str) -> int:
        """Submit one fixed `/targetexact` chat command as a single Win32 batch."""

        from perfect_assassin.brain.hunting import (
            compile_target_exact_command,
            validate_exact_target_name,
        )

        name = validate_exact_target_name(target_name)
        command = compile_target_exact_command(name)
        return self._send_fixed_chat_command(
            command,
            failure_label="exact-target",
        )

    def send_stealth_command(self) -> int:
        """Submit the single reviewed Rogue roaming command."""

        return self._send_fixed_chat_command(
            "/cast Stealth",
            failure_label="stealth",
        )

    def send_stand_command(self) -> int:
        """Put the avatar in the standing state without toggle semantics.

        `/stand` is intentionally used instead of the SITORSTAND binding: the
        latter toggles and can recreate the seated camera pivot when the avatar
        is already standing.
        """

        return self._send_fixed_chat_command(
            "/stand",
            failure_label="stand",
        )

    def send_camera_view_snapshot(self, *, view_index: int = 3) -> int:
        """Persist the operator-reviewed pitch and zoom in one native view slot."""

        if type(view_index) is not int or not 2 <= view_index <= 5:
            raise ValueError("camera snapshot view index must be in [2, 5]")
        return self._send_fixed_chat_command(
            f"/run SaveView({view_index})",
            failure_label="camera-view-snapshot",
        )

    def send_camera_home_command(
        self, *, view_index: int = 3, smart_pivot: bool = False
    ) -> int:
        """Restore the operator-reviewed TBC navigation-camera view.

        The old recovery reset the slot and rebuilt pitch/zoom from arbitrary
        mouse and wheel steps.  That erased the composition selected by the
        operator and made recovery itself look robotic.  Slot restoration is
        the native 2.4.3 mechanism for reproducing the reviewed camera while
        navigation continues to own yaw through RMB.
        """

        if type(view_index) is not int or not 2 <= view_index <= 5:
            raise ValueError("camera home view index must be in [2, 5]")
        if type(smart_pivot) is not bool:
            raise ValueError("camera home smart pivot flag must be a bool")
        pivot = "1" if smart_pivot else "0"

        return self._send_fixed_chat_command(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            f'SetCVar("cameraPivot","{pivot}");'
            'SetCVar("rotateMinimap","0");'
            f"SetView({view_index})",
            failure_label="camera-home",
        )

    def send_navigation_camera_preferences(self) -> int:
        """Own only navigation camera behavior, preserving operator framing.

        Pitch and distance are presentation choices, not movement state.  A
        normal autonomous start must therefore never call ResetView, SetView,
        or a zoom API: doing so repeatedly erased the operator's corrected
        composition.  Smart Pivot is disabled because local collision can lift
        the view toward the sky, including in a WMO interior.  Autonomous
        yaw-follow remains disabled because RMB owns it.
        """

        return self._send_fixed_chat_command(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            # Navigation keeps Smart Pivot disabled.  The client can otherwise
            # lift the view toward the sky when the avatar is pressed against
            # a lamp, cart, building, or WMO interior.
            'SetCVar("cameraPivot","0");'
            'SetCVar("rotateMinimap","0")',
            failure_label="navigation-camera-preferences",
        )

    def send_camera_pivot_profile(
        self, *, camera_distance_max_factor: float, smart_pivot: bool = False
    ) -> int:
        """Apply collision/pivot behavior without moving the camera itself.

        In the original 2.4.3 UI, ``cameraSmoothStyle=0`` is the *Never auto
        adjust* mode while ``cameraPivot=1`` is the independent Smart Pivot
        checkbox.  Keeping those concerns separate prevents the client yaw
        follower from fighting RMB facing.  Navigation keeps ``smart_pivot``
        disabled, including inside WMOs: the 2.4.3 client may tilt the camera
        toward the sky when the actor brushes an interior wall.
        """

        if (
            isinstance(camera_distance_max_factor, bool)
            or not isinstance(camera_distance_max_factor, (int, float))
            or not 1.0 <= float(camera_distance_max_factor) <= 2.0
        ):
            raise ValueError("camera distance max factor must be in [1, 2]")
        if type(smart_pivot) is not bool:
            raise ValueError("camera smart pivot flag must be a bool")
        factor = f"{float(camera_distance_max_factor):.2f}".rstrip("0").rstrip(".")
        pivot = "1" if smart_pivot else "0"
        return self._send_fixed_chat_command(
            '/run SetCVar("cameraSmoothStyle","0");'
            'SetCVar("cameraSmoothTrackingStyle","0");'
            f'SetCVar("cameraPivot","{pivot}");'
            f'SetCVar("cameraDistanceMaxFactor","{factor}");'
            'SetCVar("rotateMinimap","0")',
            failure_label="camera-pivot-profile",
        )

    def _send_fixed_chat_command(self, command: str, *, failure_label: str) -> int:
        if not isinstance(command, str) or not command:
            raise ValueError("fixed chat command must be non-empty")
        if any(ord(character) > 0xFFFF for character in command):
            raise ValueError("fixed chat command must contain BMP code units only")
        events: list[_INPUT] = []

        def append_return(*, key_up: bool) -> None:
            events.append(
                _INPUT(
                    type=INPUT_KEYBOARD,
                    payload=_INPUTUNION(
                        ki=_KEYBDINPUT(
                            wVk=VK_RETURN,
                            wScan=0,
                            dwFlags=KEYEVENTF_KEYUP if key_up else 0,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                )
            )

        append_return(key_up=False)
        append_return(key_up=True)
        for character in command:
            code_unit = ord(character)
            for key_up in (False, True):
                events.append(
                    _INPUT(
                        type=INPUT_KEYBOARD,
                        payload=_INPUTUNION(
                            ki=_KEYBDINPUT(
                                wVk=0,
                                wScan=code_unit,
                                dwFlags=KEYEVENTF_UNICODE
                                | (KEYEVENTF_KEYUP if key_up else 0),
                                time=0,
                                dwExtraInfo=0,
                            )
                        ),
                    )
                )
        append_return(key_up=False)
        append_return(key_up=True)
        batch_type = _INPUT * len(events)
        batch = batch_type(*events)
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            len(events), batch, ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != len(events):
            raise OSError(
                ctypes.get_last_error(),
                f"SendInput did not submit the complete {failure_label} batch",
            )
        return submitted

    def send_turn_mode_key(self, *, key_up: bool) -> int:
        if type(key_up) is not bool:
            raise ValueError("key_up must be boolean")
        event = _INPUT(
            type=INPUT_MOUSE,
            payload=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_RIGHTUP if key_up else MOUSEEVENTF_RIGHTDOWN,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            1, ctypes.byref(event), ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != 1:
            raise OSError(
                ctypes.get_last_error(),
                "SendInput did not submit exactly one turn-mode mouse event",
            )
        return submitted

    def send_target_select_key(self, *, key_up: bool) -> int:
        if type(key_up) is not bool:
            raise ValueError("key_up must be boolean")
        event = _INPUT(
            type=INPUT_MOUSE,
            payload=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_LEFTUP if key_up else MOUSEEVENTF_LEFTDOWN,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            1, ctypes.byref(event), ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != 1:
            raise OSError(
                ctypes.get_last_error(),
                "SendInput did not submit exactly one target-select mouse event",
            )
        return submitted

    def prepare_world_drag_cursor(self, *, hwnd: int) -> WindowsCursorPlacement:
        if type(hwnd) is not int or hwnd <= 0 or not self._user32.IsWindow(hwnd):
            raise WindowsTargetBindingError("world-drag HWND is invalid")
        client = wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, ctypes.byref(client)):
            raise OSError(ctypes.get_last_error(), "cannot query world-drag client rect")
        width = int(client.right - client.left)
        height = int(client.bottom - client.top)
        if width < 16 or height < 16:
            raise WindowsInputSinkError("world-drag client rect is too small")
        original = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(original)):
            raise OSError(ctypes.get_last_error(), "cannot capture cursor position")
        # The lower-left quarter is occupied by the expanded chat frame in the
        # reviewed windowed layout; RMB there is consumed by UI and WoW never
        # enters mouselook.  This upper-right interior point stays below the
        # minimap and clear of target frames, addon HUD, chat and action bars.
        # It is deliberately off the center/nameplate lane so a selected unit
        # cannot turn the calibration drag into a unit interaction.
        safe = wintypes.POINT((width * 72) // 100, (height * 38) // 100)
        if not self._user32.ClientToScreen(hwnd, ctypes.byref(safe)):
            raise OSError(ctypes.get_last_error(), "cannot resolve world-drag point")
        if not self._user32.SetCursorPos(int(safe.x), int(safe.y)):
            raise OSError(ctypes.get_last_error(), "cannot place world-drag cursor")
        placed = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(placed)):
            self._user32.SetCursorPos(int(original.x), int(original.y))
            raise OSError(ctypes.get_last_error(), "cannot verify world-drag cursor")
        if int(placed.x) != int(safe.x) or int(placed.y) != int(safe.y):
            self._user32.SetCursorPos(int(original.x), int(original.y))
            raise WindowsInputSinkError("world-drag cursor placement was not exact")
        return WindowsCursorPlacement(
            original_x=int(original.x),
            original_y=int(original.y),
            placed_x=int(placed.x),
            placed_y=int(placed.y),
        )

    def prepare_client_point_cursor(
        self, *, hwnd: int, x_normalized: float, y_normalized: float
    ) -> WindowsCursorPlacement:
        if type(hwnd) is not int or hwnd <= 0 or not self._user32.IsWindow(hwnd):
            raise WindowsTargetBindingError("client-point HWND is invalid")
        for label, value in (("x", x_normalized), ("y", y_normalized)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < float(value) < 1.0:
                raise ValueError(f"normalized client {label} is invalid")
        client = wintypes.RECT()
        if not self._user32.GetClientRect(hwnd, ctypes.byref(client)):
            raise OSError(ctypes.get_last_error(), "cannot query client-point rect")
        width = int(client.right - client.left)
        height = int(client.bottom - client.top)
        original = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(original)):
            raise OSError(ctypes.get_last_error(), "cannot capture cursor position")
        point = wintypes.POINT(
            int(round(width * float(x_normalized))),
            int(round(height * float(y_normalized))),
        )
        if not self._user32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise OSError(ctypes.get_last_error(), "cannot resolve client click point")
        if not self._user32.SetCursorPos(int(point.x), int(point.y)):
            raise OSError(ctypes.get_last_error(), "cannot place client click cursor")
        placed = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(placed)):
            self._user32.SetCursorPos(int(original.x), int(original.y))
            raise OSError(ctypes.get_last_error(), "cannot verify client click cursor")
        if int(placed.x) != int(point.x) or int(placed.y) != int(point.y):
            self._user32.SetCursorPos(int(original.x), int(original.y))
            raise WindowsInputSinkError("client click cursor placement was not exact")
        return WindowsCursorPlacement(
            original_x=int(original.x),
            original_y=int(original.y),
            placed_x=int(placed.x),
            placed_y=int(placed.y),
        )

    def restore_cursor_position(self, placement: WindowsCursorPlacement) -> int:
        if not isinstance(placement, WindowsCursorPlacement):
            raise ValueError("cursor placement receipt is invalid")
        if not self._user32.SetCursorPos(placement.original_x, placement.original_y):
            raise OSError(ctypes.get_last_error(), "cannot restore cursor position")
        return 1

    def send_escape_key(self) -> int:
        """Dismiss one modal game UI frame through the exact Escape key."""

        scan_code = self.map_virtual_key(VK_ESCAPE)
        if type(scan_code) is not int or not 1 <= scan_code <= 0xFF:
            raise WindowsInputSinkError("Escape requires one non-extended scan code")
        down = self.send_scan_code(scan_code, key_up=False)
        up = self.send_scan_code(scan_code, key_up=True)
        if down != 1 or up != 1:
            raise WindowsInputSinkError("Escape key submission was not exact")
        return 2

    def send_relative_mouse(self, *, delta_x: int, delta_y: int) -> int:
        for name, value in (("delta_x", delta_x), ("delta_y", delta_y)):
            if type(value) is not int or not -32_767 <= value <= 32_767:
                raise ValueError(f"{name} must be a bounded exact integer")
        if delta_x == 0 and delta_y == 0:
            raise ValueError("relative mouse movement cannot be zero")
        event = _INPUT(
            type=INPUT_MOUSE,
            payload=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=delta_x,
                    dy=delta_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            1, ctypes.byref(event), ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != 1:
            raise OSError(
                ctypes.get_last_error(),
                "SendInput did not submit exactly one relative mouse event",
            )
        return submitted

    def send_mouse_wheel(self, *, steps: int) -> int:
        """Submit one bounded camera-zoom wheel event to the focused client."""

        if type(steps) is not int or steps == 0 or not -8 <= steps <= 8:
            raise ValueError("mouse wheel steps must be a non-zero integer in [-8, 8]")
        signed_delta = steps * WHEEL_DELTA
        event = _INPUT(
            type=INPUT_MOUSE,
            payload=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=signed_delta & 0xFFFFFFFF,
                    dwFlags=MOUSEEVENTF_WHEEL,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        submitted = self._user32.SendInput(
            1, ctypes.byref(event), ctypes.sizeof(_INPUT)
        )
        if type(submitted) is not int or submitted != 1:
            raise OSError(
                ctypes.get_last_error(),
                "SendInput did not submit exactly one camera-zoom wheel event",
            )
        return submitted

    def _sha256_cached(self, path: Path) -> str:
        try:
            stat = path.stat()
        except OSError as error:
            raise WindowsTargetBindingError(
                "cannot stat the target executable"
            ) from error
        cache_key = (
            ntpath.normcase(ntpath.normpath(str(path))),
            int(stat.st_dev),
            int(stat.st_ino),
            int(stat.st_size),
            int(stat.st_mtime_ns),
        )
        cached = self._hash_cache.get(cache_key)
        if cached is not None:
            return cached
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise WindowsTargetBindingError(
                "cannot hash the target executable"
            ) from error
        if len(self._hash_cache) >= 16:
            self._hash_cache.clear()
        result = digest.hexdigest().upper()
        self._hash_cache[cache_key] = result
        return result
