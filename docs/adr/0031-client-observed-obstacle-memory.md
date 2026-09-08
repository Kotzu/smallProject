# ADR 0031: Client-observed obstacle memory is bounded and expiring

## Status

Accepted

## Context

Client assets and Recast/Detour provide the primary static geometry, but a
small doodad collision can still be missed by the generated tunnel probes. A
controller that forgets every proven contact repeats the same visibly robotic
recovery. Hardcoding the incident coordinate into a route would make the
system brittle and would not generalize to another realm or destination.

## Decision

Movement Engine may record a blocker only when all of these conditions hold:

1. visible pose proves collision/no corridor progress;
2. the bounded physical recovery clears the actor;
3. excluding the local blocker produces a complete Detour corridor;
4. the record is bound to client build, map, zone and client-world coordinates.

The record is external runtime knowledge with `execution_authority=false`.
One observation is `provisional` for 7 days. A second spatially matching
observation is `confirmed` permanently. Queries are distance sorted and expose
at most the nearest 8 blockers within 300 yd to the native worker. Stale,
malformed, wrong-build or wrong-zone data is rejected or ignored fail-closed.

Client-collision evidence is stored as bounded boundary cells. Contacts on
different parts of a wall remain different cells; they are never inflated into
one enclosing disc, because that disc could erase the real passage around a
long or concave obstacle. Detour polygon-exclusion evidence retains its union
semantics because it describes one excluded polygon cluster.

The memory stores obstacle cells, never movement commands, semantic
destinations or ordered waypoints. Operator-drawn obstacle polygons remain
separate candidate knowledge and still require runtime confirmation.

## Consequences

- A repeated trip can avoid a proven small collision before contact.
- A transient player, NPC or realm-specific object cannot poison navigation
  permanently after one observation.
- The same movement code remains portable across servers using the same client
  build and map assets.
- Geometry extraction remains the primary fix; experience memory is a bounded
  supplemental layer, not a substitute for a complete world model.
- A confirmed blocker that overlaps the selected route and has no independently
  validated bypass stops planning before input instead of repeating collision.
