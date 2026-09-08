from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import hypot, isfinite
from typing import Any


SCHEMA_VERSION = "1.0"
COORDINATE_SYSTEM = "tbc243_client_world_xy"
MAX_OBSTACLES = 512
PROVISIONAL_TTL = timedelta(days=7)
DETOUR_EXCLUSION_EVIDENCE = "collision_slide_and_successful_detour_exclusion"
LOCAL_CLEARANCE_EVIDENCE = "collision_and_navmesh_validated_local_clearance"
VALID_EVIDENCE = frozenset({DETOUR_EXCLUSION_EVIDENCE, LOCAL_CLEARANCE_EVIDENCE})
BOUNDED_CELL_REPRESENTATION = "bounded_boundary_cell_v1"
POLYGON_UNION_REPRESENTATION = "polygon_union_disc_v1"
LEGACY_MERGED_DISC_REPRESENTATION = "legacy_merged_disc_v0"
VALID_REPRESENTATIONS = frozenset({
    BOUNDED_CELL_REPRESENTATION,
    POLYGON_UNION_REPRESENTATION,
    LEGACY_MERGED_DISC_REPRESENTATION,
})
# Learned radius describes the observed object.  Navmesh exclusion must also
# carry the moving actor's horizontal capsule; otherwise a mathematically valid
# point path can graze a remembered tree/signpost while the visible character
# still collides.  Keep the two values separate so experience is not silently
# rewritten when a different actor profile consumes it.
DEFAULT_ACTOR_CLEARANCE_WORLD = 1.25
# Client collision contacts are samples of a boundary, not estimates of one
# circular object's centre.  Keep nearby samples as bounded cells so a long or
# concave wall cannot inflate into one disc that erases its real doorway.
LOCAL_CLEARANCE_CELL_MERGE_WORLD = 1.0


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("obstacle timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("obstacle timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class LearnedObstacle:
    obstacle_id: str
    map_name: str
    zone_index: int
    x: float
    y: float
    z: float
    radius: float
    observations: int
    first_observed_at: str
    last_observed_at: str
    last_run_id: str
    evidence: str = DETOUR_EXCLUSION_EVIDENCE
    representation: str = BOUNDED_CELL_REPRESENTATION

    def __post_init__(self) -> None:
        if (
            not self.obstacle_id.startswith("obstacle:")
            or not self.map_name.strip()
            or not 0 <= self.zone_index <= 10_000
            or any(not isfinite(value) for value in (self.x, self.y, self.z, self.radius))
            or not -500.0 <= self.z <= 5000.0
            or not 1.0 <= self.radius <= 30.0
            or not 1 <= self.observations <= 1_000_000
            or not self.last_run_id.strip()
            or self.evidence not in VALID_EVIDENCE
            or self.representation not in VALID_REPRESENTATIONS
        ):
            raise ValueError("learned obstacle is invalid")
        if _utc(self.last_observed_at) < _utc(self.first_observed_at):
            raise ValueError("learned obstacle timestamps are inconsistent")

    @property
    def blocker(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.z, self.radius

    def planning_blocker(
        self, *, actor_clearance_world: float = DEFAULT_ACTOR_CLEARANCE_WORLD,
    ) -> tuple[float, float, float, float]:
        if (
            not isfinite(actor_clearance_world)
            or not 0.0 <= actor_clearance_world <= 5.0
        ):
            raise ValueError("actor obstacle clearance is invalid")
        return self.x, self.y, self.z, self.radius + actor_clearance_world

    @property
    def confidence(self) -> str:
        return "confirmed" if self.observations >= 2 else "provisional"

    @property
    def planning_confirmed(self) -> bool:
        """Whether evidence is strong enough to shape a future route.

        A successful bypass proves that the maneuver was executable, but does
        not by itself prove that the blocker was static.  A player, NPC, or
        pet can produce the same short-term collision evidence.  Persistent
        route shaping therefore requires an independent repeat observation;
        dynamic avoidance belongs to the live entity layer.
        """

        return (
            self.observations >= 2
            and self.representation != LEGACY_MERGED_DISC_REPRESENTATION
        )

    def is_fresh(self, *, now: datetime) -> bool:
        # A repeated, independently observed collision is durable gameplay
        # knowledge.  Expiring it made the actor repeat a solved mistake after
        # an arbitrary number of days.  Single observations still age out of
        # active planning because they may be capture noise; confirmation
        # promotes the evidence to permanent memory.
        if self.planning_confirmed:
            return True
        return (
            now.astimezone(timezone.utc) - _utc(self.last_observed_at)
            <= PROVISIONAL_TTL
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.obstacle_id,
            "map": self.map_name,
            "zone_index": self.zone_index,
            "center_world": [self.x, self.y, self.z],
            "radius_world": self.radius,
            "observations": self.observations,
            "confidence": self.confidence,
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "last_run_id": self.last_run_id,
            "evidence": self.evidence,
            "representation": self.representation,
            "execution_authority": False,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "LearnedObstacle":
        center = record.get("center_world")
        if not isinstance(center, list) or len(center) != 3:
            raise ValueError("learned obstacle center is invalid")
        obstacle = cls(
            obstacle_id=str(record["id"]),
            map_name=str(record["map"]),
            zone_index=int(record["zone_index"]),
            x=float(center[0]),
            y=float(center[1]),
            z=float(center[2]),
            radius=float(record["radius_world"]),
            observations=int(record["observations"]),
            first_observed_at=str(record["first_observed_at"]),
            last_observed_at=str(record["last_observed_at"]),
            last_run_id=str(record["last_run_id"]),
            evidence=str(record["evidence"]),
            representation=str(record.get(
                "representation",
                LEGACY_MERGED_DISC_REPRESENTATION
                if record.get("evidence") == LOCAL_CLEARANCE_EVIDENCE
                else POLYGON_UNION_REPRESENTATION,
            )),
        )
        if record.get("confidence") != obstacle.confidence:
            raise ValueError("learned obstacle confidence is inconsistent")
        if record.get("execution_authority") is not False:
            raise ValueError("learned obstacle cannot grant execution authority")
        return obstacle


@dataclass(frozen=True, slots=True)
class LearnedObstacleMemory:
    client_build: int
    obstacles: tuple[LearnedObstacle, ...] = ()
    coordinate_system: str = COORDINATE_SYSTEM
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.client_build <= 0
            or self.coordinate_system != COORDINATE_SYSTEM
            or self.execution_authority
            or len(self.obstacles) > MAX_OBSTACLES
            or len({item.obstacle_id for item in self.obstacles}) != len(self.obstacles)
        ):
            raise ValueError("learned obstacle memory is invalid")

    def nearby(
        self,
        *,
        map_name: str,
        zone_index: int,
        x: float,
        y: float,
        now: datetime,
        maximum_distance_world: float = 300.0,
        limit: int = 8,
    ) -> tuple[LearnedObstacle, ...]:
        if (
            not map_name.strip()
            or not 0 <= zone_index <= 10_000
            or any(not isfinite(value) for value in (x, y, maximum_distance_world))
            or maximum_distance_world <= 0
            or not 1 <= limit <= 8
        ):
            raise ValueError("learned obstacle query is invalid")
        candidates = (
            item for item in self.obstacles
            if item.map_name == map_name
            and item.zone_index == zone_index
            and item.is_fresh(now=now)
            and hypot(item.x - x, item.y - y) <= maximum_distance_world
        )
        return tuple(sorted(
            candidates,
            key=lambda item: (
                hypot(item.x - x, item.y - y),
                -item.observations,
                item.x,
                item.y,
                item.obstacle_id,
            ),
        )[:limit])

    def observe(
        self,
        *,
        map_name: str,
        zone_index: int,
        blocker: tuple[float, float, float, float],
        run_id: str,
        observed_at: datetime,
        evidence: str = DETOUR_EXCLUSION_EVIDENCE,
    ) -> "LearnedObstacleMemory":
        if len(blocker) != 4 or not run_id.strip() or evidence not in VALID_EVIDENCE:
            raise ValueError("learned obstacle observation is invalid")
        x, y, z, radius = (float(value) for value in blocker)
        timestamp = _timestamp(observed_at)
        matching_index = next((
            index for index, item in enumerate(self.obstacles)
            if item.map_name == map_name
            and item.zone_index == zone_index
            and hypot(item.x - x, item.y - y) <= (
                LOCAL_CLEARANCE_CELL_MERGE_WORLD
                if evidence == LOCAL_CLEARANCE_EVIDENCE
                else max(item.radius, radius) + 1.0
            )
            and abs(item.z - z) <= 2.5
            and item.evidence == evidence
            and item.representation != LEGACY_MERGED_DISC_REPRESENTATION
        ), None)
        updated = list(self.obstacles)
        if matching_index is None:
            representation = (
                BOUNDED_CELL_REPRESENTATION
                if evidence == LOCAL_CLEARANCE_EVIDENCE
                else POLYGON_UNION_REPRESENTATION
            )
            identity = sha256(
                f"{self.client_build}|{map_name}|{zone_index}|{x:.2f}|{y:.2f}|{z:.2f}|{evidence}|{representation}".encode(
                    "utf-8"
                )
            ).hexdigest()[:16]
            updated.append(LearnedObstacle(
                obstacle_id=f"obstacle:{identity}",
                map_name=map_name,
                zone_index=zone_index,
                x=x,
                y=y,
                z=z,
                radius=radius,
                observations=1,
                first_observed_at=timestamp,
                last_observed_at=timestamp,
                last_run_id=run_id,
                evidence=evidence,
                representation=representation,
            ))
        else:
            prior = updated[matching_index]
            count = prior.observations + 1
            merged_x = (prior.x * prior.observations + x) / count
            merged_y = (prior.y * prior.observations + y) / count
            # Repeated contacts at different points describe the extent of a
            # wall, cart or tree cluster, not noisy samples of one zero-sized
            # point. Preserve the union of both observed clearance discs when
            # moving their shared centre; max(radius) alone made Predator hit
            # a different edge of the same obstacle on every later run.
            merged_radius = (
                max(prior.radius, radius)
                if evidence == LOCAL_CLEARANCE_EVIDENCE
                else max(
                    hypot(prior.x - merged_x, prior.y - merged_y) + prior.radius,
                    hypot(x - merged_x, y - merged_y) + radius,
                )
            )
            updated[matching_index] = replace(
                prior,
                x=merged_x,
                y=merged_y,
                z=(prior.z * prior.observations + z) / count,
                radius=min(30.0, merged_radius),
                observations=count,
                last_observed_at=timestamp,
                last_run_id=run_id,
            )
        fresh = [item for item in updated if item.is_fresh(now=observed_at)]
        fresh.sort(key=lambda item: (_utc(item.last_observed_at), item.obstacle_id), reverse=True)
        return replace(self, obstacles=tuple(fresh[:MAX_OBSTACLES]))

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": "client_observed_obstacle_memory",
            "client_build": self.client_build,
            "coordinate_system": self.coordinate_system,
            "execution_authority": False,
            "obstacles": [item.to_record() for item in self.obstacles],
        }

    @classmethod
    def from_record(
        cls, record: dict[str, Any], *, expected_client_build: int,
    ) -> "LearnedObstacleMemory":
        if record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported learned obstacle memory schema")
        if record.get("record_type") != "client_observed_obstacle_memory":
            raise ValueError("unexpected learned obstacle memory record type")
        if int(record.get("client_build", -1)) != expected_client_build:
            raise ValueError("learned obstacle memory client build mismatch")
        obstacles = record.get("obstacles")
        if not isinstance(obstacles, list):
            raise ValueError("learned obstacle memory list is invalid")
        return cls(
            client_build=expected_client_build,
            coordinate_system=str(record.get("coordinate_system", "")),
            execution_authority=bool(record.get("execution_authority", False)),
            obstacles=tuple(LearnedObstacle.from_record(item) for item in obstacles),
        )

    @classmethod
    def empty(cls, *, client_build: int) -> "LearnedObstacleMemory":
        return cls(client_build=client_build)
