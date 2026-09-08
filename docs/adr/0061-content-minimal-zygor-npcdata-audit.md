# ADR-0061: Content-minimal audit for user-owned Zygor NPCData

- Status: Accepted
- Date: 2026-08-31
- Scope: Offline intake of the operator's Zygor Anniversary `NPCData.lua`

## Decision

The repository may provide a reproducible audit command for a user-owned
`NPCData.lua`, but the generated repository artifact contains only source hash,
size, counts, and explicit `m####` map-area bindings. It does not copy the Lua
rows, names, coordinates, or the licensed addon archive into the repository.

The caller must provide a map-binding file. Every encountered `m####` value is
required to have an explicit binding; the audit fails closed otherwise. Those
IDs remain `zone_area` scope and are never converted to WorldPack map IDs.

## Consequences

- `scripts/audit_zygor_npcdata.py` can be rerun against a local export and
  checked for staleness with `--check`.
- The result is suitable for regression evidence without becoming a static
  NPC catalog or an execution input.
- A later compatibility adapter still needs separately reviewed map-area to
  WorldPack reconciliation and client confirmation before a location can guide
  movement.
