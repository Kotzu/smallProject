from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import floor, isfinite
from typing import Any


SCHEMA_VERSION = "1.0"
RECORD_TYPE = "client_observed_recovery_strategy_memory"
COORDINATE_SYSTEM = "tbc243_client_world_xy"
PROVENANCE = "client_observed_collision_during_recovery"
MAX_FAILURES = 256
PROVISIONAL_TTL = timedelta(days=7)
FAILURE_CELL_WORLD = 12.0
LOCAL_CLEARANCE_STRATEGY = "local_clearance"
VALID_STRATEGIES = frozenset({LOCAL_CLEARANCE_STRATEGY})


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("recovery failure timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("recovery failure timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _cell(value: float) -> int:
    if not isfinite(value):
        raise ValueError("recovery failure coordinate is non-finite")
    return int(floor(value / FAILURE_CELL_WORLD))


@dataclass(frozen=True, slots=True)
class RecoveryStrategyFailure:
    failure_id: str
    map_name: str
    zone_index: int
    cell_x: int
    cell_y: int
    strategy: str
    observations: int
    first_observed_at: str
    last_observed_at: str
    last_run_id: str

    def __post_init__(self) -> None:
        if (
            not self.failure_id.startswith("recovery-failure:")
            or not self.map_name.strip()
            or not 0 <= self.zone_index <= 10_000
            or self.strategy not in VALID_STRATEGIES
            or not 1 <= self.observations <= 1_000_000
            or not self.last_run_id.strip()
        ):
            raise ValueError("recovery strategy failure is invalid")
        if _utc(self.last_observed_at) < _utc(self.first_observed_at):
            raise ValueError("recovery strategy failure timestamps are inconsistent")

    @property
    def confidence(self) -> str:
        return "confirmed" if self.observations >= 2 else "provisional"

    @property
    def planning_confirmed(self) -> bool:
        return self.observations >= 2

    def is_fresh(self, *, now: datetime) -> bool:
        if self.planning_confirmed:
            return True
        return (
            now.astimezone(timezone.utc) - _utc(self.last_observed_at)
            <= PROVISIONAL_TTL
        )

    def to_record(self) -> dict[str, object]:
        return {
            "id": self.failure_id,
            "map": self.map_name,
            "zone_index": self.zone_index,
            "cell": [self.cell_x, self.cell_y],
            "strategy": self.strategy,
            "observations": self.observations,
            "confidence": self.confidence,
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "last_run_id": self.last_run_id,
            "execution_authority": False,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "RecoveryStrategyFailure":
        cell = record.get("cell")
        if not isinstance(cell, list) or len(cell) != 2:
            raise ValueError("recovery failure cell is invalid")
        failure = cls(
            failure_id=str(record["id"]),
            map_name=str(record["map"]),
            zone_index=int(record["zone_index"]),
            cell_x=int(cell[0]),
            cell_y=int(cell[1]),
            strategy=str(record["strategy"]),
            observations=int(record["observations"]),
            first_observed_at=str(record["first_observed_at"]),
            last_observed_at=str(record["last_observed_at"]),
            last_run_id=str(record["last_run_id"]),
        )
        if record.get("confidence") != failure.confidence:
            raise ValueError("recovery failure confidence is inconsistent")
        if record.get("execution_authority") is not False:
            raise ValueError("recovery failure cannot grant execution authority")
        return failure


@dataclass(frozen=True, slots=True)
class RecoveryStrategyMemory:
    client_build: int
    failures: tuple[RecoveryStrategyFailure, ...] = ()
    coordinate_system: str = COORDINATE_SYSTEM
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.client_build <= 0
            or self.coordinate_system != COORDINATE_SYSTEM
            or self.execution_authority
            or len(self.failures) > MAX_FAILURES
            or len({item.failure_id for item in self.failures}) != len(self.failures)
        ):
            raise ValueError("recovery strategy memory is invalid")

    @classmethod
    def empty(cls, *, client_build: int) -> "RecoveryStrategyMemory":
        return cls(client_build=client_build)

    def should_skip(
        self,
        *,
        map_name: str,
        zone_index: int,
        x: float,
        y: float,
        strategy: str,
        now: datetime,
    ) -> RecoveryStrategyFailure | None:
        if (
            not map_name.strip()
            or not 0 <= zone_index <= 10_000
            or not strategy in VALID_STRATEGIES
        ):
            raise ValueError("recovery strategy query is invalid")
        cell_x, cell_y = _cell(x), _cell(y)
        candidates = (
            item
            for item in self.failures
            if (
                item.map_name == map_name
                and item.zone_index == zone_index
                and item.cell_x == cell_x
                and item.cell_y == cell_y
                and item.strategy == strategy
                and item.planning_confirmed
                and item.is_fresh(now=now)
            )
        )
        return max(
            candidates,
            key=lambda item: (item.observations, item.last_observed_at),
            default=None,
        )

    def observe_failure(
        self,
        *,
        map_name: str,
        zone_index: int,
        x: float,
        y: float,
        strategy: str,
        run_id: str,
        observed_at: datetime,
    ) -> "RecoveryStrategyMemory":
        if (
            not map_name.strip()
            or not 0 <= zone_index <= 10_000
            or strategy not in VALID_STRATEGIES
            or not run_id.strip()
        ):
            raise ValueError("recovery strategy observation is invalid")
        cell_x, cell_y = _cell(x), _cell(y)
        timestamp = _timestamp(observed_at)
        matching_index = next(
            (
                index
                for index, item in enumerate(self.failures)
                if (
                    item.map_name == map_name
                    and item.zone_index == zone_index
                    and item.cell_x == cell_x
                    and item.cell_y == cell_y
                    and item.strategy == strategy
                )
            ),
            None,
        )
        updated = list(self.failures)
        if matching_index is None:
            identity = sha256(
                f"{self.client_build}|{map_name}|{zone_index}|{cell_x}|{cell_y}|{strategy}".encode(
                    "utf-8"
                )
            ).hexdigest()[:16]
            updated.append(
                RecoveryStrategyFailure(
                    failure_id=f"recovery-failure:{identity}",
                    map_name=map_name,
                    zone_index=zone_index,
                    cell_x=cell_x,
                    cell_y=cell_y,
                    strategy=strategy,
                    observations=1,
                    first_observed_at=timestamp,
                    last_observed_at=timestamp,
                    last_run_id=run_id,
                )
            )
        else:
            prior = updated[matching_index]
            updated[matching_index] = replace(
                prior,
                observations=prior.observations + 1,
                last_observed_at=timestamp,
                last_run_id=run_id,
            )
        fresh = [item for item in updated if item.is_fresh(now=observed_at)]
        fresh.sort(
            key=lambda item: (_utc(item.last_observed_at), item.failure_id),
            reverse=True,
        )
        return replace(self, failures=tuple(fresh[:MAX_FAILURES]))

    def resolve_success(
        self,
        *,
        map_name: str,
        zone_index: int,
        x: float,
        y: float,
        strategy: str,
    ) -> "RecoveryStrategyMemory":
        if strategy not in VALID_STRATEGIES:
            raise ValueError("recovery strategy is invalid")
        cell_x, cell_y = _cell(x), _cell(y)
        remaining = tuple(
            item
            for item in self.failures
            if not (
                item.map_name == map_name
                and item.zone_index == zone_index
                and item.cell_x == cell_x
                and item.cell_y == cell_y
                and item.strategy == strategy
            )
        )
        return replace(self, failures=remaining)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": RECORD_TYPE,
            "client_build": self.client_build,
            "coordinate_system": self.coordinate_system,
            "provenance": PROVENANCE,
            "execution_authority": False,
            "failures": [item.to_record() for item in self.failures],
        }

    @classmethod
    def from_record(
        cls, record: dict[str, Any], *, expected_client_build: int
    ) -> "RecoveryStrategyMemory":
        if record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported recovery strategy memory schema")
        if record.get("record_type") != RECORD_TYPE:
            raise ValueError("unexpected recovery strategy memory record type")
        if record.get("provenance") != PROVENANCE:
            raise ValueError("recovery strategy memory provenance is invalid")
        if int(record.get("client_build", -1)) != expected_client_build:
            raise ValueError("recovery strategy memory client build mismatch")
        failures = record.get("failures")
        if not isinstance(failures, list):
            raise ValueError("recovery strategy memory list is invalid")
        return cls(
            client_build=expected_client_build,
            coordinate_system=str(record.get("coordinate_system", "")),
            execution_authority=bool(record.get("execution_authority", False)),
            failures=tuple(RecoveryStrategyFailure.from_record(item) for item in failures),
        )
