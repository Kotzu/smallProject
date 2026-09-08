from __future__ import annotations

from dataclasses import dataclass, replace
from math import hypot, isfinite
from typing import Any


OPERATOR_PATH_SCHEMA_VERSION = "1.0"
OPERATOR_PATH_PROVENANCE = "operator_authored_external_tool"


@dataclass(frozen=True, slots=True)
class OperatorWaypoint:
    waypoint_id: str
    order: int
    x: float
    y: float
    z: float | None = None
    label: str = ""
    provenance: str = OPERATOR_PATH_PROVENANCE

    def __post_init__(self) -> None:
        coordinates = (self.x, self.y) if self.z is None else (self.x, self.y, self.z)
        if not self.waypoint_id or self.order < 1 or any(not isfinite(value) for value in coordinates):
            raise ValueError("operator waypoint is invalid")
        if self.provenance != OPERATOR_PATH_PROVENANCE:
            raise ValueError("operator waypoint provenance is invalid")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "id": self.waypoint_id,
            "order": self.order,
            "label": self.label or f"WP {self.order:03d}",
            "x": self.x,
            "y": self.y,
            "provenance": self.provenance,
        }
        if self.z is not None:
            record["z"] = self.z
        return record

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "OperatorWaypoint":
        return cls(
            waypoint_id=str(record["id"]),
            order=int(record["order"]),
            label=str(record.get("label", "")),
            x=float(record["x"]),
            y=float(record["y"]),
            z=None if "z" not in record else float(record["z"]),
            provenance=str(record["provenance"]),
        )


@dataclass(frozen=True, slots=True)
class OperatorAuthoredPath:
    path_id: str
    name: str
    map_name: str
    waypoints: tuple[OperatorWaypoint, ...] = ()
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not self.path_id or not self.name.strip() or not self.map_name.strip():
            raise ValueError("operator path identity is invalid")
        if self.execution_authority:
            raise ValueError("operator-authored paths cannot grant execution authority")
        if tuple(point.order for point in self.waypoints) != tuple(range(1, len(self.waypoints) + 1)):
            raise ValueError("operator waypoint order must be contiguous")
        if len({point.waypoint_id for point in self.waypoints}) != len(self.waypoints):
            raise ValueError("operator waypoint ids must be unique")

    def add(self, *, x: float, y: float, z: float | None = None, label: str = "") -> "OperatorAuthoredPath":
        order = len(self.waypoints) + 1
        point = OperatorWaypoint(
            waypoint_id=f"wp-{order:03d}", order=order, x=x, y=y, z=z,
            label=label or f"WP {order:03d}",
        )
        return replace(self, waypoints=(*self.waypoints, point))

    def undo(self) -> "OperatorAuthoredPath":
        return replace(self, waypoints=self.waypoints[:-1])

    def clear(self) -> "OperatorAuthoredPath":
        return replace(self, waypoints=())

    def resume_index_nearest_to(
        self, *, x: float, y: float, reached_radius: float = 3.0,
    ) -> int:
        """Choose a stable ordered-route re-entry point from a live position.

        This is used both at journey start and after a combat displacement.  A
        waypoint already inside the reached radius is advanced only when a
        later point exists, so the route never stops on the point underneath
        the actor and never skips the final destination.
        """

        if (
            not self.waypoints
            or not all(isfinite(value) for value in (x, y, reached_radius))
            or reached_radius <= 0
        ):
            raise ValueError("operator path cannot select a resume waypoint")
        index = min(
            range(len(self.waypoints)),
            key=lambda candidate: hypot(
                self.waypoints[candidate].x - x,
                self.waypoints[candidate].y - y,
            ),
        )
        if (
            index + 1 < len(self.waypoints)
            and hypot(self.waypoints[index].x - x, self.waypoints[index].y - y)
            <= reached_radius
        ):
            return index + 1
        return index

    def resume_waypoints_nearest_to(
        self, *, x: float, y: float, reached_radius: float = 3.0,
    ) -> tuple[OperatorWaypoint, ...]:
        index = self.resume_index_nearest_to(
            x=x, y=y, reached_radius=reached_radius,
        )
        return self.waypoints[index:]

    def rename(self, name: str) -> "OperatorAuthoredPath":
        return replace(self, name=name)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": OPERATOR_PATH_SCHEMA_VERSION,
            "record_type": "operator_authored_path",
            "path_id": self.path_id,
            "name": self.name,
            "map": self.map_name,
            "execution_authority": False,
            "waypoints": [point.to_record() for point in self.waypoints],
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "OperatorAuthoredPath":
        if record.get("schema_version") != OPERATOR_PATH_SCHEMA_VERSION:
            raise ValueError("unsupported operator path schema")
        if record.get("record_type") != "operator_authored_path":
            raise ValueError("unexpected operator path record type")
        return cls(
            path_id=str(record["path_id"]),
            name=str(record["name"]),
            map_name=str(record["map"]),
            execution_authority=bool(record.get("execution_authority", False)),
            waypoints=tuple(OperatorWaypoint.from_record(point) for point in record["waypoints"]),
        )
