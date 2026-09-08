from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, hypot, isfinite, pi
from typing import Any, Mapping

from .operator_map_knowledge import MapKnowledgeVertex


SCHEMA_VERSION = "1.0"
RECORD_TYPE = "manual_path_recording"
PROVENANCE = "visible_addon_hud_operator_demonstration"
COORDINATE_SYSTEM = "tbc243_client_world_xy"
ATLAS_CALIBRATION = "WorldMapArea.dbc:Tirisfal"
STATUSES = {
    "RECORDING",
    "COMPLETE",
    "IMPORTED",
    "INSUFFICIENT_PATH",
    "INTERRUPTED",
}


class ManualPathDiscontinuityError(ValueError):
    """Raised rather than connecting two observations that are not continuous."""


@dataclass(frozen=True, slots=True)
class ManualPathVertex:
    x: float
    y: float
    observed_monotonic_s: float
    facing_rad: float | None = None
    observed_facing_rad: float | None = None

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.observed_monotonic_s)
        if any(not isfinite(value) for value in values) or self.observed_monotonic_s < 0:
            raise ValueError("manual path vertex is invalid")
        if self.facing_rad is not None and not -pi <= self.facing_rad <= pi:
            raise ValueError("manual path facing is outside [-pi, pi]")
        if self.observed_facing_rad is not None and not 0.0 <= self.observed_facing_rad < 2 * pi:
            raise ValueError("observed client facing is outside [0, 2*pi)")

    def to_record(self) -> dict[str, float]:
        result = {
            "x": self.x,
            "y": self.y,
            "observed_monotonic_s": self.observed_monotonic_s,
        }
        if self.facing_rad is not None:
            result["facing_rad"] = self.facing_rad
        if self.observed_facing_rad is not None:
            result["observed_facing_rad"] = self.observed_facing_rad
        return result

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ManualPathVertex":
        return cls(
            x=float(record["x"]),
            y=float(record["y"]),
            observed_monotonic_s=float(record["observed_monotonic_s"]),
            facing_rad=(
                None if "facing_rad" not in record else float(record["facing_rad"])
            ),
            observed_facing_rad=(
                None
                if "observed_facing_rad" not in record
                else float(record["observed_facing_rad"])
            ),
        )

    def as_map_knowledge_vertex(self) -> MapKnowledgeVertex:
        return MapKnowledgeVertex(self.x, self.y, self.facing_rad)


@dataclass(frozen=True, slots=True)
class ManualPathRecording:
    recording_id: str
    name: str
    status: str
    minimum_spacing_world: float
    vertices: tuple[ManualPathVertex, ...]
    imported_feature_id: str | None = None
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.recording_id
            or not self.name.strip()
            or self.status not in STATUSES
            or not isfinite(self.minimum_spacing_world)
            or not 0.25 <= self.minimum_spacing_world <= 5.0
            or self.execution_authority
        ):
            raise ValueError("manual path recording envelope is invalid")
        if self.status in {"COMPLETE", "IMPORTED"} and len(self.vertices) < 2:
            raise ValueError("complete manual path requires at least two vertices")
        if self.status == "IMPORTED" and not self.imported_feature_id:
            raise ValueError("imported manual path requires its feature id")
        if self.status != "IMPORTED" and self.imported_feature_id is not None:
            raise ValueError("non-imported manual path cannot name an imported feature")
        times = tuple(vertex.observed_monotonic_s for vertex in self.vertices)
        if times != tuple(sorted(times)) or len(set(times)) != len(times):
            raise ValueError("manual path observation times must be strictly increasing")

    @property
    def distance_world(self) -> float:
        return sum(
            hypot(right.x - left.x, right.y - left.y)
            for left, right in zip(self.vertices, self.vertices[1:])
        )

    def as_map_knowledge_vertices(self) -> tuple[MapKnowledgeVertex, ...]:
        return tuple(vertex.as_map_knowledge_vertex() for vertex in self.vertices)

    def mark_imported(self, feature_id: str) -> "ManualPathRecording":
        if self.status != "COMPLETE" or not feature_id:
            raise ValueError("only a complete recording can be imported")
        return replace(self, status="IMPORTED", imported_feature_id=feature_id)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": RECORD_TYPE,
            "recording_id": self.recording_id,
            "name": self.name,
            "status": self.status,
            "map": "Azeroth",
            "zone": "Tirisfal",
            "coordinate_system": COORDINATE_SYSTEM,
            "atlas_calibration": ATLAS_CALIBRATION,
            "provenance": PROVENANCE,
            "minimum_spacing_world": self.minimum_spacing_world,
            "distance_world": self.distance_world,
            "vertex_count": len(self.vertices),
            "orientation_source": "forward_displacement_tangent",
            "operator_instruction": "walk_forward_and_steer_with_mouse",
            "execution_authority": False,
            "imported_feature_id": self.imported_feature_id,
            "vertices": [vertex.to_record() for vertex in self.vertices],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ManualPathRecording":
        if (
            record.get("schema_version") != SCHEMA_VERSION
            or record.get("record_type") != RECORD_TYPE
            or record.get("map") != "Azeroth"
            or record.get("zone") != "Tirisfal"
            or record.get("coordinate_system") != COORDINATE_SYSTEM
            or record.get("atlas_calibration") != ATLAS_CALIBRATION
            or record.get("provenance") != PROVENANCE
            or record.get("orientation_source") != "forward_displacement_tangent"
            or record.get("operator_instruction") != "walk_forward_and_steer_with_mouse"
            or record.get("execution_authority") is not False
        ):
            raise ValueError("manual path recording identity is invalid")
        vertices_value = record.get("vertices")
        if not isinstance(vertices_value, list):
            raise ValueError("manual path recording vertices are invalid")
        recording = cls(
            recording_id=str(record["recording_id"]),
            name=str(record["name"]),
            status=str(record["status"]),
            minimum_spacing_world=float(record["minimum_spacing_world"]),
            imported_feature_id=(
                None
                if record.get("imported_feature_id") is None
                else str(record["imported_feature_id"])
            ),
            vertices=tuple(
                ManualPathVertex.from_record(vertex) for vertex in vertices_value
            ),
            execution_authority=False,
        )
        if int(record.get("vertex_count", -1)) != len(recording.vertices):
            raise ValueError("manual path vertex count is inconsistent")
        if abs(float(record.get("distance_world", -1.0)) - recording.distance_world) > 1e-6:
            raise ValueError("manual path distance is inconsistent")
        return recording


@dataclass(slots=True)
class ManualPathRecorder:
    recording_id: str
    name: str
    minimum_spacing_world: float = 0.75
    maximum_segment_world: float = 15.0
    maximum_observation_gap_s: float = 2.0
    _vertices: tuple[ManualPathVertex, ...] = ()
    _last_observed_monotonic_s: float | None = None

    def __post_init__(self) -> None:
        if not self.recording_id or not self.name.strip():
            raise ValueError("manual path recorder identity is invalid")
        if not (
            isfinite(self.minimum_spacing_world)
            and 0.25 <= self.minimum_spacing_world <= 5.0
            and isfinite(self.maximum_segment_world)
            and 5.0 <= self.maximum_segment_world <= 50.0
            and isfinite(self.maximum_observation_gap_s)
            and 0.5 <= self.maximum_observation_gap_s <= 10.0
        ):
            raise ValueError("manual path recorder bounds are invalid")

    @property
    def vertices(self) -> tuple[ManualPathVertex, ...]:
        return self._vertices

    def observe(
        self,
        *,
        x: float,
        y: float,
        observed_monotonic_s: float,
        observed_facing_rad: float | None = None,
    ) -> bool:
        candidate = ManualPathVertex(
            x,
            y,
            observed_monotonic_s,
            observed_facing_rad=observed_facing_rad,
        )
        if self._last_observed_monotonic_s is not None:
            observation_gap = (
                candidate.observed_monotonic_s - self._last_observed_monotonic_s
            )
            if observation_gap <= 0:
                raise ValueError("manual path observation time did not advance")
            if observation_gap > self.maximum_observation_gap_s:
                raise ManualPathDiscontinuityError(
                    "manual path continuity was lost; stop and start a new demonstration"
                )
        self._last_observed_monotonic_s = candidate.observed_monotonic_s
        if not self._vertices:
            self._vertices = (candidate,)
            return True
        previous = self._vertices[-1]
        distance = hypot(candidate.x - previous.x, candidate.y - previous.y)
        if distance < self.minimum_spacing_world:
            return False
        if distance > self.maximum_segment_world:
            raise ManualPathDiscontinuityError(
                "manual path continuity was lost; stop and start a new demonstration"
            )
        heading = atan2(candidate.y - previous.y, candidate.x - previous.x)
        oriented_previous = replace(previous, facing_rad=heading)
        oriented_candidate = replace(candidate, facing_rad=heading)
        self._vertices = (*self._vertices[:-1], oriented_previous, oriented_candidate)
        return True

    def snapshot(self, *, status: str = "RECORDING") -> ManualPathRecording:
        return ManualPathRecording(
            recording_id=self.recording_id,
            name=self.name,
            status=status,
            minimum_spacing_world=self.minimum_spacing_world,
            vertices=self._vertices,
        )

    def finish(self, *, interrupted: bool = False) -> ManualPathRecording:
        if interrupted and self._vertices:
            return self.snapshot(status="INTERRUPTED")
        return self.snapshot(
            status="COMPLETE" if len(self._vertices) >= 2 else "INSUFFICIENT_PATH"
        )
