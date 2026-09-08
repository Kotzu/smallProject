from __future__ import annotations

import re
from typing import Iterable


class ZygorMapBindingError(ValueError):
    """Raised when a Zygor map-area table cannot be reconciled safely."""


_TABLE_START = re.compile(r"(?m)^\s*data\.MapIDsByName\s*=\s*\{\s*$")
_TABLE_END = re.compile(r"(?m)^\s*data\.MapNamesByID\s*=\s*\{.*$")
_ENTRY = re.compile(
    r'^\s*\["(?P<name>(?:\\.|[^"\\])*)"\]\s*=\s*'
    r"\{(?P<body>[^{}\r\n]*)\}\s*,?\s*$"
)
_MAP_ID = re.compile(r"\[\d+\]\s*=\s*(?P<map_id>\d+)")


# LibRover/guide labels and WorldMapArea internal names are two different
# client data vocabularies.  These aliases are compatibility identity only;
# they do not contain route points and cannot grant execution authority.
_WORLD_MAP_INTERNAL_ALIASES = {
    "alteracmountains": "alterac",
    "arathihighlands": "arathi",
    "azshara": "aszhara",
    "azuremystisle": "azuremystisle",
    "bladesedgemountains": "bladesedgemountains",
    "darnassus": "darnassis",
    "deadwindpass": "deadwindpass",
    "dunmorogh": "dunmorogh",
    "dustwallowmarsh": "dustwallow",
    "easternkingdoms": "azeroth",
    "elwynnforest": "elwynn",
    "eversongwoods": "eversongwoods",
    "hellfirepeninsula": "hellfire",
    "hillsbradfoothills": "hilsbrad",
    "isleofqueldanas": "sunwell",
    "kalimdor": "kalimdor",
    "netherstorm": "netherstorm",
    "orgrimmar": "ogrimmar",
    "redridgemountains": "redridge",
    "shadowmoonvalley": "shadowmoonvalley",
    "shattrathcity": "shattrathcity",
    "silvermooncity": "silvermooncity",
    "silverpineforest": "silverpine",
    "stonetalonmountains": "stonetalonmountains",
    "stormwindcity": "stormwind",
    "stranglethornvale": "stranglethorn",
    "swampofsorrows": "swampofsorrows",
    "thebarrens": "barrens",
    "theexodar": "theexodar",
    "thehinterlands": "hinterlands",
    "thunderbluff": "thunderbluff",
    "tirisfalglades": "tirisfal",
    "ungorocrater": "ungorocrater",
    "westernplaguelands": "westernplaguelands",
}


def normalize_zygor_world_map_name(value: str) -> str:
    """Normalize a static guide/client zone label for compatibility lookup."""

    if not isinstance(value, str):
        raise ZygorMapBindingError("WorldMapArea name must be a string")
    return "".join(character.lower() for character in value if character.isalnum())


def zygor_world_map_internal_key(value: str) -> str:
    """Return the explicit WorldMapArea internal-name key for a guide label."""

    if not isinstance(value, str) or not value.strip():
        raise ZygorMapBindingError("WorldMapArea label is empty")
    cleaned = re.sub(r"/\d+.*$", "", value).strip()
    normalized = normalize_zygor_world_map_name(cleaned)
    return _WORLD_MAP_INTERNAL_ALIASES.get(normalized, normalized)


def _lua_name(value: str) -> str:
    """Decode only the bounded escapes permitted in a Lua quoted key."""

    return re.sub(r"\\(.)", r"\1", value).strip()


def parse_zygor_map_name_candidates(text: str) -> dict[int, tuple[str, ...]]:
    """Parse LibRover's static ``MapIDsByName`` table without evaluating Lua.

    The returned values may contain more than one name because the upstream
    table deliberately aliases some synthetic dungeon IDs.  Callers must use
    :func:`resolve_zygor_map_bindings` for the exact IDs they intend to use;
    ambiguous aliases are never selected implicitly.
    """

    if not isinstance(text, str) or not text.strip():
        raise ZygorMapBindingError("LibRover map table is empty")
    start = _TABLE_START.search(text)
    end = _TABLE_END.search(text)
    if start is None or end is None or end.start() <= start.end():
        raise ZygorMapBindingError("LibRover MapIDsByName table is missing")

    names_by_id: dict[int, set[str]] = {}
    table_text = text[start.end() : end.start()]
    for line_number, raw_line in enumerate(table_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        entry = _ENTRY.match(raw_line)
        if entry is None:
            # Comments and section separators are permitted, but a malformed
            # map entry must not disappear silently from a compatibility table.
            if line.startswith('["'):
                raise ZygorMapBindingError(
                    f"malformed LibRover map entry at local line {line_number}"
                )
            continue
        name = _lua_name(entry.group("name"))
        if not name:
            raise ZygorMapBindingError(
                f"LibRover map entry has no name at local line {line_number}"
            )
        map_ids = [int(match.group("map_id")) for match in _MAP_ID.finditer(entry.group("body"))]
        if not map_ids:
            raise ZygorMapBindingError(
                f"LibRover map entry has no numeric ID at local line {line_number}"
            )
        for map_id in map_ids:
            names_by_id.setdefault(map_id, set()).add(name)

    if not names_by_id:
        raise ZygorMapBindingError("LibRover map table contains no numeric IDs")
    return {
        map_id: tuple(sorted(names)) for map_id, names in sorted(names_by_id.items())
    }


def resolve_zygor_map_bindings(
    text: str, required_map_ids: Iterable[int]
) -> dict[int, str]:
    """Resolve exactly the requested IDs, failing on missing/ambiguous names."""

    required = {int(map_id) for map_id in required_map_ids}
    if any(map_id < 0 for map_id in required):
        raise ZygorMapBindingError("required map IDs must be non-negative")
    candidates = parse_zygor_map_name_candidates(text)
    missing = sorted(map_id for map_id in required if map_id not in candidates)
    if missing:
        joined = ", ".join(f"m{map_id}" for map_id in missing)
        raise ZygorMapBindingError(f"LibRover map IDs are missing: {joined}")
    ambiguous = sorted(
        map_id for map_id in required if len(candidates[map_id]) != 1
    )
    if ambiguous:
        joined = ", ".join(f"m{map_id}" for map_id in ambiguous)
        raise ZygorMapBindingError(f"LibRover map IDs are ambiguous: {joined}")
    return {map_id: candidates[map_id][0] for map_id in sorted(required)}
