from __future__ import annotations

from collections import Counter
from math import hypot
from typing import Any, Iterable, Mapping, Sequence

from .manual_path_recording import ManualPathRecording


KEY_NAMES = {
    0x20: "JUMP",
    0x41: "STRAFE_LEFT",
    0x44: "STRAFE_RIGHT",
    0x57: "MOVE_FORWARD",
    0x90: "AUTORUN",
}


def _event_time(record: Mapping[str, Any]) -> float:
    value = float(record["elapsed_s"])
    if value < 0.0:
        raise ValueError("demonstration event time is invalid")
    return value


def _hold_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    identity_field: str,
    identity: object,
    duration_s: float,
) -> dict[str, object]:
    selected = [
        record
        for record in records
        if record.get("kind") == kind
        and isinstance(record.get("payload"), Mapping)
        and record["payload"].get(identity_field) == identity
    ]
    if not selected:
        return {
            "press_count": 0,
            "hold_seconds": 0.0,
            "started_held": False,
            "ended_held": False,
        }
    started_held = selected[0]["payload"].get("state") == "UP"
    held = started_held
    held_since = 0.0 if held else None
    intervals: list[tuple[float, float]] = []
    press_count = 0
    for record in selected:
        state = record["payload"].get("state")
        timestamp = _event_time(record)
        if state == "DOWN" and not held:
            held = True
            held_since = timestamp
            press_count += 1
        elif state == "UP" and held:
            intervals.append((float(held_since), timestamp))
            held = False
            held_since = None
    if held:
        intervals.append((float(held_since), duration_s))
    return {
        "press_count": press_count,
        "hold_seconds": sum(stop - start for start, stop in intervals),
        "started_held": started_held,
        "ended_held": held,
    }


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    stop: tuple[float, float],
) -> float:
    dx, dy = stop[0] - start[0], stop[1] - start[1]
    denominator = dx * dx + dy * dy
    parameter = 0.0 if denominator == 0.0 else (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / denominator
    parameter = max(0.0, min(1.0, parameter))
    projection = start[0] + parameter * dx, start[1] + parameter * dy
    return hypot(point[0] - projection[0], point[1] - projection[1])


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def planned_route_conformity(
    recording: ManualPathRecording,
    planned_points: Sequence[tuple[float, float]],
) -> dict[str, object]:
    if len(planned_points) < 2 or not recording.vertices:
        raise ValueError("route conformity requires a path and a planned polyline")
    distances = [
        min(
            _distance_to_segment((vertex.x, vertex.y), start, stop)
            for start, stop in zip(planned_points, planned_points[1:])
        )
        for vertex in recording.vertices
    ]
    return {
        "planned_point_count": len(planned_points),
        "mean_cross_track_world": sum(distances) / len(distances),
        "median_cross_track_world": _quantile(distances, 0.50),
        "p90_cross_track_world": _quantile(distances, 0.90),
        "p95_cross_track_world": _quantile(distances, 0.95),
        "maximum_cross_track_world": max(distances),
        "fraction_over_10_world": sum(value > 10.0 for value in distances)
        / len(distances),
    }


def analyze_operator_demonstration(
    records: Iterable[Mapping[str, Any]],
    recording: ManualPathRecording,
) -> dict[str, object]:
    events = tuple(records)
    if not events or events[0].get("kind") != "SESSION_START":
        raise ValueError("demonstration timeline has no session start")
    sequences = [int(record["sequence"]) for record in events]
    if sequences != list(range(len(events))):
        raise ValueError("demonstration timeline sequence is discontinuous")
    duration_s = _event_time(events[-1])
    event_counts = Counter(str(record.get("kind")) for record in events)
    controls = {
        name: _hold_summary(
            events,
            kind="KEY",
            identity_field="virtual_key",
            identity=virtual_key,
            duration_s=duration_s,
        )
        for virtual_key, name in KEY_NAMES.items()
    }
    right_mouse = _hold_summary(
        events,
        kind="MOUSE_BUTTON",
        identity_field="button",
        identity="RIGHT",
        duration_s=duration_s,
    )
    mouse_moves = [
        record
        for record in events
        if record.get("kind") == "MOUSE_MOVE"
        and isinstance(record.get("payload"), Mapping)
    ]
    cursor_warp_count = sum(
        abs(int(record["payload"].get("delta_x", 0))) > 200
        or abs(int(record["payload"].get("delta_y", 0))) > 200
        for record in mouse_moves
    )
    vertices = recording.vertices
    path_duration_s = (
        0.0
        if len(vertices) < 2
        else vertices[-1].observed_monotonic_s
        - vertices[0].observed_monotonic_s
    )
    return {
        "schema_version": "1.0",
        "record_type": "operator_movement_demonstration_analysis",
        "recording_id": recording.recording_id,
        "interpretation": "BEHAVIOR_REFERENCE_NOT_EXECUTABLE_ROUTE",
        "timeline": {
            "duration_seconds": duration_s,
            "event_count": len(events),
            "event_counts": dict(sorted(event_counts.items())),
        },
        "path": {
            "status": recording.status,
            "vertex_count": len(vertices),
            "distance_world": recording.distance_world,
            "duration_seconds": path_duration_s,
            "mean_speed_world_per_second": (
                0.0 if path_duration_s <= 0.0 else recording.distance_world / path_duration_s
            ),
            "start_world": None if not vertices else [vertices[0].x, vertices[0].y],
            "end_world": None if not vertices else [vertices[-1].x, vertices[-1].y],
        },
        "controls": {
            **controls,
            "MOUSE_LOOK_RIGHT": right_mouse,
        },
        "mouse_measurement": {
            "event_count": len(mouse_moves),
            "cursor_warp_count": cursor_warp_count,
            "relative_delta_quality": (
                "CURSOR_RECENTER_CONTAMINATED"
                if cursor_warp_count
                else "NO_CURSOR_WARP_DETECTED"
            ),
        },
        "execution_authority": False,
    }
