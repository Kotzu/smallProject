from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from perfect_assassin.adapter.coordinate_hud import (
    MAGIC,
    PROTOCOL_VERSION,
    CoordinateHudProtocolError,
    bits_to_packet,
    decode_packet,
    validate_valid_observation_semantics,
)
from perfect_assassin.contract_validation import ContractValidator


class CoordinateHudDetectionError(ValueError):
    pass


def _finite_number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise CoordinateHudDetectionError(
            f"{label} must be finite and at least {minimum:g}"
        )
    return float(value)


def load_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("protocol_version") != PROTOCOL_VERSION or profile.get("magic") != MAGIC:
        raise CoordinateHudDetectionError("unsupported coordinate HUD profile")
    return profile


def _assert_deadline(deadline_s: float, monotonic: Any = time.perf_counter) -> None:
    if monotonic() > deadline_s:
        raise CoordinateHudDetectionError("coordinate HUD detector operation budget exceeded")


def _components(
    mask: np.ndarray,
    *,
    minimum_pixels: int = 4,
    maximum_foreground_pixels: int,
    maximum_component_pixels: int,
    maximum_components: int,
    deadline_s: float,
) -> list[tuple[float, float, int]]:
    foreground_pixels = int(np.count_nonzero(mask))
    if foreground_pixels > maximum_foreground_pixels:
        raise CoordinateHudDetectionError("marker foreground pixel budget exceeded")
    _assert_deadline(deadline_s)

    # A rendered fiducial has area in both axes. Single-pixel and one-pixel-wide
    # fragments are common in game-world foliage and UI text, but can never be
    # one of the square corner markers. Remove those fragments with a bounded,
    # vectorized 2x2-support pass before counting connected components. The
    # original foreground budget above still rejects large solid-color input,
    # and repeated 2x2 adversarial blocks still consume the component budget.
    supported = np.zeros_like(mask, dtype=bool)
    if mask.shape[0] >= 2 and mask.shape[1] >= 2:
        block = (
            mask[:-1, :-1]
            & mask[1:, :-1]
            & mask[:-1, 1:]
            & mask[1:, 1:]
        )
        supported[:-1, :-1] |= block
        supported[1:, :-1] |= block
        supported[:-1, 1:] |= block
        supported[1:, 1:] |= block
    mask = supported

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    result: list[tuple[float, float, int]] = []
    nonzero_y, nonzero_x = np.nonzero(mask)
    components_seen = 0
    for y, x in zip(nonzero_y, nonzero_x, strict=True):
        if visited[y, x]:
            continue
        components_seen += 1
        if components_seen > maximum_components:
            raise CoordinateHudDetectionError("marker component count budget exceeded")
        _assert_deadline(deadline_s)
        stack = [(int(y), int(x))]
        visited[y, x] = True
        count = 0
        sum_x = 0
        sum_y = 0
        oversized = False
        while stack:
            current_y, current_x = stack.pop()
            count += 1
            if count > maximum_component_pixels:
                oversized = True
            sum_x += current_x
            sum_y += current_y
            if count % 128 == 0:
                _assert_deadline(deadline_s)
            for next_y, next_x in (
                (current_y - 1, current_x),
                (current_y + 1, current_x),
                (current_y, current_x - 1),
                (current_y, current_x + 1),
            ):
                if 0 <= next_y < height and 0 <= next_x < width and mask[next_y, next_x] and not visited[next_y, next_x]:
                    visited[next_y, next_x] = True
                    stack.append((next_y, next_x))
        # The total foreground and component-count budgets above bound the full
        # traversal. A connected region larger than a possible square marker is
        # a world/UI distractor, not a reason to hide otherwise valid fiducials.
        if not oversized and count >= minimum_pixels:
            result.append(
                (
                    sum_x / count,
                    sum_y / count,
                    count,
                )
            )
    return result


def locate_visible_hud_markers(
    frame: np.ndarray,
    profile: dict[str, Any],
    *,
    deadline_s: float,
    search_window_fraction: tuple[float, float, float, float] | None = None,
) -> tuple[tuple[float, float, int], ...] | None:
    """Locate the shared visible-HUD fiducials under bounded work limits."""

    left_fraction, top_fraction, right_fraction, bottom_fraction = (
        (0.0, 0.0, profile["search_width_fraction"], profile["search_height_fraction"])
        if search_window_fraction is None
        else search_window_fraction
    )
    search_left = max(0, int(frame.shape[1] * left_fraction))
    search_top = max(0, int(frame.shape[0] * top_fraction))
    search_right = max(search_left + 1, int(frame.shape[1] * right_fraction))
    search_bottom = max(search_top + 1, int(frame.shape[0] * bottom_fraction))
    bgr = frame[search_top:search_bottom, search_left:search_right, :3]
    high = profile["marker_high_threshold"]
    low = profile["marker_low_threshold"]
    blue, green, red = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
    masks = (
        (blue >= high) & (green >= high) & (red <= low),
        (blue >= high) & (green <= low) & (red >= high),
        (blue <= low) & (green >= high) & (red >= high),
        (blue <= low) & (green >= high) & (red <= low),
    )
    candidate_limit = int(profile["maximum_marker_candidates_per_color"])
    groups = []
    for mask in masks:
        local_components = _components(
                mask,
                maximum_foreground_pixels=int(
                    profile["maximum_marker_foreground_pixels"]
                ),
                maximum_component_pixels=int(
                    profile["maximum_marker_component_pixels"]
                ),
                maximum_components=int(
                    profile["maximum_marker_components_per_color"]
                ),
                deadline_s=deadline_s,
            )
        global_components = [
            (x + search_left, y + search_top, pixels)
            for x, y, pixels in local_components
        ]
        groups.append(sorted(
            global_components,
            key=lambda item: (-item[2], item[1], item[0]),
        )[:candidate_limit])
    if any(not group for group in groups):
        return None
    best: tuple[float, tuple[tuple[float, float, int], ...]] | None = None
    expected_ratio = profile["fiducial_dx_px"] / profile["fiducial_dy_px"]
    for cyan in groups[0]:
        _assert_deadline(deadline_s)
        for magenta in groups[1]:
            dx = magenta[0] - cyan[0]
            if dx <= 0:
                continue
            for yellow in groups[2]:
                dy = yellow[1] - cyan[1]
                if dy <= 0:
                    continue
                for green_marker in groups[3]:
                    error = (
                        abs(magenta[1] - cyan[1])
                        + abs(yellow[0] - cyan[0])
                        + abs(green_marker[0] - magenta[0])
                        + abs(green_marker[1] - yellow[1])
                        + abs((dx / dy) - expected_ratio) * 5
                    )
                    candidate = (cyan, magenta, yellow, green_marker)
                    if best is None or error < best[0]:
                        best = (error, candidate)
    if best is None or best[0] > profile["maximum_fiducial_error_px"]:
        return None
    return best[1]


class CoordinateHudDetector:
    def __init__(
        self,
        profile: dict[str, Any],
        capture_validator: ContractValidator,
        observation_validator: ContractValidator,
        *,
        search_window_fraction: tuple[float, float, float, float] | None = None,
        reuse_marker_geometry: bool = False,
    ) -> None:
        self.profile = copy.deepcopy(profile)
        canonical_profile = json.dumps(
            self.profile,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.profile_sha256 = hashlib.sha256(canonical_profile).hexdigest().upper()
        self.capture_validator = capture_validator
        self.observation_validator = observation_validator
        if search_window_fraction is not None:
            if (
                len(search_window_fraction) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in search_window_fraction
                )
                or not 0 <= float(search_window_fraction[0]) < float(search_window_fraction[2]) <= float(self.profile["search_width_fraction"])
                or not 0 <= float(search_window_fraction[1]) < float(search_window_fraction[3]) <= float(self.profile["search_height_fraction"])
            ):
                raise CoordinateHudDetectionError("coordinate HUD fast search window is invalid")
            self._search_window_fraction = (
                *(float(value) for value in search_window_fraction),
            )
        else:
            self._search_window_fraction = None
        if not isinstance(reuse_marker_geometry, bool):
            raise CoordinateHudDetectionError("reuse_marker_geometry must be boolean")
        self._reuse_marker_geometry = reuse_marker_geometry
        self._cached_markers: tuple[tuple[float, float, int], ...] | None = None
        self._cached_frame_shape: tuple[int, ...] | None = None
        _finite_number(
            self.profile["freshness_limit_ms"],
            "coordinate HUD profile freshness_limit_ms",
            minimum=0.000001,
        )
        _finite_number(
            self.profile["detector_deadline_ms"],
            "coordinate HUD profile detector_deadline_ms",
            minimum=0.000001,
        )

    def detect(
        self,
        manifest: dict[str, Any],
        frame: np.ndarray,
        *,
        observation_id: str,
    ) -> dict[str, Any]:
        self.capture_validator.validate(manifest)
        timing = manifest["timing"]
        _finite_number(
            timing["monotonic_timestamp_s"],
            "capture monotonic_timestamp_s",
        )
        _finite_number(timing["frame_age_ms"], "capture frame_age_ms")
        if timing["source_timestamp_s"] is not None:
            _finite_number(
                timing["source_timestamp_s"],
                "capture source_timestamp_s",
            )
        _finite_number(
            manifest["provenance"]["confidence"],
            "capture provenance confidence",
            minimum=0.000001,
        )
        if manifest["client_build"] != self.profile["client_build"]:
            raise CoordinateHudDetectionError("client_build does not match HUD profile")
        expected_shape = (manifest["image"]["height"], manifest["image"]["width"], 4)
        if frame.shape != expected_shape or frame.dtype != np.uint8:
            raise CoordinateHudDetectionError("BGRA8 frame shape or dtype mismatch")
        if frame.shape[0] * frame.shape[1] > int(self.profile["maximum_frame_pixels"]):
            raise CoordinateHudDetectionError("capture frame exceeds detector pixel budget")
        if manifest["timing"]["frame_age_ms"] > self.profile["freshness_limit_ms"]:
            return self._observation(
                manifest,
                observation_id,
                "DEGRADED",
                "capture_frame_stale",
                None,
                None,
                0.0,
            )

        deadline_s = time.perf_counter() + float(
            self.profile["detector_deadline_ms"]
        ) / 1000.0
        markers = self._locate_markers(frame, deadline_s=deadline_s)
        if markers is None:
            return self._observation(manifest, observation_id, "NOT_FOUND", "fiducials_not_found", None, None, 0.0)
        cyan, magenta, yellow, _green = markers
        scale_x = (magenta[0] - cyan[0]) / self.profile["fiducial_dx_px"]
        scale_y = (yellow[1] - cyan[1]) / self.profile["fiducial_dy_px"]
        scale = (scale_x + scale_y) / 2
        pitch = self.profile["cell_pitch_px"] * scale
        first_x = cyan[0] + self.profile["first_cell_dx_px"] * scale
        first_y = cyan[1] + self.profile["first_cell_dy_px"] * scale
        bits: list[int] = []
        for row in range(int(self.profile["grid_rows"])):
            for column in range(16):
                _assert_deadline(deadline_s)
                x = int(round(first_x + column * pitch))
                y = int(round(first_y + row * pitch))
                radius = max(1, int(round(scale)))
                sample = frame[max(0, y - radius) : y + radius + 1, max(0, x - radius) : x + radius + 1, :3]
                if sample.size == 0:
                    return self._observation(manifest, observation_id, "INVALID", "payload_out_of_frame", None, None, 0.0)
                bits.append(int(float(sample.mean()) >= self.profile["bit_luminance_threshold"]))
        raw_packet = bits_to_packet(bits)
        try:
            packet = decode_packet(raw_packet)
        except CoordinateHudProtocolError as error:
            return self._observation(manifest, observation_id, "INVALID", str(error), raw_packet.hex(), None, 0.0)

        position = None
        state = "DEGRADED"
        reason = "position_unavailable"
        confidence = 0.7
        if packet.position_available:
            position = {
                "coordinate_space": "normalized_current_zone_map",
                "x": packet.x,
                "y": packet.y,
                "continent_index": packet.continent_index,
                "zone_index": packet.zone_index,
            }
            if packet.facing_available:
                position["facing_rad"] = packet.facing_rad
            state = "VALID"
            reason = "crc_valid_position_observed"
            confidence = 1.0
        protocol = {
            "magic": MAGIC,
            "version": PROTOCOL_VERSION,
            "sequence": packet.sequence,
            "flags": raw_packet[2],
            "crc_valid": True,
            "packet_hex": raw_packet.hex(),
        }
        return self._observation(
            manifest,
            observation_id,
            state,
            reason,
            raw_packet.hex(),
            protocol,
            confidence,
            position,
            {
                "dead_or_ghost": packet.player_dead_or_ghost,
                "ghost": packet.player_ghost,
            },
        )

    def _locate_markers(
        self,
        frame: np.ndarray,
        *,
        deadline_s: float,
    ) -> tuple[tuple[float, float, int], ...] | None:
        if (
            self._reuse_marker_geometry
            and self._cached_markers is not None
            and self._cached_frame_shape == frame.shape
            and self._cached_markers_are_visible(frame)
        ):
            return self._cached_markers
        markers = locate_visible_hud_markers(
            frame,
            self.profile,
            deadline_s=deadline_s,
            search_window_fraction=self._search_window_fraction,
        )
        if self._reuse_marker_geometry:
            self._cached_markers = markers
            self._cached_frame_shape = frame.shape if markers is not None else None
        return markers

    def _cached_markers_are_visible(self, frame: np.ndarray) -> bool:
        assert self._cached_markers is not None
        high = float(self.profile["marker_high_threshold"])
        low = float(self.profile["marker_low_threshold"])
        expected = (
            (True, True, False),
            (True, False, True),
            (False, True, True),
            (False, True, False),
        )
        height, width = frame.shape[:2]
        for marker, channel_high in zip(
            self._cached_markers,
            expected,
            strict=True,
        ):
            x, y = int(round(marker[0])), int(round(marker[1]))
            if not (1 <= x < width - 1 and 1 <= y < height - 1):
                return False
            # Cached geometry is only trusted while every marker still has a
            # solid 3x3 core in its exact protocol colour. This check is
            # deliberately stricter and cheaper than full scene relocalization.
            mean_bgr = frame[y - 1 : y + 2, x - 1 : x + 2, :3].mean(axis=(0, 1))
            for value, should_be_high in zip(mean_bgr, channel_high, strict=True):
                if should_be_high and value < high:
                    return False
                if not should_be_high and value > low:
                    return False
        return True

    def _observation(
        self,
        manifest: dict[str, Any],
        observation_id: str,
        state: str,
        reason: str,
        packet_hex: str | None,
        protocol: dict[str, Any] | None,
        confidence: float,
        position: dict[str, Any] | None = None,
        player_state: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        capture_origin = manifest["provenance"]["origin"]
        decision_context = manifest["decision_context"]
        calibration_state = self.profile["calibration_state"]
        if capture_origin == "replay_fixture":
            scope = "synthetic_fixture"
        elif decision_context == "lab_clone":
            scope = "lab_evaluation_only"
        else:
            scope = "unpromoted_evaluation_only"
        profile_ref = (
            f"profile:{self.profile['profile']}:sha256:{self.profile_sha256}"
        )
        evidence_refs: list[str] = []
        for reference in (
            manifest["frame_id"],
            *manifest["provenance"]["evidence_refs"],
            profile_ref,
        ):
            if reference not in evidence_refs:
                evidence_refs.append(reference)
        result = {
            "record_type": "coordinate_hud_observation",
            "schema_version": "2.0",
            "observation_id": observation_id,
            "frame_id": manifest["frame_id"],
            "session_id": manifest["session_id"],
            "target_profile": manifest["target_profile"],
            "actor_binding": copy.deepcopy(manifest["actor_binding"]),
            "authorization_sha256": manifest["authorization_sha256"],
            "decision_context": decision_context,
            "client_build": manifest["client_build"],
            "build_signature": manifest["build_signature"],
            "tracking_state": state,
            "reason": reason,
            "confidence": confidence,
            "timing": {
                "captured_at": manifest["timing"]["captured_at"],
                "monotonic_timestamp_s": manifest["timing"]["monotonic_timestamp_s"],
                "frame_age_ms": manifest["timing"]["frame_age_ms"],
                "observed_monotonic_s": (
                    manifest["timing"]["monotonic_timestamp_s"]
                    + manifest["timing"]["frame_age_ms"] / 1000.0
                ),
                "age_at_observation_ms": manifest["timing"]["frame_age_ms"],
                "freshness_limit_ms": self.profile["freshness_limit_ms"],
                "expires_monotonic_s": (
                    manifest["timing"]["monotonic_timestamp_s"]
                    + self.profile["freshness_limit_ms"] / 1000.0
                ),
            },
            "protocol": protocol,
            "position": position,
            "map_position_available": position is not None,
            "player_state": player_state,
            "provenance": {
                "origin": "visible_addon_hud",
                "capture_origin": capture_origin,
                "capability": "self_map_position",
                "scope": scope,
                "profile_id": self.profile["profile"],
                "profile_version": self.profile["profile_version"],
                "profile_sha256": self.profile_sha256,
                "profile_calibration_state": calibration_state,
                "evidence_refs": evidence_refs,
            },
            "execution_authority": False,
        }
        self.observation_validator.validate(result)
        if state == "VALID":
            validate_valid_observation_semantics(result)
        return result
