from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCATOR_PATH = ROOT / "integrations" / "windows-capture" / "window_locator.py"


def load_locator():
    spec = importlib.util.spec_from_file_location("pa_window_locator_test", LOCATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load window locator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


locator = load_locator()


def window(
    *,
    hwnd: int = 100,
    pid: int = 42,
    visible: bool = True,
    minimized: bool = False,
    foreground: bool = True,
    rect=None,
):
    return locator.WindowSnapshot(
        hwnd=hwnd,
        pid=pid,
        title="World of Warcraft",
        class_name="GxWindowClass",
        visible=visible,
        minimized=minimized,
        foreground=foreground,
        client_rect=rect or locator.ScreenRect(100, 50, 1380, 770),
        dpi=96,
    )


class WindowsCaptureSidecarTests(unittest.TestCase):
    def test_selector_requires_one_exact_pid_match(self) -> None:
        selected = locator.select_unique_window(
            [window(pid=41), window(pid=42)], locator.WindowQuery(pid=42)
        )
        self.assertEqual(selected.window_ref, "hwnd:0x64:pid:42")

        with self.assertRaises(locator.WindowSelectionError):
            locator.select_unique_window(
                [window(hwnd=100), window(hwnd=101)], locator.WindowQuery(pid=42)
            )

        exact = locator.select_unique_window(
            [window(hwnd=100), window(hwnd=101)],
            locator.WindowQuery(pid=42, hwnd=101),
        )
        self.assertEqual(exact.hwnd, 101)

    def test_selector_rejects_hidden_minimized_and_empty_windows(self) -> None:
        for candidate in (
            window(visible=False),
            window(minimized=True),
            window(foreground=False),
            window(rect=locator.ScreenRect(10, 10, 10, 20)),
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(locator.WindowSelectionError):
                    locator.select_unique_window([candidate], locator.WindowQuery(pid=42))

    def test_title_and_class_filters_are_exact(self) -> None:
        candidate = window()
        selected = locator.select_unique_window(
            [candidate],
            locator.WindowQuery(
                pid=42,
                title_exact="World of Warcraft",
                class_exact="GxWindowClass",
            ),
        )
        self.assertEqual(selected.hwnd, 100)

        with self.assertRaises(locator.WindowSelectionError):
            locator.select_unique_window(
                [candidate], locator.WindowQuery(pid=42, title_exact="Warcraft")
            )

    def test_screen_rect_translation_requires_one_output(self) -> None:
        output = locator.ScreenRect(-1920, 0, 1920, 1080)
        client = locator.ScreenRect(-100, 50, 1180, 770)
        relative = client.relative_to(output)
        self.assertEqual(relative, locator.ScreenRect(1820, 50, 3100, 770))

        split_window = locator.ScreenRect(-2000, 50, 100, 770)
        with self.assertRaises(locator.WindowSelectionError):
            split_window.relative_to(output)


if __name__ == "__main__":
    unittest.main()
