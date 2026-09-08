from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from perfect_assassin.knowledge.broker import (
    KnowledgeBrokerCatalog,
    KnowledgeBrokerError,
    KnowledgeEntry,
    KnowledgePosition,
    KnowledgeSource,
)


class NpcDataImportError(ValueError):
    """Raised when a static Zygor NPC export cannot be bound safely."""


def discover_zygor_npc_map_areas(text: str) -> tuple[tuple[int, int], ...]:
    """Return only ``m####`` IDs and row counts from an NPCData export.

    This deliberately does not require a map binding and does not retain names,
    coordinates, NPC IDs, or section labels.  It is intended for the first
    intake pass, where the operator needs to see which explicit compatibility
    bindings are still missing.  Numeric rows that the bounded importer cannot
    understand remain a hard error so discovery cannot silently undercount.
    """

    if not isinstance(text, str) or not text.strip():
        raise NpcDataImportError("NPCData export is empty")
    sections = tuple(_SECTION.finditer(text))
    if not sections:
        raise NpcDataImportError("NPCData export contains no static sections")

    counts: dict[int, int] = {}
    for section_match in sections:
        for line_number, raw_line in enumerate(
            section_match.group("body").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line or line.startswith("--"):
                continue
            row = _ROW.match(raw_line)
            if row is None:
                if _NUMERIC_ROW.match(raw_line):
                    section = section_match.group("section")
                    raise NpcDataImportError(
                        f"unsupported NPCData row in {section!r} at local line {line_number}"
                    )
                continue
            map_id = int(row.group("map_id"))
            counts[map_id] = counts.get(map_id, 0) + 1

    if not counts:
        raise NpcDataImportError("NPCData export contains no supported visible rows")
    return tuple(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class NpcDataImportConfig:
    catalog_id: str
    target_profile: str
    client_version: str
    client_build: str
    provider_version: str
    retrieved_at: str
    source_uri: str
    # NPCData uses UI/WorldMapArea ``m####`` IDs, not WorldPack continent IDs.
    # Every encountered ID must be explicitly named by the caller.
    zone_area_bindings: Mapping[int, str]


_SECTION = re.compile(
    r'\["(?P<section>[^"]+)"\]\s*=\s*\[\[(?P<body>.*?)\]\]',
    re.IGNORECASE | re.DOTALL,
)
_ROW = re.compile(
    r"^\s*(?P<npc_id>\d+)=s(?P<faction>[AHB])\|m(?P<map_id>\d+)"
    r"\|x(?P<x>-?\d+(?:\.\d+)?)\|y(?P<y>-?\d+(?:\.\d+)?)(?P<tail>.*)$",
    re.IGNORECASE,
)
_NUMERIC_ROW = re.compile(r"^\s*\d+=")
_PROFESSION_SECTION = re.compile(r"^Trainer", re.IGNORECASE)
_CLASS_SECTION = re.compile(r"^Class", re.IGNORECASE)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-")
    return slug[:96] or "npc"


def _kind(section: str) -> str:
    if _PROFESSION_SECTION.match(section):
        return "profession_trainer"
    if _CLASS_SECTION.match(section):
        return "class_trainer"
    return "npc_static"


def _tags(section: str, faction: str) -> tuple[str, ...]:
    faction_name = {
        "a": "alliance",
        "h": "horde",
        "b": "neutral",
    }[faction.lower()]
    return (
        "npcdata",
        f"section:{_slug(section).replace('-', '_')}",
        f"faction:{faction_name}",
    )


def _tail_metadata(tail: str) -> tuple[str, str | None]:
    """Return a bounded display name and optional source note from one row."""

    note_match = re.search(r"\|w([^,]*)", tail, re.IGNORECASE)
    note = None if note_match is None else re.sub(r"\s+", " ", note_match.group(1)).strip()
    if note == "":
        note = None
    comma = tail.rfind(",")
    name = tail[comma + 1 :].strip() if comma >= 0 else ""
    name = re.sub(r"\s+", " ", name)
    return name[:160] or "static NPC", note[:512] if note else None


def import_zygor_npc_data(
    text: str, *, config: NpcDataImportConfig
) -> KnowledgeBrokerCatalog:
    """Import Zygor's NPCData table without evaluating Lua.

    The source's ``m####`` identifiers remain in the catalog as ``map_scope``
    ``zone_area``. They are intentionally not converted to WorldPack map IDs;
    a later compatibility adapter must provide that explicit reconciliation.
    """

    if not isinstance(text, str) or not text.strip():
        raise NpcDataImportError("NPCData export is empty")
    sections = tuple(_SECTION.finditer(text))
    if not sections:
        raise NpcDataImportError("NPCData export contains no static sections")

    source = KnowledgeSource(
        provider="route_teacher",
        origin="route_guidance",
        uri=config.source_uri,
        provider_version=config.provider_version,
        retrieved_at=config.retrieved_at,
        content_mode="user_owned_export",
    )
    entries: list[KnowledgeEntry] = []
    for section_match in sections:
        section = section_match.group("section").strip()
        if not section:
            raise NpcDataImportError("NPCData section has no name")
        body = section_match.group("body")
        for line_number, raw_line in enumerate(body.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("--"):
                continue
            row = _ROW.match(raw_line)
            if row is None:
                if _NUMERIC_ROW.match(raw_line):
                    raise NpcDataImportError(
                        f"unsupported NPCData row in {section!r} at local line {line_number}"
                    )
                continue

            map_id = int(row.group("map_id"))
            map_name = config.zone_area_bindings.get(map_id)
            if map_name is None or not str(map_name).strip():
                raise NpcDataImportError(
                    f"NPCData map area has no explicit binding: m{map_id}"
                )
            x = float(row.group("x"))
            y = float(row.group("y"))
            if not 0.0 <= x <= 100.0 or not 0.0 <= y <= 100.0:
                raise NpcDataImportError(
                    f"NPCData coordinate is outside 0..100 in {section!r}"
                )
            npc_id = row.group("npc_id")
            name, note = _tail_metadata(row.group("tail"))
            evidence = f"{config.source_uri}#NPCData/{_slug(section)}/{npc_id}"
            if len(evidence) > 256:
                raise NpcDataImportError("NPCData evidence reference is too long")
            entries.append(
                KnowledgeEntry(
                    entry_id=f"npc.{_slug(section)}.{npc_id}",
                    kind=_kind(section),
                    name=name,
                    map_id=map_id,
                    map_name=str(map_name).strip(),
                    level_min=1,
                    level_max=70,
                    source=source,
                    confidence=0.70,
                    evidence_refs=(evidence,),
                    position=KnowledgePosition(
                        x=x / 100.0,
                        y=y / 100.0,
                        coordinate_frame="normalized_map_2d",
                    ),
                    summary=note,
                    tags=_tags(section, row.group("faction")),
                    execution_authority=False,
                    map_scope="zone_area",
                )
            )

    if not entries:
        raise NpcDataImportError("NPCData export contains no supported visible rows")
    try:
        return KnowledgeBrokerCatalog(
            catalog_id=config.catalog_id,
            target_profile=config.target_profile,
            product="wow",
            expansion="the_burning_crusade",
            client_version=config.client_version,
            client_build=config.client_build,
            entries=tuple(entries),
            execution_authority=False,
        )
    except KnowledgeBrokerError as error:
        raise NpcDataImportError(str(error)) from error
