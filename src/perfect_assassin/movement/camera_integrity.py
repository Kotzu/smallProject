"""Client-neutral policy for the screen-space player-anchor safety gate."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CameraIntegrityDecision:
    """Whether a fresh observation may authorize another control frame."""

    allow_control: bool
    tracking_state: str
    confidence: float
    reason: str

    def __post_init__(self) -> None:
        if type(self.allow_control) is not bool:
            raise ValueError("camera integrity allow_control must be boolean")
        if self.tracking_state not in {"VISIBLE", "LOST", "UNKNOWN", "MISSING"}:
            raise ValueError("camera integrity tracking state is invalid")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("camera integrity confidence is invalid")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("camera integrity reason is invalid")


def _actor_anchor_is_valid(anchor: object) -> bool:
    """Check the small geometry needed before trusting a visible record."""

    if not isinstance(anchor, Mapping):
        return False
    required = {"left", "top", "right", "bottom", "center_x", "center_y"}
    if set(anchor) != required:
        return False
    values: dict[str, float] = {}
    for key in required:
        value = anchor.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            return False
        values[key] = float(value)
    return (
        values["left"] < values["right"]
        and values["top"] < values["bottom"]
        and values["left"] <= values["center_x"] <= values["right"]
        and values["top"] <= values["center_y"] <= values["bottom"]
    )


def assess_camera_integrity(
    camera_integrity: Mapping[str, object] | None,
    *,
    require_visible_anchor: bool = True,
    minimum_confidence: float = 0.55,
) -> CameraIntegrityDecision:
    """Apply a fail-closed player-anchor decision to one observation.

    A missing or malformed camera record is never treated as visible.  The
    policy has no pixel, world-coordinate, server, or actuator dependency.
    """

    if type(require_visible_anchor) is not bool:
        raise ValueError("require_visible_anchor must be boolean")
    if (
        isinstance(minimum_confidence, bool)
        or not isinstance(minimum_confidence, (int, float))
        or not isfinite(float(minimum_confidence))
        or not 0.0 <= float(minimum_confidence) <= 1.0
    ):
        raise ValueError("minimum camera integrity confidence is invalid")
    if not require_visible_anchor:
        disabled_state = "MISSING"
        disabled_confidence = 0.0
        if isinstance(camera_integrity, Mapping):
            raw_state = camera_integrity.get("tracking_state")
            if isinstance(raw_state, str) and raw_state in {
                "VISIBLE", "LOST", "UNKNOWN"
            }:
                disabled_state = raw_state
            raw_confidence = camera_integrity.get("confidence")
            if (
                isinstance(raw_confidence, (int, float))
                and not isinstance(raw_confidence, bool)
                and isfinite(float(raw_confidence))
            ):
                disabled_confidence = max(0.0, min(1.0, float(raw_confidence)))
        return CameraIntegrityDecision(
            allow_control=True,
            tracking_state=disabled_state,
            confidence=disabled_confidence,
            reason="camera_anchor_gate_disabled_for_read_only_mode",
        )
    if not isinstance(camera_integrity, Mapping):
        return CameraIntegrityDecision(
            allow_control=False,
            tracking_state="MISSING",
            confidence=0.0,
            reason="camera_integrity_evidence_missing",
        )
    state = camera_integrity.get("tracking_state")
    confidence = camera_integrity.get("confidence")
    if not isinstance(state, str) or state not in {"VISIBLE", "LOST", "UNKNOWN"}:
        return CameraIntegrityDecision(
            allow_control=False,
            tracking_state="UNKNOWN",
            confidence=0.0,
            reason="camera_integrity_evidence_malformed",
        )
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not isfinite(float(confidence))
    ):
        return CameraIntegrityDecision(
            allow_control=False,
            tracking_state="UNKNOWN",
            confidence=0.0,
            reason="camera_integrity_confidence_malformed",
        )
    confidence_value = max(0.0, min(1.0, float(confidence)))
    anchor = camera_integrity.get("actor_anchor")
    if (
        state == "VISIBLE"
        and confidence_value >= float(minimum_confidence)
        and _actor_anchor_is_valid(anchor)
    ):
        return CameraIntegrityDecision(
            allow_control=True,
            tracking_state="VISIBLE",
            confidence=confidence_value,
            reason="visible_player_anchor_above_confidence_floor",
        )
    return CameraIntegrityDecision(
        allow_control=False,
        tracking_state=state,
        confidence=confidence_value,
        reason=(
            "player_actor_anchor_lost"
            if state == "LOST"
            else "player_actor_anchor_not_safe_for_control"
        ),
    )


def navigation_camera_is_level(
    *, mouse_delta_y: int, mouse_velocity_y_px_s: float
) -> bool:
    """Return whether a navigation frame cannot pitch the camera vertically."""

    if type(mouse_delta_y) is not int:
        raise ValueError("navigation camera mouse_delta_y must be an integer")
    if (
        isinstance(mouse_velocity_y_px_s, bool)
        or not isinstance(mouse_velocity_y_px_s, (int, float))
        or not isfinite(float(mouse_velocity_y_px_s))
    ):
        raise ValueError("navigation camera vertical velocity is invalid")
    return mouse_delta_y == 0 and float(mouse_velocity_y_px_s) == 0.0


__all__ = [
    "CameraIntegrityDecision",
    "assess_camera_integrity",
    "navigation_camera_is_level",
]
