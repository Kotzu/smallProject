from __future__ import annotations

from dataclasses import dataclass
import json
from math import hypot, isfinite
from pathlib import Path
from typing import Any, Mapping

from perfect_assassin.contract_validation import ContractValidator


SCHEMA_VERSION = "1.0"
ENTRY_KINDS = frozenset(
    {
        "class_trainer",
        "profession_trainer",
        "class_quest",
        "profession_quest",
        "leveling_step",
        "route_step",
        "npc_static",
    }
)
MAP_SCOPES = frozenset({"worldpack", "zone_area"})
PROVIDERS = frozenset(
    {"wowhead", "route_teacher", "client_observed", "predator_memory"}
)
ORIGINS = frozenset(
    {"external_cached", "route_guidance", "client_observed", "predator_memory"}
)
FORBIDDEN_ORIGINS = frozenset(
    {"server_ground_truth", "server_spawn_state", "lab_oracle", "packet_state"}
)
POSITION_SEMANTICS = "STATIC_SOURCE_CANDIDATE"


class KnowledgeBrokerError(ValueError):
    """Raised when a knowledge fact is not portable, bounded or well-sourced."""


def _bounded_identifier(label: str, value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise KnowledgeBrokerError(f"{label} is not a bounded identifier")
    if not (value[0].isalnum() and all(c.isalnum() or c in "._:/-" for c in value)):
        raise KnowledgeBrokerError(f"{label} is not a bounded identifier")
    return value


def _confidence(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KnowledgeBrokerError("confidence must be numeric")
    value = float(value)
    if not isfinite(value) or not 0.0 < value <= 1.0:
        raise KnowledgeBrokerError("confidence must be in (0, 1]")
    return value


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    provider: str
    origin: str
    uri: str
    provider_version: str
    retrieved_at: str
    content_mode: str

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise KnowledgeBrokerError("knowledge provider is not allowed")
        if self.origin in FORBIDDEN_ORIGINS or self.origin not in ORIGINS:
            raise KnowledgeBrokerError("knowledge origin is not allowed")
        if not self.uri.strip() or len(self.uri) > 512:
            raise KnowledgeBrokerError("knowledge source URI is invalid")
        if not self.provider_version.strip() or len(self.provider_version) > 64:
            raise KnowledgeBrokerError("knowledge provider version is invalid")
        if self.content_mode not in {
            "metadata_only", "advisory_summary", "user_owned_export"
        }:
            raise KnowledgeBrokerError("knowledge source content mode is invalid")
        expected_origin = {
            "wowhead": "external_cached",
            "route_teacher": "route_guidance",
            "client_observed": "client_observed",
            "predator_memory": "predator_memory",
        }[self.provider]
        if self.origin != expected_origin:
            raise KnowledgeBrokerError("knowledge provider and origin do not agree")

    def to_record(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "origin": self.origin,
            "uri": self.uri,
            "provider_version": self.provider_version,
            "retrieved_at": self.retrieved_at,
            "content_mode": self.content_mode,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "KnowledgeSource":
        return cls(
            provider=str(record["provider"]),
            origin=str(record["origin"]),
            uri=str(record["uri"]),
            provider_version=str(record["provider_version"]),
            retrieved_at=str(record["retrieved_at"]),
            content_mode=str(record["content_mode"]),
        )


@dataclass(frozen=True, slots=True)
class KnowledgePosition:
    x: float
    y: float
    coordinate_frame: str
    z: float | None = None
    position_semantics: str = POSITION_SEMANTICS

    def __post_init__(self) -> None:
        values = (self.x, self.y) if self.z is None else (self.x, self.y, self.z)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) for value in values):
            raise KnowledgeBrokerError("knowledge position coordinates are invalid")
        if self.coordinate_frame not in {
            "client_world_3d", "source_world_3d", "normalized_map_2d"
        }:
            raise KnowledgeBrokerError("knowledge position coordinate frame is invalid")
        if self.position_semantics != POSITION_SEMANTICS:
            raise KnowledgeBrokerError("knowledge position cannot claim live exact semantics")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "x": float(self.x),
            "y": float(self.y),
            "coordinate_frame": self.coordinate_frame,
            "position_semantics": POSITION_SEMANTICS,
        }
        if self.z is not None:
            record["z"] = float(self.z)
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "KnowledgePosition":
        return cls(
            x=float(record["x"]), y=float(record["y"]),
            z=None if "z" not in record else float(record["z"]),
            coordinate_frame=str(record["coordinate_frame"]),
            position_semantics=str(record["position_semantics"]),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    entry_id: str
    kind: str
    name: str
    map_id: int
    map_name: str
    level_min: int
    level_max: int
    source: KnowledgeSource
    confidence: float
    evidence_refs: tuple[str, ...]
    position: KnowledgePosition | None = None
    summary: str | None = None
    tags: tuple[str, ...] = ()
    step_order: int | None = None
    execution_authority: bool = False
    map_scope: str = "worldpack"

    def __post_init__(self) -> None:
        _bounded_identifier("entry_id", self.entry_id)
        if self.kind not in ENTRY_KINDS:
            raise KnowledgeBrokerError("knowledge entry kind is invalid")
        if not self.name.strip() or len(self.name) > 160:
            raise KnowledgeBrokerError("knowledge entry name is invalid")
        if type(self.map_id) is not int or not 0 <= self.map_id <= 2147483647:
            raise KnowledgeBrokerError("knowledge map id is invalid")
        if not self.map_name.strip() or len(self.map_name) > 96:
            raise KnowledgeBrokerError("knowledge map name is invalid")
        if self.map_scope not in MAP_SCOPES:
            raise KnowledgeBrokerError("knowledge map scope is invalid")
        if type(self.level_min) is not int or type(self.level_max) is not int or not 1 <= self.level_min <= self.level_max <= 70:
            raise KnowledgeBrokerError("knowledge level range is invalid")
        _confidence(self.confidence)
        if not 1 <= len(self.evidence_refs) <= 16 or len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise KnowledgeBrokerError("knowledge entry requires unique evidence refs")
        if any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in self.evidence_refs):
            raise KnowledgeBrokerError("knowledge evidence ref is invalid")
        if self.summary is not None and (not self.summary.strip() or len(self.summary) > 512):
            raise KnowledgeBrokerError("knowledge summary is invalid")
        if len(self.tags) > 16 or len(set(self.tags)) != len(self.tags):
            raise KnowledgeBrokerError("knowledge tags are invalid")
        if self.step_order is not None and (type(self.step_order) is not int or not 0 <= self.step_order <= 100000):
            raise KnowledgeBrokerError("knowledge step order is invalid")
        if self.execution_authority:
            raise KnowledgeBrokerError("knowledge entries never have execution authority")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "entry_id": self.entry_id,
            "kind": self.kind,
            "name": self.name,
            "map_id": self.map_id,
            "map_name": self.map_name,
            "map_scope": self.map_scope,
            "level_range": {"min": self.level_min, "max": self.level_max},
            "source": self.source.to_record(),
            "confidence": float(self.confidence),
            "evidence_refs": list(self.evidence_refs),
            "position": None if self.position is None else self.position.to_record(),
            "execution_authority": False,
        }
        if self.summary is not None:
            record["summary"] = self.summary
        if self.tags:
            record["tags"] = list(self.tags)
        if self.step_order is not None:
            record["step_order"] = self.step_order
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "KnowledgeEntry":
        level_range = record["level_range"]
        position = record.get("position")
        return cls(
            entry_id=str(record["entry_id"]), kind=str(record["kind"]),
            name=str(record["name"]), map_id=int(record["map_id"]),
            map_name=str(record["map_name"]), level_min=int(level_range["min"]),
            level_max=int(level_range["max"]),
            source=KnowledgeSource.from_record(record["source"]),
            confidence=float(record["confidence"]),
            evidence_refs=tuple(str(ref) for ref in record["evidence_refs"]),
            position=None if position is None else KnowledgePosition.from_record(position),
            summary=None if "summary" not in record else str(record["summary"]),
            tags=tuple(str(tag) for tag in record.get("tags", ())),
            step_order=None if "step_order" not in record else int(record["step_order"]),
            execution_authority=bool(record.get("execution_authority", False)),
            map_scope=str(record.get("map_scope", "worldpack")),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeBrokerCatalog:
    catalog_id: str
    target_profile: str
    product: str
    expansion: str
    client_version: str
    client_build: str
    entries: tuple[KnowledgeEntry, ...]
    execution_authority: bool = False

    def __post_init__(self) -> None:
        _bounded_identifier("catalog_id", self.catalog_id)
        _bounded_identifier("target_profile", self.target_profile)
        if self.product != "wow" or self.expansion != "the_burning_crusade":
            raise KnowledgeBrokerError("catalog target is not TBC WoW")
        if not self.client_version.strip() or not self.client_build.strip():
            raise KnowledgeBrokerError("catalog client identity is missing")
        if not self.entries or len({entry.entry_id for entry in self.entries}) != len(self.entries):
            raise KnowledgeBrokerError("knowledge entry ids must be unique")
        if self.execution_authority:
            raise KnowledgeBrokerError("knowledge broker is read-only")

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": "knowledge_broker_catalog",
            "schema_version": SCHEMA_VERSION,
            "catalog_id": self.catalog_id,
            "target_profile": self.target_profile,
            "product": self.product,
            "expansion": self.expansion,
            "client_version": self.client_version,
            "client_build": self.client_build,
            "entries": [entry.to_record() for entry in self.entries],
            "execution_authority": False,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "KnowledgeBrokerCatalog":
        if record.get("schema_version") != SCHEMA_VERSION or record.get("record_type") != "knowledge_broker_catalog":
            raise KnowledgeBrokerError("unsupported knowledge broker catalog")
        return cls(
            catalog_id=str(record["catalog_id"]), target_profile=str(record["target_profile"]),
            product=str(record["product"]), expansion=str(record["expansion"]),
            client_version=str(record["client_version"]), client_build=str(record["client_build"]),
            entries=tuple(KnowledgeEntry.from_record(entry) for entry in record["entries"]),
            execution_authority=bool(record.get("execution_authority", False)),
        )

    def by_kind(
        self, kind: str, *, map_id: int | None = None,
        map_scope: str | None = None,
    ) -> tuple[KnowledgeEntry, ...]:
        if kind not in ENTRY_KINDS:
            raise KnowledgeBrokerError("knowledge entry kind is invalid")
        if map_scope is not None and map_scope not in MAP_SCOPES:
            raise KnowledgeBrokerError("knowledge map scope is invalid")
        return tuple(
            entry for entry in self.entries
            if entry.kind == kind
            and (map_id is None or entry.map_id == map_id)
            and (map_scope is None or entry.map_scope == map_scope)
        )

    def by_map(
        self, *, map_id: int, map_name: str,
        map_scope: str = "worldpack",
    ) -> tuple[KnowledgeEntry, ...]:
        """Return facts bound to one exact map identity and coordinate scope."""

        if map_scope not in MAP_SCOPES:
            raise KnowledgeBrokerError("knowledge map scope is invalid")

        return tuple(
            entry for entry in self.entries
            if entry.map_id == map_id
            and entry.map_name == map_name
            and entry.map_scope == map_scope
        )

    def nearby_static_candidates(
        self,
        *,
        map_id: int,
        map_name: str,
        normalized_x: float,
        normalized_y: float,
        radius: float = 0.08,
        map_scope: str = "zone_area",
        kinds: frozenset[str] | None = None,
    ) -> tuple[KnowledgeEntry, ...]:
        """Return advisory source candidates near one exact map-area position.

        The query is intentionally two-dimensional and source-relative.  It
        never claims a live NPC position, performs no map guessing, and does
        not create a movement destination or execution authority.  A caller
        that has a separately validated client transform may project the
        returned candidates for display or later client confirmation.
        """

        if type(map_id) is not int or map_id < 0:
            raise KnowledgeBrokerError("nearby query map id is invalid")
        if not isinstance(map_name, str) or not map_name.strip():
            raise KnowledgeBrokerError("nearby query map name is invalid")
        coordinates = (normalized_x, normalized_y, radius)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            for value in coordinates
        ):
            raise KnowledgeBrokerError("nearby query coordinates are invalid")
        if not all(0.0 <= float(value) <= 1.0 for value in coordinates[:2]):
            raise KnowledgeBrokerError("nearby query coordinates are out of range")
        if not 0.0 < float(radius) <= 1.0:
            raise KnowledgeBrokerError("nearby query radius is invalid")
        if map_scope not in MAP_SCOPES:
            raise KnowledgeBrokerError("knowledge map scope is invalid")
        if kinds is not None and (
            not isinstance(kinds, frozenset)
            or not kinds
            or not kinds.issubset(ENTRY_KINDS)
        ):
            raise KnowledgeBrokerError("nearby query kinds are invalid")
        candidates: list[tuple[float, KnowledgeEntry]] = []
        for entry in self.by_map(
            map_id=map_id, map_name=map_name, map_scope=map_scope,
        ):
            if kinds is not None and entry.kind not in kinds:
                continue
            position = entry.position
            if position is None or position.coordinate_frame != "normalized_map_2d":
                continue
            distance = hypot(
                float(position.x) - float(normalized_x),
                float(position.y) - float(normalized_y),
            )
            if distance <= float(radius):
                candidates.append((distance, entry))
        candidates.sort(
            key=lambda item: (
                item[0], -float(item[1].confidence), item[1].entry_id,
            )
        )
        return tuple(entry for _distance, entry in candidates)

    def entry(self, entry_id: str) -> KnowledgeEntry:
        matches = tuple(item for item in self.entries if item.entry_id == entry_id)
        if len(matches) != 1:
            raise KnowledgeBrokerError(f"knowledge entry is not unique: {entry_id}")
        return matches[0]


def load_knowledge_broker_catalog(
    path: Path, *, schema_path: Path | None = None
) -> KnowledgeBrokerCatalog:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[3] / "contracts" / "knowledge-broker-catalog.schema.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise KnowledgeBrokerError(f"cannot read knowledge broker catalog: {error}") from error
    ContractValidator(schema_path).validate(record)
    return KnowledgeBrokerCatalog.from_record(record)
