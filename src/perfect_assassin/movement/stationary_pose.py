from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import hypot, isfinite, pi
from pathlib import Path
from typing import Iterable


EXACT_BODY_FACING_SOURCE = "COORDINATE_HUD_EXACT"
CALIBRATED_MINIMAP_BODY_FACING_SOURCE = "MINIMAP_VISION_FALLBACK"
MINIMUM_CALIBRATED_MINIMAP_CONFIDENCE = 0.70
LIVE_POSITION_SOURCE = "COORDINATE_HUD"


@dataclass(frozen=True, slots=True)
class LivePoseSample:
    sequence: int
    observed_monotonic_s: float
    world_x: float
    world_y: float
    facing_rad: float | None
    position_source: str = LIVE_POSITION_SOURCE
    facing_source: str | None = None
    facing_confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExpectedStationaryLocation:
    location_id: str
    map_name: str
    coordinate_system: str
    center_world: tuple[float, float]
    arrival_radius_world: float


@dataclass(frozen=True, slots=True)
class StationaryPoseReport:
    sample_count: int
    duration_s: float
    maximum_sample_gap_s: float
    maximum_position_drift_world: float
    maximum_facing_jitter_rad: float | None
    position_source: str | None
    facing_source: str | None
    expected_location_id: str | None
    expected_map_name: str | None
    expected_coordinate_system: str | None
    expected_location_center_world: tuple[float, float] | None
    expected_location_radius_world: float | None
    maximum_distance_from_expected_location_world: float | None
    within_expected_location: bool | None
    passed: bool
    failures: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "stationary_pose_validation",
            "schema_version": "1.0",
            **asdict(self),
            "failures": list(self.failures),
            "execution_authority": False,
        }


def parse_live_pose_state(
    content: str,
    *,
    now_monotonic_s: float,
    maximum_age_s: float = 0.75,
) -> LivePoseSample | None:
    """Parse a fresh client-visible pose from the shared viewer protocol."""

    lines = content.splitlines()
    if not lines or lines[0] not in {
        "PA_NAV_VIEWER_STATE 2",
        "PA_NAV_VIEWER_STATE 3",
        "PA_NAV_VIEWER_STATE 4",
        "PA_NAV_VIEWER_STATE 5",
    }:
        return None
    values: dict[str, list[str]] = {}
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        if parts[0] in {
            "sequence", "observed", "pose", "facing",
            "facing_source", "facing_confidence",
        }:
            values[parts[0]] = parts[1:]
    try:
        sequence = int(values["sequence"][0])
        observed_s = float(values["observed"][0])
        world_x, world_y = (float(value) for value in values["pose"])
        raw_facing = values["facing"]
        facing_rad = None if raw_facing == ["none"] else float(raw_facing[0])
        raw_source = values.get("facing_source")
        facing_source = (
            EXACT_BODY_FACING_SOURCE
            if raw_source is None and facing_rad is not None
            else None
            if raw_source == ["none"] or raw_source is None
            else raw_source[0]
        )
        raw_confidence = values.get("facing_confidence")
        facing_confidence = (
            None
            if raw_confidence in (None, ["none"])
            else float(raw_confidence[0])
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    age_s = now_monotonic_s - observed_s
    if (
        sequence < 1
        or not all(isfinite(value) for value in (observed_s, world_x, world_y))
        or facing_rad is not None and not isfinite(facing_rad)
        or (facing_rad is None) != (facing_source is None)
        or facing_confidence is not None and (
            facing_source is None
            or not isfinite(facing_confidence)
            or not 0.0 <= facing_confidence <= 1.0
        )
        or not 0.0 <= age_s <= maximum_age_s
    ):
        return None
    return LivePoseSample(
        sequence=sequence,
        observed_monotonic_s=observed_s,
        world_x=world_x,
        world_y=world_y,
        facing_rad=facing_rad,
        facing_source=facing_source,
        facing_confidence=facing_confidence,
    )


def read_live_pose_file(
    path: Path,
    *,
    now_monotonic_s: float,
    maximum_age_s: float = 0.75,
) -> LivePoseSample | None:
    try:
        content = path.read_text(encoding="ascii")
    except (FileNotFoundError, OSError):
        return None
    return parse_live_pose_state(
        content,
        now_monotonic_s=now_monotonic_s,
        maximum_age_s=maximum_age_s,
    )


def load_expected_stationary_location(
    catalog_path: Path,
    *,
    location_id: str,
) -> ExpectedStationaryLocation:
    """Load a named validation region from the versioned semantic catalog."""

    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("stationary location catalog is unreadable") from error
    if (
        not isinstance(catalog, dict)
        or catalog.get("record_type") != "semantic_location_catalog"
        or catalog.get("schema_version") != "1.0"
        or not isinstance(catalog.get("map_name"), str)
        or not catalog.get("map_name")
        or catalog.get("coordinate_system") != "tbc243_client_world_xy"
        or not isinstance(catalog.get("locations"), list)
    ):
        raise ValueError("stationary location catalog identity is invalid")
    matches = [
        item for item in catalog["locations"]
        if isinstance(item, dict) and item.get("id") == location_id
    ]
    if len(matches) != 1:
        raise ValueError("expected stationary location is missing or duplicated")
    item = matches[0]
    world = item.get("world")
    radius = item.get("arrival_radius_yards")
    if (
        not isinstance(world, list)
        or len(world) != 2
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in world)
        or any(not isfinite(float(value)) for value in world)
        or isinstance(radius, bool)
        or not isinstance(radius, (int, float))
        or not isfinite(float(radius))
        or float(radius) <= 0.0
    ):
        raise ValueError("expected stationary location geometry is invalid")
    return ExpectedStationaryLocation(
        location_id=location_id,
        map_name=str(catalog["map_name"]),
        coordinate_system=str(catalog["coordinate_system"]),
        center_world=(float(world[0]), float(world[1])),
        arrival_radius_world=float(radius),
    )


def evaluate_stationary_pose(
    samples: Iterable[LivePoseSample],
    *,
    expected_location: ExpectedStationaryLocation | None = None,
    minimum_samples: int = 15,
    minimum_duration_s: float = 2.0,
    maximum_sample_gap_s: float = 0.60,
    maximum_position_drift_world: float = 0.10,
    maximum_facing_jitter_rad: float = 0.05,
) -> StationaryPoseReport:
    ordered = tuple(samples)
    failures: list[str] = []
    if len(ordered) < minimum_samples:
        failures.append("insufficient_unique_samples")
    sequence_valid = all(
        current.sequence > previous.sequence
        for previous, current in zip(ordered, ordered[1:])
    )
    observed_valid = all(
        current.observed_monotonic_s > previous.observed_monotonic_s
        for previous, current in zip(ordered, ordered[1:])
    )
    if not sequence_valid:
        failures.append("sequence_not_strictly_increasing")
    if not observed_valid:
        failures.append("observation_time_not_strictly_increasing")
    duration_s = (
        ordered[-1].observed_monotonic_s - ordered[0].observed_monotonic_s
        if len(ordered) >= 2
        else 0.0
    )
    if duration_s < minimum_duration_s:
        failures.append("observation_window_too_short")
    gaps = tuple(
        current.observed_monotonic_s - previous.observed_monotonic_s
        for previous, current in zip(ordered, ordered[1:])
    )
    largest_gap = max(gaps, default=0.0)
    if largest_gap > maximum_sample_gap_s:
        failures.append("live_pose_gap")
    position_source = (
        ordered[0].position_source if ordered and all(
            sample.position_source == ordered[0].position_source
            for sample in ordered
        ) else None
    )
    if position_source != LIVE_POSITION_SOURCE:
        failures.append("position_source_not_exact_client_hud")
    facings = tuple(sample.facing_rad for sample in ordered)
    facing_source = (
        ordered[0].facing_source
        if ordered
        and ordered[0].facing_source in {
            EXACT_BODY_FACING_SOURCE,
            CALIBRATED_MINIMAP_BODY_FACING_SOURCE,
        }
        and all(
            sample.facing_source == ordered[0].facing_source
            and sample.facing_rad is not None
            for sample in ordered
        )
        else None
    )
    if (
        facing_source == CALIBRATED_MINIMAP_BODY_FACING_SOURCE
        and not all(
            sample.facing_confidence is not None
            and sample.facing_confidence
            >= MINIMUM_CALIBRATED_MINIMAP_CONFIDENCE
            for sample in ordered
        )
    ):
        facing_source = None
    if facing_source is None:
        failures.append("exact_body_facing_missing")
    position_drift = 0.0
    if ordered:
        first = ordered[0]
        position_drift = max(
            hypot(sample.world_x - first.world_x, sample.world_y - first.world_y)
            for sample in ordered
        )
    if position_drift > maximum_position_drift_world:
        failures.append("actor_not_stationary")
    facing_jitter: float | None = None
    if facing_source is not None:
        anchor = float(facings[0])
        facing_jitter = max(
            abs((float(facing) - anchor + pi) % (2.0 * pi) - pi)
            for facing in facings
        )
        if facing_jitter > maximum_facing_jitter_rad:
            failures.append("body_facing_not_stationary")
    expected_distance: float | None = None
    within_expected_location: bool | None = None
    if expected_location is not None:
        if ordered:
            expected_distance = max(
                hypot(
                    sample.world_x - expected_location.center_world[0],
                    sample.world_y - expected_location.center_world[1],
                )
                for sample in ordered
            )
        within_expected_location = (
            expected_distance is not None
            and isfinite(expected_distance)
            and expected_distance <= expected_location.arrival_radius_world
        )
        if not within_expected_location:
            failures.append("outside_expected_location")
    return StationaryPoseReport(
        sample_count=len(ordered),
        duration_s=max(0.0, duration_s),
        maximum_sample_gap_s=largest_gap,
        maximum_position_drift_world=position_drift,
        maximum_facing_jitter_rad=facing_jitter,
        position_source=position_source,
        facing_source=facing_source,
        expected_location_id=(
            None if expected_location is None else expected_location.location_id
        ),
        expected_map_name=(
            None if expected_location is None else expected_location.map_name
        ),
        expected_coordinate_system=(
            None if expected_location is None else expected_location.coordinate_system
        ),
        expected_location_center_world=(
            None if expected_location is None else expected_location.center_world
        ),
        expected_location_radius_world=(
            None if expected_location is None else expected_location.arrival_radius_world
        ),
        maximum_distance_from_expected_location_world=expected_distance,
        within_expected_location=within_expected_location,
        passed=not failures,
        failures=tuple(failures),
    )


__all__ = [
    "CALIBRATED_MINIMAP_BODY_FACING_SOURCE",
    "EXACT_BODY_FACING_SOURCE",
    "ExpectedStationaryLocation",
    "LIVE_POSITION_SOURCE",
    "LivePoseSample",
    "MINIMUM_CALIBRATED_MINIMAP_CONFIDENCE",
    "StationaryPoseReport",
    "evaluate_stationary_pose",
    "load_expected_stationary_location",
    "parse_live_pose_state",
    "read_live_pose_file",
]
