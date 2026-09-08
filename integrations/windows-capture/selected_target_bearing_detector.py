from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

import numpy as np

from perfect_assassin.adapter.combat_hud import validate_valid_observation_semantics
from perfect_assassin.adapter.target_bearing import (
    SelectedTargetBearingError,
    validate_selected_target_bearing_semantics,
)
from perfect_assassin.contract_validation import ContractValidator


CONTINUITY_CENTER_ALPHA = 0.35


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


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SelectedTargetBearingError("bearing profile is unreadable") from error
    if type(value) is not dict:
        raise SelectedTargetBearingError("bearing profile root must be an object")
    required = {
        "profile",
        "profile_version",
        "target_profile",
        "client_build",
        "roi_left_fraction",
        "roi_right_fraction",
        "ring_top_fraction",
        "ring_bottom_fraction",
        "nameplate_top_fraction",
        "nameplate_bottom_fraction",
        "top_ui_exclusion_bottom_fraction",
        "top_ui_exclusion_left_fraction",
        "top_ui_exclusion_right_fraction",
        "bottom_left_ui_exclusion_top_fraction",
        "bottom_left_ui_exclusion_right_fraction",
        "bottom_right_ui_exclusion_top_fraction",
        "bottom_right_ui_exclusion_left_fraction",
        "yellow_red_min",
        "yellow_green_min",
        "yellow_blue_max",
        "yellow_red_blue_delta_min",
        "combat_red_min",
        "combat_red_green_max",
        "combat_red_blue_max",
        "combat_red_green_delta_min",
        "minimum_component_pixels",
        "maximum_foreground_pixels",
        "maximum_component_pixels",
        "maximum_components",
        "ring_minimum_pixels",
        "ring_minimum_span_fraction",
        "ring_minimum_height_fraction",
        "ring_maximum_height_fraction",
        "ring_maximum_fill_fraction",
        "ring_minimum_pixels_per_span",
        "ring_maximum_height_to_span_ratio",
        "ring_cluster_y_tolerance_fraction",
        "ring_cluster_gap_fraction",
        "nameplate_minimum_pixels",
        "nameplate_minimum_width_fraction",
        "nameplate_maximum_height_fraction",
        "center_tolerance_fraction",
        "continuity_max_offset_delta",
        "continuity_max_age_ms",
        "maximum_frame_pixels",
        "detector_deadline_ms",
        "freshness_limit_ms",
        "calibration_state",
        "execution_authority",
    }
    if set(value) != required:
        raise SelectedTargetBearingError("bearing profile fields are not exact")
    if (
        value["profile"] != "selected_target_bearing_tbc243_v1"
        or value["profile_version"] != "0.9.0"
        or value["target_profile"] != "tbc_243_lab"
        or value["client_build"] != "2.4.3.8606"
        or value["calibration_state"] != "controlled_live_lab_verified"
        or value["execution_authority"] is not False
    ):
        raise SelectedTargetBearingError("bearing profile identity is unsupported")
    fractions = (
        "roi_left_fraction",
        "roi_right_fraction",
        "ring_top_fraction",
        "ring_bottom_fraction",
        "nameplate_top_fraction",
        "nameplate_bottom_fraction",
        "top_ui_exclusion_bottom_fraction",
        "top_ui_exclusion_left_fraction",
        "top_ui_exclusion_right_fraction",
        "bottom_left_ui_exclusion_top_fraction",
        "bottom_left_ui_exclusion_right_fraction",
        "bottom_right_ui_exclusion_top_fraction",
        "bottom_right_ui_exclusion_left_fraction",
        "ring_minimum_span_fraction",
        "ring_minimum_height_fraction",
        "ring_maximum_height_fraction",
        "ring_maximum_fill_fraction",
        "ring_cluster_y_tolerance_fraction",
        "ring_cluster_gap_fraction",
        "nameplate_minimum_width_fraction",
        "nameplate_maximum_height_fraction",
        "center_tolerance_fraction",
        "continuity_max_offset_delta",
    )
    for name in fractions:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not 0 < item < 1:
            raise SelectedTargetBearingError(f"{name} is invalid")
    for name in (
        "ring_minimum_pixels_per_span",
        "ring_maximum_height_to_span_ratio",
    ):
        item = value[name]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or item <= 0
        ):
            raise SelectedTargetBearingError(f"{name} is invalid")
    if not (
        value["roi_left_fraction"] < value["roi_right_fraction"]
        and value["ring_top_fraction"] < value["ring_bottom_fraction"]
        and value["nameplate_top_fraction"] < value["nameplate_bottom_fraction"]
        and value["top_ui_exclusion_left_fraction"]
        < value["top_ui_exclusion_right_fraction"]
    ):
        raise SelectedTargetBearingError("bearing profile ROI ordering is invalid")
    integer_fields = required - set(fractions) - {
        "profile",
        "profile_version",
        "target_profile",
        "client_build",
        "detector_deadline_ms",
        "freshness_limit_ms",
        "continuity_max_age_ms",
        "calibration_state",
        "execution_authority",
        "ring_minimum_pixels_per_span",
        "ring_maximum_height_to_span_ratio",
    }
    for name in integer_fields:
        if type(value[name]) is not int or value[name] <= 0:
            raise SelectedTargetBearingError(f"{name} must be a positive integer")
    for name in ("detector_deadline_ms", "freshness_limit_ms"):
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item <= 0:
            raise SelectedTargetBearingError(f"{name} is invalid")
    return value


def _canonical_sha256(value: dict[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _deadline(deadline_s: float) -> None:
    if time.perf_counter() > deadline_s:
        raise SelectedTargetBearingError("bearing detector operation budget exceeded")


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
    require_2x2_support: bool = True,
) -> list[_Component]:
    foreground = int(np.count_nonzero(mask))
    if foreground > maximum_foreground_pixels:
        raise SelectedTargetBearingError("bearing foreground pixel budget exceeded")
    supported = mask if not require_2x2_support else np.zeros_like(mask, dtype=bool)
    if require_2x2_support and mask.shape[0] >= 2 and mask.shape[1] >= 2:
        block = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
        supported[:-1, :-1] |= block
        supported[1:, :-1] |= block
        supported[:-1, 1:] |= block
        supported[1:, 1:] |= block
    visited = np.zeros_like(supported, dtype=bool)
    ys, xs = np.nonzero(supported)
    result: list[_Component] = []
    seen_components = 0
    height, width = supported.shape
    for raw_y, raw_x in zip(ys, xs, strict=True):
        y, x = int(raw_y), int(raw_x)
        if visited[y, x]:
            continue
        seen_components += 1
        # Natural foliage can contain many tiny colour islands.  Traverse a
        # separately bounded amount of that noise, then apply the public
        # component budget only to candidates that survive minimum_pixels.
        if seen_components > maximum_components * 8:
            raise SelectedTargetBearingError("bearing component count budget exceeded")
        _deadline(deadline_s)
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
                raise SelectedTargetBearingError("bearing component pixel budget exceeded")
            sum_x += current_x
            sum_y += current_y
            left = min(left, current_x)
            right = max(right, current_x)
            top = min(top, current_y)
            bottom = max(bottom, current_y)
            if pixels % 128 == 0:
                _deadline(deadline_s)
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
            # The traversal budget above limits adversarial work. Natural
            # foliage may still produce more valid small colour islands than
            # the public candidate capacity; retain the strongest bounded set
            # instead of converting harmless background detail into a loss of
            # target lock.
            if len(result) > maximum_components + 64:
                result = sorted(
                    result,
                    key=lambda item: item.pixels,
                    reverse=True,
                )[:maximum_components]
    return sorted(
        result,
        key=lambda item: item.pixels,
        reverse=True,
    )[:maximum_components]


def _cluster_ring_components(
    components: list[_Component],
    *,
    frame_width: int,
    frame_height: int,
    profile: dict[str, Any],
    deadline_s: float,
) -> list[tuple[float, float, int, int, int]]:
    top = frame_height * profile["ring_top_fraction"]
    bottom = frame_height * profile["ring_bottom_fraction"]
    candidates = [
        item
        for item in components
        if top <= item.center_y <= bottom
        and item.height <= frame_height * profile["ring_maximum_height_fraction"]
    ]
    candidates = sorted(candidates, key=lambda item: (-item.pixels, item.left))[:128]
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root, right_root = find(left_index), find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    y_tolerance = frame_height * profile["ring_cluster_y_tolerance_fraction"]
    gap_tolerance = frame_width * profile["ring_cluster_gap_fraction"]
    for left_index, left_item in enumerate(candidates):
        _deadline(deadline_s)
        for right_index in range(left_index + 1, len(candidates)):
            right_item = candidates[right_index]
            horizontal_gap = max(
                0,
                max(left_item.left, right_item.left)
                - min(left_item.right, right_item.right),
            )
            if (
                abs(left_item.center_y - right_item.center_y) <= y_tolerance
                and horizontal_gap <= gap_tolerance
            ):
                union(left_index, right_index)
    groups: dict[int, list[_Component]] = {}
    for index, item in enumerate(candidates):
        groups.setdefault(find(index), []).append(item)
    result: list[tuple[float, float, int, int, int]] = []
    for group in groups.values():
        pixels = sum(item.pixels for item in group)
        left = min(item.left for item in group)
        right = max(item.right for item in group)
        top_px = min(item.top for item in group)
        bottom_px = max(item.bottom for item in group)
        span = right - left + 1
        height = bottom_px - top_px + 1
        if (
            pixels >= profile["ring_minimum_pixels"]
            and span >= frame_width * profile["ring_minimum_span_fraction"]
            and height >= frame_height * profile["ring_minimum_height_fraction"]
            and height <= frame_height * profile["ring_maximum_height_fraction"]
            and pixels / (span * height) <= profile["ring_maximum_fill_fraction"]
            and pixels / span >= profile["ring_minimum_pixels_per_span"]
            and height / span <= profile["ring_maximum_height_to_span_ratio"]
        ):
            center_x = sum(item.center_x * item.pixels for item in group) / pixels
            center_y = sum(item.center_y * item.pixels for item in group) / pixels
            result.append((center_x, center_y, pixels, span, height))
    return sorted(result, key=lambda item: (-(item[2] * item[3]), item[0]))


class SelectedTargetBearingDetector:
    def __init__(
        self,
        profile: dict[str, Any],
        capture_validator: ContractValidator,
        combat_validator: ContractValidator,
        bearing_validator: ContractValidator,
    ) -> None:
        self.profile = copy.deepcopy(profile)
        self.profile_sha256 = _canonical_sha256(self.profile)
        self.capture_validator = capture_validator
        self.combat_validator = combat_validator
        self.bearing_validator = bearing_validator
        self._continuity_target_crc16: int | None = None
        self._continuity_center_x: float | None = None
        self._continuity_center_y: float | None = None
        self._continuity_observed_s: float | None = None

    def detect(
        self,
        manifest: dict[str, Any],
        frame: np.ndarray,
        combat_observation: dict[str, Any],
        *,
        observation_id: str,
        indicator_color_override: str | None = None,
    ) -> dict[str, Any]:
        self.capture_validator.validate(manifest)
        self.combat_validator.validate(combat_observation)
        validate_valid_observation_semantics(combat_observation)
        if (
            manifest["frame_id"] != combat_observation["frame_id"]
            or manifest["authorization_sha256"] != combat_observation["authorization_sha256"]
            or manifest["actor_binding"] != combat_observation["actor_binding"]
        ):
            raise SelectedTargetBearingError("combat and visual frame identity diverge")
        if (
            manifest["target_profile"] != self.profile["target_profile"]
            or manifest["client_build"] != self.profile["client_build"]
        ):
            raise SelectedTargetBearingError("bearing profile target identity diverges")
        expected_shape = (
            manifest["image"]["height"],
            manifest["image"]["width"],
            4,
        )
        if frame.dtype != np.uint8 or frame.shape != expected_shape:
            raise SelectedTargetBearingError("bearing frame shape or dtype mismatch")
        height, width = frame.shape[:2]
        if width * height > self.profile["maximum_frame_pixels"]:
            raise SelectedTargetBearingError("bearing frame exceeds pixel budget")
        target = combat_observation["target"]
        if target is None:
            self._reset_continuity()
            return self._observation(
                manifest,
                combat_observation,
                observation_id=observation_id,
                tracking_state="LOST",
                reason="combat_target_absent",
            )
        if indicator_color_override not in {None, "red", "yellow"}:
            raise SelectedTargetBearingError(
                "selected-target indicator colour override is invalid"
            )
        deadline_s = time.perf_counter() + self.profile["detector_deadline_ms"] / 1000.0
        left = int(width * self.profile["roi_left_fraction"])
        right = int(width * self.profile["roi_right_fraction"])
        top = int(height * min(
            self.profile["ring_top_fraction"],
            self.profile["nameplate_top_fraction"],
        ))
        bottom = int(height * max(
            self.profile["ring_bottom_fraction"],
            self.profile["nameplate_bottom_fraction"],
        ))
        bgr = frame[top:bottom, left:right, :3]
        blue = bgr[:, :, 0]
        green = bgr[:, :, 1]
        red = bgr[:, :, 2]
        yellow_mask = (
            (red >= self.profile["yellow_red_min"])
            & (green >= self.profile["yellow_green_min"])
            & (blue <= self.profile["yellow_blue_max"])
            & (
                red.astype(np.int16) - blue.astype(np.int16)
                >= self.profile["yellow_red_blue_delta_min"]
            )
        )
        combat_red_mask = (
            (red >= self.profile["combat_red_min"])
            & (green <= self.profile["combat_red_green_max"])
            & (blue <= self.profile["combat_red_blue_max"])
            & (
                red.astype(np.int16) - green.astype(np.int16)
                >= self.profile["combat_red_green_delta_min"]
            )
        )
        # Reaction 1-3 uses a red selection circle and reaction 4 uses a
        # yellow circle.  Binding the expected indicator colour to the target
        # reaction prevents scenery of the other colour from steering facing.
        reaction = target["reaction"]
        expected_indicator = (
            indicator_color_override
            if indicator_color_override is not None
            else "yellow"
            if reaction == 4
            else "red"
        )
        def exclude_native_ui(source: np.ndarray) -> np.ndarray:
            result = source.copy()
            exclusion_rows = max(
                0,
                min(
                    result.shape[0],
                    int(height * self.profile["top_ui_exclusion_bottom_fraction"])
                    - top,
                ),
            )
            if exclusion_rows:
                exclusion_left = max(
                    0,
                    min(
                        result.shape[1],
                        int(width * self.profile["top_ui_exclusion_left_fraction"])
                        - left,
                    ),
                )
                exclusion_right = max(
                    0,
                    min(
                        result.shape[1],
                        int(width * self.profile["top_ui_exclusion_right_fraction"])
                        - left,
                    ),
                )
                result[:exclusion_rows, :exclusion_left] = False
                result[:exclusion_rows, exclusion_right:] = False
            bottom_exclusion_start = max(
                0,
                min(
                    result.shape[0],
                    int(height * self.profile["bottom_left_ui_exclusion_top_fraction"])
                    - top,
                ),
            )
            bottom_exclusion_right = max(
                0,
                min(
                    result.shape[1],
                    int(width * self.profile["bottom_left_ui_exclusion_right_fraction"])
                    - left,
                ),
            )
            if bottom_exclusion_start < result.shape[0] and bottom_exclusion_right:
                result[bottom_exclusion_start:, :bottom_exclusion_right] = False
            bottom_right_exclusion_start = max(
                0,
                min(
                    result.shape[0],
                    int(height * self.profile["bottom_right_ui_exclusion_top_fraction"])
                    - top,
                ),
            )
            bottom_right_exclusion_left = max(
                0,
                min(
                    result.shape[1],
                    int(width * self.profile["bottom_right_ui_exclusion_left_fraction"])
                    - left,
                ),
            )
            if (
                bottom_right_exclusion_start < result.shape[0]
                and bottom_right_exclusion_left < result.shape[1]
            ):
                result[
                    bottom_right_exclusion_start:,
                    bottom_right_exclusion_left:,
                ] = False
            return result

        mask = exclude_native_ui(
            yellow_mask if expected_indicator == "yellow" else combat_red_mask
        )
        nameplate_mask = exclude_native_ui(yellow_mask)
        components = _components(
            mask,
            offset_x=left,
            offset_y=top,
            minimum_pixels=self.profile["minimum_component_pixels"],
            maximum_foreground_pixels=self.profile["maximum_foreground_pixels"],
            maximum_component_pixels=self.profile["maximum_component_pixels"],
            maximum_components=self.profile["maximum_components"],
            deadline_s=deadline_s,
        )
        ring_clusters = _cluster_ring_components(
            components,
            frame_width=width,
            frame_height=height,
            profile=self.profile,
            deadline_s=deadline_s,
        )
        detection_method = "selection_circle"
        detection_confidence = 0.95
        if not ring_clusters:
            thin_components = _components(
                mask,
                offset_x=left,
                offset_y=top,
                minimum_pixels=1,
                maximum_foreground_pixels=self.profile["maximum_foreground_pixels"],
                maximum_component_pixels=self.profile["maximum_component_pixels"],
                maximum_components=self.profile["maximum_components"],
                deadline_s=deadline_s,
                require_2x2_support=False,
            )
            ring_clusters = _cluster_ring_components(
                thin_components,
                frame_width=width,
                frame_height=height,
                profile=self.profile,
                deadline_s=deadline_s,
            )
            detection_method = "distant_selection_arc"
            detection_confidence = 0.90
        if ring_clusters:
            observed_s = float(combat_observation["timing"]["observed_monotonic_s"])
            target_crc16 = int(target["identity_crc16"])
            continuity_candidates = ring_clusters
            continuity_active = False
            if (
                self._continuity_target_crc16 == target_crc16
                and self._continuity_center_x is not None
                and self._continuity_observed_s is not None
                and 0.0 <= observed_s - self._continuity_observed_s
                <= self.profile["continuity_max_age_ms"] / 1000.0
            ):
                continuity_active = True
                maximum_delta_px = (
                    width * self.profile["continuity_max_offset_delta"] / 2.0
                )
                continuity_candidates = [
                    item
                    for item in ring_clusters
                    if abs(item[0] - self._continuity_center_x) <= maximum_delta_px
                ]
                if not continuity_candidates:
                    return self._observation(
                        manifest,
                        combat_observation,
                        observation_id=observation_id,
                        tracking_state="AMBIGUOUS",
                        reason="selected_target_bearing_discontinuous",
                    )
                continuity_candidates = sorted(
                    continuity_candidates,
                    key=lambda item: (
                        abs(item[0] - self._continuity_center_x),
                        -(item[2] * item[3]),
                    ),
                )
                # Only one native selection circle can belong to the same
                # selected target.  Once exact target continuity exists, use
                # the closest plausible fragment; other same-colour geometry
                # cannot overrule that established lock.  An impossible jump
                # above maximum_delta_px still fails ambiguous above.
                continuity_candidates = continuity_candidates[:1]
            ring_clusters = continuity_candidates
            # A distant selected unit can yield two strong horizontal traces:
            # its orange ground arc and the hostile name text above it.  When
            # those traces share the same horizontal bearing they corroborate
            # one unit; only spatially separated strong candidates are
            # ambiguous.
            if (
                len(ring_clusters) > 1
                and ring_clusters[1][2] * ring_clusters[1][3]
                >= ring_clusters[0][2] * ring_clusters[0][3] * 0.75
                and abs(ring_clusters[1][0] - ring_clusters[0][0])
                > width * self.profile["ring_cluster_gap_fraction"]
            ):
                return self._observation(
                    manifest,
                    combat_observation,
                    observation_id=observation_id,
                    tracking_state="AMBIGUOUS",
                    reason="multiple_selection_circle_candidates",
                )
            raw_center_x = ring_clusters[0][0]
            raw_center_y = ring_clusters[0][1]
            # The circle proves which world unit is selected, but a huge or
            # partially occluded model can expose only one unstable arc.  For
            # neutral/yellow units, fuse that exact selection witness with the
            # closest visible yellow nameplate and steer by the plate center.
            if reaction == 4 and expected_indicator == "red":
                nameplate_components = _components(
                    nameplate_mask,
                    offset_x=left,
                    offset_y=top,
                    minimum_pixels=self.profile["minimum_component_pixels"],
                    maximum_foreground_pixels=self.profile["maximum_foreground_pixels"],
                    maximum_component_pixels=self.profile["maximum_component_pixels"],
                    maximum_components=self.profile["maximum_components"],
                    deadline_s=deadline_s,
                )
                nameplate_top = height * self.profile["nameplate_top_fraction"]
                nameplate_bottom = height * self.profile["nameplate_bottom_fraction"]
                nameplates = [
                    item
                    for item in nameplate_components
                    if nameplate_top <= item.center_y <= nameplate_bottom
                    and item.pixels >= self.profile["nameplate_minimum_pixels"]
                    and item.width
                    >= width * self.profile["nameplate_minimum_width_fraction"]
                    and item.height
                    <= height * self.profile["nameplate_maximum_height_fraction"]
                ]
                if nameplates:
                    closest_nameplate = min(
                        nameplates,
                        key=lambda item: abs(item.center_x - raw_center_x),
                    )
                    if (
                        abs(closest_nameplate.center_x - raw_center_x)
                        <= width * self.profile["continuity_max_offset_delta"] / 2.0
                    ):
                        raw_center_x = closest_nameplate.center_x
                        detection_method = "selection_circle_nameplate_fusion"
                        detection_confidence = 0.98
            stable_center_x = (
                raw_center_x
                if not continuity_active or self._continuity_center_x is None
                else CONTINUITY_CENTER_ALPHA * raw_center_x
                + (1.0 - CONTINUITY_CENTER_ALPHA) * self._continuity_center_x
            )
            stable_center_y = (
                raw_center_y
                if not continuity_active or self._continuity_center_y is None
                else CONTINUITY_CENTER_ALPHA * raw_center_y
                + (1.0 - CONTINUITY_CENTER_ALPHA) * self._continuity_center_y
            )
            self._continuity_target_crc16 = target_crc16
            self._continuity_center_x = stable_center_x
            self._continuity_center_y = stable_center_y
            self._continuity_observed_s = observed_s
            return self._visible_observation(
                manifest,
                combat_observation,
                observation_id=observation_id,
                center_x=stable_center_x,
                center_y=stable_center_y,
                method=detection_method,
                confidence=detection_confidence,
            )
        nameplate_top = height * self.profile["nameplate_top_fraction"]
        nameplate_bottom = height * self.profile["nameplate_bottom_fraction"]
        nameplates = [
            item
            for item in components
            if nameplate_top <= item.center_y <= nameplate_bottom
            and item.pixels >= self.profile["nameplate_minimum_pixels"]
            and item.width >= width * self.profile["nameplate_minimum_width_fraction"]
            and item.height <= height * self.profile["nameplate_maximum_height_fraction"]
        ]
        # A hostile nameplate is not bound to the selected unit.  Even a
        # unique plate can belong to a bystander while another off-screen unit
        # remains selected, so it may only explain ambiguity and never provide
        # an executable bearing.
        return self._observation(
            manifest,
            combat_observation,
            observation_id=observation_id,
            tracking_state="AMBIGUOUS" if nameplates else "LOST",
            reason=(
                "multiple_nameplate_candidates"
                if len(nameplates) > 1
                else "unbound_nameplate_not_selected_target_evidence"
                if nameplates
                else "selected_target_indicator_not_visible"
            ),
        )

    def _reset_continuity(self) -> None:
        self._continuity_target_crc16 = None
        self._continuity_center_x = None
        self._continuity_center_y = None
        self._continuity_observed_s = None

    def _visible_observation(
        self,
        manifest: dict[str, Any],
        combat_observation: dict[str, Any],
        *,
        observation_id: str,
        center_x: float,
        center_y: float,
        method: str,
        confidence: float,
    ) -> dict[str, Any]:
        frame_center = manifest["image"]["width"] / 2.0
        offset = max(-1.0, min(1.0, (center_x - frame_center) / frame_center))
        tolerance = self.profile["center_tolerance_fraction"]
        direction = "LEFT" if offset < -tolerance else "RIGHT" if offset > tolerance else "CENTER"
        return self._observation(
            manifest,
            combat_observation,
            observation_id=observation_id,
            tracking_state="VISIBLE",
            reason=f"{method}_bearing_observed",
            detection_method=method,
            direction=direction,
            offset_x_normalized=offset,
            center_x_px=center_x,
            center_y_px=center_y,
            confidence=confidence,
        )

    def _observation(
        self,
        manifest: dict[str, Any],
        combat_observation: dict[str, Any],
        *,
        observation_id: str,
        tracking_state: str,
        reason: str,
        detection_method: str | None = None,
        direction: str | None = None,
        offset_x_normalized: float | None = None,
        center_x_px: float | None = None,
        center_y_px: float | None = None,
        confidence: float = 0.0,
    ) -> dict[str, Any]:
        combat_hash = _canonical_sha256(combat_observation)
        target = combat_observation["target"]
        capture_origin = manifest["provenance"]["origin"]
        scope = (
            "synthetic_fixture"
            if capture_origin == "replay_fixture"
            else "lab_evaluation_only"
            if manifest["decision_context"] == "lab_clone"
            else "unpromoted_evaluation_only"
        )
        combat_timing = combat_observation["timing"]
        captured_s = float(combat_timing["monotonic_timestamp_s"])
        observed_s = float(combat_timing["observed_monotonic_s"])
        expires_s = min(
            float(combat_timing["expires_monotonic_s"]),
            captured_s + self.profile["freshness_limit_ms"] / 1000.0,
        )
        result = {
            "record_type": "selected_target_bearing_observation",
            "schema_version": "1.0",
            "observation_id": observation_id,
            "frame_id": manifest["frame_id"],
            "combat_observation_id": combat_observation["observation_id"],
            "combat_observation_sha256": combat_hash,
            "target_identity_crc16": None if target is None else target["identity_crc16"],
            "target_profile": manifest["target_profile"],
            "actor_binding": copy.deepcopy(manifest["actor_binding"]),
            "authorization_sha256": manifest["authorization_sha256"],
            "client_build": manifest["client_build"],
            "build_signature": manifest["build_signature"],
            "tracking_state": tracking_state,
            "reason": reason,
            "detection_method": detection_method,
            "direction": direction,
            "offset_x_normalized": offset_x_normalized,
            "center_x_px": center_x_px,
            "center_y_px": center_y_px,
            "frame_center_x_px": manifest["image"]["width"] / 2.0,
            "frame_height_px": manifest["image"]["height"],
            "confidence": confidence,
            "timing": {
                "captured_at": combat_timing["captured_at"],
                "monotonic_timestamp_s": captured_s,
                "frame_age_ms": combat_timing["frame_age_ms"],
                "observed_monotonic_s": observed_s,
                "age_at_observation_ms": combat_timing["age_at_observation_ms"],
                "freshness_limit_ms": self.profile["freshness_limit_ms"],
                "expires_monotonic_s": expires_s,
            },
            "provenance": {
                "origin": "visible_selected_target_indicator",
                "capture_origin": capture_origin,
                "capability": "selected_target_visual_bearing_read_only",
                "scope": scope,
                "profile_id": self.profile["profile"],
                "profile_version": self.profile["profile_version"],
                "profile_sha256": self.profile_sha256,
                "calibration_state": self.profile["calibration_state"],
                "evidence_refs": [
                    manifest["frame_id"],
                    combat_observation["observation_id"],
                    f"sha256:{combat_hash}",
                    f"profile:{self.profile['profile']}:sha256:{self.profile_sha256}",
                ],
            },
            "execution_authority": False,
        }
        self.bearing_validator.validate(result)
        validate_selected_target_bearing_semantics(result)
        return result
