# ADR-0058 — Registry-bound semantic catalog in Control Center

## Status

Accepted — 2026-08-31

## Context

The Control Center exposes the complete WorldPack inventory, while only a
subset of profiles currently has semantic destinations and a structure/access
graph.  The UI previously loaded the Azeroth/Tirisfal catalog once and could
keep those destination IDs visible after another map profile was selected.
That risks presenting coordinates from one map as if they belonged to another.

## Decision

The selected registry profile is the only source allowed to populate semantic
destinations.  The default profile keeps the exact Tirisfal binding.  A future
profile may provide its own catalog only when the catalog declares the selected
map identity, a valid TBC client-world coordinate system, a non-empty atlas
binding, and valid destination records.  Switching to a profile without a
valid catalog clears the destination and sequence state and leaves autonomous
start fail-closed.

Semantic planning also resolves the WorldPack binding from the selected
profile, rather than silently falling back to the Azeroth profile.

## Consequences

- The map picker can remain inventory-complete without inventing destinations.
- Existing Brill/Deathknell behavior is unchanged for the validated Azeroth
  profile.
- Shadowfang and other profiles remain `OBSERVE_ONLY` until their own semantic
  catalog, transform, navmesh and structure evidence exist.
- This change does not add input authority and does not imply live validation.
