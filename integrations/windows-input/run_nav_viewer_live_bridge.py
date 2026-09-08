from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import hashlib
import json
from math import hypot, isfinite
import os
from pathlib import Path
import sys
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_navmesh_roaming import (
    DEFAULT_ZONE_TRANSFORM_CATALOG,
    EXACT_BODY_HEADING_SOURCE,
    ClientVisibleStateError,
    LiveCoordinatePoseSource,
    _load_zone_transform,
    _position,
)
from persistent_navmesh_awareness import (
    AsyncPersistentNavmeshAwareness,
    PersistentAwarenessSample,
)
from perfect_assassin.capture import NoFreshCaptureFrameError
from window_locator import WindowSelectionError


DEFAULT_AUTHORIZATION = (
    ROOT / "data" / "runtime" / "operator" / "tbc_243_lab.active.json"
)
DEFAULT_RECEIPT = (
    ROOT / "data" / "runtime" / "operator" / "lab-client-launch-receipt.json"
)
DEFAULT_STATE = (
    ROOT / "data" / "runtime" / "operator" / "nav-viewer-live-state.txt"
)
DEFAULT_DIAGNOSTIC = (
    ROOT / "data" / "runtime" / "operator" / "nav-viewer-live-bridge.json"
)
DEFAULT_MOVEMENT_STATE = (
    ROOT / "data" / "runtime" / "movement-lab" / "latest.json"
)
DEFAULT_NAVIGATION_CONTINUITY_STATE = (
    ROOT / "data" / "runtime" / "navigation-f3b" / "continuity" / "latest.json"
)
VIEWER_TRAIL_MAX_POINTS = 256
VIEWER_TRAIL_REFRESH_INTERVAL_S = 1.0

ViewerSegment = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class LiveAwarenessFrame:
    source_x: float
    source_y: float
    resolved_z: float
    observed_monotonic_s: float
    walls: tuple[ViewerSegment, ...]
    transitions: tuple[ViewerSegment, ...]
    egresses: tuple[ViewerSegment, ...]


def _server_segments(
    value: object, *, name: str, maximum: int,
) -> tuple[ViewerSegment, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise RuntimeError(f"awareness server {name} are invalid")
    result: list[ViewerSegment] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise RuntimeError(f"awareness server {name} item is invalid")
        left, right = item
        if (
            not isinstance(left, list) or len(left) != 3
            or not isinstance(right, list) or len(right) != 3
        ):
            raise RuntimeError(f"awareness server {name} geometry is invalid")
        segment = tuple(float(number) for number in (*left, *right))
        if not all(isfinite(number) for number in segment):
            raise RuntimeError(f"awareness server {name} geometry is non-finite")
        result.append(segment)  # type: ignore[arg-type]
    return tuple(result)


def _awareness_frame_from_server_response(
    response: object, *, expected_sequence: int, observed_monotonic_s: float,
) -> LiveAwarenessFrame:
    if not isinstance(response, dict):
        raise RuntimeError("awareness server response is not an object")
    if response.get("status") != "OK":
        raise RuntimeError("awareness server rejected the query")
    if response.get("sequence") != expected_sequence:
        raise RuntimeError("awareness server response sequence is invalid")
    source = response.get("source")
    resolved = response.get("resolved")
    if (
        not isinstance(source, list) or len(source) != 3
        or not isinstance(resolved, list) or len(resolved) != 3
    ):
        raise RuntimeError("awareness server pose is invalid")
    source_xyz = tuple(float(value) for value in source)
    resolved_xyz = tuple(float(value) for value in resolved)
    if not all(isfinite(value) for value in (*source_xyz, *resolved_xyz)):
        raise RuntimeError("awareness server pose is non-finite")
    return LiveAwarenessFrame(
        source_x=source_xyz[0],
        source_y=source_xyz[1],
        resolved_z=resolved_xyz[2],
        observed_monotonic_s=float(observed_monotonic_s),
        walls=_server_segments(response.get("walls"), name="walls", maximum=128),
        transitions=_server_segments(
            response.get("transitions"), name="transitions", maximum=64,
        ),
        egresses=_server_segments(
            response.get("egresses"), name="egresses", maximum=32,
        ),
    )


def _movement_floor_hint(
    path: Path, *, world_x: float, world_y: float, fallback_z: float,
    maximum_horizontal_offset_yards: float = 3.0,
) -> float:
    """Reuse a navmesh-confirmed floor only while it still matches live XY.

    The visible TBC map API exposes X/Y but not Z.  Movement snapshots already
    carry the Detour-resolved floor.  Their timestamp may be old while the actor
    is stationary, so spatial applicability is the relevant invariant here.
    """
    try:
        record = _read_object(path)
        player = record.get("player_world")
        if not isinstance(player, list) or len(player) != 3:
            return fallback_z
        x, y, z = (float(value) for value in player)
        if not all(isfinite(value) for value in (x, y, z)):
            return fallback_z
        if hypot(x - world_x, y - world_y) > maximum_horizontal_offset_yards:
            return fallback_z
        return z
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return fallback_z


AsyncLocalAwarenessProbe = AsyncPersistentNavmeshAwareness


def _viewer_awareness_frame(
    sample: PersistentAwarenessSample,
) -> LiveAwarenessFrame:
    awareness = sample.awareness
    return LiveAwarenessFrame(
        source_x=sample.source.x,
        source_y=sample.source.y,
        resolved_z=sample.resolved.z,
        observed_monotonic_s=sample.observed_monotonic_s,
        walls=tuple(
            (
                item.left.x, item.left.y, item.left.z,
                item.right.x, item.right.y, item.right.z,
            )
            for item in awareness.wall_segments
        ),
        transitions=tuple(
            (
                item.left.x, item.left.y, item.left.z,
                item.right.x, item.right.y, item.right.z,
            )
            for item in awareness.surface_transition_portals
        ),
        egresses=tuple(
            (
                item.left.x, item.left.y, item.left.z,
                item.right.x, item.right.y, item.right.z,
            )
            for item in awareness.egress_portals
        ),
    )


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain an object")
    return value


def _viewer_is_alive(pid: int) -> bool:
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _fresh_corridor(path: Path, *, now_s: float) -> tuple[tuple[float, float], ...]:
    try:
        record = _read_object(path)
        observed_s = float(record["observed_monotonic_s"])
        raw = record.get("corridor_centerline_world", [])
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isfinite(observed_s) or now_s - observed_s > 1.0 or not isinstance(raw, list):
        return ()
    points: list[tuple[float, float]] = []
    for point in raw[:128]:
        if not isinstance(point, list) or len(point) != 2:
            return ()
        x, y = float(point[0]), float(point[1])
        if not isfinite(x) or not isfinite(y):
            return ()
        points.append((x, y))
    return tuple(points)


def _fresh_movement_pose(
    path: Path, *, now_s: float, maximum_age_s: float = 0.75,
) -> tuple[
    float, float, float, float | None, str | None, float | None, float | None,
] | None:
    """Prefer the navigator's already captured pose during an active run.

    Opening a second DXGI stream while navigation owns the client starved both
    feedback loops on the LAB machine. The movement snapshot is the exact pose
    which drove the controller, so it is also the authoritative viewer pose
    while fresh. Screen capture remains a fallback when navigation is idle.
    """

    try:
        record = _read_object(path)
        observed_s = float(record["observed_monotonic_s"])
        player = record.get("player_world")
        topographic = record.get("topographic_brain")
        actor = topographic.get("actor") if isinstance(topographic, dict) else None
        facing_value = record.get("body_facing_rad")
        facing_source = record.get("body_facing_source")
        if facing_source != EXACT_BODY_HEADING_SOURCE:
            facing_value = (
                actor.get("body_facing_rad")
                if isinstance(actor, dict)
                and actor.get("body_facing_source") == EXACT_BODY_HEADING_SOURCE
                else None
            )
        camera_yaw_value = record.get("camera_yaw_estimate_rad")
        camera_yaw_source = record.get("camera_yaw_source")
        if not isinstance(camera_yaw_source, str) or not camera_yaw_source:
            camera_yaw_value = None
        if facing_value is None:
            candidate = record.get("player_facing_rad")
            candidate_source = record.get("heading_source")
            if (
                isinstance(candidate, (int, float))
                and not isinstance(candidate, bool)
                and isinstance(candidate_source, str)
                and candidate_source
            ):
                facing_value = candidate
                facing_source = candidate_source
    except (
        FileNotFoundError, OSError, KeyError, TypeError, ValueError,
        json.JSONDecodeError,
    ):
        return None
    if (
        not isfinite(observed_s)
        or now_s < observed_s
        or now_s - observed_s > maximum_age_s
        or not isinstance(player, list)
        or len(player) not in {2, 3}
    ):
        return None
    try:
        world_x, world_y = float(player[0]), float(player[1])
        facing = None if facing_value is None else float(facing_value)
        camera_yaw = (
            None if camera_yaw_value is None else float(camera_yaw_value)
        )
    except (TypeError, ValueError):
        return None
    if not all(isfinite(value) for value in (world_x, world_y)):
        return None
    if facing is not None and not isfinite(facing):
        return None
    if camera_yaw is not None and not isfinite(camera_yaw):
        return None
    return (
        observed_s, world_x, world_y, facing,
        facing_source if facing is not None else None,
        1.0 if facing_source == EXACT_BODY_HEADING_SOURCE else None,
        camera_yaw,
    )


def _navigation_owns_capture(
    path: Path, *, now_wall_s: float, maximum_age_s: float = 5.0,
) -> bool:
    """Detect the startup gap before Movement Lab publishes its first pose."""

    try:
        record = _read_object(path)
        age_s = now_wall_s - path.stat().st_mtime
    except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError):
        return False
    return bool(
        0.0 <= age_s <= maximum_age_s
        and record.get("status") in {"STARTING", "RUNNING"}
    )


def _fresh_traversed_path(
    path: Path, *, now_s: float,
) -> tuple[tuple[float, float], ...]:
    try:
        record = _read_object(path)
        observed_s = float(record["observed_monotonic_s"])
        raw = record.get("traversed_path_world", [])
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isfinite(observed_s) or now_s - observed_s > 1.0 or not isinstance(raw, list):
        return ()
    points: list[tuple[float, float]] = []
    for point in raw[:4096]:
        if not isinstance(point, list) or len(point) != 2:
            return ()
        x, y = float(point[0]), float(point[1])
        if not isfinite(x) or not isfinite(y):
            return ()
        points.append((x, y))
    if len(points) <= VIEWER_TRAIL_MAX_POINTS:
        return tuple(points)
    # The 3D viewer projects every trail vertex onto terrain whenever the
    # sequence changes. Sending thousands of points five times per second can
    # starve its render loop and make the player arrow appear frozen even
    # though the pose stream is current. Preserve the whole journey with a
    # bounded, uniformly distributed diagnostic polyline.
    last_index = len(points) - 1
    selected_indices = {
        round(index * last_index / (VIEWER_TRAIL_MAX_POINTS - 1))
        for index in range(VIEWER_TRAIL_MAX_POINTS)
    }
    return tuple(points[index] for index in sorted(selected_indices))


def _fresh_awareness_segments(
    path: Path, *, now_s: float,
) -> tuple[
    tuple[ViewerSegment, ...],
    tuple[ViewerSegment, ...],
    tuple[ViewerSegment, ...],
]:
    empty: tuple[ViewerSegment, ...] = ()
    try:
        record = _read_object(path)
        observed_s = float(record["observed_monotonic_s"])
        awareness = record.get("local_static_awareness")
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return empty, empty, empty
    if (
        not isfinite(observed_s)
        or now_s - observed_s > 1.0
        or not isinstance(awareness, dict)
        or awareness.get("available") is not True
    ):
        return empty, empty, empty

    def segments(name: str, *, maximum: int) -> tuple[ViewerSegment, ...]:
        raw = awareness.get(name)
        if not isinstance(raw, list) or len(raw) > maximum:
            raise ValueError(f"viewer {name} are invalid")
        result: list[ViewerSegment] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(f"viewer {name} item is invalid")
            left = item.get("left")
            right = item.get("right")
            if (
                not isinstance(left, list) or len(left) != 3
                or not isinstance(right, list) or len(right) != 3
            ):
                raise ValueError(f"viewer {name} geometry is invalid")
            values = tuple(float(value) for value in (*left, *right))
            if not all(isfinite(value) for value in values):
                raise ValueError(f"viewer {name} geometry is non-finite")
            result.append(values)  # type: ignore[arg-type]
        return tuple(result)

    try:
        return (
            segments("wall_segments", maximum=128),
            segments("surface_transition_portals", maximum=64),
            segments("egress_portals", maximum=32),
        )
    except (TypeError, ValueError):
        return empty, empty, empty


def _fresh_conditional_boundary_segments(
    path: Path, *, now_s: float,
) -> tuple[ViewerSegment, ...]:
    try:
        record = _read_object(path)
        observed_s = float(record["observed_monotonic_s"])
        awareness = record.get("local_static_awareness")
        if not isinstance(awareness, dict):
            return ()
        conditional = awareness.get("conditional_traversal_frontier")
    except (
        FileNotFoundError, OSError, KeyError, TypeError, ValueError,
        json.JSONDecodeError,
    ):
        return ()
    if (
        not isfinite(observed_s)
        or now_s - observed_s > 1.0
        or not isinstance(conditional, dict)
        or conditional.get("requires_live_visible_confirmation") is not True
        or conditional.get("execution_authority") is not False
    ):
        return ()
    raw = conditional.get("boundary_segments")
    if not isinstance(raw, list) or len(raw) > 32:
        return ()
    result: list[ViewerSegment] = []
    try:
        for item in raw:
            if not isinstance(item, dict):
                return ()
            left = item.get("left")
            right = item.get("right")
            if (
                not isinstance(left, list) or len(left) != 3
                or not isinstance(right, list) or len(right) != 3
            ):
                return ()
            values = tuple(float(value) for value in (*left, *right))
            if not all(isfinite(value) for value in values):
                return ()
            result.append(values)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ()
    return tuple(result)


def bridge_state_text(
    *,
    sequence: int,
    observed_monotonic_s: float,
    world_x: float,
    world_y: float,
    facing_rad: float | None,
    facing_source: str | None = None,
    facing_confidence: float | None = None,
    camera_yaw_estimate_rad: float | None = None,
    corridor: tuple[tuple[float, float], ...],
    traversed_path: tuple[tuple[float, float], ...] = (),
    awareness_walls: tuple[ViewerSegment, ...] = (),
    awareness_transitions: tuple[ViewerSegment, ...] = (),
    awareness_egresses: tuple[ViewerSegment, ...] = (),
    conditional_boundaries: tuple[ViewerSegment, ...] = (),
    protocol_version: int = 2,
) -> str:
    if type(sequence) is not int or sequence < 1:
        raise ValueError("bridge sequence must be positive")
    scalars = (observed_monotonic_s, world_x, world_y)
    if not all(isfinite(value) for value in scalars):
        raise ValueError("bridge pose must be finite")
    if facing_rad is not None and not isfinite(facing_rad):
        raise ValueError("bridge facing must be finite")
    if (facing_rad is None) != (facing_source is None):
        raise ValueError("bridge facing source must match facing availability")
    if facing_source is not None and (
        not facing_source or any(character.isspace() for character in facing_source)
    ):
        raise ValueError("bridge facing source is invalid")
    if facing_confidence is not None and (
        facing_source is None
        or not isfinite(facing_confidence)
        or not 0.0 <= facing_confidence <= 1.0
    ):
        raise ValueError("bridge facing confidence is invalid")
    if (
        camera_yaw_estimate_rad is not None
        and not isfinite(camera_yaw_estimate_rad)
    ):
        raise ValueError("bridge camera yaw must be finite")
    if len(corridor) > 128 or any(
        not all(isfinite(value) for value in point) for point in corridor
    ):
        raise ValueError("bridge corridor is invalid")
    if protocol_version not in (2, 3, 4, 5):
        raise ValueError("bridge protocol version is invalid")
    if protocol_version == 2 and conditional_boundaries:
        raise ValueError("conditional boundaries require bridge protocol 3")
    if protocol_version < 4 and traversed_path:
        raise ValueError("traversed path requires bridge protocol 4")
    if protocol_version < 5 and camera_yaw_estimate_rad is not None:
        raise ValueError("camera yaw requires bridge protocol 5")
    if len(traversed_path) > 4096 or any(
        not all(isfinite(value) for value in point) for point in traversed_path
    ):
        raise ValueError("bridge traversed path is invalid")
    awareness_limits = (
        (awareness_walls, 128),
        (awareness_transitions, 64),
        (awareness_egresses, 32),
        (conditional_boundaries, 32),
    )
    if any(
        len(segments) > maximum
        or any(len(segment) != 6 or not all(isfinite(value) for value in segment)
               for segment in segments)
        for segments, maximum in awareness_limits
    ):
        raise ValueError("bridge awareness geometry is invalid")
    lines = [
        f"PA_NAV_VIEWER_STATE {protocol_version}",
        f"sequence {sequence}",
        f"observed {observed_monotonic_s:.9f}",
        f"pose {world_x:.6f} {world_y:.6f}",
        "facing none" if facing_rad is None else f"facing {facing_rad:.9f}",
    ]
    if protocol_version >= 5:
        lines.append(
            "camera_yaw none"
            if camera_yaw_estimate_rad is None
            else f"camera_yaw {camera_yaw_estimate_rad:.9f}"
        )
    lines.append(f"corridor {len(corridor)}")
    lines.extend(f"point {x:.6f} {y:.6f}" for x, y in corridor)
    lines.append(f"walls {len(awareness_walls)}")
    lines.extend(
        "wall " + " ".join(f"{value:.6f}" for value in segment)
        for segment in awareness_walls
    )
    lines.append(f"transitions {len(awareness_transitions)}")
    lines.extend(
        "transition " + " ".join(f"{value:.6f}" for value in segment)
        for segment in awareness_transitions
    )
    lines.append(f"egresses {len(awareness_egresses)}")
    lines.extend(
        "egress " + " ".join(f"{value:.6f}" for value in segment)
        for segment in awareness_egresses
    )
    if protocol_version >= 3:
        lines.append(f"conditional_boundaries {len(conditional_boundaries)}")
        lines.extend(
            "conditional_boundary "
            + " ".join(f"{value:.6f}" for value in segment)
            for segment in conditional_boundaries
        )
    if protocol_version >= 4:
        lines.append(f"trail {len(traversed_path)}")
        lines.extend(
            f"trail_point {x:.6f} {y:.6f}" for x, y in traversed_path
        )
    lines.append("end")
    # Compatibility metadata follows ``end``. The existing native viewer
    # deliberately stops after that token, while Python readers can retain
    # provenance instead of labelling every visible arrow as exact.
    lines.append(
        "facing_source none"
        if facing_source is None else f"facing_source {facing_source}"
    )
    lines.append(
        "facing_confidence none"
        if facing_confidence is None
        else f"facing_confidence {facing_confidence:.6f}"
    )
    return "\n".join(lines) + "\n"


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                # A Windows reader which opened just before an atomic rename
                # can briefly deny replacement. Keep the publisher bounded
                # and retry inside one 5 Hz frame budget.
                time.sleep(0.005 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _live_diagnostic_interval(*, continuity_enabled: bool) -> float:
    # Publishing/polling only: the observer retains its independent 1 s query gate.
    return 0.2 if continuity_enabled else 1.0


def _write_diagnostic(
    path: Path, *, status: str, sequence: int, detail: str | None = None,
    awareness_service_pid: int | None = None,
    awareness_queries: int | None = None,
    location_labels: dict[str, object] | None = None,
    owner_pid: int | None = None,
    spatial_sonar: dict[str, object] | None = None,
    spatial_sonar_error: str | None = None,
) -> None:
    _atomic_text(path, json.dumps({
        "record_type": "nav_viewer_live_bridge_status",
        "location_labels": location_labels,
        "spatial_sonar": spatial_sonar,
        "spatial_sonar_error": spatial_sonar_error,
        "owner_pid": owner_pid,
        "status": status,
        "sequence": sequence,
        "detail": detail,
        "awareness_service_pid": awareness_service_pid,
        "awareness_queries": awareness_queries,
        "observed_monotonic_s": time.monotonic(),
        "execution_authority": False,
    }, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")


def _session_binding_fingerprint(
    authorization_file: Path, receipt_file: Path,
) -> tuple[str, str]:
    """Identify one exact on-disk authorization/receipt generation."""
    return (
        hashlib.sha256(authorization_file.read_bytes()).hexdigest(),
        hashlib.sha256(receipt_file.read_bytes()).hexdigest(),
    )


def _open_pose_source(
    *, authorization_file: Path, receipt_file: Path,
) -> tuple[LiveCoordinatePoseSource, tuple[str, str]]:
    """Open a source only when both session files stay stable while binding."""
    last_error: Exception | None = None
    for _attempt in range(3):
        before = _session_binding_fingerprint(authorization_file, receipt_file)
        receipt = _read_object(receipt_file)
        source = LiveCoordinatePoseSource(
            authorization_file=authorization_file,
            receipt_file=receipt_file,
            receipt=receipt,
            session_id=f"session:nav-viewer-live:{uuid4()}",
            # The Control Center is a read-only viewer, so its map must keep
            # receiving pose data even when the operator foregrounds the
            # Center. Input-owning navigation still uses the default strict
            # foreground requirement. A foreground mismatch therefore
            # cannot grant or route any keyboard/mouse input.
            require_foreground_capture=False,
            observe_location=True,
        )
        try:
            source.open()
            after = _session_binding_fingerprint(authorization_file, receipt_file)
            if before == after:
                return source, after
        except Exception as error:
            last_error = error
        source.close()
    if last_error is not None:
        raise last_error
    raise RuntimeError("LAB session files changed repeatedly while binding")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish fresh read-only HUD pose to the external 3D nav viewer."
    )
    parser.add_argument(
        "--session-authorization-file", type=Path, default=DEFAULT_AUTHORIZATION,
    )
    parser.add_argument("--session-receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--diagnostic-file", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--movement-state", type=Path, default=DEFAULT_MOVEMENT_STATE)
    parser.add_argument(
        "--navigation-continuity-state",
        type=Path,
        default=DEFAULT_NAVIGATION_CONTINUITY_STATE,
    )
    parser.add_argument("--viewer-pid", type=int, required=True)
    parser.add_argument(
        "--expected-zone-index", type=int, choices=range(0, 65_536), default=25,
    )
    parser.add_argument("--map-id", type=int, choices=range(0, 65_536), default=0)
    parser.add_argument(
        "--zone-transform-catalog", type=Path,
        default=DEFAULT_ZONE_TRANSFORM_CATALOG,
    )
    parser.add_argument("--awareness-worker", type=Path)
    parser.add_argument("--spatial-sonar-profile", type=Path)
    parser.add_argument("--spatial-sonar-wmo-config", type=Path)
    parser.add_argument("--spatial-sonar-continuity", action="store_true")
    parser.add_argument("--awareness-nav-root", type=Path)
    parser.add_argument("--awareness-map-name", default="Azeroth")
    parser.add_argument("--initial-world-z", type=float)
    parser.add_argument("--target-hz", type=float, default=5.0)
    parser.add_argument(
        "--state-protocol", type=int, choices=(2, 3, 4, 5), default=2,
    )
    parser.add_argument(
        "--maximum-duration-s", type=float, default=0.0,
        help=(
            "Optional lifetime cap in seconds; zero keeps the read-only bridge "
            "alive exactly as long as its viewer."
        ),
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.viewer_pid < 1:
        raise SystemExit("--viewer-pid must be positive")
    if not 1.0 <= args.target_hz <= 10.0:
        raise SystemExit("--target-hz must be in [1, 10]")
    if args.maximum_duration_s != 0.0 and not 10.0 <= args.maximum_duration_s <= 86400.0:
        raise SystemExit("--maximum-duration-s must be zero or in [10, 86400]")
    awareness_values = (
        args.awareness_worker, args.awareness_nav_root, args.initial_world_z,
    )
    if any(value is not None for value in awareness_values) and not all(
        value is not None for value in awareness_values
    ):
        raise SystemExit(
            "awareness worker, nav root, and initial world Z must be supplied together"
        )
    source: LiveCoordinatePoseSource | None = None
    session_binding_fingerprint = _session_binding_fingerprint(
        args.session_authorization_file, args.session_receipt,
    )
    interval_s = 1.0 / args.target_hz
    started_s = time.monotonic()
    # Sequence identity must survive a bridge restart while MapViewer stays
    # open. A process-local counter restarts at one and the viewer correctly
    # rejects it as stale forever. Monotonic milliseconds are increasing for
    # the lifetime of the Windows boot and also make concurrent old bridges
    # harmless once a newer bridge publishes its first frame.
    sequence = time.monotonic_ns() // 1_000_000
    last_diagnostic_s = 0.0
    traversed_path: tuple[tuple[float, float], ...] = ()
    last_trail_refresh_s = float("-inf")
    awareness_probe = None
    sonar_observer = None
    if args.spatial_sonar_profile is not None:
        from spatial_sonar_observer import SpatialSonarObserver
        sonar_observer = SpatialSonarObserver(
            args.spatial_sonar_profile, wmo_bundle_spec=args.spatial_sonar_wmo_config,
            vertical_continuity=args.spatial_sonar_continuity,
        )
    transform = _load_zone_transform(
        args.zone_transform_catalog,
        map_id=args.map_id,
        zone_index=args.expected_zone_index,
    )
    if all(value is not None for value in awareness_values):
        awareness_probe = AsyncLocalAwarenessProbe(
            worker=args.awareness_worker,
            nav_root=args.awareness_nav_root,
            map_name=str(args.awareness_map_name),
            initial_z=float(args.initial_world_z),
        )
    _write_diagnostic(
        args.diagnostic_file,
        status="OPEN",
        sequence=sequence,
        awareness_service_pid=(
            awareness_probe.service_pid if awareness_probe is not None else None
        ),
        awareness_queries=(
            awareness_probe.query_count if awareness_probe is not None else None
        ),
    )
    try:
        while (
            _viewer_is_alive(args.viewer_pid)
            and (
                args.maximum_duration_s == 0.0
                or time.monotonic() - started_s <= args.maximum_duration_s
            )
        ):
            iteration_started = time.monotonic()
            try:
                now_s = time.monotonic()
                movement_pose = _fresh_movement_pose(
                    args.movement_state, now_s=now_s,
                )
                if movement_pose is not None:
                    (
                        observed_s, world_x, world_y, facing_rad,
                        facing_source, facing_confidence,
                        camera_yaw_estimate_rad,
                    ) = movement_pose
                else:
                    if _navigation_owns_capture(
                        args.navigation_continuity_state,
                        now_wall_s=time.time(),
                    ):
                        if source is not None:
                            source.close()
                            source = None
                        # The navigator has declared ownership but has not yet
                        # published its first pose. Do not create a second
                        # DXGI stream in that narrow startup interval.
                        time.sleep(min(0.10, interval_s))
                        continue
                    if source is None:
                        source, session_binding_fingerprint = _open_pose_source(
                            authorization_file=args.session_authorization_file,
                            receipt_file=args.session_receipt,
                        )
                    observation = source.next_observation()
                    normalized_x, normalized_y, world_x, world_y = _position(
                        observation,
                        expected_zone_index=args.expected_zone_index,
                        transform=transform,
                        expected_map_id=args.map_id,
                    )
                    del normalized_x, normalized_y
                    timing = observation.get("timing")
                    position = observation.get("position")
                    if not isinstance(timing, dict) or not isinstance(position, dict):
                        raise RuntimeError("live bridge observation is incomplete")
                    observed_s = float(timing["observed_monotonic_s"])
                    facing = position.get("facing_rad")
                    facing_rad = (
                        float(facing)
                        if facing is not None
                        else None
                    )
                    facing_source = (
                        source.latest_facing_source
                        if facing_rad is not None else None
                    )
                    facing_confidence = (
                        source.latest_facing_confidence
                        if facing_rad is not None else None
                    )
                    camera_yaw_estimate_rad = None
                corridor = _fresh_corridor(args.movement_state, now_s=now_s)
                if (
                    now_s - last_trail_refresh_s
                    >= VIEWER_TRAIL_REFRESH_INTERVAL_S
                ):
                    traversed_path = _fresh_traversed_path(
                        args.movement_state, now_s=now_s,
                    )
                    last_trail_refresh_s = now_s
                awareness_walls, awareness_transitions, awareness_egresses = (
                    _fresh_awareness_segments(args.movement_state, now_s=now_s)
                )
                if awareness_probe is not None:
                    z_hint = _movement_floor_hint(
                        args.movement_state,
                        world_x=world_x,
                        world_y=world_y,
                        fallback_z=awareness_probe.z_hint,
                    )
                    live_awareness = awareness_probe.poll(
                        world_x=world_x,
                        world_y=world_y,
                        now_s=now_s,
                        z_hint=z_hint,
                    )
                    if live_awareness is not None:
                        viewer_awareness = _viewer_awareness_frame(live_awareness)
                        awareness_walls = viewer_awareness.walls
                        awareness_transitions = viewer_awareness.transitions
                        awareness_egresses = viewer_awareness.egresses
                conditional_boundaries = (
                    _fresh_conditional_boundary_segments(
                        args.movement_state, now_s=time.monotonic(),
                    )
                    if args.state_protocol >= 3 else ()
                )
                next_sequence = sequence + 1
                state_text = bridge_state_text(
                    sequence=next_sequence,
                    observed_monotonic_s=observed_s,
                    world_x=world_x,
                    world_y=world_y,
                    facing_rad=facing_rad,
                    facing_source=facing_source,
                    facing_confidence=facing_confidence,
                    camera_yaw_estimate_rad=camera_yaw_estimate_rad,
                    corridor=corridor,
                    traversed_path=traversed_path,
                    awareness_walls=awareness_walls,
                    awareness_transitions=awareness_transitions,
                    awareness_egresses=awareness_egresses,
                    conditional_boundaries=conditional_boundaries,
                    protocol_version=args.state_protocol,
                )
                _atomic_text(args.state_file, state_text)
            except (
                ClientVisibleStateError,
                NoFreshCaptureFrameError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                WindowSelectionError,
            ) as initial_error:
                diagnostic_error: Exception = initial_error
                try:
                    current_session_fingerprint = _session_binding_fingerprint(
                        args.session_authorization_file, args.session_receipt,
                    )
                except OSError:
                    current_session_fingerprint = session_binding_fingerprint
                if current_session_fingerprint != session_binding_fingerprint:
                    if source is not None:
                        source.close()
                        source = None
                    try:
                        source, session_binding_fingerprint = _open_pose_source(
                            authorization_file=args.session_authorization_file,
                            receipt_file=args.session_receipt,
                        )
                    except Exception as rebind_error:
                        diagnostic_error = rebind_error
                    else:
                        _write_diagnostic(
                            args.diagnostic_file,
                            status="SESSION_REBOUND",
                            sequence=sequence,
                            detail="authorization and launch receipt rotated together",
                            awareness_service_pid=(
                                awareness_probe.service_pid
                                if awareness_probe is not None else None
                            ),
                            awareness_queries=(
                                awareness_probe.query_count
                                if awareness_probe is not None else None
                            ),
                        )
                        last_diagnostic_s = time.monotonic()
                        continue
                now_s = time.monotonic()
                if now_s - last_diagnostic_s >= 0.5:
                    _write_diagnostic(
                        args.diagnostic_file,
                        status="PAUSED_VISIBLE_STATE",
                        sequence=sequence,
                        detail=(
                            f"{type(diagnostic_error).__name__}: "
                            f"{diagnostic_error}"
                        ),
                        awareness_service_pid=(
                            awareness_probe.service_pid
                            if awareness_probe is not None else None
                        ),
                        awareness_queries=(
                            awareness_probe.query_count
                            if awareness_probe is not None else None
                        ),
                    )
                    last_diagnostic_s = now_s
                time.sleep(min(0.25, interval_s))
                continue
            sequence = next_sequence
            now_s = time.monotonic()
            if now_s - last_diagnostic_s >= _live_diagnostic_interval(
                continuity_enabled=args.spatial_sonar_continuity
            ):
                location_labels = (
                    getattr(source, "latest_location_labels", None)
                    if movement_pose is None else None
                )
                if movement_pose is not None:
                    try:
                        location_labels = _read_object(args.movement_state).get("location_labels")
                    except (OSError, ValueError, RuntimeError):
                        location_labels = None
                _write_diagnostic(
                    args.diagnostic_file,
                    status="LIVE",
                    location_labels=location_labels,
                    spatial_sonar=(sonar_observer.poll(
                        labels=location_labels, map_id=args.map_id,
                        xy=(world_x, world_y), pose_s=observed_s, now_s=now_s,
                    ) if sonar_observer is not None else None),
                    owner_pid=args.viewer_pid,
                    spatial_sonar_error=(sonar_observer.last_error if sonar_observer else None),
                    sequence=sequence,
                    awareness_service_pid=(
                        awareness_probe.service_pid
                        if awareness_probe is not None else None
                    ),
                    awareness_queries=(
                        awareness_probe.query_count
                        if awareness_probe is not None else None
                    ),
                )
                last_diagnostic_s = now_s
            remaining = interval_s - (time.monotonic() - iteration_started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        if source is not None:
            source.close()
        if awareness_probe is not None:
            awareness_probe.close()
        if sonar_observer is not None:
            sonar_observer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
