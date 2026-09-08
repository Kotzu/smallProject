"""Bounded screen-space evidence that the controlled player is still visible.

The coordinate HUD can remain perfectly valid while a third-person camera is
pressed into a wall or ceiling.  This adapter therefore exposes a deliberately
conservative, client-visible actor-anchor check.  It never returns a world
position, a unit identity, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np


class PlayerActorAnchorError(ValueError):
    """The bounded actor-anchor detector or its profile is invalid."""


@dataclass(frozen=True, slots=True)
class _Component:
    pixels: int
    center_x: float
    center_y: float
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


_PROFILE_FIELDS = {
    "record_type",
    "schema_version",
    "profile",
    "profile_version",
    "target_profile",
    "client_build",
    "pixel_format",
    "sample_stride",
    "head_roi",
    "support_roi",
    "head_center_x",
    "head_center_y",
    "head_width",
    "head_height",
    "support_center_x",
    "support_center_y",
    "minimum_luminance",
    "maximum_channel_spread",
    "minimum_head_component_pixels",
    "minimum_support_component_pixels",
    "minimum_support_vertical_gap_fraction",
    "maximum_foreground_pixels",
    "maximum_component_pixels",
    "maximum_components",
    "minimum_confidence",
    "detector_deadline_ms",
    "calibration_state",
    "evidence_refs",
    "execution_authority",
}


def _validate_roi(value: Any, label: str) -> None:
    if type(value) is not dict or set(value) != {"left", "top", "right", "bottom"}:
        raise PlayerActorAnchorError(f"{label} is invalid")
    numbers = [value[key] for key in ("left", "top", "right", "bottom")]
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        or not 0.0 <= float(item) <= 1.0
        for item in numbers
    ):
        raise PlayerActorAnchorError(f"{label} contains invalid fractions")
    if not (
        float(value["left"]) < float(value["right"])
        and float(value["top"]) < float(value["bottom"])
    ):
        raise PlayerActorAnchorError(f"{label} ordering is invalid")


def _validate_range(value: Any, label: str, *, upper: float = 1.0) -> None:
    if type(value) is not dict or set(value) != {"min", "max"}:
        raise PlayerActorAnchorError(f"{label} is invalid")
    minimum, maximum = value["min"], value["max"]
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        or not 0.0 <= float(item) <= upper
        for item in (minimum, maximum)
    ) or float(minimum) > float(maximum):
        raise PlayerActorAnchorError(f"{label} range is invalid")


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlayerActorAnchorError("player actor profile is unreadable") from error
    if type(value) is not dict or set(value) != _PROFILE_FIELDS:
        raise PlayerActorAnchorError("player actor profile fields are not exact")
    supported_identity = {
        ("player_actor_anchor_tbc243_v1", "0.1.0"),
        ("player_actor_anchor_tbc243_v2", "0.2.0"),
    }
    if (
        value["record_type"] != "player_actor_anchor_profile"
        or value["schema_version"] != "0.1"
        or (value["profile"], value["profile_version"]) not in supported_identity
        or value["target_profile"] != "tbc_243_lab"
        or value["client_build"] != "2.4.3.8606"
        or value["pixel_format"] != "BGRA8"
        or value["execution_authority"] is not False
    ):
        raise PlayerActorAnchorError("player actor profile identity is unsupported")
    if type(value["sample_stride"]) is not int or not 1 <= value["sample_stride"] <= 8:
        raise PlayerActorAnchorError("player actor sample stride is invalid")
    for name in ("head_roi", "support_roi"):
        _validate_roi(value[name], name)
    for name in ("head_center_x", "head_center_y", "head_width", "head_height", "support_center_x", "support_center_y"):
        _validate_range(value[name], name)
    if not (
        value["head_width"]["max"] > 0
        and value["head_height"]["max"] > 0
        and value["support_center_y"]["max"] > 0
    ):
        raise PlayerActorAnchorError("player actor component ranges are invalid")
    integer_fields = (
        "minimum_luminance",
        "maximum_channel_spread",
        "minimum_head_component_pixels",
        "minimum_support_component_pixels",
        "maximum_foreground_pixels",
        "maximum_component_pixels",
        "maximum_components",
    )
    for name in integer_fields:
        item = value[name]
        if type(item) is not int or item <= 0:
            raise PlayerActorAnchorError(f"{name} must be a positive integer")
    if value["minimum_luminance"] > 255 or value["maximum_channel_spread"] > 255:
        raise PlayerActorAnchorError("player actor colour thresholds are invalid")
    for name in ("minimum_support_vertical_gap_fraction", "minimum_confidence"):
        item = value[name]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or not 0.0 <= float(item) <= 1.0
        ):
            raise PlayerActorAnchorError(f"{name} is invalid")
    deadline = value["detector_deadline_ms"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(float(deadline))
        or not 0.1 <= float(deadline) <= 100.0
    ):
        raise PlayerActorAnchorError("player actor detector deadline is invalid")
    if value["calibration_state"] not in {
        "retained_video_candidate",
        "synthetic_verified",
        "controlled_live_verified",
    }:
        raise PlayerActorAnchorError("player actor calibration state is invalid")
    refs = value["evidence_refs"]
    if (
        not isinstance(refs, list)
        or not 1 <= len(refs) <= 8
        or any(not isinstance(item, str) or not item for item in refs)
        or len(set(refs)) != len(refs)
    ):
        raise PlayerActorAnchorError("player actor evidence references are invalid")
    return value


def _components(
    mask: np.ndarray,
    *,
    offset_x: int,
    offset_y: int,
    minimum_pixels: int,
    maximum_foreground_pixels: int,
    maximum_component_pixels: int,
    maximum_components: int,
    deadline_s: float,
) -> list[_Component]:
    foreground = int(np.count_nonzero(mask))
    if foreground > maximum_foreground_pixels:
        raise PlayerActorAnchorError("player actor foreground budget exceeded")
    # A two-pixel support pass rejects isolated UI/noise pixels before the
    # bounded connected-component traversal.
    supported = np.zeros_like(mask, dtype=bool)
    if mask.shape[0] >= 2 and mask.shape[1] >= 2:
        block = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
        supported[:-1, :-1] |= block
        supported[1:, :-1] |= block
        supported[:-1, 1:] |= block
        supported[1:, 1:] |= block
    visited = np.zeros_like(supported, dtype=bool)
    height, width = supported.shape
    result: list[_Component] = []
    seen = 0
    ys, xs = np.nonzero(supported)
    for raw_y, raw_x in zip(ys, xs, strict=True):
        y, x = int(raw_y), int(raw_x)
        if visited[y, x]:
            continue
        seen += 1
        if seen > maximum_components * 8:
            raise PlayerActorAnchorError("player actor component budget exceeded")
        if time.perf_counter() > deadline_s:
            raise PlayerActorAnchorError("player actor detector operation budget exceeded")
        visited[y, x] = True
        stack = [(y, x)]
        pixels = 0
        sum_x = 0
        sum_y = 0
        left = right = x
        top = bottom = y
        while stack:
            current_y, current_x = stack.pop()
            pixels += 1
            if pixels > maximum_component_pixels:
                raise PlayerActorAnchorError("player actor component pixel budget exceeded")
            sum_x += current_x
            sum_y += current_y
            left = min(left, current_x)
            right = max(right, current_x)
            top = min(top, current_y)
            bottom = max(bottom, current_y)
            if pixels % 128 == 0 and time.perf_counter() > deadline_s:
                raise PlayerActorAnchorError("player actor detector operation budget exceeded")
            for next_y, next_x in (
                (current_y - 1, current_x),
                (current_y + 1, current_x),
                (current_y, current_x - 1),
                (current_y, current_x + 1),
            ):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and supported[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    stack.append((next_y, next_x))
        if pixels >= minimum_pixels:
            result.append(
                _Component(
                    pixels=pixels,
                    center_x=offset_x + sum_x / pixels,
                    center_y=offset_y + sum_y / pixels,
                    left=offset_x + left,
                    top=offset_y + top,
                    right=offset_x + right,
                    bottom=offset_y + bottom,
                )
            )
    return sorted(result, key=lambda item: item.pixels, reverse=True)[:maximum_components]


def _roi(frame: np.ndarray, bounds: dict[str, float]) -> tuple[np.ndarray, int, int]:
    height, width = frame.shape[:2]
    left = max(0, min(width - 1, int(round(bounds["left"] * width))))
    right = max(left + 1, min(width, int(round(bounds["right"] * width))))
    top = max(0, min(height - 1, int(round(bounds["top"] * height))))
    bottom = max(top + 1, min(height, int(round(bounds["bottom"] * height))))
    return frame[top:bottom, left:right], left, top


def _inside(value: float, bounds: dict[str, float]) -> bool:
    return bounds["min"] <= value <= bounds["max"]


class PlayerActorAnchorDetector:
    """Conservative visual check for a central third-person player silhouette."""

    def __init__(self, profile: dict[str, Any]) -> None:
        if type(profile) is not dict or set(profile) != _PROFILE_FIELDS:
            raise PlayerActorAnchorError("player actor detector profile is invalid")
        self.profile = dict(profile)

    def failure_record(
        self,
        *,
        observed_at_s: float,
        reason: str,
        sampled_width: int = 1,
        sampled_height: int = 1,
    ) -> dict[str, Any]:
        """Return contract-shaped unknown evidence after a bounded detector error."""

        if not isinstance(reason, str) or not reason:
            raise PlayerActorAnchorError("player actor failure reason is invalid")
        if (
            type(sampled_width) is not int
            or type(sampled_height) is not int
            or sampled_width < 1
            or sampled_height < 1
        ):
            raise PlayerActorAnchorError("player actor failure dimensions are invalid")
        return self._record(
            observed_at_s=float(observed_at_s),
            state="UNKNOWN",
            confidence=0.0,
            reason=reason[:128],
            head=None,
            support=None,
            width=sampled_width,
            height=sampled_height,
        )

    def detect(self, frame_bgra: np.ndarray, *, observed_at_s: float) -> dict[str, Any]:
        if (
            not isinstance(frame_bgra, np.ndarray)
            or frame_bgra.dtype != np.uint8
            or frame_bgra.ndim != 3
            or frame_bgra.shape[2] != 4
            or frame_bgra.shape[0] < 240
            or frame_bgra.shape[1] < 320
        ):
            raise PlayerActorAnchorError("player actor frame must be BGRA8")
        if (
            isinstance(observed_at_s, bool)
            or not isinstance(observed_at_s, (int, float))
            or not math.isfinite(float(observed_at_s))
            or float(observed_at_s) < 0
        ):
            raise PlayerActorAnchorError("player actor observation time is invalid")
        stride = self.profile["sample_stride"]
        sampled = frame_bgra[::stride, ::stride, :3]
        height, width = sampled.shape[:2]
        deadline_s = time.perf_counter() + float(self.profile["detector_deadline_ms"]) / 1000.0
        head_image, head_left, head_top = _roi(sampled, self.profile["head_roi"])
        support_image, support_left, support_top = _roi(sampled, self.profile["support_roi"])

        def neutral_bright(image: np.ndarray) -> np.ndarray:
            minimum = image.min(axis=2)
            spread = image.max(axis=2).astype(np.int16) - minimum.astype(np.int16)
            return (minimum >= self.profile["minimum_luminance"]) & (
                spread <= self.profile["maximum_channel_spread"]
            )

        head_components = _components(
            neutral_bright(head_image),
            offset_x=head_left,
            offset_y=head_top,
            minimum_pixels=self.profile["minimum_head_component_pixels"],
            maximum_foreground_pixels=self.profile["maximum_foreground_pixels"],
            maximum_component_pixels=self.profile["maximum_component_pixels"],
            maximum_components=self.profile["maximum_components"],
            deadline_s=deadline_s,
        )
        support_components = _components(
            neutral_bright(support_image),
            offset_x=support_left,
            offset_y=support_top,
            minimum_pixels=self.profile["minimum_support_component_pixels"],
            maximum_foreground_pixels=self.profile["maximum_foreground_pixels"],
            maximum_component_pixels=self.profile["maximum_component_pixels"],
            maximum_components=self.profile["maximum_components"],
            deadline_s=deadline_s,
        )

        def normalized(component: _Component) -> tuple[float, float, float, float]:
            return (
                component.center_x / width,
                component.center_y / height,
                component.width / width,
                component.height / height,
            )

        heads = [
            item
            for item in head_components
            if (
                _inside(normalized(item)[0], self.profile["head_center_x"])
                and _inside(normalized(item)[1], self.profile["head_center_y"])
                and _inside(normalized(item)[2], self.profile["head_width"])
                and _inside(normalized(item)[3], self.profile["head_height"])
            )
        ]
        head = max(heads, key=lambda item: item.pixels, default=None)
        supports = []
        if head is not None:
            head_x, head_y, _head_w, _head_h = normalized(head)
            for item in support_components:
                support_x, support_y, _support_w, _support_h = normalized(item)
                if (
                    _inside(support_x, self.profile["support_center_x"])
                    and _inside(support_y, self.profile["support_center_y"])
                    and support_y - head_y
                    >= self.profile["minimum_support_vertical_gap_fraction"]
                ):
                    supports.append(item)
        support = max(supports, key=lambda item: item.pixels, default=None)
        if head is None or support is None:
            return self._record(
                observed_at_s=float(observed_at_s),
                state="LOST",
                confidence=0.0,
                reason="central_actor_anchor_not_found",
                head=head,
                support=support,
                width=width,
                height=height,
            )

        head_score = min(
            1.0,
            head.pixels / max(1.0, self.profile["minimum_head_component_pixels"] * 3.0),
        )
        support_score = min(
            1.0,
            support.pixels / max(1.0, self.profile["minimum_support_component_pixels"] * 3.0),
        )
        center_score = max(0.0, 1.0 - abs(normalized(head)[0] - 0.5) / 0.20)
        confidence = round(0.45 * head_score + 0.40 * support_score + 0.15 * center_score, 4)
        state = "VISIBLE" if confidence >= self.profile["minimum_confidence"] else "UNKNOWN"
        return self._record(
            observed_at_s=float(observed_at_s),
            state=state,
            confidence=confidence,
            reason=("central_actor_head_and_body_found" if state == "VISIBLE" else "actor_anchor_confidence_below_threshold"),
            head=head,
            support=support,
            width=width,
            height=height,
        )

    def _record(
        self,
        *,
        observed_at_s: float,
        state: str,
        confidence: float,
        reason: str,
        head: _Component | None,
        support: _Component | None,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        components = [item for item in (head, support) if item is not None]
        anchor = None
        if components:
            left = min(item.left for item in components) / width
            top = min(item.top for item in components) / height
            right = (max(item.right for item in components) + 1) / width
            bottom = (max(item.bottom for item in components) + 1) / height
            anchor = {
                "left": round(left, 6),
                "top": round(top, 6),
                "right": round(right, 6),
                "bottom": round(bottom, 6),
                "center_x": round((left + right) / 2.0, 6),
                "center_y": round((top + bottom) / 2.0, 6),
            }
        return {
            "record_type": "player_actor_anchor_observation",
            "schema_version": "0.1",
            "tracking_state": state,
            "confidence": confidence,
            "reason": reason,
            "actor_anchor": anchor,
            "metrics": {
                "head_component_pixels": 0 if head is None else head.pixels,
                "support_component_pixels": 0 if support is None else support.pixels,
                "sampled_width": width,
                "sampled_height": height,
            },
            "observed_monotonic_s": observed_at_s,
            "provenance": {
                "origin": "scene_vision",
                "capability": "player_actor_screen_visibility",
                "scope": "unpromoted_evaluation_only",
                "profile": self.profile["profile"],
                "profile_version": self.profile["profile_version"],
                "evidence_refs": list(self.profile["evidence_refs"]),
            },
            "execution_authority": False,
        }


__all__ = [
    "PlayerActorAnchorDetector",
    "PlayerActorAnchorError",
    "load_profile",
]
