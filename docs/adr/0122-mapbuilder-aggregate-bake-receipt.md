# ADR-0122 — MapBuilder aggregate completion receipt

## Context

MapBuilder v5 writes one completion line such as `Finished DeadminesInstance
(9216 tiles) in 18 seconds.` instead of one `Finished ... ADT (x, y)` line for
each ADT. The existing quality auditor could therefore show all nav files as
present while leaving `finished_adt_count=0`.

## Decizie

The auditor accepts the aggregate line only when the map name matches and the
reported inner-tile count equals the pinned `256 × expected ADT count`. The
exact nav artifact set, zero failed tiles, return code, and independent
geometry validator remain required. A malformed or partial aggregate does not
turn an incomplete bake into a pass.

## Evidence

The Deadmines candidate now reports `36/36` finished ADTs, `36/36` nav ADTs and
`0` missing coordinates. Recast diagnostics remain visible and the status is
`COMPLETE_WITH_RECAST_DIAGNOSTICS`; geometry separately passes `36/36`.
