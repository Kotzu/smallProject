"""Read-only local spatial context from observed pose and immutable asset evidence.

This is not a localization sensor, collision certificate, route planner or
input gate. Unknown metric uncertainty stays unknown; sparse rays are never
interpolated into a free-space disk. No game/process/server access occurs here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import atan2, hypot, isfinite, pi

from .client_navmesh import LocalStaticAwareness, NavPoint


def _number(value: float, name: str, *, minimum: float = 0.0) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"invalid {name}")


def _point(value: NavPoint) -> None:
    for coordinate in (value.x, value.y, value.z):
        _number(coordinate, "coordinate", minimum=-float("inf"))
        if abs(coordinate) > 1e7:
            raise ValueError("coordinate outside diagnostic numeric domain")


@dataclass(frozen=True, slots=True)
class SpatialBinding:
    session_id: str
    map_name: str
    world_pack_sha256: str
    floor_id: str | None
    coordinate_frame: str = "CLIENT_WORLD_XYZ_YARDS"

    def __post_init__(self) -> None:
        if (
            not self.session_id
            or not self.map_name
            or self.coordinate_frame != "CLIENT_WORLD_XYZ_YARDS"
            or len(self.world_pack_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.world_pack_sha256
            )
            or self.floor_id == ""
        ):
            raise ValueError("invalid spatial binding")


@dataclass(frozen=True, slots=True)
class SpatialPoseEvidence:
    binding: SpatialBinding
    position: NavPoint
    observed_monotonic_s: float
    evidence_ref: str
    source: str
    confidence: float
    horizontal_error_bound_yards: float | None
    body_heading_rad: float | None = None

    def __post_init__(self) -> None:
        _point(self.position)
        _number(self.observed_monotonic_s, "pose time")
        _number(self.confidence, "pose confidence")
        if (
            self.confidence > 1
            or not self.evidence_ref
            or self.source
            not in {
                "CLIENT_VISIBLE_HUD",
                "CALIBRATED_MINIMAP",
                "CLIENT_OBSERVATION_FUSION",
            }
        ):
            raise ValueError("invalid client-observed pose provenance")
        if self.horizontal_error_bound_yards is not None:
            _number(self.horizontal_error_bound_yards, "metric pose error bound")
        if self.body_heading_rad is not None:
            _number(self.body_heading_rad, "body heading", minimum=-float("inf"))


@dataclass(frozen=True, slots=True)
class SpatialGeometryEvidence:
    binding: SpatialBinding
    query_origin: NavPoint
    observed_monotonic_s: float
    evidence_ref: str
    awareness: LocalStaticAwareness
    source: str = "CLIENT_ASSET_NAVMESH_BVH"

    def __post_init__(self) -> None:
        _point(self.query_origin)
        for wall in self.awareness.wall_segments:
            _point(wall.left)
            _point(wall.right)
        _number(self.observed_monotonic_s, "geometry time")
        if not self.evidence_ref or self.source != "CLIENT_ASSET_NAVMESH_BVH":
            raise ValueError("invalid static geometry provenance")


@dataclass(frozen=True, slots=True)
class SpatialContextPolicy:
    """Diagnostic thresholds only. Not a deployed movement policy."""

    maximum_pose_age_s: float = 0.25
    maximum_geometry_age_s: float = 1.0
    maximum_query_offset_yards: float = 0.30
    minimum_pose_confidence: float = 0.70
    body_radius_yards: float = 0.389

    def __post_init__(self) -> None:
        for name in (
            "maximum_pose_age_s",
            "maximum_geometry_age_s",
            "maximum_query_offset_yards",
            "minimum_pose_confidence",
            "body_radius_yards",
        ):
            _number(getattr(self, name), name)
        if self.minimum_pose_confidence > 1 or self.body_radius_yards <= 0:
            raise ValueError("invalid spatial context policy")


def _nearest_on_segment(
    position: NavPoint, left: NavPoint, right: NavPoint
) -> NavPoint:
    dx, dy = right.x - left.x, right.y - left.y
    length_squared = dx * dx + dy * dy
    fraction = (
        0.0
        if length_squared == 0
        else max(
            0.0,
            min(
                1.0,
                ((position.x - left.x) * dx + (position.y - left.y) * dy)
                / length_squared,
            ),
        )
    )
    return NavPoint(
        left.x + fraction * dx,
        left.y + fraction * dy,
        left.z + fraction * (right.z - left.z),
    )


def evaluate_spatial_context(
    pose: SpatialPoseEvidence,
    geometry: SpatialGeometryEvidence | None,
    *,
    now_monotonic_s: float,
    speed_bound_yards_per_s: float,
    response_latency_bound_s: float,
    policy: SpatialContextPolicy | None = None,
) -> dict[str, object]:
    """Explain applicability and exposure without returning any movement command.

    The exposure radius is body + supplied metric pose bound + speed bound times
    pose age and future response delay. It is a conditional diagnostic budget,
    not a measured body radius, braking model or collision prediction.
    """
    if policy is None:
        policy = SpatialContextPolicy()
    for name, value in (
        ("now", now_monotonic_s),
        ("speed bound", speed_bound_yards_per_s),
        ("response latency", response_latency_bound_s),
    ):
        _number(value, name)
    pose_age = now_monotonic_s - pose.observed_monotonic_s
    reasons: list[str] = []
    if pose_age < 0:
        reasons.append("FUTURE_POSE_TIMESTAMP")
    elif pose_age > policy.maximum_pose_age_s:
        reasons.append("STALE_POSE")
    if pose.confidence < policy.minimum_pose_confidence:
        reasons.append("LOW_POSE_CONFIDENCE")
    if pose.horizontal_error_bound_yards is None:
        reasons.append("UNKNOWN_METRIC_POSE_ERROR")
    if pose.binding.floor_id is None:
        reasons.append("UNRESOLVED_FLOOR")

    geometry_age = offset = None
    if geometry is None:
        reasons.append("MISSING_GEOMETRY")
    else:
        geometry_age = now_monotonic_s - geometry.observed_monotonic_s
        if pose.binding != geometry.binding:
            reasons.append("GEOMETRY_BINDING_MISMATCH")
        if geometry_age < 0:
            reasons.append("FUTURE_GEOMETRY_TIMESTAMP")
        elif geometry_age > policy.maximum_geometry_age_s:
            reasons.append("STALE_LOCAL_QUERY")
        # Matching floor identity must be supplied by an independent adapter;
        # we never obtain it by selecting whichever navmesh floor is closest.
        offset = hypot(
            pose.position.distance_2d(geometry.query_origin),
            pose.position.z - geometry.query_origin.z,
        )
        if offset > policy.maximum_query_offset_yards:
            reasons.append("QUERY_ORIGIN_MOVED")

    exposure = None
    if not any(
        reason in reasons
        for reason in (
            "FUTURE_POSE_TIMESTAMP",
            "STALE_POSE",
            "LOW_POSE_CONFIDENCE",
            "UNKNOWN_METRIC_POSE_ERROR",
        )
    ):
        exposure = (
            policy.body_radius_yards
            + pose.horizontal_error_bound_yards
            + speed_bound_yards_per_s * (pose_age + response_latency_bound_s)
        )
        _number(exposure, "computed exposure radius")

    applicable = not reasons
    nearest = None
    probes: list[dict[str, object]] = []
    if applicable and geometry is not None:
        awareness = geometry.awareness
        if awareness.wall_segments:
            candidates = [
                (_nearest_on_segment(pose.position, wall.left, wall.right), index)
                for index, wall in enumerate(awareness.wall_segments)
            ]
            closest, index = min(
                candidates, key=lambda item: pose.position.distance_2d(item[0])
            )
            distance = pose.position.distance_2d(closest)
            bearing = atan2(closest.y - pose.position.y, closest.x - pose.position.x)
            nearest = {
                "sample_index": index,
                "distance_yards": distance,
                "distance_origin": "CURRENT_OBSERVED_POSE",
                "relative_body_bearing_rad": None
                if pose.body_heading_rad is None or distance <= 1e-9
                else (bearing - pose.body_heading_rad + pi) % (2 * pi) - pi,
                "exposure_budget_remaining_yards": None
                if exposure is None
                else distance - exposure,
                "semantics": "NEAREST_REPORTED_NAVMESH_BOUNDARY_NOT_PHYSICAL_WALL",
                "set_truncated": awareness.component_truncated
                or awareness.wall_segments_truncated,
            }
        probes = [
            {
                "bearing_world_rad": item.bearing_rad,
                "clear_sample_length_yards": item.clearance_yards,
                "range_limit_reached": item.clearance_yards
                >= awareness.probe_radius_yards,
                "navmesh_reachable": item.navmesh_reachable,
                "distance_origin": "RECORDED_QUERY_ORIGIN_NOT_CURRENT_POSE",
            }
            for item in awareness.radial_probes
        ]

    if not applicable:
        summary = "Distanțe locale neaplicabile: trebuie clarificată poziția sau refăcută interogarea."
    elif nearest is None:
        summary = (
            "Nu avem o limită de navmesh raportată; asta nu înseamnă spațiu liber."
        )
    else:
        summary = f"Limită navmesh raportată la {nearest['distance_yards']:.2f} yd; nu este un zid confirmat."
    return {
        "record_type": "spatial_context_diagnostic",
        "schema_version": "1.0",
        "binding": asdict(pose.binding),
        "evaluated_monotonic_s": now_monotonic_s,
        "pose_observed_monotonic_s": pose.observed_monotonic_s,
        "position": [pose.position.x, pose.position.y, pose.position.z],
        "body_heading_rad": pose.body_heading_rad,
        "horizontal_error_bound_yards": pose.horizontal_error_bound_yards,
        "diagnostic_policy": asdict(policy),
        "status": "LOCAL_SAMPLES_ONLY" if applicable else "REOBSERVE_OR_REQUERY",
        "reasons": reasons,
        "pose_evidence_ref": pose.evidence_ref,
        "geometry_evidence_ref": None if geometry is None else geometry.evidence_ref,
        "geometry_binding": None if geometry is None else asdict(geometry.binding),
        "geometry_source": None if geometry is None else geometry.source,
        "geometry_observed_monotonic_s": None
        if geometry is None
        else geometry.observed_monotonic_s,
        "pose_source": pose.source,
        "pose_confidence": pose.confidence,
        "pose_age_s": pose_age,
        "geometry_age_s": geometry_age,
        "query_origin_offset_yards": offset,
        "exposure_radius_yards": exposure,
        "exposure_semantics": "CONDITIONAL_ON_SUPPLIED_BOUNDS_NOT_MEASURED_CLEARANCE",
        "speed_bound_yards_per_s": speed_bound_yards_per_s,
        "response_latency_bound_s": response_latency_bound_s,
        "nearest_reported_boundary": nearest,
        "radial_samples": probes,
        "radial_origin": None
        if geometry is None
        else [
            geometry.query_origin.x,
            geometry.query_origin.y,
            geometry.query_origin.z,
        ],
        "radial_gaps_semantics": "UNKNOWN_NOT_INTERPOLATED",
        "dynamic_obstacles": "NOT_EVALUATED",
        "free_space_certified": False,
        "execution_authority": False,
        "operator_summary_ro": summary,
    }
