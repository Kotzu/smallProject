# ADR-0062: Content-minimal discovery of Zygor NPCData map IDs

- Status: Accepted
- Date: 2026-08-31
- Scope: Offline intake of the operator's Zygor Anniversary `NPCData.lua`

## Decision

The first compatibility pass may discover the `m####` map-area IDs and row
counts without requiring a binding file. The generated record contains only
the source hash/size, client/provider identity, and numeric map-area counts. It
does not retain Lua rows, NPC IDs, names, coordinates, or section labels.

Discovery is not a map reconciliation. IDs remain `zone_area` identifiers and
cannot be converted to WorldPack IDs or used as movement destinations. A later
adapter must supply reviewed bindings and client-visible confirmation before
static knowledge can influence navigation.

## Consequences

- `scripts/discover_zygor_npcdata_maps.py` makes the missing-binding set
  reproducible while keeping the repository artifact content-minimal.
- Malformed numeric rows fail closed instead of being silently omitted.
- The discovery result is evidence for compatibility work only and carries no
  execution authority.
