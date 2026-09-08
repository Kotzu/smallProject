from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor, hypot, isfinite
from typing import Literal


EntityKind = Literal[
    "HOSTILE_NPC", "HOSTILE_PLAYER", "FRIENDLY_NPC", "PLAYER", "RESOURCE", "OBJECT"
]
StaticFeatureKind = Literal[
    "INTERIOR", "EXIT", "ROAD", "LANDMARK", "NPC_SPAWN", "HOSTILE_SPAWN", "PATROL_ROUTE"
]
TrackSemantics = Literal[
    "live_visible_bearing", "last_seen_area", "observer_position_at_detection", "spawn_prior"
]


@dataclass(frozen=True, slots=True)
class EntityTrack:
    track_id: str
    kind: EntityKind
    name: str
    semantics: TrackSemantics
    observed_at_s: float
    expires_at_s: float
    confidence: float
    x: float | None = None
    y: float | None = None

    def __post_init__(self) -> None:
        if not self.track_id or not self.name or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("entity track identity or confidence is invalid")
        if not (isfinite(self.observed_at_s) and isfinite(self.expires_at_s)):
            raise ValueError("entity track time is invalid")
        if self.expires_at_s <= self.observed_at_s:
            raise ValueError("entity track expiry is invalid")
        if (self.x is None) != (self.y is None):
            raise ValueError("entity track position must be complete")
        if self.x is not None and (not isfinite(self.x) or not isfinite(self.y)):
            raise ValueError("entity track position is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalRiskObservation:
    """Permanent hostile observation, never a claim it remains at this point."""

    observation_id: str
    track_id: str
    kind: Literal["HOSTILE_NPC", "HOSTILE_PLAYER"]
    name: str
    semantics: TrackSemantics
    x: float
    y: float
    observed_at_s: float
    confidence: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.track_id or not self.name:
            raise ValueError("historical risk observation identity is invalid")
        if any(not isfinite(value) for value in (self.x, self.y, self.observed_at_s)):
            raise ValueError("historical risk observation position or time is invalid")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("historical risk observation confidence is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalRiskArea:
    """Permanent regional prior distilled from hostile observations."""

    area_id: str
    kind: Literal["HOSTILE_NPC", "HOSTILE_PLAYER"]
    x: float
    y: float
    radius_yards: float
    risk_score: float
    observation_count: int
    first_observed_s: float
    last_observed_s: float

    def __post_init__(self) -> None:
        if not self.area_id:
            raise ValueError("historical risk area identity is invalid")
        if any(not isfinite(value) for value in (
            self.x, self.y, self.radius_yards, self.risk_score,
            self.first_observed_s, self.last_observed_s,
        )):
            raise ValueError("historical risk area is non-finite")
        if not 1.0 <= self.radius_yards <= 1_000.0:
            raise ValueError("historical risk area radius is invalid")
        if not 0.0 < self.risk_score <= 5.0:
            raise ValueError("historical risk area score is invalid")
        if self.observation_count < 1 or self.last_observed_s < self.first_observed_s:
            raise ValueError("historical risk area chronology is invalid")


@dataclass(frozen=True, slots=True)
class ExperienceCell:
    x: int
    y: int
    visits: int
    last_seen_s: float
    stuck_heat: float


@dataclass(frozen=True, slots=True)
class StaticWorldFeature:
    feature_id: str
    kind: StaticFeatureKind
    name: str
    x: float
    y: float
    z: float | None
    radius_yards: float
    confidence: float
    learned_at_s: float
    provenance: str

    def __post_init__(self) -> None:
        if not self.feature_id or not self.name or not self.provenance:
            raise ValueError("static feature identity or provenance is invalid")
        coordinates = (self.x, self.y, self.learned_at_s)
        if any(not isfinite(value) for value in coordinates):
            raise ValueError("static feature coordinates or time are invalid")
        if self.z is not None and not isfinite(self.z):
            raise ValueError("static feature height is invalid")
        if not 0 <= self.radius_yards <= 1_000 or not 0 <= self.confidence <= 1:
            raise ValueError("static feature radius or confidence is invalid")


@dataclass(frozen=True, slots=True)
class LocalAwarenessSnapshot:
    map_name: str
    x: float
    y: float
    static_radius_yards: float
    dynamic_visibility_radius_yards: float
    observed_at_s: float
    static_features: tuple[StaticWorldFeature, ...]
    visible_dynamic_tracks: tuple[EntityTrack, ...]
    remembered_dynamic_tracks: tuple[EntityTrack, ...]
    historical_risk_areas: tuple[HistoricalRiskArea, ...] = ()
    static_semantics: str = "KNOWN_THROUGH_STATIC_WORLD_MODEL"
    dynamic_semantics: str = "SERVER_VISIBILITY_SET_OR_LAST_SEEN_WITH_EXPIRY"
    historical_semantics: str = "PERMANENT_OBSERVED_EXPERIENCE_NOT_LIVE_POSITION"


class LayeredWorldModel:
    """Separate static truth, live observations and permanent experience."""

    def __init__(self, *, map_name: str, static_navmesh_sha256: str, cell_size: float = 8.0):
        if not map_name or len(static_navmesh_sha256) != 64:
            raise ValueError("world model map binding is invalid")
        if not 1.0 <= cell_size <= 100.0:
            raise ValueError("world model cell size is invalid")
        self.map_name = map_name
        self.static_navmesh_sha256 = static_navmesh_sha256.upper()
        self.cell_size = float(cell_size)
        self._tracks: dict[str, EntityTrack] = {}
        self._cells: dict[tuple[int, int], ExperienceCell] = {}
        self._static_features: dict[str, StaticWorldFeature] = {}
        self._historical_observations: dict[str, HistoricalRiskObservation] = {}
        self._historical_risks: dict[str, HistoricalRiskArea] = {}

    @property
    def static_knowledge(self) -> str:
        return "CLIENT_ASSET_GEOMETRY_KNOWN"

    @property
    def dynamic_knowledge(self) -> str:
        return "OBSERVED_ONLY_FOG_OF_WAR"

    @property
    def historical_knowledge(self) -> str:
        return "PERMANENT_OBSERVED_EXPERIENCE_NOT_LIVE_POSITION"

    def observe_position(self, *, x: float, y: float, observed_at_s: float) -> ExperienceCell:
        if any(not isfinite(value) for value in (x, y, observed_at_s)):
            raise ValueError("position observation is invalid")
        key = (floor(x / self.cell_size), floor(y / self.cell_size))
        previous = self._cells.get(key)
        cell = ExperienceCell(
            x=key[0], y=key[1], visits=1 if previous is None else previous.visits + 1,
            last_seen_s=observed_at_s,
            stuck_heat=0.0 if previous is None else previous.stuck_heat,
        )
        self._cells[key] = cell
        return cell

    def mark_stuck(self, *, x: float, y: float, observed_at_s: float) -> ExperienceCell:
        cell = self.observe_position(x=x, y=y, observed_at_s=observed_at_s)
        heated = replace(cell, stuck_heat=min(1.0, cell.stuck_heat + 0.25))
        self._cells[(cell.x, cell.y)] = heated
        return heated

    def upsert_track(self, track: EntityTrack) -> None:
        previous = self._tracks.get(track.track_id)
        if previous is not None and track.observed_at_s < previous.observed_at_s:
            raise ValueError("entity observations cannot travel backward in time")
        self._tracks[track.track_id] = track
        self._remember_hostile_observation(track)

    def _remember_hostile_observation(self, track: EntityTrack) -> None:
        if track.kind not in {"HOSTILE_NPC", "HOSTILE_PLAYER"} or track.x is None:
            return
        observation_id = f"{track.track_id}@{track.observed_at_s:.9f}"
        if observation_id in self._historical_observations:
            return
        observation = HistoricalRiskObservation(
            observation_id=observation_id,
            track_id=track.track_id,
            kind=track.kind,
            name=track.name,
            semantics=track.semantics,
            x=track.x,
            y=track.y,
            observed_at_s=track.observed_at_s,
            confidence=track.confidence,
        )
        self._historical_observations[observation_id] = observation
        area_size = max(16.0, self.cell_size * 4.0)
        cell_x, cell_y = floor(track.x / area_size), floor(track.y / area_size)
        area_id = f"observed-risk:{track.kind}:{cell_x}:{cell_y}"
        previous_area = self._historical_risks.get(area_id)
        if previous_area is None:
            area = HistoricalRiskArea(
                area_id=area_id,
                kind=track.kind,
                x=track.x,
                y=track.y,
                radius_yards=area_size,
                risk_score=max(0.05, track.confidence),
                observation_count=1,
                first_observed_s=track.observed_at_s,
                last_observed_s=track.observed_at_s,
            )
        else:
            count = previous_area.observation_count + 1
            area = HistoricalRiskArea(
                area_id=area_id,
                kind=track.kind,
                x=(previous_area.x * previous_area.observation_count + track.x) / count,
                y=(previous_area.y * previous_area.observation_count + track.y) / count,
                radius_yards=previous_area.radius_yards,
                risk_score=min(5.0, previous_area.risk_score + track.confidence),
                observation_count=count,
                first_observed_s=previous_area.first_observed_s,
                last_observed_s=track.observed_at_s,
            )
        self._historical_risks[area_id] = area

    def upsert_static_feature(self, feature: StaticWorldFeature) -> None:
        previous = self._static_features.get(feature.feature_id)
        if previous is not None and feature.learned_at_s < previous.learned_at_s:
            raise ValueError("static knowledge cannot travel backward in time")
        self._static_features[feature.feature_id] = feature

    def local_awareness(
        self,
        *,
        x: float,
        y: float,
        static_radius_yards: float = 1_000.0,
        dynamic_visibility_radius_yards: float = 100.0,
        now_s: float,
    ) -> LocalAwarenessSnapshot:
        if any(not isfinite(value) for value in (
            x, y, static_radius_yards, dynamic_visibility_radius_yards, now_s
        )):
            raise ValueError("local awareness query is invalid")
        if not 1 <= static_radius_yards <= 1_000:
            raise ValueError("static awareness radius is outside its bound")
        if not 1 <= dynamic_visibility_radius_yards <= 500:
            raise ValueError("dynamic visibility radius is outside its bound")
        features = tuple(sorted(
            (
                feature for feature in self._static_features.values()
                if hypot(feature.x - x, feature.y - y)
                <= static_radius_yards + feature.radius_yards
            ),
            key=lambda item: (hypot(item.x - x, item.y - y), item.feature_id),
        ))
        active = self.active_tracks(now_s=now_s)
        visible = tuple(
            track for track in active
            if track.semantics == "live_visible_bearing"
            and (
                track.x is None
                or hypot(track.x - x, track.y - y) <= dynamic_visibility_radius_yards
            )
        )
        remembered = tuple(
            track for track in active if track not in visible
        )
        historical_risks = tuple(sorted(
            (
                area for area in self._historical_risks.values()
                if hypot(area.x - x, area.y - y) <= static_radius_yards + area.radius_yards
            ),
            key=lambda item: (hypot(item.x - x, item.y - y), item.area_id),
        ))
        return LocalAwarenessSnapshot(
            map_name=self.map_name,
            x=x,
            y=y,
            static_radius_yards=static_radius_yards,
            dynamic_visibility_radius_yards=dynamic_visibility_radius_yards,
            observed_at_s=now_s,
            static_features=features,
            visible_dynamic_tracks=visible,
            remembered_dynamic_tracks=remembered,
            historical_risk_areas=historical_risks,
        )

    def active_tracks(self, *, now_s: float) -> tuple[EntityTrack, ...]:
        if not isfinite(now_s):
            raise ValueError("world model time is invalid")
        expired = [key for key, value in self._tracks.items() if value.expires_at_s <= now_s]
        for key in expired:
            del self._tracks[key]
        return tuple(sorted(self._tracks.values(), key=lambda item: (-item.confidence, item.track_id)))

    def cells(self) -> tuple[ExperienceCell, ...]:
        return tuple(sorted(self._cells.values(), key=lambda item: (item.x, item.y)))

    def historical_observations(self) -> tuple[HistoricalRiskObservation, ...]:
        """Append-only hostile observations, retained after live tracks expire."""

        return tuple(sorted(
            self._historical_observations.values(),
            key=lambda item: (item.observed_at_s, item.observation_id),
        ))

    def historical_risk_areas(self) -> tuple[HistoricalRiskArea, ...]:
        """Permanent regional priors, never exact current hostile positions."""

        return tuple(sorted(self._historical_risks.values(), key=lambda item: item.area_id))
