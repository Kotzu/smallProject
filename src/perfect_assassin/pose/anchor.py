from __future__ import annotations

import copy
from dataclasses import dataclass
from math import degrees, isfinite, sqrt
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator
from perfect_assassin.pose.common import diagonal_covariance, freshness


@dataclass(frozen=True, slots=True)
class PoseIdentity:
    session_id: str
    champion_id: str
    target_profile: str
    decision_context: str
    client_build: str
    build_signature: str
    map_ref: str
    map_signature: str
    coordinate_space: Mapping[str, Any]

    def __post_init__(self) -> None:
        required = (
            self.session_id,
            self.champion_id,
            self.target_profile,
            self.client_build,
            self.build_signature,
            self.map_ref,
            self.map_signature,
        )
        if any(not value for value in required):
            raise ValueError("Pose identity strings cannot be empty")
        if self.decision_context not in {"champion", "lab_clone"}:
            raise ValueError("Unsupported pose decision context")
        coordinate_space = copy.deepcopy(dict(self.coordinate_space))
        object.__setattr__(self, "coordinate_space", coordinate_space)


@dataclass(frozen=True, slots=True)
class MinimapAnchorMeasurement:
    observation_id: str
    source_id: str
    observed_at: str
    published_at: str
    evidence_ref: str
    normalized_x: float
    normalized_y: float
    normalized_z: float
    body_yaw_deg: float
    position_variance: float
    vertical_variance: float
    yaw_variance_rad2: float
    confidence: float
    stale_after_ms: float = 250.0

    def __post_init__(self) -> None:
        if not self.observation_id or not self.source_id or not self.evidence_ref:
            raise ValueError("Anchor identifiers cannot be empty")
        numeric = (
            self.normalized_x,
            self.normalized_y,
            self.normalized_z,
            self.body_yaw_deg,
            self.position_variance,
            self.vertical_variance,
            self.yaw_variance_rad2,
            self.confidence,
            self.stale_after_ms,
        )
        if not all(isfinite(value) for value in numeric):
            raise ValueError("Anchor measurement values must be finite")
        if not 0 <= self.normalized_x <= 1 or not 0 <= self.normalized_y <= 1:
            raise ValueError("Normalized anchor position must be inside [0, 1]")
        if not -180 <= self.body_yaw_deg <= 180:
            raise ValueError("body_yaw_deg must be inside [-180, 180]")
        if self.position_variance <= 0 or self.vertical_variance <= 0:
            raise ValueError("Position variances must be positive")
        if self.yaw_variance_rad2 <= 0:
            raise ValueError("Yaw variance must be positive")
        if not 0 < self.confidence <= 1:
            raise ValueError("Anchor confidence must be inside (0, 1]")
        if self.stale_after_ms <= 0:
            raise ValueError("stale_after_ms must be positive")


class MinimapAnchorObservationBuilder:
    """Convert a bounded visual anchor measurement into a pose observation.

    The builder does not inspect pixels and never infers camera state. A future
    vision sidecar can be replaced independently as long as it supplies the
    calibrated measurement and evidence reference represented here.
    """

    version = "0.1.0"

    def __init__(self, validator: ContractValidator) -> None:
        self._validator = validator

    def build(
        self,
        identity: PoseIdentity,
        measurement: MinimapAnchorMeasurement,
    ) -> dict[str, Any]:
        current_freshness = freshness(
            measurement.observed_at,
            measurement.published_at,
            measurement.stale_after_ms,
        )
        provenance = {
            "source_id": measurement.source_id,
            "origin": "minimap_vision",
            "capability": "pose_observation",
            "scope": "champion_eligible",
            "evidence_refs": [measurement.evidence_ref],
        }
        if current_freshness["status"] == "EXPIRED":
            player = self._lost_component(current_freshness, provenance)
        else:
            state = (
                "ANCHORED"
                if current_freshness["status"] == "FRESH"
                else "DEGRADED"
            )
            position_radius = 1.96 * sqrt(2 * measurement.position_variance)
            vertical_error = 1.96 * sqrt(measurement.vertical_variance)
            yaw_error = min(
                180.0,
                degrees(1.96 * sqrt(measurement.yaw_variance_rad2)),
            )
            player = {
                "tracking_state": state,
                "pose": {
                    "position": {
                        "x": measurement.normalized_x,
                        "y": measurement.normalized_y,
                        "z": measurement.normalized_z,
                    },
                    "body_yaw_deg": measurement.body_yaw_deg,
                    "linear_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                },
                "uncertainty": {
                    "covariance": diagonal_covariance(
                        ["x", "y", "z", "body_yaw_rad"],
                        [
                            measurement.position_variance,
                            measurement.position_variance,
                            measurement.vertical_variance,
                            measurement.yaw_variance_rad2,
                        ],
                    ),
                    "position_radius_95": position_radius,
                    "vertical_error_95": vertical_error,
                    "yaw_error_95_deg": yaw_error,
                },
                "confidence": measurement.confidence,
                "freshness": copy.deepcopy(current_freshness),
                "provenance": copy.deepcopy(provenance),
            }
        camera = self._lost_component(current_freshness, provenance)
        observation = {
            "record_type": "pose_observation",
            "schema_version": "0.1",
            "observation_id": measurement.observation_id,
            "session_id": identity.session_id,
            "champion_id": identity.champion_id,
            "target_profile": identity.target_profile,
            "decision_context": identity.decision_context,
            "client_build": identity.client_build,
            "build_signature": identity.build_signature,
            "map_ref": identity.map_ref,
            "map_signature": identity.map_signature,
            "coordinate_space": copy.deepcopy(dict(identity.coordinate_space)),
            "provider_id": measurement.source_id,
            "provider_version": self.version,
            "navigation_state": player["tracking_state"],
            "player": player,
            "camera": camera,
            "execution_authority": False,
            "created_at": measurement.published_at,
        }
        self._validator.validate(observation)
        return observation

    @staticmethod
    def _lost_component(
        current_freshness: Mapping[str, Any], provenance: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "tracking_state": "LOST",
            "pose": None,
            "uncertainty": None,
            "confidence": 0,
            "freshness": copy.deepcopy(dict(current_freshness)),
            "provenance": copy.deepcopy(dict(provenance)),
        }
