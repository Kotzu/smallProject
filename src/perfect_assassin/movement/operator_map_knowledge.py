from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, pi
from typing import Any


SCHEMA_VERSION = "1.0"
PROVENANCE = "operator_authored_external_map_editor"
FEATURE_KINDS = {
    "roaming_zone",
    "obstacle",
    "interior_route",
    "recovery_anchor",
    "manual_demonstration",
}
POLYGON_KINDS = {"roaming_zone", "obstacle"}
POLYLINE_KINDS = {"interior_route", "manual_demonstration"}


@dataclass(frozen=True, slots=True)
class MapKnowledgeVertex:
    x: float
    y: float
    facing_rad: float | None = None

    def __post_init__(self) -> None:
        values = (self.x, self.y) if self.facing_rad is None else (self.x, self.y, self.facing_rad)
        if any(not isfinite(value) for value in values):
            raise ValueError("map knowledge vertex is invalid")
        if self.facing_rad is not None and not -pi <= self.facing_rad <= pi:
            raise ValueError("map knowledge facing is outside [-pi, pi]")

    def to_record(self) -> dict[str, float]:
        record = {"x": self.x, "y": self.y}
        if self.facing_rad is not None:
            record["facing_rad"] = self.facing_rad
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "MapKnowledgeVertex":
        return cls(
            x=float(record["x"]), y=float(record["y"]),
            facing_rad=(None if "facing_rad" not in record else float(record["facing_rad"])),
        )


@dataclass(frozen=True, slots=True)
class OperatorMapFeature:
    feature_id: str
    kind: str
    name: str
    vertices: tuple[MapKnowledgeVertex, ...]
    provenance: str = PROVENANCE
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.feature_id
            or self.kind not in FEATURE_KINDS
            or not self.name.strip()
            or self.provenance != PROVENANCE
            or self.execution_authority
        ):
            raise ValueError("operator map feature identity is invalid")
        minimum = 3 if self.kind in POLYGON_KINDS else 2 if self.kind in POLYLINE_KINDS else 1
        if len(self.vertices) < minimum:
            raise ValueError("operator map feature has too few vertices")

    @property
    def planner_effect(self) -> str:
        return {
            "roaming_zone": "preferred_search_region",
            "obstacle": "candidate_blocked_region_requires_runtime_confirmation",
            "interior_route": "preferred_indoor_corridor",
            "recovery_anchor": "candidate_reentry_anchor",
            "manual_demonstration": "movement_demonstration_prior",
        }[self.kind]

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.feature_id,
            "kind": self.kind,
            "name": self.name,
            "provenance": self.provenance,
            "planner_effect": self.planner_effect,
            "execution_authority": False,
            "vertices": [vertex.to_record() for vertex in self.vertices],
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "OperatorMapFeature":
        feature = cls(
            feature_id=str(record["id"]), kind=str(record["kind"]),
            name=str(record["name"]), provenance=str(record["provenance"]),
            execution_authority=bool(record.get("execution_authority", False)),
            vertices=tuple(
                MapKnowledgeVertex.from_record(vertex) for vertex in record["vertices"]
            ),
        )
        if record.get("planner_effect") != feature.planner_effect:
            raise ValueError("operator map feature planner effect is inconsistent")
        return feature


@dataclass(frozen=True, slots=True)
class OperatorMapKnowledge:
    map_name: str
    features: tuple[OperatorMapFeature, ...] = ()
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.map_name.strip() or self.execution_authority:
            raise ValueError("operator map knowledge identity is invalid")
        if len({feature.feature_id for feature in self.features}) != len(self.features):
            raise ValueError("operator map feature ids must be unique")

    def add_feature(
        self, *, kind: str, name: str,
        vertices: tuple[MapKnowledgeVertex, ...],
    ) -> "OperatorMapKnowledge":
        feature = OperatorMapFeature(
            feature_id=f"feature-{len(self.features) + 1:03d}",
            kind=kind, name=name, vertices=vertices,
        )
        return replace(self, features=(*self.features, feature))

    def undo(self) -> "OperatorMapKnowledge":
        return replace(self, features=self.features[:-1])

    def clear(self) -> "OperatorMapKnowledge":
        return replace(self, features=())

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": "operator_map_knowledge",
            "map": self.map_name,
            "execution_authority": False,
            "features": [feature.to_record() for feature in self.features],
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "OperatorMapKnowledge":
        if record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported operator map knowledge schema")
        if record.get("record_type") != "operator_map_knowledge":
            raise ValueError("unexpected operator map knowledge record type")
        return cls(
            map_name=str(record["map"]),
            execution_authority=bool(record.get("execution_authority", False)),
            features=tuple(
                OperatorMapFeature.from_record(feature) for feature in record["features"]
            ),
        )
