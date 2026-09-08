from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable, Sequence


class WindowSelectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScreenRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def relative_to(self, outer: ScreenRect) -> ScreenRect:
        if (
            self.left < outer.left
            or self.top < outer.top
            or self.right > outer.right
            or self.bottom > outer.bottom
        ):
            raise WindowSelectionError("window client rectangle is outside the selected output")
        return ScreenRect(
            left=self.left - outer.left,
            top=self.top - outer.top,
            right=self.right - outer.left,
            bottom=self.bottom - outer.top,
        )


@dataclass(frozen=True, slots=True)
class WindowSnapshot:
    hwnd: int
    pid: int
    title: str
    class_name: str
    visible: bool
    minimized: bool
    foreground: bool
    client_rect: ScreenRect
    dpi: int

    @property
    def usable(self) -> bool:
        return self.visible and not self.minimized and self.foreground and self.client_rect.valid

    @property
    def window_ref(self) -> str:
        return f"hwnd:0x{self.hwnd:X}:pid:{self.pid}"

    @property
    def title_sha256(self) -> str:
        return hashlib.sha256(self.title.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WindowQuery:
    pid: int
    hwnd: int | None = None
    title_exact: str | None = None
    class_exact: str | None = None
    require_foreground: bool = True

    def __post_init__(self) -> None:
        if self.pid <= 0:
            raise ValueError("pid must be positive")
        if self.hwnd is not None and self.hwnd <= 0:
            raise ValueError("hwnd must be positive")


def select_unique_window(
    windows: Iterable[WindowSnapshot], query: WindowQuery
) -> WindowSnapshot:
    matches = [
        window
        for window in windows
        if window.pid == query.pid
        and (query.hwnd is None or window.hwnd == query.hwnd)
        and (query.title_exact is None or window.title == query.title_exact)
        and (query.class_exact is None or window.class_name == query.class_exact)
    ]
    if len(matches) != 1:
        raise WindowSelectionError(
            f"expected exactly one target window, found {len(matches)}"
        )
    selected = matches[0]
    if not selected.visible:
        raise WindowSelectionError("target window is not visible")
    if selected.minimized:
        raise WindowSelectionError("target window is minimized")
    if query.require_foreground and not selected.foreground:
        raise WindowSelectionError("target window is not the foreground window")
    if not selected.client_rect.valid:
        raise WindowSelectionError("target window has an empty client rectangle")
    return selected


def _windows_api() -> tuple[ctypes.WinDLL, object]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not hasattr(user32, "SetThreadDpiAwarenessContext"):
        raise RuntimeError("per-monitor DPI awareness is unavailable")
    user32.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
    ctypes.set_last_error(0)
    previous_context = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous_context and ctypes.get_last_error():
        raise OSError(ctypes.get_last_error(), "cannot set per-monitor DPI awareness")

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    if hasattr(user32, "GetDpiForWindow"):
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
    return user32, callback_type


def enumerate_top_level_windows() -> list[WindowSnapshot]:
    user32, callback_type = _windows_api()
    windows: list[WindowSnapshot] = []
    foreground_hwnd = int(user32.GetForegroundWindow() or 0)

    def callback(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))

        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))

        client = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not user32.GetClientRect(hwnd, ctypes.byref(client)):
            return True
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return True

        dpi = int(user32.GetDpiForWindow(hwnd)) if hasattr(user32, "GetDpiForWindow") else 96
        windows.append(
            WindowSnapshot(
                hwnd=int(hwnd),
                pid=int(pid.value),
                title=title_buffer.value,
                class_name=class_buffer.value,
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                foreground=int(hwnd) == foreground_hwnd,
                client_rect=ScreenRect(
                    left=int(origin.x),
                    top=int(origin.y),
                    right=int(origin.x + client.right - client.left),
                    bottom=int(origin.y + client.bottom - client.top),
                ),
                dpi=dpi or 96,
            )
        )
        return True

    enum_callback = callback_type(callback)
    if not user32.EnumWindows(enum_callback, 0):
        error_code = ctypes.get_last_error()
        if error_code:
            raise OSError(error_code, "EnumWindows failed")
    return windows


def locate_window(query: WindowQuery) -> WindowSnapshot:
    return select_unique_window(enumerate_top_level_windows(), query)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Locate one visible, non-minimized top-level window by PID."
    )
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--hwnd", type=lambda value: int(value, 0))
    parser.add_argument("--title-exact")
    parser.add_argument("--class-exact")
    parser.add_argument("--allow-background", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        window = locate_window(
            WindowQuery(
                pid=args.pid,
                hwnd=args.hwnd,
                title_exact=args.title_exact,
                class_exact=args.class_exact,
                require_foreground=not args.allow_background,
            )
        )
    except (ValueError, WindowSelectionError, OSError, RuntimeError) as error:
        print(
            json.dumps(
                {
                    "status": "window_unavailable",
                    "detail": str(error),
                    "execution_authority": False,
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "window_located",
                "window_ref": window.window_ref,
                "pid": window.pid,
                "class_name": window.class_name,
                "title_sha256": window.title_sha256,
                "client_rect_screen": {
                    "left": window.client_rect.left,
                    "top": window.client_rect.top,
                    "right": window.client_rect.right,
                    "bottom": window.client_rect.bottom,
                    "width": window.client_rect.width,
                    "height": window.client_rect.height,
                },
                "coordinate_space": "desktop_physical_pixels",
                "dpi": window.dpi,
                "visible": window.visible,
                "minimized": window.minimized,
                "foreground": window.foreground,
                "execution_authority": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
