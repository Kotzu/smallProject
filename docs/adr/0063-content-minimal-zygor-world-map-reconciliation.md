# ADR-0063: Content-minimal reconciliation Zygor–WorldMapArea

- Status: Accepted
- Date: 2026-09-01
- Scope: Offline compatibility intake for the operator's Zygor TBC Anniversary export

## Decision

The static `m####` IDs discovered in Zygor `NPCData.lua` may be compared with
the client `WorldMapArea.dbc` names through LibRover's explicit
`MapIDsByName` table. The audit persists only source hashes, numeric IDs,
row-counts, reconciliation status and client WorldPack map IDs. It does not
persist licensed Lua rows, NPC names, map names or coordinates.

Exact and punctuation-normalized matches are evidence for a later adapter
binding only. Unresolved or ambiguous IDs remain fail-closed and cannot
become semantic destinations or Champion execution input. The report always
has `execution_authority=false`.

## Consequences

- `scripts/audit_zygor_world_map_reconciliation.py` makes the comparison
  deterministic and contract-validated.
- The current Anniversary source resolves 45/66 IDs (22 exact, 23
  normalized) and leaves 21 unresolved, including cosmetic-name variants and
  synthetic dungeon IDs.
- A separate reviewed crosswalk is still required before NPC/trainer facts
  can be promoted into any map semantic catalog.
