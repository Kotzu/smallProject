from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
import time
from typing import Any

import numpy as np

from perfect_assassin.movement.dynamic_avoidance import ScreenEntityObservation
from selected_target_bearing_detector import (
    SelectedTargetBearingError,
    _Component,
    _components,
)


class VisibleEntityDetectorError(RuntimeError):
    pass


_PROFILE_FIELDS = {
    "profile",
    "profile_version",
    "target_profile",
    "client_build",
    "sample_stride",
    "roi_left_fraction",
    "roi_right_fraction",
    "roi_top_fraction",
    "roi_bottom_fraction",
    "top_left_ui_right_fraction",
    "top_left_ui_bottom_fraction",
    "top_right_ui_left_fraction",
    "top_right_ui_bottom_fraction",
    "hostile_red_min",
    "hostile_green_max",
    "hostile_blue_max",
    "hostile_red_green_delta_min",
    "neutral_red_min",
    "neutral_green_min",
    "neutral_blue_max",
    "friendly_green_min",
    "friendly_red_max",
    "friendly_blue_max",
    "friendly_green_red_delta_min",
    "minimum_component_pixels",
    "minimum_width_fraction",
    "maximum_width_fraction",
    "maximum_height_fraction",
    "minimum_aspect_ratio",
    "minimum_fill_fraction",
    "maximum_foreground_pixels",
    "maximum_component_pixels",
    "maximum_components",
    "detector_deadline_ms",
    "execution_authority",
}


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VisibleEntityDetectorError(
            "visible entity profile is unreadable"
        ) from error
    if type(value) is not dict or set(value) != _PROFILE_FIELDS:
        raise VisibleEntityDetectorError(
            "visible entity profile fields are not exact"
        )
    if (
        value["profile"] != "visible_entity_nameplates_tbc243_v1"
        or value["profile_version"] != "1.0.0"
        or value["target_profile"] != "tbc_243_lab"
        or value["client_build"] != "2.4.3.8606"
        or value["execution_authority"] is not False
    ):
        raise VisibleEntityDetectorError(
            "visible entity profile identity is unsupported"
        )
    fractions = {
        "roi_left_fraction",
        "roi_right_fraction",
        "roi_top_fraction",
        "roi_bottom_fraction",
        "top_left_ui_right_fraction",
        "top_left_ui_bottom_fraction",
        "top_right_ui_left_fraction",
        "top_right_ui_bottom_fraction",
        "minimum_width_fraction",
        "maximum_width_fraction",
        "maximum_height_fraction",
        "minimum_fill_fraction",
    }
    for field in fractions:
        item = value[field]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not isfinite(float(item))
            or not 0.0 < float(item) < 1.0
        ):
            raise VisibleEntityDetectorError(
                f"visible entity profile {field} is invalid"
            )
    if not (
        value["roi_left_fraction"] < value["roi_right_fraction"]
        and value["roi_top_fraction"] < value["roi_bottom_fraction"]
        and value["minimum_width_fraction"] < value["maximum_width_fraction"]
    ):
        raise VisibleEntityDetectorError(
            "visible entity profile ROI ordering is invalid"
        )
    integer_fields = _PROFILE_FIELDS - fractions - {
        "profile",
        "profile_version",
        "target_profile",
        "client_build",
        "minimum_aspect_ratio",
        "detector_deadline_ms",
        "execution_authority",
    }
    for field in integer_fields:
        item = value[field]
        if type(item) is not int or item <= 0:
            raise VisibleEntityDetectorError(
                f"visible entity profile {field} must be positive integer"
            )
    if not 1 <= value["sample_stride"] <= 4:
        raise VisibleEntityDetectorError(
            "visible entity profile sample_stride is invalid"
        )
    for field in ("minimum_aspect_ratio", "detector_deadline_ms"):
        item = value[field]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not isfinite(float(item))
            or float(item) <= 0.0
        ):
            raise VisibleEntityDetectorError(
                f"visible entity profile {field} is invalid"
            )
    return value


class VisibleEntityNameplateDetector:
    """Read-only adapter from visible health bars to generic entity cues.

    It reports viewport evidence, never a guessed world coordinate or unit
    identity.  Colour thresholds live in a client profile; the downstream
    tracker and avoidance policy are client-independent.
    """

    def __init__(self, profile: dict[str, Any]) -> None:
        if type(profile) is not dict or set(profile) != _PROFILE_FIELDS:
            raise VisibleEntityDetectorError(
                "visible entity detector profile is invalid"
            )
        self.profile = dict(profile)

    def detect(
        self,
        frame: np.ndarray,
        *,
        observed_at_s: float,
    ) -> tuple[ScreenEntityObservation, ...]:
        if not isfinite(observed_at_s):
            raise VisibleEntityDetectorError(
                "visible entity observation time is invalid"
            )
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.ndim != 3
            or frame.shape[2] not in {3, 4}
            or frame.shape[0] < 120
            or frame.shape[1] < 160
        ):
            raise VisibleEntityDetectorError(
                "visible entity frame is invalid"
            )
        stride = self.profile["sample_stride"]
        sampled = frame[::stride, ::stride, :3]
        sample_height, sample_width = sampled.shape[:2]
        left = int(round(sample_width * self.profile["roi_left_fraction"]))
        right = int(round(sample_width * self.profile["roi_right_fraction"]))
        top = int(round(sample_height * self.profile["roi_top_fraction"]))
        bottom = int(round(sample_height * self.profile["roi_bottom_fraction"]))
        if right <= left or bottom <= top:
            raise VisibleEntityDetectorError(
                "visible entity ROI collapsed"
            )
        bgr = sampled[top:bottom, left:right]
        blue = bgr[:, :, 0]
        green = bgr[:, :, 1]
        red = bgr[:, :, 2]
        red_i = red.astype(np.int16)
        green_i = green.astype(np.int16)
        masks = {
            "HOSTILE": (
                (red >= self.profile["hostile_red_min"])
                & (green <= self.profile["hostile_green_max"])
                & (blue <= self.profile["hostile_blue_max"])
                & (
                    red_i - green_i
                    >= self.profile["hostile_red_green_delta_min"]
                )
            ),
            "NEUTRAL": (
                (red >= self.profile["neutral_red_min"])
                & (green >= self.profile["neutral_green_min"])
                & (blue <= self.profile["neutral_blue_max"])
            ),
            "FRIENDLY": (
                (green >= self.profile["friendly_green_min"])
                & (red <= self.profile["friendly_red_max"])
                & (blue <= self.profile["friendly_blue_max"])
                & (
                    green_i - red_i
                    >= self.profile["friendly_green_red_delta_min"]
                )
            ),
        }
        self._exclude_native_ui(
            masks,
            frame_width=sample_width,
            frame_height=sample_height,
            offset_x=left,
            offset_y=top,
        )
        deadline_s = time.perf_counter() + (
            float(self.profile["detector_deadline_ms"]) / 1000.0
        )
        candidates: list[tuple[str, _Component, float]] = []
        try:
            for reaction, mask in masks.items():
                components = _components(
                    mask,
                    offset_x=left,
                    offset_y=top,
                    minimum_pixels=self.profile["minimum_component_pixels"],
                    maximum_foreground_pixels=(
                        self.profile["maximum_foreground_pixels"]
                    ),
                    maximum_component_pixels=(
                        self.profile["maximum_component_pixels"]
                    ),
                    maximum_components=self.profile["maximum_components"],
                    deadline_s=deadline_s,
                )
                for component in components:
                    confidence = self._candidate_confidence(
                        component,
                        frame_width=sample_width,
                        frame_height=sample_height,
                    )
                    if confidence is not None:
                        candidates.append((reaction, component, confidence))
        except SelectedTargetBearingError as error:
            raise VisibleEntityDetectorError(
                "visible entity component extraction failed"
            ) from error
        # A bright yellow bar can include a red subset.  Merge overlapping
        # candidates and keep the colour class with the stronger rectangular
        # evidence so one visible unit creates one ephemeral observation.
        retained: list[tuple[str, _Component, float]] = []
        for candidate in sorted(candidates, key=lambda item: item[2], reverse=True):
            _, component, _ = candidate
            if any(
                self._overlap_fraction(component, existing[1]) >= 0.60
                for existing in retained
            ):
                continue
            retained.append(candidate)
        observations = [
            ScreenEntityObservation(
                observed_at_s=observed_at_s,
                center_x_normalized=max(
                    -1.0,
                    min(
                        1.0,
                        (component.center_x - sample_width / 2.0)
                        / (sample_width / 2.0),
                    ),
                ),
                center_y_normalized=max(
                    0.0, min(1.0, component.center_y / sample_height),
                ),
                width_normalized=component.width / sample_width,
                height_normalized=component.height / sample_height,
                reaction=reaction,  # type: ignore[arg-type]
                confidence=confidence,
            )
            for reaction, component, confidence in retained
        ]
        return tuple(
            sorted(
                observations,
                key=lambda item: (
                    abs(item.center_x_normalized),
                    -item.center_y_normalized,
                    item.reaction,
                ),
            )
        )

    def _exclude_native_ui(
        self,
        masks: dict[str, np.ndarray],
        *,
        frame_width: int,
        frame_height: int,
        offset_x: int,
        offset_y: int,
    ) -> None:
        left_ui_right = int(
            round(frame_width * self.profile["top_left_ui_right_fraction"])
        )
        left_ui_bottom = int(
            round(frame_height * self.profile["top_left_ui_bottom_fraction"])
        )
        right_ui_left = int(
            round(frame_width * self.profile["top_right_ui_left_fraction"])
        )
        right_ui_bottom = int(
            round(frame_height * self.profile["top_right_ui_bottom_fraction"])
        )
        local_left_ui_right = max(0, left_ui_right - offset_x)
        local_left_ui_bottom = max(0, left_ui_bottom - offset_y)
        local_right_ui_left = max(0, right_ui_left - offset_x)
        local_right_ui_bottom = max(0, right_ui_bottom - offset_y)
        for mask in masks.values():
            mask[:local_left_ui_bottom, :local_left_ui_right] = False
            mask[:local_right_ui_bottom, local_right_ui_left:] = False

    def _candidate_confidence(
        self,
        component: _Component,
        *,
        frame_width: int,
        frame_height: int,
    ) -> float | None:
        width_fraction = component.width / frame_width
        height_fraction = component.height / frame_height
        aspect = component.width / max(1, component.height)
        fill = component.pixels / max(1, component.width * component.height)
        if not (
            self.profile["minimum_width_fraction"]
            <= width_fraction
            <= self.profile["maximum_width_fraction"]
            and height_fraction <= self.profile["maximum_height_fraction"]
            and aspect >= self.profile["minimum_aspect_ratio"]
            and fill >= self.profile["minimum_fill_fraction"]
        ):
            return None
        width_score = min(
            1.0,
            width_fraction / (self.profile["minimum_width_fraction"] * 2.0),
        )
        aspect_score = min(
            1.0,
            aspect / (self.profile["minimum_aspect_ratio"] * 2.0),
        )
        return max(
            0.0,
            min(1.0, 0.45 * fill + 0.30 * width_score + 0.25 * aspect_score),
        )

    @staticmethod
    def _overlap_fraction(left: _Component, right: _Component) -> float:
        overlap_width = max(0, min(left.right, right.right) - max(left.left, right.left) + 1)
        overlap_height = max(0, min(left.bottom, right.bottom) - max(left.top, right.top) + 1)
        overlap = overlap_width * overlap_height
        smaller = min(left.width * left.height, right.width * right.height)
        return overlap / max(1, smaller)
