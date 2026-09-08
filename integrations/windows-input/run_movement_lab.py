from __future__ import annotations

import argparse
import ctypes
import json
from math import cos, hypot, sin
from pathlib import Path
import sys
import time
import tkinter as tk


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from perfect_assassin.movement.movement_lab import MovementLabSnapshot


DEFAULT_STATE = ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
DEFAULT_WAYPOINTS = ROOT / "config" / "movement-lab" / "manual-waypoints.json"
DEFAULT_CONTROL = (
    ROOT / "data" / "runtime" / "operator" / "movement-lab-overlay-control.json"
)
TRANSPARENT_COLOR = "#010101"


def _north_up_radar_delta(
    *, world_x: float, world_y: float, player_x: float, player_y: float,
    scale: float,
) -> tuple[float, float]:
    """Project WoW world axes into the same north-up plane as the atlas."""

    return (
        -(world_y - player_y) * scale,
        -(world_x - player_x) * scale,
    )


class Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class Rect(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    )


def _client_geometry(window_class: str, window_title: str) -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    hwnd = int(user32.FindWindowW(window_class, window_title))
    if not hwnd:
        raise RuntimeError("exact WoW window was not found")
    rect = Rect()
    origin = Point(0, 0)
    if user32.GetClientRect(hwnd, ctypes.byref(rect)) != 1:
        raise RuntimeError("WoW client rectangle is unavailable")
    if user32.ClientToScreen(hwnd, ctypes.byref(origin)) != 1:
        raise RuntimeError("WoW client origin is unavailable")
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def _read_snapshot(path: Path) -> MovementLabSnapshot | None:
    try:
        return MovementLabSnapshot.from_record(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _load_waypoints(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": "1.0", "waypoints": []}
    if not isinstance(value, dict) or not isinstance(value.get("waypoints"), list):
        raise ValueError("manual waypoint file is invalid")
    return value


def _read_control(path: Path) -> tuple[int, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return 0, None
    if not isinstance(value, dict):
        return 0, None
    revision = value.get("revision")
    command = value.get("command")
    if type(revision) is not int or revision < 0:
        return 0, None
    if command not in {"START", "STOP"}:
        return revision, None
    return revision, str(command)


def _write_waypoints(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class MovementLabWindow:
    def __init__(
        self,
        *,
        state_file: Path,
        waypoints_file: Path,
        control_file: Path,
        window_class: str,
        window_title: str,
        opacity: float,
        show_mesh: bool,
        show_facing: bool,
    ) -> None:
        self._state_file = state_file
        self._waypoints_file = waypoints_file
        self._control_file = control_file
        self._control_revision = _read_control(control_file)[0]
        self._window_class = window_class
        self._window_title = window_title
        self._opacity = opacity
        self._show_mesh = show_mesh
        self._show_facing = show_facing
        user32 = ctypes.windll.user32
        previous_foreground = int(user32.GetForegroundWindow() or 0)
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("Predator Movement Lab")
        self._root.configure(bg=TRANSPARENT_COLOR)
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", self._opacity)
        self._root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
        self._canvas = tk.Canvas(
            self._root, bg=TRANSPARENT_COLOR, highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)
        self._last_geometry: tuple[int, int, int, int] | None = None
        self._last_snapshot: MovementLabSnapshot | None = None
        self._last_render_signature: object = object()
        overlay_hwnd = self._make_click_through()
        # Extended WS_EX_NOACTIVATE is already in place before the first show,
        # so the transparent overlay cannot take foreground from WoW.
        self._root.deiconify()
        user32.ShowWindow(overlay_hwnd, 4)  # SW_SHOWNOACTIVATE
        if previous_foreground and previous_foreground != overlay_hwnd:
            user32.SetForegroundWindow(previous_foreground)

    def _make_click_through(self) -> int:
        self._root.update_idletasks()
        child_hwnd = int(self._root.winfo_id())
        user32 = ctypes.windll.user32
        parent_hwnd = int(user32.GetParent(child_hwnd))
        hwnd = parent_hwnd or child_hwnd
        get_window_long = user32.GetWindowLongW
        set_window_long = user32.SetWindowLongW
        style = int(get_window_long(hwnd, -20))
        # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        set_window_long(hwnd, -20, style | 0x80000 | 0x20 | 0x08000000 | 0x80)
        # Tk's -transparentcolor can lose its color-key when the extended style
        # is changed after window creation.  Re-assert the exact Win32 key on
        # the real toplevel wrapper; otherwise the whole overlay becomes an
        # opaque near-black rectangle over the client.
        LWA_COLORKEY = 0x1
        colorref_010101 = 0x00010101
        if user32.SetLayeredWindowAttributes(
            hwnd, colorref_010101, 255, LWA_COLORKEY
        ) != 1:
            raise RuntimeError("Movement Lab color-key transparency failed")
        return hwnd

    def _draw_arrow(
        self, center_x: float, center_y: float, vector: tuple[float, float], color: str, width: int
    ) -> None:
        if vector == (0.0, 0.0):
            return
        self._canvas.create_line(
            center_x, center_y,
            center_x + vector[0], center_y + vector[1],
            fill=color, width=width, arrow=tk.LAST, arrowshape=(13, 16, 6),
        )

    def _redraw(self) -> None:
        control_revision, control_command = _read_control(self._control_file)
        if control_revision > self._control_revision:
            self._control_revision = control_revision
            if control_command == "STOP":
                self._root.destroy()
                return
        try:
            geometry = _client_geometry(self._window_class, self._window_title)
        except RuntimeError:
            self._root.after(250, self._redraw)
            return
        if geometry != self._last_geometry:
            left, top, width, height = geometry
            self._root.geometry(f"{width}x{height}+{left}+{top}")
            self._last_geometry = geometry
        snapshot = _read_snapshot(self._state_file)
        if snapshot is not None:
            self._last_snapshot = snapshot
        snapshot = self._last_snapshot
        stale = (
            False if snapshot is None
            else time.monotonic() - snapshot.observed_monotonic_s > 0.45
        )
        render_signature = (geometry, snapshot, stale)
        if render_signature == self._last_render_signature:
            self._root.after(50, self._redraw)
            return
        self._last_render_signature = render_signature
        self._canvas.delete("all")
        if snapshot is not None:
            _left, _top, width, height = geometry
            if self._show_mesh:
                self._draw_navmesh_radar(snapshot, width, height)
            center_x, center_y = width * 0.5, height * 0.70
            vectors = snapshot.arrow_vectors(radius_px=68)
            if (
                snapshot.tracking_state == "VISIBLE"
                and snapshot.target_error_x_normalized is not None
                and snapshot.target_screen_y_normalized is not None
            ):
                target_x = width * (
                    0.5 + 0.5 * snapshot.target_error_x_normalized
                )
                target_y = height * snapshot.target_screen_y_normalized
                tether_colors = {
                    "DIRECT": "#55ff88",
                    "IN_MELEE": "#39e6ff",
                    "DETOUR_LEFT": "#ffc857",
                    "DETOUR_RIGHT": "#ffc857",
                    "PARTIAL_ADVANCE_DIRECT": "#72ff59",
                    "PARTIAL_ADVANCE_LEFT": "#72ff59",
                    "PARTIAL_ADVANCE_RIGHT": "#72ff59",
                    "WAITING_NAVMESH": "#b8b8b8",
                    "PARTIAL_BLOCKED": "#ff5757",
                }
                tether_color = tether_colors.get(
                    snapshot.tether_state, "#ff35d3"
                )
                # The actor anchor is deliberately low in the viewport.  The
                # endpoint is the CRC-bound selected circle/nameplate geometry.
                self._canvas.create_line(
                    center_x, height * 0.77, target_x, target_y,
                    fill=tether_color, width=3, dash=(8, 4), arrow=tk.LAST,
                )
                self._canvas.create_oval(
                    target_x - 7, target_y - 7, target_x + 7, target_y + 7,
                    outline=tether_color, width=3,
                )
            ring_color = "#ff4b4b" if stale else "#78f7ff"
            if self._show_facing:
                self._canvas.create_oval(
                    center_x - 76, center_y - 76,
                    center_x + 76, center_y + 76,
                    outline=ring_color, width=2,
                )
                self._draw_arrow(center_x, center_y, vectors["player"], "#39e6ff", 5)
                self._draw_arrow(center_x, center_y, vectors["target"], "#ff35d3", 3)
                self._draw_arrow(center_x, center_y, vectors["waypoint"], "#72ff59", 2)
            error = snapshot.target_error_x_normalized
            label = (
                f"{snapshot.controller_state}  {snapshot.tracking_state}  "
                f"TETHER={snapshot.tether_state}  "
                f"MOBS={snapshot.visible_attackable_candidate_count}  "
                f"error={error:+.3f}" if error is not None
                else f"{snapshot.controller_state}  {snapshot.tracking_state}"
            )
            if self._show_facing:
                self._canvas.create_text(
                    center_x, center_y + 94, text=label,
                    fill="#ffffff" if not stale else "#ff7474",
                    font=("Segoe UI", 10, "bold"),
                )
        self._root.after(50, self._redraw)

    def _draw_navmesh_radar(
        self, snapshot: MovementLabSnapshot, width: int, height: int
    ) -> None:
        if snapshot.player_world_x is None:
            return
        radius_px = 145.0
        scale = 3.0
        center_x, center_y = width - radius_px - 24, height - radius_px - 42
        self._canvas.create_oval(
            center_x - radius_px, center_y - radius_px,
            center_x + radius_px, center_y + radius_px,
            fill="#07140d", outline="#68ff9a", width=2,
        )

        def screen(point: tuple[float, float]) -> tuple[float, float]:
            # Match the client atlas/minimap convention exactly: north is
            # world +X and east is world -Y.  The previous X-right/Y-up view
            # was a rotated engineering plot, not a faithful WoW north-up map.
            delta_x, delta_y = _north_up_radar_delta(
                world_x=point[0], world_y=point[1],
                player_x=snapshot.player_world_x,
                player_y=snapshot.player_world_y,
                scale=scale,
            )
            return center_x + delta_x, center_y + delta_y

        for polygon in snapshot.navmesh_polygons_world:
            flat = [value for point in polygon for value in screen(point)]
            if any(
                hypot(screen(point)[0] - center_x, screen(point)[1] - center_y)
                <= radius_px + 20
                for point in polygon
            ):
                self._canvas.create_polygon(
                    *flat, fill="", outline="#2f9e5b", width=1,
                )
        trail = [
            screen(point) for point in snapshot.traversed_path_world[-512:]
            if hypot(screen(point)[0] - center_x, screen(point)[1] - center_y)
            <= radius_px + 20
        ]
        if len(trail) >= 2:
            self._canvas.create_line(
                *[value for point in trail for value in point],
                fill="#ff8df2", width=2,
            )
        centerline = [
            screen(point) for point in snapshot.corridor_centerline_world
            if hypot(screen(point)[0] - center_x, screen(point)[1] - center_y)
            <= radius_px + 20
        ]
        if len(centerline) >= 2:
            self._canvas.create_line(
                *[value for point in centerline for value in point],
                fill="#ffe45e", width=2,
            )
        for index, waypoint in enumerate(
            snapshot.planned_waypoints_world[:12], start=1,
        ):
            waypoint_x, waypoint_y = screen(waypoint)
            if hypot(
                waypoint_x - center_x, waypoint_y - center_y,
            ) > radius_px + 8:
                continue
            radius = 5 if index == 1 else 3
            color = "#ff9f1c" if index == 1 else "#ff4bd8"
            self._canvas.create_oval(
                waypoint_x - radius, waypoint_y - radius,
                waypoint_x + radius, waypoint_y + radius,
                fill=color, outline="#ffffff", width=1,
            )
            if index <= 4:
                self._canvas.create_text(
                    waypoint_x + 8, waypoint_y - 8,
                    text=str(index), fill=color,
                    font=("Segoe UI", 8, "bold"),
                )
        tether = [
            screen(point) for point in snapshot.tether_centerline_world
            if hypot(screen(point)[0] - center_x, screen(point)[1] - center_y)
            <= radius_px + 20
        ]
        if len(tether) >= 2:
            tether_color = (
                "#ffc857"
                if snapshot.tether_state.startswith("DETOUR")
                else "#72ff59"
                if snapshot.tether_state.startswith("PARTIAL_ADVANCE")
                else "#ff5757"
                if snapshot.tether_state == "PARTIAL_BLOCKED"
                else "#ff35d3"
            )
            self._canvas.create_line(
                *[value for point in tether for value in point],
                fill=tether_color, width=3, arrow=tk.LAST,
            )
        self._canvas.create_oval(
            center_x - 4, center_y - 4, center_x + 4, center_y + 4,
            fill="#39e6ff", outline="#ffffff",
        )
        if snapshot.player_facing_rad is not None:
            facing_length = 26.0
            facing_x = center_x - sin(snapshot.player_facing_rad) * facing_length
            facing_y = center_y - cos(snapshot.player_facing_rad) * facing_length
            self._canvas.create_line(
                center_x, center_y, facing_x, facing_y,
                fill="#39e6ff", width=3, arrow=tk.LAST,
            )
        self._canvas.create_text(
            center_x, center_y - radius_px + 13,
            text="N", fill="#ffffff", font=("Segoe UI", 10, "bold"),
        )
        self._canvas.create_text(
            center_x, center_y - radius_px - 12,
            text=(
                "MESH  ~48 yd  •  NORTH-UP"
                if snapshot.navmesh_polygons_world
                else "POSE/TRAIL LIVE  •  MESH PENDING"
            ),
            fill="#68ff9a",
            font=("Segoe UI", 9, "bold"),
        )

    def run(self) -> None:
        self._redraw()
        self._root.mainloop()


def add_current_waypoint(state_file: Path, waypoints_file: Path, label: str) -> None:
    snapshot = _read_snapshot(state_file)
    if snapshot is None or snapshot.player_world_x is None:
        raise RuntimeError("the latest movement state has no player world position")
    route = _load_waypoints(waypoints_file)
    waypoints = route["waypoints"]
    assert isinstance(waypoints, list)
    waypoints.append({
        "id": f"manual-{len(waypoints) + 1:03d}",
        "label": label,
        "x": snapshot.player_world_x,
        "y": snapshot.player_world_y,
        **({} if snapshot.player_world_z is None else {"z": snapshot.player_world_z}),
        "recorded_monotonic_s": snapshot.observed_monotonic_s,
        "source": "operator_recorded_visible_position",
    })
    _write_waypoints(waypoints_file, route)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External Predator Movement Lab overlay.")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--waypoints-file", type=Path, default=DEFAULT_WAYPOINTS)
    parser.add_argument("--control-file", type=Path, default=DEFAULT_CONTROL)
    parser.add_argument("--window-class", default="GxWindowClassD3d")
    parser.add_argument("--window-title", default="World of Warcraft")
    parser.add_argument("--opacity", type=float, default=0.85)
    parser.add_argument("--hide-mesh", action="store_true")
    parser.add_argument("--hide-facing", action="store_true")
    parser.add_argument("--add-current-waypoint", metavar="LABEL")
    return parser


def run() -> int:
    args = build_parser().parse_args()
    if args.add_current_waypoint:
        add_current_waypoint(
            args.state_file, args.waypoints_file, args.add_current_waypoint
        )
        return 0
    if not 0.2 <= args.opacity <= 1.0:
        raise SystemExit("--opacity must be in [0.2, 1.0]")
    MovementLabWindow(
        state_file=args.state_file,
        waypoints_file=args.waypoints_file,
        control_file=args.control_file,
        window_class=args.window_class,
        window_title=args.window_title,
        opacity=args.opacity,
        show_mesh=not args.hide_mesh,
        show_facing=not args.hide_facing,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
