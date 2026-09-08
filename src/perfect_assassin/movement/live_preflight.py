"""Read-only readiness checks for one client-visible movement observation.

The movement planner can be correct while the live client observation is
missing, stale, or pointed at a wall.  This module turns that distinction into
one small, versioned diagnostic record.  It never reads a client, sends input,
uses server truth, or grants execution authority.
"""

from __future__ import annotations

from math import isfinite
from typing import Mapping, Sequence

from perfect_assassin.movement.camera_integrity import assess_camera_integrity
from perfect_assassin.movement.heading_integrity import (
    EXACT_CLIENT_FACING_SOURCE,
    MINIMAP_CLIENT_FACING_SOURCE,
    assess_heading_integrity,
    is_current_visual_heading,
)


LIVE_PREFLIGHT_RECORD_TYPE = "live_observation_preflight"
LIVE_PREFLIGHT_SCHEMA_VERSION = "0.1"
DEFAULT_MAXIMUM_OBSERVATION_AGE_MS = 295.0
MAX_EXACT_BODY_HEADING_DISAGREEMENT_RAD = 0.02
_CAPTURE_ORIGINS = frozenset({"window_capture", "replay_fixture"})


def build_live_preflight_record(
    *,
    observation: Mapping[str, object] | None,
    camera_integrity: Mapping[str, object] | None,
    heading_rad: float | None,
    heading_source: str | None,
    client_facing_source: str | None,
    now_monotonic_s: float,
    capture_latency_ms: float | None,
    observation_latency_ms: float | None,
    foreground_matches_target: bool | None,
    evidence_refs: Sequence[str],
    capture_origin: str = "window_capture",
    maximum_observation_age_ms: float = DEFAULT_MAXIMUM_OBSERVATION_AGE_MS,
    require_exact_body_heading: bool = False,
    require_visible_player_anchor: bool = True,
) -> dict[str, object]:
    """Build a fail-closed preflight record from one fresh observation.

    ``foreground_matches_target`` is supplied by the input boundary's
    read-only hot check.  A ``None`` value is deliberately a rejection: a
    preflight must distinguish "checked and good" from "not checked".
    """

    if capture_origin not in _CAPTURE_ORIGINS:
        raise ValueError("preflight capture origin is invalid")
    if not isinstance(require_exact_body_heading, bool):
        raise ValueError("preflight exact-body-heading flag is invalid")
    if not isinstance(require_visible_player_anchor, bool):
        raise ValueError("preflight player-anchor flag is invalid")
    if (
        isinstance(maximum_observation_age_ms, bool)
        or not isinstance(maximum_observation_age_ms, (int, float))
        or not isfinite(float(maximum_observation_age_ms))
        or not 1.0 <= float(maximum_observation_age_ms) <= 5_000.0
    ):
        raise ValueError("preflight observation-age bound is invalid")
    refs = _validate_evidence_refs(evidence_refs)

    reasons: list[str] = []
    position: Mapping[str, object] | None = None
    timing: Mapping[str, object] | None = None
    observed_s: float | None = None
    if not isinstance(observation, Mapping):
        reasons.append("observation_missing")
    else:
        if observation.get("tracking_state") != "VALID":
            reasons.append("coordinate_observation_not_valid")
        candidate_position = observation.get("position")
        if isinstance(candidate_position, Mapping):
            position = candidate_position
        else:
            reasons.append("position_missing")
        candidate_timing = observation.get("timing")
        if isinstance(candidate_timing, Mapping):
            timing = candidate_timing
            candidate_observed = candidate_timing.get("observed_monotonic_s")
            if _finite_nonnegative(candidate_observed):
                observed_s = float(candidate_observed)
            else:
                reasons.append("observation_clock_missing_or_invalid")
        else:
            reasons.append("observation_timing_missing")

    if position is not None:
        if not _finite_normalized(position.get("x")) or not _finite_normalized(
            position.get("y")
        ):
            reasons.append("position_xy_missing_or_invalid")

    now_valid = _finite_nonnegative(now_monotonic_s)
    if not now_valid:
        reasons.append("preflight_clock_invalid")
    observation_age_ms: float | None = None
    if now_valid and observed_s is not None:
        observation_age_ms = (float(now_monotonic_s) - observed_s) * 1000.0
        if not isfinite(observation_age_ms) or observation_age_ms < 0.0:
            reasons.append("observation_clock_reversed")
            observation_age_ms = None
        elif observation_age_ms > float(maximum_observation_age_ms):
            reasons.append("observation_too_old")

    capture_latency_valid = _finite_nonnegative(capture_latency_ms)
    if not capture_latency_valid:
        reasons.append("capture_latency_missing_or_invalid")
    observation_latency_valid = _finite_nonnegative(observation_latency_ms)
    if not observation_latency_valid:
        reasons.append("observation_latency_missing_or_invalid")

    camera_decision = assess_camera_integrity(
        camera_integrity,
        require_visible_anchor=require_visible_player_anchor,
    )
    if not camera_decision.allow_control:
        reasons.append(f"camera_{camera_decision.reason}")

    normalized_heading_source = (
        heading_source if isinstance(heading_source, str) else "UNAVAILABLE"
    )
    normalized_client_source = (
        client_facing_source
        if isinstance(client_facing_source, str)
        else "UNAVAILABLE"
    )
    body_yaw = _body_yaw_from_exact_source(
        position,
        client_facing_source=normalized_client_source,
    )
    camera_yaw = _finite_value(heading_rad)
    current_heading_visual = is_current_visual_heading(
        heading_source=normalized_heading_source,
        client_facing_source=normalized_client_source,
    )
    heading_decision = assess_heading_integrity(
        heading_rad=camera_yaw,
        heading_source=normalized_heading_source,
        client_facing_source=normalized_client_source,
        observed_monotonic_s=(0.0 if observed_s is None else observed_s),
        last_visible_observed_s=(
            observed_s if current_heading_visual else None
        ),
    )
    if not heading_decision.allow_control or not current_heading_visual:
        reasons.append("heading_not_current_visual")
    if require_exact_body_heading and (
        normalized_client_source != EXACT_CLIENT_FACING_SOURCE
        or normalized_heading_source != EXACT_CLIENT_FACING_SOURCE
        or body_yaw is None
    ):
        reasons.append("exact_body_heading_missing")

    if foreground_matches_target is not True:
        reasons.append(
            "foreground_target_not_verified"
            if foreground_matches_target is None
            else "foreground_target_mismatch"
        )

    body_camera_delta = _body_camera_delta(body_yaw, camera_yaw)
    if (
        require_exact_body_heading
        and body_camera_delta is not None
        and body_camera_delta > MAX_EXACT_BODY_HEADING_DISAGREEMENT_RAD
    ):
        reasons.append("exact_body_heading_disagreement")
    camera_confidence = float(camera_decision.confidence)
    ready = not reasons
    return {
        "record_type": LIVE_PREFLIGHT_RECORD_TYPE,
        "schema_version": LIVE_PREFLIGHT_SCHEMA_VERSION,
        "status": "READY" if ready else "REJECTED",
        "ready": ready,
        "reasons": reasons,
        "observed_monotonic_s": observed_s,
        "now_monotonic_s": float(now_monotonic_s)
        if now_valid
        else None,
        "observation_age_ms": observation_age_ms,
        "maximum_observation_age_ms": float(maximum_observation_age_ms),
        "capture_latency_ms": (
            float(capture_latency_ms) if capture_latency_valid else None
        ),
        "observation_latency_ms": (
            float(observation_latency_ms)
            if observation_latency_valid
            else None
        ),
        "checks": {
            "coordinate_tracking_state": (
                None if not isinstance(observation, Mapping) else observation.get("tracking_state")
            ),
            "position_available": position is not None
            and not any(
                reason in reasons
                for reason in ("position_missing", "position_xy_missing_or_invalid")
            ),
            "camera_integrity_state": camera_decision.tracking_state,
            "camera_integrity_confidence": camera_confidence,
            "camera_integrity_ready": camera_decision.allow_control,
            "client_facing_source": normalized_client_source,
            "heading_source": normalized_heading_source,
            "heading_integrity_state": heading_decision.state,
            "heading_integrity_ready": heading_decision.allow_control,
            "heading_is_current_visual": current_heading_visual,
            "body_yaw_observation_rad": body_yaw,
            "camera_yaw_estimate_rad": camera_yaw,
            "body_camera_yaw_delta_rad": body_camera_delta,
            "body_yaw_exact": body_yaw is not None,
            "camera_yaw_available": camera_yaw is not None,
            "foreground_matches_target": foreground_matches_target,
            "capture_latency_valid": capture_latency_valid,
            "observation_latency_valid": observation_latency_valid,
        },
        "provenance": {
            "origin": "client_observation_preflight",
            "capture_origin": capture_origin,
            "capability": "navigation_live_preflight",
            "scope": "unpromoted_evaluation_only",
            "evidence_refs": refs,
        },
        "input_emitted": False,
        "execution_authority": False,
        "server_truth_used": False,
    }


def _body_yaw_from_exact_source(
    position: Mapping[str, object] | None,
    *,
    client_facing_source: str,
) -> float | None:
    """Keep minimap heading estimates out of the raw body-yaw channel."""

    if position is None or client_facing_source != EXACT_CLIENT_FACING_SOURCE:
        return None
    return _finite_value(position.get("facing_rad"))


def _body_camera_delta(body_yaw: float | None, camera_yaw: float | None) -> float | None:
    if body_yaw is None or camera_yaw is None:
        return None
    # The preflight record is diagnostic only.  Keep the smallest wrapped
    # separation without importing the runner's steering implementation.
    from math import pi

    delta = (float(body_yaw) - float(camera_yaw) + pi) % (2.0 * pi) - pi
    return abs(delta)


def _finite_value(value: object) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
    ):
        return None
    return float(value)


def _finite_nonnegative(value: object) -> bool:
    number = _finite_value(value)
    return number is not None and number >= 0.0


def _finite_normalized(value: object) -> bool:
    number = _finite_value(value)
    return number is not None and 0.0 <= number <= 1.0


def _validate_evidence_refs(evidence_refs: Sequence[str]) -> list[str]:
    if not isinstance(evidence_refs, Sequence) or isinstance(
        evidence_refs, (str, bytes, bytearray)
    ):
        raise ValueError("preflight evidence references must be a sequence")
    refs = list(evidence_refs)
    if not 1 <= len(refs) <= 8 or any(
        not isinstance(item, str) or not item or len(item) > 256 for item in refs
    ) or len(set(refs)) != len(refs):
        raise ValueError("preflight evidence references are invalid")
    return refs


__all__ = [
    "DEFAULT_MAXIMUM_OBSERVATION_AGE_MS",
    "LIVE_PREFLIGHT_RECORD_TYPE",
    "LIVE_PREFLIGHT_SCHEMA_VERSION",
    "MAX_EXACT_BODY_HEADING_DISAGREEMENT_RAD",
    "build_live_preflight_record",
]
