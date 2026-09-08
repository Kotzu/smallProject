from __future__ import annotations

import copy
from math import atan2, cos, degrees, isfinite, radians, sin, sqrt
from typing import Any, Iterable, Mapping, Sequence

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.pose.common import (
    PoseFusionError,
    diagonal_covariance as _diagonal_covariance,
    freshness as _freshness,
    parse_timestamp as _parse_timestamp,
)


class PoseFusionEngine:
    """Deterministic, uncertainty-weighted fusion of client-observed pose records."""

    version = "0.1.0"
    _identity_fields = (
        "session_id",
        "champion_id",
        "target_profile",
        "decision_context",
        "client_build",
        "build_signature",
        "map_ref",
        "map_signature",
        "coordinate_space",
    )

    def __init__(
        self,
        validator: ContractValidator,
        estimator_id: str = "pa_uncertainty_pose_fusion",
        degraded_confidence_floor: float = 0.55,
    ) -> None:
        if not estimator_id:
            raise ValueError("estimator_id cannot be empty")
        if not 0 < degraded_confidence_floor <= 1:
            raise ValueError("degraded_confidence_floor must be inside (0, 1]")
        self._validator = validator
        self.estimator_id = estimator_id
        self.degraded_confidence_floor = degraded_confidence_floor

    def fuse(
        self,
        observations: Iterable[Mapping[str, Any]],
        *,
        estimate_id: str,
        created_at: str,
    ) -> dict[str, Any]:
        if not estimate_id:
            raise ValueError("estimate_id cannot be empty")
        owned = [copy.deepcopy(dict(item)) for item in observations]
        if not owned:
            raise PoseFusionError("At least one pose observation is required")
        owned.sort(key=lambda item: item.get("observation_id", ""))
        for observation in owned:
            self._validator.validate(observation)
            if observation.get("record_type") != "pose_observation":
                raise PoseFusionError("Pose fusion accepts observations, not estimates")
        self._require_same_identity(owned)
        self._require_client_observed_sources(owned)
        _parse_timestamp(created_at)

        player = self._fuse_player(owned, created_at)
        camera = self._fuse_camera(owned, created_at)
        first = owned[0]
        observation_ids = [item["observation_id"] for item in owned]
        estimate = {
            "record_type": "pose_estimate",
            "schema_version": "0.1",
            "estimate_id": estimate_id,
            "session_id": first["session_id"],
            "champion_id": first["champion_id"],
            "target_profile": first["target_profile"],
            "decision_context": first["decision_context"],
            "client_build": first["client_build"],
            "build_signature": first["build_signature"],
            "map_ref": first["map_ref"],
            "map_signature": first["map_signature"],
            "coordinate_space": copy.deepcopy(first["coordinate_space"]),
            "estimator_id": self.estimator_id,
            "estimator_version": self.version,
            "input_observation_ids": observation_ids,
            "navigation_state": player["tracking_state"],
            "player": player,
            "camera": camera,
            "execution_authority": False,
            "created_at": created_at,
        }
        self._validator.validate(estimate)
        return estimate

    def _require_same_identity(self, observations: Sequence[Mapping[str, Any]]) -> None:
        first = observations[0]
        for observation in observations[1:]:
            for field in self._identity_fields:
                if observation[field] != first[field]:
                    raise PoseFusionError(f"Pose identity mismatch: {field}")

    @staticmethod
    def _require_client_observed_sources(
        observations: Sequence[Mapping[str, Any]],
    ) -> None:
        forbidden_origins = {"lab_oracle", "server_ground_truth"}
        for observation in observations:
            for component_name in ("player", "camera"):
                provenance = observation[component_name]["provenance"]
                if provenance["origin"] in forbidden_origins:
                    raise PoseFusionError(
                        f"Pose fusion rejects {provenance['origin']} input"
                    )
                if provenance["scope"] != "champion_eligible":
                    raise PoseFusionError(
                        "Pose fusion accepts only champion-eligible observations"
                    )

    def _eligible_components(
        self,
        observations: Sequence[Mapping[str, Any]],
        component_name: str,
        created_at: str,
    ) -> list[tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any], float]]:
        eligible = []
        for observation in observations:
            component = observation[component_name]
            freshness = _freshness(
                component["freshness"]["observed_at"],
                created_at,
                float(component["freshness"]["stale_after_ms"]),
            )
            factor = {"FRESH": 1.0, "STALE": 0.25, "EXPIRED": 0.0}[freshness["status"]]
            if (
                factor == 0
                or component["tracking_state"] == "LOST"
                or component["pose"] is None
                or component["uncertainty"] is None
            ):
                continue
            eligible.append((observation, component, freshness, factor))
        return eligible

    def _fuse_player(
        self,
        observations: Sequence[Mapping[str, Any]],
        created_at: str,
    ) -> dict[str, Any]:
        eligible = self._eligible_components(observations, "player", created_at)
        if not eligible:
            return self._lost_fused_component(observations, "player", created_at)

        values = [item[1]["pose"] for item in eligible]
        variances = [
            self._covariance_diagonal(item[1]["uncertainty"]["covariance"])
            for item in eligible
        ]
        confidence_weights = [float(item[1]["confidence"]) * item[3] for item in eligible]
        x, var_x = self._weighted_scalar([value["position"]["x"] for value in values], variances, confidence_weights, 0)
        y, var_y = self._weighted_scalar([value["position"]["y"] for value in values], variances, confidence_weights, 1)
        z, var_z = self._weighted_scalar([value["position"]["z"] for value in values], variances, confidence_weights, 2)
        yaw, var_yaw = self._weighted_angle([value["body_yaw_deg"] for value in values], variances, confidence_weights, 3)
        pose: dict[str, Any] = {
            "position": {"x": x, "y": y, "z": z},
            "body_yaw_deg": yaw,
        }
        velocity_sources = [value.get("linear_velocity") for value in values]
        if any(source is not None for source in velocity_sources):
            pose["linear_velocity"] = {
                axis: self._weighted_optional_velocity(
                    velocity_sources, variances, confidence_weights, axis
                )
                for axis in ("x", "y", "z")
            }

        confidence = self._combined_confidence(confidence_weights)
        freshness = self._combined_freshness(eligible, created_at)
        anchored = any(
            item[1]["tracking_state"] == "ANCHORED" and item[2]["status"] == "FRESH"
            for item in eligible
        )
        if anchored:
            state = "ANCHORED"
        elif freshness["status"] == "FRESH" and confidence >= self.degraded_confidence_floor:
            state = "TRACKED"
        else:
            state = "DEGRADED"
        return {
            "tracking_state": state,
            "pose": pose,
            "uncertainty": {
                "covariance": _diagonal_covariance(
                    ["x", "y", "z", "body_yaw_rad"],
                    [var_x, var_y, var_z, var_yaw],
                ),
                "position_radius_95": 1.96 * sqrt(var_x + var_y),
                "vertical_error_95": 1.96 * sqrt(var_z),
                "yaw_error_95_deg": min(180.0, degrees(1.96 * sqrt(var_yaw))),
            },
            "confidence": confidence,
            "freshness": freshness,
            "provenance": self._fused_provenance(eligible),
        }

    def _fuse_camera(
        self,
        observations: Sequence[Mapping[str, Any]],
        created_at: str,
    ) -> dict[str, Any]:
        eligible = self._eligible_components(observations, "camera", created_at)
        if not eligible:
            return self._lost_fused_component(observations, "camera", created_at)
        values = [item[1]["pose"] for item in eligible]
        frames = {value["reference_frame"] for value in values}
        if len(frames) != 1:
            raise PoseFusionError("Camera reference frames cannot be mixed")
        variances = [
            self._covariance_diagonal(item[1]["uncertainty"]["covariance"])
            for item in eligible
        ]
        confidence_weights = [float(item[1]["confidence"]) * item[3] for item in eligible]
        yaw, var_yaw = self._weighted_angle([value["yaw_deg"] for value in values], variances, confidence_weights, 0)
        pitch, var_pitch = self._weighted_angle([value["pitch_deg"] for value in values], variances, confidence_weights, 1)
        roll, var_roll = self._weighted_angle([value["roll_deg"] for value in values], variances, confidence_weights, 2)
        zoom, var_zoom = self._weighted_scalar([value["zoom"] for value in values], variances, confidence_weights, 3)
        confidence = self._combined_confidence(confidence_weights)
        freshness = self._combined_freshness(eligible, created_at)
        state = (
            "TRACKED"
            if freshness["status"] == "FRESH" and confidence >= self.degraded_confidence_floor
            else "DEGRADED"
        )
        angular_error = max(
            degrees(1.96 * sqrt(var_yaw)),
            degrees(1.96 * sqrt(var_pitch)),
            degrees(1.96 * sqrt(var_roll)),
        )
        return {
            "tracking_state": state,
            "pose": {
                "reference_frame": next(iter(frames)),
                "yaw_deg": yaw,
                "pitch_deg": pitch,
                "roll_deg": roll,
                "zoom": zoom,
            },
            "uncertainty": {
                "covariance": _diagonal_covariance(
                    ["yaw_rad", "pitch_rad", "roll_rad", "zoom"],
                    [var_yaw, var_pitch, var_roll, var_zoom],
                ),
                "angular_error_95_deg": min(180.0, angular_error),
                "zoom_error_95": 1.96 * sqrt(var_zoom),
            },
            "confidence": confidence,
            "freshness": freshness,
            "provenance": self._fused_provenance(eligible),
        }

    def _lost_fused_component(
        self,
        observations: Sequence[Mapping[str, Any]],
        component_name: str,
        created_at: str,
    ) -> dict[str, Any]:
        observed_at = max(
            observation[component_name]["freshness"]["observed_at"]
            for observation in observations
        )
        stale_after_ms = min(
            float(observation[component_name]["freshness"]["stale_after_ms"])
            for observation in observations
        )
        freshness = _freshness(observed_at, created_at, stale_after_ms)
        return {
            "tracking_state": "LOST",
            "pose": None,
            "uncertainty": None,
            "confidence": 0,
            "freshness": freshness,
            "provenance": {
                "source_id": self.estimator_id,
                "origin": "fused_client_observations",
                "capability": "pose_estimate",
                "scope": "champion_eligible",
                "evidence_refs": [
                    observation["observation_id"] for observation in observations
                ],
            },
        }

    def _combined_freshness(
        self,
        eligible: Sequence[tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any], float]],
        created_at: str,
    ) -> dict[str, Any]:
        observed_at = max(item[2]["observed_at"] for item in eligible)
        stale_after_ms = min(float(item[2]["stale_after_ms"]) for item in eligible)
        return _freshness(observed_at, created_at, stale_after_ms)

    def _fused_provenance(
        self,
        eligible: Sequence[tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any], float]],
    ) -> dict[str, Any]:
        return {
            "source_id": self.estimator_id,
            "origin": "fused_client_observations",
            "capability": "pose_estimate",
            "scope": "champion_eligible",
            "evidence_refs": [item[0]["observation_id"] for item in eligible],
        }

    @staticmethod
    def _covariance_diagonal(covariance: Mapping[str, Any]) -> tuple[float, float, float, float]:
        matrix = covariance["matrix_row_major"]
        diagonal = tuple(float(matrix[index]) for index in (0, 5, 10, 15))
        if any(not isfinite(value) or value <= 0 for value in diagonal):
            raise PoseFusionError("Input covariance diagonal must be finite and positive")
        return diagonal  # type: ignore[return-value]

    @staticmethod
    def _weighted_scalar(
        values: Sequence[float],
        variances: Sequence[Sequence[float]],
        confidence_weights: Sequence[float],
        dimension: int,
    ) -> tuple[float, float]:
        weights = [
            confidence / variance[dimension]
            for confidence, variance in zip(confidence_weights, variances, strict=True)
        ]
        total = sum(weights)
        if total <= 0:
            raise PoseFusionError("Pose fusion has no positive weight")
        return (
            sum(value * weight for value, weight in zip(values, weights, strict=True)) / total,
            1.0 / total,
        )

    @classmethod
    def _weighted_angle(
        cls,
        values_deg: Sequence[float],
        variances: Sequence[Sequence[float]],
        confidence_weights: Sequence[float],
        dimension: int,
    ) -> tuple[float, float]:
        weights = [
            confidence / variance[dimension]
            for confidence, variance in zip(confidence_weights, variances, strict=True)
        ]
        total = sum(weights)
        if total <= 0:
            raise PoseFusionError("Pose fusion has no positive angular weight")
        x = sum(cos(radians(value)) * weight for value, weight in zip(values_deg, weights, strict=True))
        y = sum(sin(radians(value)) * weight for value, weight in zip(values_deg, weights, strict=True))
        if abs(x) < 1e-12 and abs(y) < 1e-12:
            raise PoseFusionError("Angular evidence is ambiguous")
        angle = degrees(atan2(y, x))
        if angle > 180:
            angle -= 360
        if angle < -180:
            angle += 360
        return angle, 1.0 / total

    @classmethod
    def _weighted_optional_velocity(
        cls,
        sources: Sequence[Mapping[str, float] | None],
        variances: Sequence[Sequence[float]],
        confidence_weights: Sequence[float],
        axis: str,
    ) -> float:
        dimension = {"x": 0, "y": 1, "z": 2}[axis]
        values: list[float] = []
        selected_variances: list[Sequence[float]] = []
        selected_confidence: list[float] = []
        for source, variance, confidence in zip(
            sources, variances, confidence_weights, strict=True
        ):
            if source is None:
                continue
            values.append(float(source[axis]))
            selected_variances.append(variance)
            selected_confidence.append(confidence)
        value, _ = cls._weighted_scalar(
            values, selected_variances, selected_confidence, dimension
        )
        return value

    @staticmethod
    def _combined_confidence(weights: Sequence[float]) -> float:
        missed_probability = 1.0
        for weight in weights:
            missed_probability *= 1.0 - min(1.0, max(0.0, weight))
        return min(1.0, max(1e-12, 1.0 - missed_probability))
