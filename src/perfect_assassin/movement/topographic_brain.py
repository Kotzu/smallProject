from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from perfect_assassin.movement.client_navmesh import NavCorridor, NavPoint
from perfect_assassin.movement.heading_integrity import EXACT_CLIENT_FACING_SOURCE
from perfect_assassin.movement.local_environment_awareness import (
    LocalEnvironmentAwareness,
)
from perfect_assassin.movement.world_model import LayeredWorldModel


TOPOGRAPHIC_BRAIN_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class TopographicBrainSnapshot:
    """Versioned view of the world knowledge used by movement.

    The immutable WorldPack remains the geometry source of truth.  This
    snapshot binds the actor, destination, current Detour corridor, local
    topology, road prior, live visibility and permanent experience without
    copying the whole mesh into another mutable map.
    """

    observed_monotonic_s: float
    map_name: str
    navmesh_sha256: str
    actor: NavPoint
    actor_facing_rad: float | None
    actor_position_source: str
    actor_facing_source: str
    controller_heading_rad: float | None
    destination: NavPoint
    corridor: NavCorridor
    environment: LocalEnvironmentAwareness | None
    semantic_route_profile: str | None
    semantic_goal_index: int
    semantic_goal_count: int
    visible_dynamic_entity_count: int
    routine_aggro_travel_enabled: bool
    minimum_travel_health_fraction: float
    experience_cell_count: int
    historical_risk_area_count: int

    def __post_init__(self) -> None:
        if (
            not self.map_name
            or len(self.navmesh_sha256) != 64
            or self.corridor.map_name != self.map_name
            or any(not isfinite(value) for value in (
                self.observed_monotonic_s,
                self.actor.x, self.actor.y, self.actor.z,
                self.destination.x, self.destination.y, self.destination.z,
                self.minimum_travel_health_fraction,
            ))
            or (
                self.actor_facing_rad is not None
                and not isfinite(self.actor_facing_rad)
            )
            or not self.actor_position_source
            or not self.actor_facing_source
            or (
                self.controller_heading_rad is not None
                and not isfinite(self.controller_heading_rad)
            )
            or self.observed_monotonic_s < 0
            or not 0.0 <= self.minimum_travel_health_fraction <= 1.0
            or self.semantic_goal_index < 0
            or self.semantic_goal_count < 0
            or (
                self.semantic_goal_count == 0 and self.semantic_goal_index != 0
            )
            or (
                self.semantic_goal_count > 0
                and self.semantic_goal_index >= self.semantic_goal_count
            )
            or min(
                self.visible_dynamic_entity_count,
                self.experience_cell_count,
                self.historical_risk_area_count,
            ) < 0
        ):
            raise ValueError("topographic brain snapshot is invalid")
        if self.environment is not None and (
            self.environment.map_name != self.map_name
            or self.environment.position.distance_2d(self.actor) > 3.0
            or abs(self.environment.position.z - self.actor.z) > 3.0
        ):
            raise ValueError("topographic environment is not bound to actor")

    def to_record(self) -> dict[str, Any]:
        awareness = self.corridor.start_awareness
        environment_state = (
            awareness.environment_class if awareness is not None else "UNAVAILABLE"
        )
        exact_body_facing = (
            self.actor_facing_rad is not None
            and self.actor_facing_source == EXACT_CLIENT_FACING_SOURCE
        )
        return {
            "record_type": "topographic_world_brain",
            "schema_version": TOPOGRAPHIC_BRAIN_SCHEMA_VERSION,
            "map_name": self.map_name,
            "observed_monotonic_s": self.observed_monotonic_s,
            "coordinate_frame": "CLIENT_WORLD_XYZ",
            "actor": {
                "position": [self.actor.x, self.actor.y, self.actor.z],
                "position_source": self.actor_position_source,
                "body_facing_rad": self.actor_facing_rad,
                "body_facing_source": self.actor_facing_source,
                "controller_heading_rad": self.controller_heading_rad,
            },
            "foundation": {
                "model": "LOCALIZED_ACTOR_IN_IMMUTABLE_3D_WORLD",
                "static_world_bound": True,
                "live_position_available": True,
                "exact_body_facing_available": exact_body_facing,
                "autonomous_planning_ready": exact_body_facing,
                "visual_actor_silhouette_is_authority": False,
            },
            "destination": [
                self.destination.x, self.destination.y, self.destination.z,
            ],
            "knowledge_layers": {
                "global_static_geometry": {
                    "semantics": "IMMUTABLE_CLIENT_ASSET_WORLDPACK",
                    "navmesh_sha256": self.navmesh_sha256.upper(),
                    "query_model": "TILED_DETOUR_NAVMESH",
                    "whole_mesh_duplicated_in_snapshot": False,
                },
                "local_topology": {
                    "semantics": "QUERIED_AROUND_CURRENT_ACTOR_POSE",
                    "available": awareness is not None,
                    "environment_state": environment_state,
                    "physical_surfaces": (
                        [] if awareness is None
                        else sorted(awareness.physical_surfaces)
                    ),
                    "topology_radius_yards": (
                        None if awareness is None else awareness.topology_radius_yards
                    ),
                    "polygon_count": (
                        0 if awareness is None else awareness.component_polygon_count
                    ),
                    "boundary_count": (
                        0 if self.environment is None
                        else len(self.environment.boundaries)
                    ),
                    "verified_egress_count": (
                        0 if self.environment is None
                        else len(self.environment.verified_egresses)
                    ),
                    "topology_complete": (
                        False if self.environment is None
                        else self.environment.topology_complete
                    ),
                },
                "road_semantics": {
                    "semantics": "GLOBAL_CLIENT_ADT_TEXTURE_PRIOR",
                    "active": self.semantic_route_profile is not None,
                    "profile": self.semantic_route_profile,
                    "goal_index": self.semantic_goal_index,
                    "goal_count": self.semantic_goal_count,
                },
                "live_dynamic": {
                    "semantics": "CURRENT_CLIENT_VISIBILITY_SET_ONLY",
                    "visibility_ceiling_yards": 100.0,
                    "visible_entity_count": self.visible_dynamic_entity_count,
                },
                "permanent_experience": {
                    "semantics": "RETAINED_WITHOUT_TIME_EXPIRY",
                    "visited_cell_count": self.experience_cell_count,
                    "historical_risk_area_count": self.historical_risk_area_count,
                },
            },
            "active_navigation": {
                "planner": "GLOBAL_SEMANTIC_PRIOR_PLUS_LOCAL_3D_NAVMESH",
                "corridor_complete": self.corridor.complete,
                "corridor_point_count": len(self.corridor.guidance_points()),
                "corridor_polygon_count": len(self.corridor.polygons),
                "road_polygons_preferred": self.corridor.road_polygons_preferred,
                "route_is_operator_hardcoded": False,
            },
            "routine_aggro_policy": {
                "continue_destination_corridor": self.routine_aggro_travel_enabled,
                "minimum_health_fraction": self.minimum_travel_health_fraction,
                "combat_handoff_for_routine_aggro": False,
            },
            "execution_authority": False,
        }


def build_topographic_brain_snapshot(
    *,
    world: LayeredWorldModel,
    observed_monotonic_s: float,
    actor: NavPoint,
    actor_facing_rad: float | None,
    actor_position_source: str,
    actor_facing_source: str,
    controller_heading_rad: float | None,
    destination: NavPoint,
    corridor: NavCorridor,
    environment: LocalEnvironmentAwareness | None,
    semantic_route_profile: str | None,
    semantic_goal_index: int,
    semantic_goal_count: int,
    visible_dynamic_entity_count: int,
    routine_aggro_travel_enabled: bool,
    minimum_travel_health_fraction: float,
) -> TopographicBrainSnapshot:
    return TopographicBrainSnapshot(
        observed_monotonic_s=observed_monotonic_s,
        map_name=world.map_name,
        navmesh_sha256=world.static_navmesh_sha256,
        actor=actor,
        actor_facing_rad=actor_facing_rad,
        actor_position_source=actor_position_source,
        actor_facing_source=actor_facing_source,
        controller_heading_rad=controller_heading_rad,
        destination=destination,
        corridor=corridor,
        environment=environment,
        semantic_route_profile=semantic_route_profile,
        semantic_goal_index=semantic_goal_index,
        semantic_goal_count=semantic_goal_count,
        visible_dynamic_entity_count=visible_dynamic_entity_count,
        routine_aggro_travel_enabled=routine_aggro_travel_enabled,
        minimum_travel_health_fraction=minimum_travel_health_fraction,
        experience_cell_count=len(world.cells()),
        historical_risk_area_count=len(world.historical_risk_areas()),
    )
