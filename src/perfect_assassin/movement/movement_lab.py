from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi, sin
from typing import Any, Mapping

MOVEMENT_LAB_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class MovementLabSnapshot:
    """Read-only state consumed by the optional external debug overlay."""

    observed_monotonic_s: float
    tracking_state: str
    target_identity_crc16: int | None
    target_error_x_normalized: float | None
    target_screen_y_normalized: float | None = None
    player_world_x: float | None = None
    player_world_y: float | None = None
    player_world_z: float | None = None
    player_facing_rad: float | None = None
    body_facing_rad: float | None = None
    body_facing_source: str | None = None
    camera_yaw_estimate_rad: float | None = None
    camera_yaw_source: str | None = None
    body_camera_yaw_delta_rad: float | None = None
    waypoint_error_rad: float | None = None
    controller_state: str = "OBSERVE"
    navmesh_polygons_world: tuple[tuple[tuple[float, float], ...], ...] = ()
    corridor_centerline_world: tuple[tuple[float, float], ...] = ()
    planned_waypoints_world: tuple[tuple[float, float], ...] = ()
    traversed_path_world: tuple[tuple[float, float], ...] = ()
    tether_state: str = "UNAVAILABLE"
    tether_guidance_error_rad: float | None = None
    tether_projected_target_world: tuple[float, float] | None = None
    tether_centerline_world: tuple[tuple[float, float], ...] = ()
    visible_attackable_candidate_count: int = 0

    def __post_init__(self) -> None:
        if not isfinite(self.observed_monotonic_s) or self.observed_monotonic_s < 0:
            raise ValueError("movement lab observation time is invalid")
        if self.tracking_state not in {"VISIBLE", "LOST", "AMBIGUOUS"}:
            raise ValueError("movement lab tracking state is invalid")
        if self.target_identity_crc16 is not None and (
            type(self.target_identity_crc16) is not int
            or not 1 <= self.target_identity_crc16 <= 65_535
        ):
            raise ValueError("movement lab target identity is invalid")
        if self.tracking_state == "VISIBLE":
            if (
                self.target_error_x_normalized is None
                or not isfinite(self.target_error_x_normalized)
                or not -1 <= self.target_error_x_normalized <= 1
            ):
                raise ValueError("visible movement lab target error is invalid")
        elif self.target_error_x_normalized is not None:
            raise ValueError("non-visible movement lab state contains target error")
        if self.target_screen_y_normalized is not None and (
            self.tracking_state != "VISIBLE"
            or not isfinite(self.target_screen_y_normalized)
            or not 0 <= self.target_screen_y_normalized <= 1
        ):
            raise ValueError("movement lab target screen Y is invalid")
        if (self.player_world_x is None) != (self.player_world_y is None):
            raise ValueError("movement lab player position is incomplete")
        if self.player_world_x is not None and not all(
            isfinite(value) for value in (self.player_world_x, self.player_world_y)
        ):
            raise ValueError("movement lab player position is invalid")
        if self.player_world_z is not None and (
            self.player_world_x is None or not isfinite(self.player_world_z)
        ):
            raise ValueError("movement lab player height is invalid")
        if self.player_facing_rad is not None and not (
            isfinite(self.player_facing_rad) and -pi * 2 <= self.player_facing_rad <= pi * 2
        ):
            raise ValueError("movement lab player facing is invalid")
        for label, value in (
            ("body facing", self.body_facing_rad),
            ("camera yaw", self.camera_yaw_estimate_rad),
        ):
            if value is not None and not (
                isfinite(value) and -pi * 2 <= value <= pi * 2
            ):
                raise ValueError(f"movement lab {label} is invalid")
        if (self.body_facing_rad is None) != (self.body_facing_source is None):
            raise ValueError("movement lab body facing provenance is incomplete")
        if (self.camera_yaw_estimate_rad is None) != (self.camera_yaw_source is None):
            raise ValueError("movement lab camera yaw provenance is incomplete")
        if self.body_facing_source is not None and not self.body_facing_source:
            raise ValueError("movement lab body facing source is invalid")
        if self.camera_yaw_source is not None and not self.camera_yaw_source:
            raise ValueError("movement lab camera yaw source is invalid")
        if self.body_camera_yaw_delta_rad is not None and (
            self.body_facing_rad is None
            or self.camera_yaw_estimate_rad is None
            or not isfinite(self.body_camera_yaw_delta_rad)
            or not -pi <= self.body_camera_yaw_delta_rad <= pi
        ):
            raise ValueError("movement lab body/camera yaw delta is invalid")
        if self.waypoint_error_rad is not None and not (
            isfinite(self.waypoint_error_rad) and -pi <= self.waypoint_error_rad <= pi
        ):
            raise ValueError("movement lab waypoint error is invalid")
        if not isinstance(self.controller_state, str) or not self.controller_state:
            raise ValueError("movement lab controller state is invalid")
        if len(self.navmesh_polygons_world) > 4096:
            raise ValueError("movement lab navmesh polygon count is invalid")
        for polygon in self.navmesh_polygons_world:
            if not 3 <= len(polygon) <= 6 or any(
                len(point) != 2 or any(not isfinite(value) for value in point)
                for point in polygon
            ):
                raise ValueError("movement lab navmesh polygon is invalid")
        if len(self.corridor_centerline_world) > 4097 or any(
            len(point) != 2 or any(not isfinite(value) for value in point)
            for point in self.corridor_centerline_world
        ):
            raise ValueError("movement lab corridor centerline is invalid")
        if len(self.planned_waypoints_world) > 128 or any(
            len(point) != 2 or any(not isfinite(value) for value in point)
            for point in self.planned_waypoints_world
        ):
            raise ValueError("movement lab planned waypoints are invalid")
        if len(self.traversed_path_world) > 4096 or any(
            len(point) != 2 or any(not isfinite(value) for value in point)
            for point in self.traversed_path_world
        ):
            raise ValueError("movement lab traversed path is invalid")
        if self.tether_state not in {
            "UNAVAILABLE", "IN_MELEE", "WAITING_NAVMESH", "DIRECT",
            "DETOUR_LEFT", "DETOUR_RIGHT", "PARTIAL_ADVANCE_DIRECT",
            "PARTIAL_ADVANCE_LEFT", "PARTIAL_ADVANCE_RIGHT", "PARTIAL_BLOCKED",
        }:
            raise ValueError("movement lab tether state is invalid")
        if self.tether_guidance_error_rad is not None and not (
            isfinite(self.tether_guidance_error_rad)
            and -pi <= self.tether_guidance_error_rad <= pi
        ):
            raise ValueError("movement lab tether guidance is invalid")
        if self.tether_projected_target_world is not None and (
            len(self.tether_projected_target_world) != 2
            or any(not isfinite(value) for value in self.tether_projected_target_world)
        ):
            raise ValueError("movement lab projected target is invalid")
        if len(self.tether_centerline_world) > 128 or any(
            len(point) != 2 or any(not isfinite(value) for value in point)
            for point in self.tether_centerline_world
        ):
            raise ValueError("movement lab tether centerline is invalid")
        if self.tether_state != "UNAVAILABLE" and (
            self.player_world_x is None
            or self.tether_projected_target_world is None
            or not self.tether_centerline_world
        ):
            raise ValueError("movement lab active tether evidence is incomplete")
        if (
            type(self.visible_attackable_candidate_count) is not int
            or not 0 <= self.visible_attackable_candidate_count <= 255
        ):
            raise ValueError("movement lab visible candidate count is invalid")

    def arrow_vectors(self, *, radius_px: float = 70.0) -> dict[str, tuple[float, float]]:
        if not isfinite(radius_px) or radius_px <= 0:
            raise ValueError("movement lab radius is invalid")
        # RMB camera coupling defines player facing as the screen's vertical
        # axis.  The target arrow is relative to that axis; overlap means the
        # exact visual condition the servo is trying to hold.
        player = (0.0, -radius_px)
        target = (0.0, 0.0)
        if self.target_error_x_normalized is not None:
            angle = self.target_error_x_normalized * (pi / 2.0)
            target = (sin(angle) * radius_px, -cos(angle) * radius_px)
        waypoint = (0.0, 0.0)
        if self.waypoint_error_rad is not None:
            waypoint = (
                sin(self.waypoint_error_rad) * radius_px,
                -cos(self.waypoint_error_rad) * radius_px,
            )
        return {"player": player, "target": target, "waypoint": waypoint}

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "movement_lab_snapshot",
            "schema_version": MOVEMENT_LAB_SCHEMA_VERSION,
            "observed_monotonic_s": self.observed_monotonic_s,
            "tracking_state": self.tracking_state,
            "target_identity_crc16": self.target_identity_crc16,
            "target_error_x_normalized": self.target_error_x_normalized,
            "target_screen_y_normalized": self.target_screen_y_normalized,
            "player_world": (
                None
                if self.player_world_x is None
                else [
                    self.player_world_x,
                    self.player_world_y,
                    *([] if self.player_world_z is None else [self.player_world_z]),
                ]
            ),
            "player_facing_rad": self.player_facing_rad,
            "body_facing_rad": self.body_facing_rad,
            "body_facing_source": self.body_facing_source,
            "camera_yaw_estimate_rad": self.camera_yaw_estimate_rad,
            "camera_yaw_source": self.camera_yaw_source,
            "body_camera_yaw_delta_rad": self.body_camera_yaw_delta_rad,
            "waypoint_error_rad": self.waypoint_error_rad,
            "controller_state": self.controller_state,
            "navmesh_polygons_world": [
                [list(point) for point in polygon]
                for polygon in self.navmesh_polygons_world
            ],
            "corridor_centerline_world": [
                list(point) for point in self.corridor_centerline_world
            ],
            "planned_waypoints_world": [
                list(point) for point in self.planned_waypoints_world
            ],
            "traversed_path_world": [
                list(point) for point in self.traversed_path_world
            ],
            "tether_state": self.tether_state,
            "tether_guidance_error_rad": self.tether_guidance_error_rad,
            "tether_projected_target_world": (
                None
                if self.tether_projected_target_world is None
                else list(self.tether_projected_target_world)
            ),
            "tether_centerline_world": [
                list(point) for point in self.tether_centerline_world
            ],
            "visible_attackable_candidate_count": (
                self.visible_attackable_candidate_count
            ),
            "execution_authority": False,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "MovementLabSnapshot":
        if (
            record.get("record_type") != "movement_lab_snapshot"
            or record.get("schema_version") != MOVEMENT_LAB_SCHEMA_VERSION
            or record.get("execution_authority") is not False
        ):
            raise ValueError("movement lab record envelope is invalid")
        player_world = record.get("player_world")
        if player_world is not None and (
            not isinstance(player_world, list) or len(player_world) not in {2, 3}
        ):
            raise ValueError("movement lab player position record is invalid")
        return cls(
            observed_monotonic_s=float(record["observed_monotonic_s"]),
            tracking_state=str(record["tracking_state"]),
            target_identity_crc16=record.get("target_identity_crc16"),
            target_error_x_normalized=record.get("target_error_x_normalized"),
            target_screen_y_normalized=record.get("target_screen_y_normalized"),
            player_world_x=None if player_world is None else float(player_world[0]),
            player_world_y=None if player_world is None else float(player_world[1]),
            player_world_z=(
                None
                if player_world is None or len(player_world) == 2
                else float(player_world[2])
            ),
            player_facing_rad=record.get("player_facing_rad"),
            body_facing_rad=record.get("body_facing_rad"),
            body_facing_source=record.get("body_facing_source"),
            camera_yaw_estimate_rad=record.get("camera_yaw_estimate_rad"),
            camera_yaw_source=record.get("camera_yaw_source"),
            body_camera_yaw_delta_rad=record.get("body_camera_yaw_delta_rad"),
            waypoint_error_rad=record.get("waypoint_error_rad"),
            controller_state=str(record.get("controller_state", "OBSERVE")),
            navmesh_polygons_world=tuple(
                tuple((float(point[0]), float(point[1])) for point in polygon)
                for polygon in record.get("navmesh_polygons_world", ())
            ),
            corridor_centerline_world=tuple(
                (float(point[0]), float(point[1]))
                for point in record.get("corridor_centerline_world", ())
            ),
            planned_waypoints_world=tuple(
                (float(point[0]), float(point[1]))
                for point in record.get("planned_waypoints_world", ())
            ),
            traversed_path_world=tuple(
                (float(point[0]), float(point[1]))
                for point in record.get("traversed_path_world", ())
            ),
            tether_state=str(record.get("tether_state", "UNAVAILABLE")),
            tether_guidance_error_rad=record.get("tether_guidance_error_rad"),
            tether_projected_target_world=(
                None
                if record.get("tether_projected_target_world") is None
                else (
                    float(record["tether_projected_target_world"][0]),
                    float(record["tether_projected_target_world"][1]),
                )
            ),
            tether_centerline_world=tuple(
                (float(point[0]), float(point[1]))
                for point in record.get("tether_centerline_world", ())
            ),
            visible_attackable_candidate_count=int(
                record.get("visible_attackable_candidate_count", 0)
            ),
        )
