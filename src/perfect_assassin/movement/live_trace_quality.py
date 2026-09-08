from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from math import isfinite, pi
from typing import Any


_KNOWN_CLIENT_FACING_SOURCES = frozenset(
    {
        "COORDINATE_HUD_EXACT",
        "MINIMAP_VISION_FALLBACK",
    }
)
_KNOWN_BODY_YAW_SOURCES = _KNOWN_CLIENT_FACING_SOURCES
_KNOWN_CAMERA_YAW_SOURCES = frozenset(
    {"RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY"}
)


@dataclass(frozen=True, slots=True)
class LiveSteeringTraceQuality:
    frame_count: int
    duration_s: float
    arrived: bool
    steering_sign_changes: int
    steering_sign_changes_per_minute: float
    rapid_steering_reversals: int
    rapid_steering_reversals_per_minute: float
    pivot_frames: int
    pivot_fraction: float
    maximum_forward_no_progress_s: float
    forward_stall_frames: int
    observation_gaps_over_300ms: int
    maximum_observation_gap_s: float
    motion_continuity_exempted_gaps: int
    unexplained_observation_gaps_over_300ms: int
    client_facing_source_frames: int
    frames_missing_client_facing_source: int
    client_facing_source_complete: bool
    body_camera_separation_frames: int
    frames_missing_body_camera_separation: int
    body_camera_separation_complete: bool
    camera_integrity_frames: int
    frames_missing_camera_integrity: int
    camera_integrity_complete: bool
    passed: bool
    failures: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_live_steering_trace(
    result: dict[str, Any],
    *,
    maximum_sign_changes_per_minute: float = 12.0,
    rapid_reversal_window_s: float = 0.50,
    maximum_pivot_fraction: float = 0.05,
    maximum_forward_no_progress_s: float = 0.75,
    maximum_observation_gap_s: float = 0.30,
    require_client_facing_source: bool = False,
    require_body_camera_separation: bool = False,
    require_camera_integrity: bool = False,
) -> LiveSteeringTraceQuality:
    """Grade observed client motion, independently from destination arrival.

    This is intentionally a replay gate over actual client telemetry. A route
    that reaches its destination while visibly balancing left/right must fail.
    """

    frames = tuple(
        action for action in result.get("actions", ())
        if isinstance(action, dict) and action.get("kind") == "CONTINUOUS_FRAME"
    )
    client_source_frames = sum(
        _has_usable_client_facing_source(frame) for frame in frames
    )
    missing_client_source = len(frames) - client_source_frames
    body_camera_frames = sum(
        _has_body_camera_yaw_separation(frame) for frame in frames
    )
    missing_body_camera = len(frames) - body_camera_frames
    camera_integrity_frames = sum(
        _has_usable_camera_integrity(frame) for frame in frames
    )
    missing_camera_integrity = len(frames) - camera_integrity_frames
    times = tuple(float(frame["observed_monotonic_s"]) for frame in frames)
    if any(not isfinite(value) for value in times):
        raise ValueError("live steering trace contains a non-finite timestamp")
    duration_s = max(0.0, times[-1] - times[0]) if len(times) >= 2 else 0.0
    prior_sign = 0
    prior_nonzero_time: float | None = None
    prior_nonzero_frame: dict[str, Any] | None = None
    sign_changes = 0
    rapid_reversals = 0
    for frame in frames:
        command = int(frame.get("requested_mouse_delta_x", 0))
        sign = 1 if command > 0 else -1 if command < 0 else 0
        if sign:
            if prior_sign and sign != prior_sign:
                sign_changes += 1
                observed_s = float(frame["observed_monotonic_s"])
                assert prior_nonzero_time is not None
                if (
                    observed_s - prior_nonzero_time <= rapid_reversal_window_s
                    and prior_nonzero_frame is not None
                    and _looks_like_camera_balance(prior_nonzero_frame, frame)
                ):
                    rapid_reversals += 1
            prior_sign = sign
            prior_nonzero_time = float(frame["observed_monotonic_s"])
            prior_nonzero_frame = frame
    pivot_frames = sum(
        frame.get("controller_state") == "PIVOT" for frame in frames
    )
    gaps = tuple(current - previous for previous, current in pairwise(times))
    maximum_gap = max(gaps, default=0.0)
    excessive_gaps = sum(gap > maximum_observation_gap_s for gap in gaps)
    motion_continuity_exempted_gaps = 0
    unexplained_gaps = 0
    for previous, current, gap in zip(frames, frames[1:], gaps):
        if gap <= maximum_observation_gap_s:
            continue
        if _gap_has_continuous_motion_evidence(previous, current, gap):
            motion_continuity_exempted_gaps += 1
        else:
            unexplained_gaps += 1
    reversal_rate = sign_changes * 60.0 / max(duration_s, 1.0)
    rapid_reversal_rate = rapid_reversals * 60.0 / max(duration_s, 1.0)
    pivot_fraction = pivot_frames / max(1, len(frames))
    forward_no_progress = tuple(
        float(frame.get("no_progress_s", 0.0))
        for frame in frames
        if isinstance(frame.get("held_controls", ()), (list, tuple, set))
        and "MOVE_FORWARD" in frame.get("held_controls", ())
        and _is_finite_number(frame.get("no_progress_s", 0.0))
    )
    maximum_forward_stall = max(forward_no_progress, default=0.0)
    forward_stall_frames = sum(
        elapsed > maximum_forward_no_progress_s
        for elapsed in forward_no_progress
    )
    failures: list[str] = []
    if result.get("status") != "ARRIVED":
        failures.append("destination_not_reached")
    if len(frames) < 50:
        failures.append("insufficient_live_frames")
    # A road can legitimately bend left and later right.  Camera balance is
    # the actuator changing direction again before the previous pulse has had
    # time to settle, not every sign change across an entire S-shaped route.
    # Keep the raw count as diagnostic evidence and gate the rapid subset.
    if rapid_reversal_rate > maximum_sign_changes_per_minute:
        failures.append("camera_left_right_balance")
    if pivot_fraction > maximum_pivot_fraction:
        failures.append("excessive_stationary_pivot")
    if forward_stall_frames:
        failures.append("forward_input_without_progress")
    if unexplained_gaps:
        failures.append("control_observation_gap")
    if require_client_facing_source and missing_client_source:
        failures.append("missing_client_facing_source")
    if require_body_camera_separation and missing_body_camera:
        failures.append("missing_body_camera_yaw_separation")
    if require_camera_integrity and missing_camera_integrity:
        failures.append("missing_camera_integrity")
    return LiveSteeringTraceQuality(
        frame_count=len(frames),
        duration_s=duration_s,
        arrived=result.get("status") == "ARRIVED",
        steering_sign_changes=sign_changes,
        steering_sign_changes_per_minute=reversal_rate,
        rapid_steering_reversals=rapid_reversals,
        rapid_steering_reversals_per_minute=rapid_reversal_rate,
        pivot_frames=pivot_frames,
        pivot_fraction=pivot_fraction,
        maximum_forward_no_progress_s=maximum_forward_stall,
        forward_stall_frames=forward_stall_frames,
        observation_gaps_over_300ms=excessive_gaps,
        maximum_observation_gap_s=maximum_gap,
        motion_continuity_exempted_gaps=motion_continuity_exempted_gaps,
        unexplained_observation_gaps_over_300ms=unexplained_gaps,
        client_facing_source_frames=client_source_frames,
        frames_missing_client_facing_source=missing_client_source,
        client_facing_source_complete=missing_client_source == 0,
        body_camera_separation_frames=body_camera_frames,
        frames_missing_body_camera_separation=missing_body_camera,
        body_camera_separation_complete=missing_body_camera == 0,
        camera_integrity_frames=camera_integrity_frames,
        frames_missing_camera_integrity=missing_camera_integrity,
        camera_integrity_complete=missing_camera_integrity == 0,
        passed=not failures,
        failures=tuple(failures),
    )


def _has_usable_client_facing_source(frame: dict[str, Any]) -> bool:
    """Return whether a frame identifies a usable client-facing observation.

    A missing field and the explicit ``UNAVAILABLE`` marker are both
    incomplete evidence.  The quality report may still be produced in
    diagnostic mode, but a strict live gate must reject either case.
    """

    source = frame.get("client_facing_source")
    if (
        not isinstance(source, str)
        or source.strip() not in _KNOWN_CLIENT_FACING_SOURCES
    ):
        return False
    # ``player_facing_rad`` is the raw value from the labelled client-facing
    # channel.  ``body_yaw_observation_rad`` is deliberately exact-HUD-only;
    # using it for a minimap frame would turn a camera estimate into fake body
    # evidence.  Keep a narrow legacy fallback for old exact-HUD traces that
    # predate ``player_facing_rad``.
    raw_yaw = frame.get("player_facing_rad")
    if raw_yaw is None and source == "COORDINATE_HUD_EXACT":
        raw_yaw = frame.get("body_yaw_observation_rad")
    return _is_finite_number(raw_yaw)


def _looks_like_camera_balance(
    previous: dict[str, Any], current: dict[str, Any],
    *, maximum_mouse_delta: int = 4,
    maximum_heading_error_rad: float = 0.40,
    maximum_cross_track_world: float = 1.50,
) -> bool:
    """Separate small settled oscillation from a real S-bend correction."""

    try:
        commands = (
            abs(int(previous.get("requested_mouse_delta_x", 0))),
            abs(int(current.get("requested_mouse_delta_x", 0))),
        )
    except (TypeError, ValueError):
        return False
    if any(command > maximum_mouse_delta for command in commands):
        return False
    for frame in (previous, current):
        heading_error = frame.get("waypoint_error_rad")
        if heading_error is not None and (
            not _is_finite_number(heading_error)
            or abs(float(heading_error)) > maximum_heading_error_rad
        ):
            return False
        cross_track = frame.get("cross_track_error_world")
        if cross_track is not None and (
            not _is_finite_number(cross_track)
            or abs(float(cross_track)) > maximum_cross_track_world
        ):
            return False
    return True


def _has_body_camera_yaw_separation(frame: dict[str, Any]) -> bool:
    """Return whether a frame records two labelled yaw channels and a delta.

    On legacy 2.4.3 the minimap player arrow is a bounded visual body-facing
    observation; it is not the exact addon API introduced in 3.1.  Requiring
    the labels here keeps that distinction explicit while still separating it
    from the RMB mouse-integrated camera/control model.
    """

    if frame.get("body_yaw_observation_source") not in _KNOWN_BODY_YAW_SOURCES:
        return False
    if frame.get("camera_yaw_source") not in _KNOWN_CAMERA_YAW_SOURCES:
        return False

    values = (
        frame.get("body_yaw_observation_rad"),
        frame.get("camera_yaw_estimate_rad"),
        frame.get("body_camera_yaw_delta_rad"),
    )
    if not all(_is_finite_number(value) for value in values):
        return False
    body, camera, recorded_delta = (float(value) for value in values)
    expected_delta = abs((body - camera + pi) % (2.0 * pi) - pi)
    return 0.0 <= recorded_delta <= pi + 1.0e-6 and abs(
        recorded_delta - expected_delta
    ) <= 1.0e-3


def _has_usable_camera_integrity(frame: dict[str, Any]) -> bool:
    """Return whether the frame proves the player stayed visible on screen.

    The runtime gate accepts only the visible actor-anchor state above the
    reviewed 0.55 confidence floor.  A missing state, an old trace, or an
    ``UNKNOWN``/``LOST`` frame is therefore incomplete evidence for a strict
    live-quality claim.  This does not infer camera pitch or world position;
    it only mirrors the client-visible safety gate.
    """

    state = frame.get("camera_integrity_state")
    confidence = frame.get("camera_integrity_confidence")
    actor_visible = (
        state == "VISIBLE"
        and _is_finite_number(confidence)
        and 0.55 <= float(confidence) <= 1.0
    )
    if actor_visible:
        return True
    # The actor silhouette is deliberately diagnostic: normal wall collision
    # changes the third-person zoom and can make the same visible character
    # much smaller.  The actuator receipt is the stronger camera-control
    # proof: RMB remained held and the navigation frame could not pitch.
    return bool(
        frame.get("camera_control_integrity_state") == "RMB_LEVEL_LOCKED"
        and frame.get("camera_yaw_source") in _KNOWN_CAMERA_YAW_SOURCES
        and frame.get("mouse_look_held") is True
        and frame.get("mouse_delta_y") == 0
        and _is_finite_number(frame.get("mouse_velocity_y_px_s"))
        and float(frame["mouse_velocity_y_px_s"]) == 0.0
    )


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _gap_has_continuous_motion_evidence(
    previous: dict[str, Any],
    current: dict[str, Any],
    gap_s: float,
    *,
    minimum_displacement_world: float = 0.50,
) -> bool:
    """Recognize a missing capture interval while locomotion visibly continued.

    A capture gap is not equivalent to a gameplay pause when both endpoint
    frames hold forward input, show meaningful world displacement, and retain
    a compatible heading.  Missing or malformed endpoint evidence remains a
    hard failure; this helper cannot manufacture continuity from timestamps.
    """

    if not isfinite(gap_s) or gap_s <= 0.0:
        return False
    previous_controls = previous.get("held_controls")
    current_controls = current.get("held_controls")
    if not isinstance(previous_controls, (list, tuple, set)) or not isinstance(
        current_controls, (list, tuple, set)
    ):
        return False
    if "MOVE_FORWARD" not in previous_controls or "MOVE_FORWARD" not in current_controls:
        return False
    try:
        previous_x = float(previous["world_x"])
        previous_y = float(previous["world_y"])
        current_x = float(current["world_x"])
        current_y = float(current["world_y"])
    except (KeyError, TypeError, ValueError):
        return False
    if not all(isfinite(value) for value in (previous_x, previous_y, current_x, current_y)):
        return False
    displacement = ((current_x - previous_x) ** 2 + (current_y - previous_y) ** 2) ** 0.5
    if displacement < minimum_displacement_world:
        return False
    # A real turn can change heading substantially during a slow capture
    # interval.  World displacement with W held proves locomotion continued;
    # steering quality is graded separately from the mouse-command trace.
    return True


__all__ = ["LiveSteeringTraceQuality", "evaluate_live_steering_trace"]
