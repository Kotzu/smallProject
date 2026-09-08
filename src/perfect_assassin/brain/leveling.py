"""Bounded leveling decisions built from the read-only RouteTeacher contract.

Zygor is a teacher here.  It can suggest the next guide facts, but it cannot
press a key, choose a server position, or grant movement authority.  The
client observer and the movement planner must still confirm every suggested
location before any execution gateway is considered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


PLAN_SCHEMA_VERSION = "1.0"
POLICY_ID = "zygor_leveling_brain_v1"
POLICY_VERSION = "1.0.0"
MAX_PLAN_STEPS = 64


class LevelingContractError(ValueError):
    """A leveling request or proposal is outside its bounded contract."""


@runtime_checkable
class RouteEntryContract(Protocol):
    entry_id: str
    kind: str
    map_id: int
    map_name: str
    map_scope: str
    level_min: int
    level_max: int
    step_order: int | None
    position: Any
    source: Any
    execution_authority: bool

    def to_record(self) -> dict[str, Any]: ...


@runtime_checkable
class RouteCatalogContract(Protocol):
    catalog_id: str
    target_profile: str
    execution_authority: bool
    entries: tuple[RouteEntryContract, ...]


@dataclass(frozen=True, slots=True)
class LevelingRequest:
    """The small, observed input needed for one leveling plan."""

    current_level: int
    map_id: int
    completed_entry_ids: frozenset[str] = frozenset()
    after_step_order: int = 0
    limit: int = 16

    def __post_init__(self) -> None:
        if type(self.current_level) is not int or not 1 <= self.current_level <= 70:
            raise LevelingContractError("leveling current level must be in 1..70")
        if type(self.map_id) is not int or not 0 <= self.map_id <= 2_147_483_647:
            raise LevelingContractError("leveling map id is invalid")
        if (
            not isinstance(self.completed_entry_ids, frozenset)
            or any(
                type(entry_id) is not str or not entry_id
                for entry_id in self.completed_entry_ids
            )
        ):
            raise LevelingContractError("leveling completed entry IDs are invalid")
        if type(self.after_step_order) is not int or not 0 <= self.after_step_order <= 100_000:
            raise LevelingContractError("leveling cursor order is invalid")
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PLAN_STEPS:
            raise LevelingContractError("leveling plan limit is invalid")


@dataclass(frozen=True, slots=True)
class LevelingPlan:
    """Read-only guide suggestions plus the next safe-to-project candidate."""

    plan_id: str
    catalog_id: str
    target_profile: str
    current_level: int
    map_id: int
    map_name: str
    steps: tuple[RouteEntryContract, ...]
    next_step_order: int
    status: str
    next_goal: tuple[float, float] | None

    def __post_init__(self) -> None:
        if not self.plan_id or len(self.plan_id) > 128:
            raise LevelingContractError("leveling plan ID is invalid")
        if not self.catalog_id or len(self.catalog_id) > 128:
            raise LevelingContractError("leveling catalog ID is invalid")
        if not self.target_profile or len(self.target_profile) > 128:
            raise LevelingContractError("leveling target profile is invalid")
        if type(self.current_level) is not int or not 1 <= self.current_level <= 70:
            raise LevelingContractError("leveling plan level is invalid")
        if type(self.map_id) is not int or self.map_id < 0:
            raise LevelingContractError("leveling plan map ID is invalid")
        if not isinstance(self.map_name, str) or not self.map_name.strip():
            raise LevelingContractError("leveling plan map name is invalid")
        if not isinstance(self.steps, tuple) or len(self.steps) > MAX_PLAN_STEPS:
            raise LevelingContractError("leveling plan step count is invalid")
        if any(not hasattr(step, "to_record") for step in self.steps):
            raise LevelingContractError("leveling plan contains an invalid step")
        if type(self.next_step_order) is not int or not 0 <= self.next_step_order <= 100_000:
            raise LevelingContractError("leveling next step order is invalid")
        if self.status not in {"READY", "NO_STEP", "ADVISORY_ONLY"}:
            raise LevelingContractError("leveling plan status is invalid")
        if self.next_goal is not None:
            if (
                not isinstance(self.next_goal, tuple)
                or len(self.next_goal) != 2
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0.0 <= float(value) <= 1.0
                    for value in self.next_goal
                )
            ):
                raise LevelingContractError("leveling next goal is invalid")
        if self.status == "READY" and self.next_goal is None:
            raise LevelingContractError("ready leveling plan needs a goal")

    @property
    def next_position_step(self) -> RouteEntryContract | None:
        for step in self.steps:
            if step.position is not None:
                return step
        return None

    def to_record(self) -> dict[str, Any]:
        return {
            "record_type": "leveling_plan",
            "schema_version": PLAN_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "catalog_id": self.catalog_id,
            "target_profile": self.target_profile,
            "current_level": self.current_level,
            "map_id": self.map_id,
            "map_name": self.map_name,
            "status": self.status,
            "next_step_order": self.next_step_order,
            "next_goal": (
                None
                if self.next_goal is None
                else {
                    "x": float(self.next_goal[0]),
                    "y": float(self.next_goal[1]),
                    "coordinate_frame": "normalized_map_2d",
                }
            ),
            "steps": [step.to_record() for step in self.steps],
            "execution_authority": False,
        }


class LevelingBrain:
    """Select the next bounded RouteTeacher facts for the current level."""

    policy_id = POLICY_ID
    policy_version = POLICY_VERSION

    def plan(
        self,
        catalog: RouteCatalogContract,
        request: LevelingRequest,
        *,
        plan_id: str,
    ) -> LevelingPlan:
        if not isinstance(catalog, RouteCatalogContract):
            raise LevelingContractError("leveling catalog is invalid")
        if catalog.execution_authority:
            raise LevelingContractError("leveling catalog cannot grant authority")
        if not isinstance(request, LevelingRequest):
            raise LevelingContractError("leveling request is invalid")
        if not isinstance(plan_id, str) or not plan_id or len(plan_id) > 128:
            raise LevelingContractError("leveling plan ID is invalid")

        candidates = [
            entry
            for entry in catalog.entries
            if entry.source.provider == "route_teacher"
            and entry.execution_authority is False
            and entry.map_scope == "worldpack"
            and entry.map_id == request.map_id
            and entry.level_min <= request.current_level <= entry.level_max
            and entry.entry_id not in request.completed_entry_ids
            and entry.step_order is not None
            and entry.step_order > request.after_step_order
        ]
        candidates.sort(key=lambda entry: (entry.step_order or 0, entry.entry_id))
        entries = tuple(candidates[: request.limit])
        map_name = next(
            (
                entry.map_name
                for entry in catalog.entries
                if entry.map_id == request.map_id
                and entry.map_scope == "worldpack"
            ),
            f"map-{request.map_id}",
        )
        next_position_step = next(
            (entry for entry in entries if entry.position is not None), None
        )
        next_goal = None
        if next_position_step is not None and next_position_step.position is not None:
            position = next_position_step.position
            if position.coordinate_frame != "normalized_map_2d":
                raise LevelingContractError("leveling goal is not a normalized map candidate")
            next_goal = (float(position.x), float(position.y))
        if not entries:
            status = "NO_STEP"
            next_step_order = request.after_step_order
        elif next_goal is None:
            status = "ADVISORY_ONLY"
            next_step_order = max(
                (entry.step_order or request.after_step_order for entry in entries),
                default=request.after_step_order,
            )
        else:
            status = "READY"
            next_step_order = max(
                (entry.step_order or request.after_step_order for entry in entries),
                default=request.after_step_order,
            )
        return LevelingPlan(
            plan_id=plan_id,
            catalog_id=catalog.catalog_id,
            target_profile=catalog.target_profile,
            current_level=request.current_level,
            map_id=request.map_id,
            map_name=map_name,
            steps=entries,
            next_step_order=next_step_order,
            status=status,
            next_goal=next_goal,
        )
