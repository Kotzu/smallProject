from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import floor, isfinite, pi
from pathlib import Path
import sqlite3

from perfect_assassin.movement.dynamic_avoidance import DynamicEntityTrack
from perfect_assassin.movement.world_model import HistoricalRiskArea


DYNAMIC_EXPERIENCE_SCHEMA_VERSION = 2
REACTIONS = ("HOSTILE", "NEUTRAL", "FRIENDLY", "UNKNOWN")
EXPERIENCE_SEMANTICS = "APPEND_ONLY_OBSERVER_POSE_ENCOUNTER_MEMORY"
ENTITY_POSITION_SEMANTICS = "UNKNOWN_NOT_INFERRED"
OBSERVER_FACING_SEMANTICS = "VISIBLE_OR_DISPLACEMENT_ESTIMATE"


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789ABCDEF" for character in value)


def _validate_utc(value: str) -> None:
    if not value.endswith("Z"):
        raise ValueError("dynamic experience UTC time is not canonical")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("dynamic experience UTC time is invalid") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("dynamic experience UTC time is not UTC")


@dataclass(frozen=True, slots=True)
class DynamicEncounterObservation:
    """Permanent evidence of an encounter, never an entity world position."""

    event_id: str
    session_id: str
    map_name: str
    navmesh_sha256: str
    observed_at_utc: str
    observed_monotonic_s: float
    observer_world_x: float
    observer_world_y: float
    observer_world_z: float | None
    observer_facing_rad: float | None
    track_id: str
    reaction: str
    center_x_normalized: float
    center_y_normalized: float
    width_normalized: float
    height_normalized: float
    confidence: float
    position_uncertainty_normalized: float
    observation_count: int
    source_key: str | None

    def __post_init__(self) -> None:
        if not _valid_sha256(self.event_id):
            raise ValueError("dynamic experience event id is invalid")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("dynamic experience session id is invalid")
        if not self.map_name or len(self.map_name) > 160:
            raise ValueError("dynamic experience map name is invalid")
        if not _valid_sha256(self.navmesh_sha256):
            raise ValueError("dynamic experience navmesh binding is invalid")
        _validate_utc(self.observed_at_utc)
        coordinates = (
            self.observed_monotonic_s,
            self.observer_world_x,
            self.observer_world_y,
            self.center_x_normalized,
            self.center_y_normalized,
            self.width_normalized,
            self.height_normalized,
            self.confidence,
            self.position_uncertainty_normalized,
        )
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("dynamic experience observation is non-finite")
        if self.observed_monotonic_s < 0.0:
            raise ValueError("dynamic experience monotonic time is invalid")
        if self.observer_world_z is not None and not isfinite(self.observer_world_z):
            raise ValueError("dynamic experience observer height is invalid")
        if self.observer_facing_rad is not None and not (
            isfinite(self.observer_facing_rad)
            and -2.0 * pi <= self.observer_facing_rad <= 2.0 * pi
        ):
            raise ValueError("dynamic experience observer facing is invalid")
        if not self.track_id or len(self.track_id) > 128:
            raise ValueError("dynamic experience track id is invalid")
        if self.reaction not in REACTIONS:
            raise ValueError("dynamic experience reaction is invalid")
        if not -1.0 <= self.center_x_normalized <= 1.0:
            raise ValueError("dynamic experience screen X is invalid")
        if not 0.0 <= self.center_y_normalized <= 1.0:
            raise ValueError("dynamic experience screen Y is invalid")
        if not 0.0 < self.width_normalized <= 1.0:
            raise ValueError("dynamic experience screen width is invalid")
        if not 0.0 < self.height_normalized <= 1.0:
            raise ValueError("dynamic experience screen height is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("dynamic experience confidence is invalid")
        if not 0.0 <= self.position_uncertainty_normalized <= 1.0:
            raise ValueError("dynamic experience uncertainty is invalid")
        if type(self.observation_count) is not int or self.observation_count < 2:
            raise ValueError("dynamic experience requires a mature track")
        if self.source_key is not None and (
            not self.source_key or len(self.source_key) > 128
        ):
            raise ValueError("dynamic experience source key is invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "dynamic_encounter_observation",
            "schema_version": "1.0",
            "event_id": self.event_id,
            "session_id": self.session_id,
            "map_name": self.map_name,
            "navmesh_sha256": self.navmesh_sha256,
            "observed_at_utc": self.observed_at_utc,
            "observed_monotonic_s": self.observed_monotonic_s,
            "observer_world_position": [
                self.observer_world_x,
                self.observer_world_y,
                *([] if self.observer_world_z is None else [self.observer_world_z]),
            ],
            "observer_facing_rad": self.observer_facing_rad,
            "observer_facing_semantics": OBSERVER_FACING_SEMANTICS,
            "track_id": self.track_id,
            "reaction": self.reaction,
            "center_x_normalized": self.center_x_normalized,
            "center_y_normalized": self.center_y_normalized,
            "width_normalized": self.width_normalized,
            "height_normalized": self.height_normalized,
            "confidence": self.confidence,
            "position_uncertainty_normalized": (
                self.position_uncertainty_normalized
            ),
            "observation_count": self.observation_count,
            "source_key": self.source_key,
            "experience_semantics": EXPERIENCE_SEMANTICS,
            "entity_position_semantics": ENTITY_POSITION_SEMANTICS,
            "entity_world_position": None,
            "execution_authority": False,
        }


@dataclass(frozen=True, slots=True)
class EscapedRiskObservation:
    """Permanent evidence that combat required retreat from an observer pose."""

    event_id: str
    session_id: str
    map_name: str
    navmesh_sha256: str
    observed_at_utc: str
    observer_world_x: float
    observer_world_y: float
    observer_world_z: float | None
    encounter_id: str
    navigation_run_id: str
    radius_yards: float = 45.0
    risk_score: float = 5.0

    def __post_init__(self) -> None:
        if not _valid_sha256(self.event_id):
            raise ValueError("escaped risk event id is invalid")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("escaped risk session id is invalid")
        if not self.map_name or len(self.map_name) > 160:
            raise ValueError("escaped risk map name is invalid")
        if not _valid_sha256(self.navmesh_sha256):
            raise ValueError("escaped risk navmesh binding is invalid")
        _validate_utc(self.observed_at_utc)
        if not all(isfinite(value) for value in (
            self.observer_world_x, self.observer_world_y,
            self.radius_yards, self.risk_score,
        )):
            raise ValueError("escaped risk observation is non-finite")
        if self.observer_world_z is not None and not isfinite(self.observer_world_z):
            raise ValueError("escaped risk observer height is invalid")
        if not self.encounter_id or len(self.encounter_id) > 160:
            raise ValueError("escaped risk encounter id is invalid")
        if not self.navigation_run_id or len(self.navigation_run_id) > 160:
            raise ValueError("escaped risk navigation run id is invalid")
        if not 8.0 <= self.radius_yards <= 100.0:
            raise ValueError("escaped risk radius is invalid")
        if not 0.05 <= self.risk_score <= 5.0:
            raise ValueError("escaped risk score is invalid")

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "escaped_risky_aggro_observation",
            "schema_version": "1.0",
            "event_id": self.event_id,
            "session_id": self.session_id,
            "map_name": self.map_name,
            "navmesh_sha256": self.navmesh_sha256,
            "observed_at_utc": self.observed_at_utc,
            "observer_world_position": [
                self.observer_world_x,
                self.observer_world_y,
                *([] if self.observer_world_z is None else [self.observer_world_z]),
            ],
            "encounter_id": self.encounter_id,
            "navigation_run_id": self.navigation_run_id,
            "radius_yards": self.radius_yards,
            "risk_score": self.risk_score,
            "risk_semantics": "OBSERVER_POSE_WHERE_COMBAT_REQUIRED_SAFE_RETREAT",
            "entity_world_position": None,
            "execution_authority": False,
        }


def escaped_risk_observation(
    *,
    session_id: str,
    map_name: str,
    navmesh_sha256: str,
    observed_at_utc: str,
    observer_world_x: float,
    observer_world_y: float,
    observer_world_z: float | None,
    encounter_id: str,
    navigation_run_id: str,
) -> EscapedRiskObservation:
    identity = _canonical_json({
        "session_id": session_id,
        "encounter_id": encounter_id,
        "navigation_run_id": navigation_run_id,
        "navmesh_sha256": navmesh_sha256.upper(),
    })
    return EscapedRiskObservation(
        event_id=hashlib.sha256(identity.encode("utf-8")).hexdigest().upper(),
        session_id=session_id,
        map_name=map_name,
        navmesh_sha256=navmesh_sha256.upper(),
        observed_at_utc=observed_at_utc,
        observer_world_x=observer_world_x,
        observer_world_y=observer_world_y,
        observer_world_z=observer_world_z,
        encounter_id=encounter_id,
        navigation_run_id=navigation_run_id,
    )


def encounter_from_track(
    track: DynamicEntityTrack,
    *,
    session_id: str,
    map_name: str,
    navmesh_sha256: str,
    observed_at_utc: str,
    observer_world_x: float,
    observer_world_y: float,
    observer_world_z: float | None,
    observer_facing_rad: float | None,
) -> DynamicEncounterObservation:
    identity = _canonical_json({
        "session_id": session_id,
        "track_id": track.track_id,
        "first_observed_at_s": track.first_observed_at_s,
        "navmesh_sha256": navmesh_sha256.upper(),
    })
    event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest().upper()
    return DynamicEncounterObservation(
        event_id=event_id,
        session_id=session_id,
        map_name=map_name,
        navmesh_sha256=navmesh_sha256.upper(),
        observed_at_utc=observed_at_utc,
        observed_monotonic_s=track.last_observed_at_s,
        observer_world_x=observer_world_x,
        observer_world_y=observer_world_y,
        observer_world_z=observer_world_z,
        observer_facing_rad=observer_facing_rad,
        track_id=track.track_id,
        reaction=track.reaction,
        center_x_normalized=track.center_x_normalized,
        center_y_normalized=track.center_y_normalized,
        width_normalized=track.width_normalized,
        height_normalized=track.height_normalized,
        confidence=track.confidence,
        position_uncertainty_normalized=(
            track.position_uncertainty_normalized
        ),
        observation_count=track.observation_count,
        source_key=track.source_key,
    )


class DynamicExperienceStore:
    """SQLite WAL store for durable, append-only encounter evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, timeout=5.0)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in {0, 1, DYNAMIC_EXPERIENCE_SCHEMA_VERSION}:
            self._connection.close()
            raise ValueError("dynamic experience database version is unsupported")
        if version == 0:
            with self._connection:
                self._connection.execute(
                    """
                    CREATE TABLE dynamic_encounters (
                        event_id TEXT PRIMARY KEY,
                        map_name TEXT NOT NULL,
                        navmesh_sha256 TEXT NOT NULL,
                        observed_at_utc TEXT NOT NULL,
                        reaction TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                self._connection.execute(
                    "CREATE INDEX dynamic_encounters_world_time "
                    "ON dynamic_encounters(map_name, navmesh_sha256, observed_at_utc)"
                )
        if version in {0, 1}:
            with self._connection:
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS escaped_risk_observations (
                        event_id TEXT PRIMARY KEY,
                        map_name TEXT NOT NULL,
                        navmesh_sha256 TEXT NOT NULL,
                        observed_at_utc TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        record_json TEXT NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                self._connection.execute(
                    "CREATE INDEX IF NOT EXISTS escaped_risks_world_time "
                    "ON escaped_risk_observations"
                    "(map_name, navmesh_sha256, observed_at_utc)"
                )
                self._connection.execute(
                    f"PRAGMA user_version={DYNAMIC_EXPERIENCE_SCHEMA_VERSION}"
                )
        # Summary runs when a new encounter matures on the control loop. The
        # world/time index requires table lookups into large record_json rows
        # and a temporary GROUP BY tree. Keep the summary entirely in a small
        # covering index, including databases already at schema version 2.
        with self._connection:
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS dynamic_encounters_world_reaction_time "
                "ON dynamic_encounters"
                "(map_name, navmesh_sha256, reaction, observed_at_utc)"
            )
        quick_check = str(
            self._connection.execute("PRAGMA quick_check").fetchone()[0]
        )
        if quick_check != "ok":
            self._connection.close()
            raise ValueError("dynamic experience database integrity check failed")

    def append(self, observation: DynamicEncounterObservation) -> bool:
        record = observation.to_record()
        serialized = _canonical_json(record)
        content_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest().upper()
        with self._connection:
            existing = self._connection.execute(
                "SELECT content_sha256 FROM dynamic_encounters WHERE event_id = ?",
                (observation.event_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != content_sha256:
                    raise ValueError("dynamic experience event id collision")
                return False
            self._connection.execute(
                """
                INSERT INTO dynamic_encounters (
                    event_id, map_name, navmesh_sha256, observed_at_utc,
                    reaction, content_sha256, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.event_id,
                    observation.map_name,
                    observation.navmesh_sha256,
                    observation.observed_at_utc,
                    observation.reaction,
                    content_sha256,
                    serialized,
                ),
            )
        return True

    def append_escaped_risk(self, observation: EscapedRiskObservation) -> bool:
        record = observation.to_record()
        serialized = _canonical_json(record)
        content_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest().upper()
        with self._connection:
            existing = self._connection.execute(
                "SELECT content_sha256 FROM escaped_risk_observations "
                "WHERE event_id = ?",
                (observation.event_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != content_sha256:
                    raise ValueError("escaped risk event id collision")
                return False
            self._connection.execute(
                """
                INSERT INTO escaped_risk_observations (
                    event_id, map_name, navmesh_sha256, observed_at_utc,
                    content_sha256, record_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.event_id,
                    observation.map_name,
                    observation.navmesh_sha256,
                    observation.observed_at_utc,
                    content_sha256,
                    serialized,
                ),
            )
        return True

    def summary_record(
        self,
        *,
        map_name: str,
        navmesh_sha256: str,
    ) -> dict[str, object]:
        binding = navmesh_sha256.upper()
        if not map_name or not _valid_sha256(binding):
            raise ValueError("dynamic experience summary binding is invalid")
        rows = self._connection.execute(
            """
            SELECT reaction, COUNT(*), MAX(observed_at_utc)
            FROM dynamic_encounters
            WHERE map_name = ? AND navmesh_sha256 = ?
            GROUP BY reaction
            """,
            (map_name, binding),
        ).fetchall()
        counts = {reaction: 0 for reaction in REACTIONS}
        latest: str | None = None
        for reaction, count, observed_at_utc in rows:
            counts[str(reaction)] = int(count)
            candidate = str(observed_at_utc)
            if latest is None or candidate > latest:
                latest = candidate
        return {
            "record_type": "dynamic_experience_summary",
            "schema_version": "2.0",
            "database_schema_version": DYNAMIC_EXPERIENCE_SCHEMA_VERSION,
            "map_name": map_name,
            "navmesh_sha256": binding,
            "observation_count": sum(counts.values()),
            "reaction_counts": counts,
            "last_observed_at_utc": latest,
            "experience_semantics": EXPERIENCE_SEMANTICS,
            "entity_position_semantics": ENTITY_POSITION_SEMANTICS,
            "execution_authority": False,
        }

    def historical_risk_areas(
        self,
        *,
        map_name: str,
        navmesh_sha256: str,
        area_size_yards: float = 32.0,
    ) -> tuple[HistoricalRiskArea, ...]:
        """Distill hostile encounter regions from observer poses.

        The stored entity has no inferred world coordinate.  A risk area says
        only that the observer saw a hostile while standing in this region.
        """

        binding = navmesh_sha256.upper()
        if not map_name or not _valid_sha256(binding):
            raise ValueError("dynamic experience risk binding is invalid")
        if not isfinite(area_size_yards) or not 8.0 <= area_size_yards <= 100.0:
            raise ValueError("dynamic experience risk area size is invalid")
        rows = self._connection.execute(
            """
            SELECT record_json
            FROM dynamic_encounters
            WHERE map_name = ? AND navmesh_sha256 = ? AND reaction = 'HOSTILE'
            ORDER BY observed_at_utc, event_id
            """,
            (map_name, binding),
        ).fetchall()
        grouped: dict[tuple[int, int], list[dict[str, object]]] = {}
        for (raw_record,) in rows:
            record = json.loads(str(raw_record))
            position = record.get("observer_world_position")
            if (
                not isinstance(position, list)
                or len(position) not in {2, 3}
                or not all(isinstance(value, (int, float)) for value in position)
            ):
                raise ValueError("stored hostile encounter observer pose is invalid")
            x, y = float(position[0]), float(position[1])
            if not isfinite(x) or not isfinite(y):
                raise ValueError("stored hostile encounter observer pose is non-finite")
            key = (floor(x / area_size_yards), floor(y / area_size_yards))
            grouped.setdefault(key, []).append(record)
        areas: list[HistoricalRiskArea] = []
        for (cell_x, cell_y), records in sorted(grouped.items()):
            positions = [record["observer_world_position"] for record in records]
            timestamps = [
                datetime.fromisoformat(
                    str(record["observed_at_utc"])[:-1] + "+00:00"
                ).timestamp()
                for record in records
            ]
            confidence_sum = sum(float(record["confidence"]) for record in records)
            areas.append(HistoricalRiskArea(
                area_id=f"observer-hostile-risk:{map_name}:{cell_x}:{cell_y}",
                kind="HOSTILE_NPC",
                x=sum(float(position[0]) for position in positions) / len(positions),
                y=sum(float(position[1]) for position in positions) / len(positions),
                radius_yards=area_size_yards,
                risk_score=min(5.0, max(0.05, confidence_sum)),
                observation_count=len(records),
                first_observed_s=min(timestamps),
                last_observed_s=max(timestamps),
            ))
        escaped_rows = self._connection.execute(
            """
            SELECT record_json
            FROM escaped_risk_observations
            WHERE map_name = ? AND navmesh_sha256 = ?
            ORDER BY observed_at_utc, event_id
            """,
            (map_name, binding),
        ).fetchall()
        escaped_grouped: dict[tuple[int, int], list[dict[str, object]]] = {}
        for (raw_record,) in escaped_rows:
            record = json.loads(str(raw_record))
            position = record.get("observer_world_position")
            if (
                not isinstance(position, list)
                or len(position) not in {2, 3}
                or not all(isinstance(value, (int, float)) for value in position)
            ):
                raise ValueError("stored escaped risk observer pose is invalid")
            x, y = float(position[0]), float(position[1])
            if not isfinite(x) or not isfinite(y):
                raise ValueError("stored escaped risk observer pose is non-finite")
            key = (floor(x / area_size_yards), floor(y / area_size_yards))
            escaped_grouped.setdefault(key, []).append(record)
        for (cell_x, cell_y), records in sorted(escaped_grouped.items()):
            positions = [record["observer_world_position"] for record in records]
            timestamps = [
                datetime.fromisoformat(
                    str(record["observed_at_utc"])[:-1] + "+00:00"
                ).timestamp()
                for record in records
            ]
            areas.append(HistoricalRiskArea(
                area_id=f"escaped-risk:{map_name}:{cell_x}:{cell_y}",
                kind="HOSTILE_NPC",
                x=sum(float(position[0]) for position in positions) / len(positions),
                y=sum(float(position[1]) for position in positions) / len(positions),
                radius_yards=max(float(record["radius_yards"]) for record in records),
                risk_score=min(
                    5.0,
                    sum(float(record["risk_score"]) for record in records),
                ),
                observation_count=len(records),
                first_observed_s=min(timestamps),
                last_observed_s=max(timestamps),
            ))
        return tuple(areas)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> DynamicExperienceStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
