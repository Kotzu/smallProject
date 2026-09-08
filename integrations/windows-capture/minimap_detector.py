from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite, pi, radians
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class MinimapDetectionError(ValueError):
    """Raised when minimap detection cannot safely inspect the supplied frame."""


@dataclass(frozen=True, slots=True)
class CircleCandidate:
    center_x_px: float
    center_y_px: float
    radius_px: float
    ring_coverage: float
    confidence: float


@dataclass(frozen=True, slots=True)
class MarkerCandidate:
    center_x_px: float
    center_y_px: float
    orientation_deg_screen: float | None
    pixel_count: int
    confidence: float
    detection_model: str = "profile_color"


def load_profile(path: Path, validator) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    validator.validate(profile)
    _validate_profile_relationships(profile)
    return profile


def _validate_profile_relationships(profile: Mapping[str, Any]) -> None:
    search = profile["search_region"]
    if search["x"] + search["width"] > 1 or search["y"] + search["height"] > 1:
        raise MinimapDetectionError("Minimap search region exceeds the client frame")
    circle = profile["circle"]
    if circle["radius_fraction_min"] >= circle["radius_fraction_max"]:
        raise MinimapDetectionError("Minimap radius range is empty")
    marker = profile["marker"]
    if marker["min_pixels"] >= marker["max_pixels"]:
        raise MinimapDetectionError("Marker pixel range is empty")
    if any(
        lower > upper
        for lower, upper in zip(
            marker["color_bgr_min"], marker["color_bgr_max"], strict=True
        )
    ):
        raise MinimapDetectionError("Marker color range is inverted")
    neutral = marker["neutral_model"]
    if neutral["min_pixels"] >= neutral["max_pixels"]:
        raise MinimapDetectionError("Neutral marker pixel range is empty")
    heading = profile["heading_calibration"]
    if heading["screen_orientation_sign"] not in {-1, 1}:
        raise MinimapDetectionError("Heading screen-orientation sign is invalid")
    if profile["calibration_state"] == "controlled_live_verified" and len(
        heading["evidence_refs"]
    ) < 2:
        raise MinimapDetectionError("Live heading calibration evidence is incomplete")


def world_heading_from_marker(
    marker: MarkerCandidate,
    profile: Mapping[str, Any],
) -> float:
    """Convert the build-calibrated minimap model angle to world yaw.

    The TBC player arrow is a rendered MDX model rather than a flat texture,
    so its principal visual axis has a small, build-specific offset from the
    world-facing axis.  The profile stores only that client presentation
    calibration; no route, zone destination, or server state is involved.
    """

    if not isinstance(marker, MarkerCandidate):
        raise MinimapDetectionError("Heading conversion requires one marker candidate")
    if marker.detection_model != "neutral_mdx":
        raise MinimapDetectionError("World heading requires the calibrated neutral MDX marker")
    orientation = marker.orientation_deg_screen
    if orientation is None or not isfinite(orientation):
        raise MinimapDetectionError("Minimap marker has no usable orientation")
    calibration = profile["heading_calibration"]
    if marker.confidence < calibration["minimum_marker_confidence"]:
        raise MinimapDetectionError("Minimap marker confidence is below heading calibration")
    heading = (
        float(calibration["screen_orientation_sign"]) * radians(orientation)
        + float(calibration["offset_rad"])
    )
    return heading % (2 * pi)


class MinimapVisionDetector:
    """Find minimap UI geometry without claiming an absolute world pose."""

    detector_id = "pa_numpy_minimap_geometry"
    version = "0.4.0"

    def __init__(self, profile, capture_validator, observation_validator) -> None:
        owned = copy.deepcopy(dict(profile))
        observation_validator.validate(owned)
        _validate_profile_relationships(owned)
        if owned["record_type"] != "minimap_roi_profile":
            raise MinimapDetectionError("Expected a minimap ROI profile")
        self.profile = owned
        self._capture_validator = capture_validator
        self._observation_validator = observation_validator
        self._cached_circle: CircleCandidate | None = None
        self._cached_frame_shape: tuple[int, ...] | None = None

    def detect(
        self,
        manifest: Mapping[str, Any],
        pixels: memoryview | np.ndarray | None,
        *,
        observation_id: str,
    ) -> dict[str, Any]:
        if not observation_id:
            raise MinimapDetectionError("observation_id cannot be empty")
        self._capture_validator.validate(manifest)
        self._require_matching_identity(manifest)
        provenance_scope = self._provenance_scope(manifest)
        frame = self._view_bgra(manifest, pixels)
        if (
            self._cached_circle is not None
            and self._cached_frame_shape == frame.shape
        ):
            circle = self._cached_circle
        else:
            circle = self._find_circle(frame)
            self._cached_circle = circle
            self._cached_frame_shape = frame.shape if circle is not None else None
        marker = self._find_marker(frame, circle) if circle is not None else None

        if circle is None:
            state = "NOT_FOUND"
            confidence = 0.0
            reasons = ["minimap_circle_not_found"]
        elif marker is None:
            state = "DEGRADED"
            confidence = circle.confidence
            reasons = [
                "minimap_circle_found",
                "player_marker_not_found",
                "absolute_pose_unavailable",
            ]
        else:
            state = "FOUND"
            confidence = min(circle.confidence, marker.confidence)
            reasons = [
                "minimap_circle_found",
                "player_marker_found",
                "absolute_pose_unavailable",
            ]

        observation = {
            "record_type": "minimap_visual_observation",
            "schema_version": "1.0",
            "observation_id": observation_id,
            "session_id": manifest["session_id"],
            "target_profile": manifest["target_profile"],
            "authorization_sha256": manifest["authorization_sha256"],
            "actor_binding": copy.deepcopy(manifest["actor_binding"]),
            "decision_context": manifest["decision_context"],
            "client_build": manifest["client_build"],
            "build_signature": manifest["build_signature"],
            "frame_id": manifest["frame_id"],
            "profile_id": self.profile["profile_id"],
            "profile_version": self.profile["profile_version"],
            "detector_id": self.detector_id,
            "detector_version": self.version,
            "tracking_state": state,
            "minimap": self._circle_record(circle),
            "player_marker": self._marker_record(marker),
            "absolute_pose_available": False,
            "confidence": confidence,
            "reason_codes": reasons,
            "provenance": {
                "origin": manifest["provenance"]["origin"],
                "capability": "minimap_visual_localization",
                "scope": provenance_scope,
                "evidence_refs": list(
                    dict.fromkeys(
                        [manifest["frame_id"], *manifest["provenance"]["evidence_refs"]]
                    )
                ),
            },
            "execution_authority": False,
            "created_at": manifest["timing"]["captured_at"],
        }
        self._observation_validator.validate(observation)
        return observation

    def _require_matching_identity(self, manifest: Mapping[str, Any]) -> None:
        for field in ("target_profile", "client_build", "build_signature"):
            if manifest[field] != self.profile[field]:
                raise MinimapDetectionError(f"Minimap profile mismatch: {field}")
        image = manifest["image"]
        if image["pixel_format"] != self.profile["pixel_format"]:
            raise MinimapDetectionError("Minimap profile pixel format mismatch")
        actor_binding = manifest["actor_binding"]
        if actor_binding["decision_context"] != manifest["decision_context"]:
            raise MinimapDetectionError("Minimap actor binding context mismatch")

    @staticmethod
    def _provenance_scope(manifest: Mapping[str, Any]) -> str:
        origin = manifest["provenance"]["origin"]
        context = manifest["decision_context"]
        assurance = manifest["actor_binding"]["binding_assurance"]["state"]
        if origin == "replay_fixture":
            expected = "synthetic_fixture"
        elif origin == "window_capture" and context == "lab_clone":
            expected = "lab_evaluation_only"
        elif (
            origin == "window_capture"
            and context == "champion"
            and assurance == "configured_expected_only"
        ):
            expected = "unpromoted_evaluation_only"
        else:
            raise MinimapDetectionError(
                "Minimap capture provenance has no allowed actor-bound scope"
            )
        if manifest["provenance"]["scope"] != expected:
            raise MinimapDetectionError(
                "Minimap capture provenance scope does not match its source and actor"
            )
        return expected

    @staticmethod
    def _view_bgra(
        manifest: Mapping[str, Any], pixels: memoryview | np.ndarray | None
    ) -> np.ndarray:
        if pixels is None:
            raise MinimapDetectionError("Minimap detection requires caller-owned pixels")
        image = manifest["image"]
        width = int(image["width"])
        height = int(image["height"])
        stride = int(image["row_stride_bytes"])
        if stride < width * 4:
            raise MinimapDetectionError("BGRA row stride is smaller than the image width")
        if isinstance(pixels, np.ndarray):
            if pixels.dtype != np.uint8 or pixels.shape != (height, width, 4):
                raise MinimapDetectionError("NumPy frame must be uint8 HxWx4 BGRA")
            return pixels
        raw = np.frombuffer(pixels, dtype=np.uint8)
        expected = height * stride
        if raw.size != expected:
            raise MinimapDetectionError(
                f"BGRA buffer size mismatch: expected {expected}, got {raw.size}"
            )
        rows = raw.reshape(height, stride)
        return rows[:, : width * 4].reshape(height, width, 4)

    def _find_circle(self, frame: np.ndarray) -> CircleCandidate | None:
        height, width, _ = frame.shape
        scale = min(width, height)
        search = self.profile["search_region"]
        left = max(0, int(round(search["x"] * width)))
        top = max(0, int(round(search["y"] * height)))
        right = min(width, int(round((search["x"] + search["width"]) * width)))
        bottom = min(height, int(round((search["y"] + search["height"]) * height)))
        if right - left < 8 or bottom - top < 8:
            raise MinimapDetectionError("Minimap search region is too small")

        roi = frame[top:bottom, left:right, :3].astype(np.float32)
        gray = roi[:, :, 0] * 0.114 + roi[:, :, 1] * 0.587 + roi[:, :, 2] * 0.299
        grad_y, grad_x = np.gradient(gray)
        magnitude = np.hypot(grad_x, grad_y)
        circle_profile = self.profile["circle"]
        gradient_scale = float(
            np.percentile(magnitude, circle_profile["gradient_percentile"])
        )
        if not isfinite(gradient_scale) or gradient_scale <= 1e-6:
            return None

        min_radius = max(3, int(round(circle_profile["radius_fraction_min"] * scale)))
        max_radius = max(
            min_radius + 1,
            int(round(circle_profile["radius_fraction_max"] * scale)),
        )
        radius_step = max(1, int(round(circle_profile["radius_step_fraction"] * scale)))
        center_step = max(1, int(round(circle_profile["center_step_fraction"] * scale)))
        angles = np.linspace(
            0,
            2 * np.pi,
            int(circle_profile["ring_samples"]),
            endpoint=False,
        )
        cosines = np.cos(angles)
        sines = np.sin(angles)
        best: CircleCandidate | None = None

        for radius in range(min_radius, max_radius + 1, radius_step):
            sample_margin = radius + 1
            x_values = self._grid_values(
                left + sample_margin,
                right - sample_margin - 1,
                center_step,
            )
            y_values = self._grid_values(
                top + sample_margin,
                bottom - sample_margin - 1,
                center_step,
            )
            for center_y in y_values:
                for center_x in x_values:
                    ring_strength = np.zeros_like(angles, dtype=np.float32)
                    for delta in (-1, 0, 1):
                        sample_radius = max(1, radius + delta)
                        sample_x = np.rint(center_x + sample_radius * cosines).astype(int)
                        sample_y = np.rint(center_y + sample_radius * sines).astype(int)
                        strengths = magnitude[sample_y - top, sample_x - left]
                        ring_strength = np.maximum(ring_strength, strengths)
                    coverage = float(np.mean(ring_strength >= gradient_scale))
                    mean_strength = float(np.mean(ring_strength))
                    strength_score = min(1.0, mean_strength / (gradient_scale * 1.5))
                    confidence = 0.7 * coverage + 0.3 * strength_score
                    candidate = CircleCandidate(
                        center_x_px=float(center_x),
                        center_y_px=float(center_y),
                        radius_px=float(radius),
                        ring_coverage=coverage,
                        confidence=confidence,
                    )
                    if best is None or candidate.confidence > best.confidence:
                        best = candidate

        if best is None:
            return None
        if best.ring_coverage < circle_profile["min_ring_coverage"]:
            return None
        if best.confidence < circle_profile["min_confidence"]:
            return None
        return best

    def _find_marker(
        self, frame: np.ndarray, circle: CircleCandidate
    ) -> MarkerCandidate | None:
        neutral = self._find_neutral_marker(frame, circle)
        if neutral is not None:
            return neutral

        marker_profile = self.profile["marker"]
        radius = circle.radius_px * marker_profile["central_radius_fraction"]
        left = max(0, int(circle.center_x_px - radius))
        right = min(frame.shape[1], int(circle.center_x_px + radius + 1))
        top = max(0, int(circle.center_y_px - radius))
        bottom = min(frame.shape[0], int(circle.center_y_px + radius + 1))
        patch = frame[top:bottom, left:right, :3]
        lower = np.asarray(marker_profile["color_bgr_min"], dtype=np.uint8)
        upper = np.asarray(marker_profile["color_bgr_max"], dtype=np.uint8)
        color_mask = np.all((patch >= lower) & (patch <= upper), axis=2)
        yy, xx = np.indices(color_mask.shape)
        global_x = xx + left
        global_y = yy + top
        central_mask = (
            (global_x - circle.center_x_px) ** 2
            + (global_y - circle.center_y_px) ** 2
            <= radius**2
        )
        points_y, points_x = np.nonzero(color_mask & central_mask)
        count = int(points_x.size)
        if count < marker_profile["min_pixels"] or count > marker_profile["max_pixels"]:
            return None

        points = np.column_stack((points_x + left, points_y + top)).astype(np.float64)
        center = points.mean(axis=0)
        centered = points - center
        covariance = centered.T @ centered / max(1, count)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        major_index = int(np.argmax(eigenvalues))
        major = eigenvectors[:, major_index]
        major_variance = float(eigenvalues[major_index])
        minor_variance = float(eigenvalues[1 - major_index])
        anisotropy = (
            0.0
            if major_variance <= 1e-9
            else max(0.0, 1.0 - minor_variance / major_variance)
        )
        orientation: float | None = None
        if anisotropy >= 0.1:
            projections = centered @ major
            if float(projections.max()) < abs(float(projections.min())):
                major = -major
            orientation = degrees(atan2(float(major[0]), -float(major[1])))
            if orientation > 180:
                orientation -= 360
            if orientation < -180:
                orientation += 360

        center_distance = hypot(
            float(center[0] - circle.center_x_px),
            float(center[1] - circle.center_y_px),
        )
        centrality = max(0.0, 1.0 - center_distance / max(1.0, radius))
        pixel_score = min(1.0, count / max(1.0, marker_profile["min_pixels"] * 3))
        confidence = 0.4 * centrality + 0.3 * pixel_score + 0.3 * anisotropy
        if confidence < marker_profile["min_confidence"]:
            return None
        return MarkerCandidate(
            center_x_px=float(center[0]),
            center_y_px=float(center[1]),
            orientation_deg_screen=orientation,
            pixel_count=count,
            confidence=confidence,
            detection_model="profile_color",
        )

    def _find_neutral_marker(
        self, frame: np.ndarray, circle: CircleCandidate
    ) -> MarkerCandidate | None:
        """Detect the neutral-grey TBC MinimapArrow MDX model.

        World-map pixels below the model can have the same grey palette, so
        all thresholded pixels must first form one compact, central connected
        component.  PCA is then applied only to that component; applying it to
        the complete colour mask was the source of the former 90-degree yaw
        error in live WMO tests.
        """

        profile = self.profile["marker"]["neutral_model"]
        radius = circle.radius_px * profile["central_radius_fraction"]
        left = max(0, int(circle.center_x_px - radius))
        right = min(frame.shape[1], int(circle.center_x_px + radius + 1))
        top = max(0, int(circle.center_y_px - radius))
        bottom = min(frame.shape[0], int(circle.center_y_px + radius + 1))
        patch = frame[top:bottom, left:right, :3]
        if patch.size == 0:
            return None
        yy, xx = np.indices(patch.shape[:2])
        global_x = xx + left
        global_y = yy + top
        channel_min = patch.min(axis=2)
        channel_spread = patch.max(axis=2) - channel_min
        mask = (
            (channel_min >= profile["minimum_channel_value"])
            & (channel_spread <= profile["maximum_channel_spread"])
            & (
                (global_x - circle.center_x_px) ** 2
                + (global_y - circle.center_y_px) ** 2
                <= radius**2
            )
        )

        # Require 2x2 support so anti-aliased world-map speckles cannot become
        # tiny orientation candidates.  The real MDX arrow has a solid core.
        supported = np.zeros_like(mask, dtype=bool)
        if mask.shape[0] >= 2 and mask.shape[1] >= 2:
            blocks = (
                mask[:-1, :-1]
                & mask[1:, :-1]
                & mask[:-1, 1:]
                & mask[1:, 1:]
            )
            supported[:-1, :-1] |= blocks
            supported[1:, :-1] |= blocks
            supported[:-1, 1:] |= blocks
            supported[1:, 1:] |= blocks

        candidates: list[MarkerCandidate] = []
        for component in self._connected_point_sets(
            supported,
            left=left,
            top=top,
            maximum_components=64,
            maximum_component_pixels=int(profile["max_pixels"]),
        ):
            count = int(component.shape[0])
            if count < profile["min_pixels"] or count > profile["max_pixels"]:
                continue
            center = component.mean(axis=0)
            center_distance = hypot(
                float(center[0] - circle.center_x_px),
                float(center[1] - circle.center_y_px),
            )
            if center_distance > radius * profile["maximum_center_offset_fraction"]:
                continue
            centered = component - center
            covariance = centered.T @ centered / max(1, count)
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            major_index = int(np.argmax(eigenvalues))
            major_variance = float(eigenvalues[major_index])
            minor_variance = float(eigenvalues[1 - major_index])
            anisotropy = (
                0.0
                if major_variance <= 1e-9
                else max(0.0, 1.0 - minor_variance / major_variance)
            )
            if anisotropy < profile["min_anisotropy"]:
                continue
            major = eigenvectors[:, major_index]
            projections = centered @ major
            if float(projections.max()) < abs(float(projections.min())):
                major = -major
            orientation = degrees(atan2(float(major[0]), -float(major[1])))
            if orientation > 180:
                orientation -= 360
            if orientation < -180:
                orientation += 360
            centrality = max(0.0, 1.0 - center_distance / max(1.0, radius))
            pixel_score = min(1.0, count / max(1.0, profile["min_pixels"] * 2))
            confidence = 0.45 * centrality + 0.25 * pixel_score + 0.30 * anisotropy
            if confidence < profile["min_confidence"]:
                continue
            candidates.append(
                MarkerCandidate(
                    center_x_px=float(center[0]),
                    center_y_px=float(center[1]),
                    orientation_deg_screen=orientation,
                    pixel_count=count,
                    confidence=confidence,
                    detection_model="neutral_mdx",
                )
            )
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.confidence)

    @staticmethod
    def _connected_point_sets(
        mask: np.ndarray,
        *,
        left: int,
        top: int,
        maximum_components: int,
        maximum_component_pixels: int,
    ) -> tuple[np.ndarray, ...]:
        visited = np.zeros_like(mask, dtype=bool)
        components: list[np.ndarray] = []
        for source_y, source_x in zip(*np.nonzero(mask), strict=True):
            if visited[source_y, source_x]:
                continue
            if len(components) >= maximum_components:
                raise MinimapDetectionError("Neutral marker component budget exceeded")
            stack = [(int(source_y), int(source_x))]
            visited[source_y, source_x] = True
            points: list[tuple[float, float]] = []
            oversized = False
            while stack:
                y, x = stack.pop()
                if len(points) <= maximum_component_pixels:
                    points.append((float(x + left), float(y + top)))
                else:
                    oversized = True
                for delta_y in (-1, 0, 1):
                    for delta_x in (-1, 0, 1):
                        if delta_x == 0 and delta_y == 0:
                            continue
                        next_y, next_x = y + delta_y, x + delta_x
                        if (
                            0 <= next_y < mask.shape[0]
                            and 0 <= next_x < mask.shape[1]
                            and mask[next_y, next_x]
                            and not visited[next_y, next_x]
                        ):
                            visited[next_y, next_x] = True
                            stack.append((next_y, next_x))
            if not oversized and points:
                components.append(np.asarray(points, dtype=np.float64))
        return tuple(components)

    @staticmethod
    def _grid_values(start: int, stop: int, step: int) -> tuple[int, ...]:
        if stop < start:
            return ()
        values = list(range(start, stop + 1, step))
        if not values or values[-1] != stop:
            values.append(stop)
        return tuple(values)

    @staticmethod
    def _circle_record(circle: CircleCandidate | None) -> dict[str, Any] | None:
        if circle is None:
            return None
        return {
            "center_x_px": circle.center_x_px,
            "center_y_px": circle.center_y_px,
            "radius_px": circle.radius_px,
            "ring_coverage": circle.ring_coverage,
            "confidence": circle.confidence,
        }

    @staticmethod
    def _marker_record(marker: MarkerCandidate | None) -> dict[str, Any] | None:
        if marker is None:
            return None
        return {
            "center_x_px": marker.center_x_px,
            "center_y_px": marker.center_y_px,
            "orientation_deg_screen": marker.orientation_deg_screen,
            "orientation_reference": "clockwise_from_screen_up",
            "detection_model": marker.detection_model,
            "pixel_count": marker.pixel_count,
            "confidence": marker.confidence,
        }
