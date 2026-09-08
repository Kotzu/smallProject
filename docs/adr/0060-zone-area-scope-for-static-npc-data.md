# ADR-0060 — Keep source NPC map-area IDs separate from WorldPack maps

- Status: Accepted
- Date: 2026-08-31
- Scope: Static Zygor `NPCData.lua` intake for TBC 2.4.3

## Context

Zygor's static NPC table stores coordinates as percentages alongside UI
`m####` map-area identifiers. Those identifiers are not the Movement Engine's
WorldPack continent IDs (`0`, `1`, `530`) and cannot be converted safely from a
string or a guessed table.

## Decision

Add `map_scope` to the read-only Knowledge Broker entry. Existing route and
WorldPack facts use `worldpack`; the bounded NPCData importer uses `zone_area`
and requires an explicit map-area binding for every visible row. The importer
classifies class/profession trainer sections but retains other static entries as
`npc_static`. Coordinates are normalized 2D source candidates only.

## Consequences

- Static trainer/NPC awareness can be indexed without laundering source IDs into
  runtime map identity.
- A future compatibility adapter must reconcile a `zone_area` entry with a
  client-observed map and WorldPack profile before any planner query.
- Missing or malformed rows fail closed; no source position becomes live-exact
  or executable.

## Rollback

Do not load `npc_data.py` catalogs. Existing WorldPack and client-observed
movement behavior is unchanged.
