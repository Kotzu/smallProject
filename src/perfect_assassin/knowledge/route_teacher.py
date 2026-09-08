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


class RouteTeacherImportError(ValueError):
    """Raised when a user-owned route export cannot be bound safely."""


def next_advisory_route_steps(
    catalog: KnowledgeBrokerCatalog,
    *,
    map_id: int,
    level: int,
    completed_entry_ids: frozenset[str] = frozenset(),
    after_step_order: int = 0,
    limit: int = 1,
) -> tuple[KnowledgeEntry, ...]:
    """Return the next RouteTeacher facts without granting movement authority.

    The cursor is deliberately small: it uses only the imported guide order,
    exact WorldPack map identity, level range and a caller-owned completion
    set.  A returned ``KnowledgeEntry.position`` is still a static source
    candidate.  The movement engine must validate it against fresh client
    observations and its own navmesh before proposing any route.
    """

    if not isinstance(catalog, KnowledgeBrokerCatalog):
        raise KnowledgeBrokerError("route teacher catalog is invalid")
    if type(map_id) is not int or not 0 <= map_id <= 2_147_483_647:
        raise KnowledgeBrokerError("route teacher map id is invalid")
    if type(level) is not int or not 1 <= level <= 70:
        raise KnowledgeBrokerError("route teacher level is invalid")
    if (
        not isinstance(completed_entry_ids, frozenset)
        or any(not isinstance(entry_id, str) or not entry_id for entry_id in completed_entry_ids)
    ):
        raise KnowledgeBrokerError("completed route entry IDs are invalid")
    if type(after_step_order) is not int or not 0 <= after_step_order <= 100_000:
        raise KnowledgeBrokerError("route teacher cursor order is invalid")
    if type(limit) is not int or not 1 <= limit <= 64:
        raise KnowledgeBrokerError("route teacher cursor limit is invalid")

    candidates = [
        entry
        for entry in catalog.entries
        if entry.source.provider == "route_teacher"
        and entry.execution_authority is False
        and entry.map_scope == "worldpack"
        and entry.map_id == map_id
        and entry.level_min <= level <= entry.level_max
        and entry.entry_id not in completed_entry_ids
        and entry.step_order is not None
        and entry.step_order > after_step_order
    ]
    candidates.sort(key=lambda entry: (entry.step_order or 0, entry.entry_id))
    return tuple(candidates[:limit])


@dataclass(frozen=True, slots=True)
class RouteTeacherImportConfig:
    catalog_id: str
    target_profile: str
    client_version: str
    client_build: str
    provider_version: str
    retrieved_at: str
    source_uri: str
    default_map_id: int
    default_map_name: str
    zone_map_bindings: Mapping[str, tuple[int, str]]


_REGISTER_GUIDE = re.compile(r"RegisterGuide\(\s*['\"]([^'\"]+)")
_GOTO = re.compile(
    r"^\s*goto\s+(?:(?P<zone>[^,]+),\s*)?(?P<x>\d+(?:\.\d+)?)\s*,\s*(?P<y>\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_ACTION = re.compile(r"^\s*(?P<kind>talk|accept|turnin|learn)\s+(?P<value>[^#\r\n]+)", re.IGNORECASE)
# Lua zone names may contain the other quote character (for example
# ``Un'Goro Crater``).  Match the opening quote and require the same quote at
# the end instead of stopping at the first apostrophe.
_MAPZONE = re.compile(
    r"\bmapzone\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_LEVEL = re.compile(r"(?m)^\s*level\s*=\s*(\d+)\s*,?\s*$", re.IGNORECASE)
_XY_FIELDS = re.compile(
    r"\bx\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*y\s*=\s*(-?\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_CL_COORDINATES = re.compile(
    r"\bcl\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)
_MODERN_GOTO = re.compile(
    r"\|goto\s+(?P<zone>[^|]*?)\s+(?P<x>\d+(?:\.\d+)?)\s*,\s*(?P<y>\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-")
    return slug[:100] or "guide"


def _map_binding(
    config: RouteTeacherImportConfig, zone: str | None
) -> tuple[int, str]:
    if zone is None or not zone.strip():
        return config.default_map_id, config.default_map_name
    binding = config.zone_map_bindings.get(zone.strip())
    if binding is None:
        raise RouteTeacherImportError(
            f"route zone has no explicit WorldPack binding: {zone.strip()!r}"
        )
    return int(binding[0]), str(binding[1])


def _legacy_step_blocks(text: str) -> list[tuple[int, str]]:
    """Extract top-level entries from legacy ``steps = { { ... }, ... }`` tables.

    The guide is Lua data, not a Python module. A tiny quote/comment-aware brace
    scanner is sufficient for the table shape and avoids executing untrusted Lua.
    """

    blocks: list[tuple[int, str]] = []
    for match in re.finditer(r"\bsteps\s*=\s*\{", text, re.IGNORECASE):
        opening = match.end() - 1
        depth = 1
        start: int | None = None
        quote: str | None = None
        escaped = False
        comment = False
        index = opening + 1
        while index < len(text) and depth:
            char = text[index]
            if comment:
                if char == "\n":
                    comment = False
                index += 1
                continue
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char == "-" and index + 1 < len(text) and text[index + 1] == "-":
                comment = True
                index += 2
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                continue
            if char == "{":
                depth += 1
                if depth == 2:
                    start = index
            elif char == "}":
                if depth == 2 and start is not None:
                    line_number = text.count("\n", 0, start) + 1
                    blocks.append((line_number, text[start : index + 1]))
                    start = None
                depth -= 1
            index += 1
        if depth:
            raise RouteTeacherImportError("route export has an unterminated steps table")
    return blocks


def _source_coordinates(block: str) -> tuple[float, float] | None:
    match = _XY_FIELDS.search(_without_comment_only_lines(block)) or _CL_COORDINATES.search(
        _without_comment_only_lines(block)
    )
    if match is None:
        return None
    return float(match.group(1)), float(match.group(2))


def _without_comment_only_lines(block: str) -> str:
    """Remove guide comment lines before looking for actionable coordinates.

    Anniversary guide exports use both Lua ``--`` and legacy ``//`` comments.
    A commented ``|goto`` is documentation, not a route candidate; retaining it
    can attach an instance-only coordinate to the active step above it.
    """

    return "\n".join(
        line
        for line in block.splitlines()
        if not line.lstrip().startswith(("--", "//"))
    )


def _legacy_tags(block: str) -> tuple[str, ...]:
    lower = block.lower()
    tags: list[str] = []
    if re.search(r"\btalk\b", lower):
        tags.append("talk")
    if re.search(r"\baccept\b", lower):
        tags.append("accept")
    if re.search(r"\bturn\s+in\b|questturnedin", lower):
        tags.append("turnin")
    if re.search(r"\bkill\b|\bgrind\b", lower):
        tags.append("combat")
    if re.search(r"\bprofession\b|\blearn\b", lower):
        tags.append("profession")
    if re.search(r"\btrainer\b|train abilities", lower):
        tags.append("trainer")
    return tuple(tags)


_PROFESSION_MARKERS = re.compile(
    r"\b(alchemy|blacksmith|cooking|enchant|engineering|first aid|fishing|herbal|jewel|leatherwork|mining|skinning|tailor|profession|tradeskill)\b",
    re.IGNORECASE,
)
_CLASS_MARKERS = re.compile(
    r"\b(warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid|death knight)\b",
    re.IGNORECASE,
)


def _entry_kind(block: str) -> str:
    """Classify only unambiguous guide facts; everything else stays a route step."""

    lower = block.lower()
    if re.search(r"\|trainer\b|train abilities", lower):
        return "profession_trainer" if _PROFESSION_MARKERS.search(lower) else "class_trainer"
    if re.search(r"\|skillmax\b|\|learn\b", lower):
        return "profession_trainer"
    if re.search(r"\b(accept|turnin|turn in)\b", lower):
        if _PROFESSION_MARKERS.search(lower):
            return "profession_quest"
        if re.search(r"\|only if[^\n]*(?:warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid)", lower):
            return "class_quest"
    return "route_step"


def _modern_step_blocks(text: str) -> list[tuple[int, str, str]]:
    """Extract ``step`` blocks from current Zygor long-bracket guide data."""

    blocks: list[tuple[int, str, str]] = []
    for body_match in re.finditer(r"\[\[(.*?)\]\]", text, re.DOTALL):
        body = body_match.group(1)
        step_matches = list(re.finditer(r"(?m)^\s*step\s*$", body, re.IGNORECASE))
        if not step_matches:
            continue
        prefix = text[: body_match.start()]
        guide_matches = list(_REGISTER_GUIDE.finditer(prefix))
        guide_name = guide_matches[-1].group(1).strip() if guide_matches else "user-owned-guide"
        for index, step_match in enumerate(step_matches):
            start = step_match.end()
            end = step_matches[index + 1].start() if index + 1 < len(step_matches) else len(body)
            block = body[start:end]
            line_number = text.count("\n", 0, body_match.start() + step_match.start()) + 1
            blocks.append((line_number, guide_name, block))
    return blocks


def _modern_coordinates(block: str) -> tuple[str | None, float, float] | None:
    match = _MODERN_GOTO.search(_without_comment_only_lines(block))
    if match is None:
        return None
    zone = match.group("zone").strip()
    # Some guide branches spell the same map as ``Zone/0 Zone``; the
    # compatibility suffix is not part of the WorldPack zone identity.
    zone = re.sub(r"/\d+.*$", "", zone).strip()
    return zone or None, float(match.group("x")), float(match.group("y"))


def import_zygor_lua(
    text: str, *, config: RouteTeacherImportConfig
) -> KnowledgeBrokerCatalog:
    """Import bounded route metadata from a user-owned Zygor-style Lua export.

    This deliberately supports only visible route verbs and the legacy Zygor
    ``steps`` table shape. It does not evaluate Lua, execute guide actions, or
    retain the original guide payload. Every coordinate is a 0..100 source map
    percentage and is stored as a static 2D candidate pending client
    confirmation.
    """

    if not isinstance(text, str) or not text.strip():
        raise RouteTeacherImportError("route export is empty")
    guide_match = _REGISTER_GUIDE.search(text)
    guide_name = guide_match.group(1).strip() if guide_match else "user-owned-guide"
    source = KnowledgeSource(
        provider="route_teacher",
        origin="route_guidance",
        uri=config.source_uri,
        provider_version=config.provider_version,
        retrieved_at=config.retrieved_at,
        content_mode="user_owned_export",
    )
    entries: list[KnowledgeEntry] = []
    legacy_blocks = _legacy_step_blocks(text)
    if legacy_blocks:
        for step_order, (line_number, block) in enumerate(legacy_blocks, start=1):
            zone_match = _MAPZONE.search(block)
            zone = zone_match.group("value").strip() if zone_match else None
            map_id, map_name = _map_binding(config, zone)
            coordinates = _source_coordinates(block)
            position = None
            if coordinates is not None:
                x, y = coordinates
                if not 0.0 <= x <= 100.0 or not 0.0 <= y <= 100.0:
                    raise RouteTeacherImportError(
                        f"route coordinate is outside 0..100 at line {line_number}"
                    )
                position = KnowledgePosition(
                    x=x / 100.0, y=y / 100.0,
                    coordinate_frame="normalized_map_2d",
                )
            level_match = _LEVEL.search(block)
            level = int(level_match.group(1)) if level_match else 1
            if not 1 <= level <= 70:
                raise RouteTeacherImportError(
                    f"route level is outside 1..70 at line {line_number}"
                )
            entries.append(
                KnowledgeEntry(
                    entry_id=f"route.{_safe_id(guide_name)}.legacy-step-{step_order:05d}",
                    kind=_entry_kind(block),
                    name=f"legacy-step:{step_order:05d}",
                    map_id=map_id,
                    map_name=map_name,
                    level_min=level,
                    level_max=70,
                    source=source,
                    confidence=0.75,
                    evidence_refs=(f"{config.source_uri}#L{line_number}",),
                    position=position,
                    tags=_legacy_tags(block),
                    step_order=step_order,
                    execution_authority=False,
                )
            )
        if entries:
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
                raise RouteTeacherImportError(str(error)) from error

    modern_blocks = _modern_step_blocks(text)
    if modern_blocks:
        current_guide_name: str | None = None
        current_zone: str | None = None
        for step_order, (line_number, block_guide_name, block) in enumerate(modern_blocks, start=1):
            if block_guide_name != current_guide_name:
                current_guide_name = block_guide_name
                current_zone = None
            coordinates = _modern_coordinates(block)
            zone = coordinates[0] if coordinates is not None else None
            if zone is not None:
                current_zone = zone
            else:
                # Modern guides commonly put a talk/kill step before the
                # coordinate-bearing action.  Keep the last explicit zone
                # within the same guide so advisory map coverage does not
                # silently fall back to Azeroth for every coordinate-less
                # step.  This remains a compatibility binding, never a route
                # execution instruction.
                zone = current_zone
            map_id, map_name = _map_binding(config, zone)
            position = None
            if coordinates is not None:
                _, x, y = coordinates
                if not 0.0 <= x <= 100.0 or not 0.0 <= y <= 100.0:
                    raise RouteTeacherImportError(
                        f"route coordinate is outside 0..100 at line {line_number}"
                    )
                position = KnowledgePosition(
                    x=x / 100.0, y=y / 100.0,
                    coordinate_frame="normalized_map_2d",
                )
            entries.append(
                KnowledgeEntry(
                    entry_id=f"route.{_safe_id(block_guide_name)}.step-{step_order:05d}",
                    kind=_entry_kind(block),
                    name=f"route-step:{step_order:05d}",
                    map_id=map_id,
                    map_name=map_name,
                    level_min=1,
                    level_max=70,
                    source=source,
                    confidence=0.75,
                    evidence_refs=(f"{config.source_uri}#L{line_number}",),
                    position=position,
                    tags=_legacy_tags(block),
                    step_order=step_order,
                    execution_authority=False,
                )
            )
        if entries:
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
                raise RouteTeacherImportError(str(error)) from error

    current_zone: str | None = None
    step_order = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        if line.lower() == "step" or line.lower().startswith("step "):
            step_order += 1
            continue
        goto = _GOTO.match(line)
        action = _ACTION.match(line)
        if goto is None and action is None:
            continue
        if goto is not None:
            zone = goto.group("zone")
            if zone is not None:
                current_zone = zone.strip()
            x = float(goto.group("x"))
            y = float(goto.group("y"))
            if not 0.0 <= x <= 100.0 or not 0.0 <= y <= 100.0:
                raise RouteTeacherImportError(
                    f"route coordinate is outside 0..100 at line {line_number}"
                )
            map_id, map_name = _map_binding(config, current_zone)
            entry_name = f"goto:{current_zone or map_name}:{x:g},{y:g}"
            position = KnowledgePosition(
                x=x / 100.0,
                y=y / 100.0,
                coordinate_frame="normalized_map_2d",
            )
        else:
            assert action is not None
            action_kind = action.group("kind").lower()
            value = action.group("value").strip()
            if not value or len(value) > 120:
                raise RouteTeacherImportError(
                    f"route action value is invalid at line {line_number}"
                )
            map_id, map_name = _map_binding(config, current_zone)
            entry_name = f"{action_kind}:{value}"
            position = None
        entry_id = f"route.{_safe_id(guide_name)}.line-{line_number:05d}"
        entries.append(
            KnowledgeEntry(
                entry_id=entry_id,
                kind="route_step",
                name=entry_name,
                map_id=map_id,
                map_name=map_name,
                level_min=1,
                level_max=70,
                source=source,
                confidence=0.75,
                evidence_refs=(f"{config.source_uri}#L{line_number}",),
                position=position,
                step_order=step_order,
                execution_authority=False,
            )
        )
    if not entries:
        raise RouteTeacherImportError("route export contains no supported visible steps")
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
        raise RouteTeacherImportError(str(error)) from error
