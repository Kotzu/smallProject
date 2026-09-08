"""Boundary loader for the read-only leveling-plan contract."""

from __future__ import annotations

import json
from pathlib import Path

from perfect_assassin.brain.leveling import (
    LevelingContractError,
    LevelingPlan,
    PLAN_SCHEMA_VERSION,
)
from perfect_assassin.knowledge.broker import KnowledgeBrokerError, KnowledgeEntry


def load_leveling_plan(path: Path) -> LevelingPlan:
    """Load and re-check a plan before an integration runner may use it."""

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise KnowledgeBrokerError(f"cannot read leveling plan: {error}") from error
    if not isinstance(record, dict):
        raise KnowledgeBrokerError("leveling plan root must be an object")
    if (
        record.get("record_type") != "leveling_plan"
        or record.get("schema_version") != PLAN_SCHEMA_VERSION
        or record.get("execution_authority") is not False
        or not isinstance(record.get("steps"), list)
    ):
        raise KnowledgeBrokerError("unsupported leveling plan")
    try:
        steps = tuple(KnowledgeEntry.from_record(item) for item in record["steps"])
        goal = record.get("next_goal")
        next_goal = None
        if goal is not None:
            if (
                not isinstance(goal, dict)
                or goal.get("coordinate_frame") != "normalized_map_2d"
            ):
                raise LevelingContractError("leveling plan goal is invalid")
            next_goal = (float(goal["x"]), float(goal["y"]))
        return LevelingPlan(
            plan_id=str(record["plan_id"]),
            catalog_id=str(record["catalog_id"]),
            target_profile=str(record["target_profile"]),
            current_level=int(record["current_level"]),
            map_id=int(record["map_id"]),
            map_name=str(record["map_name"]),
            steps=steps,
            next_step_order=int(record["next_step_order"]),
            status=str(record["status"]),
            next_goal=next_goal,
        )
    except (KeyError, TypeError, ValueError, KnowledgeBrokerError) as error:
        raise KnowledgeBrokerError(f"invalid leveling plan: {error}") from error
