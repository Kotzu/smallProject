# ADR 0054 — Client-visible mouseover unit witness

## Status

Accepted for the TBC 2.4.3 LAB observer; execution remains unchanged.

## Context

The legacy client can expose one unit under the operator cursor through the
public `mouseover` token. This is useful for identifying a nearby mob/NPC that
has not been selected, but TBC 2.4.3 does not provide a verified public 3D
position or distance for that token. Treating the cursor cue as an exact world
coordinate would create false awareness and would violate provenance rules.

The legacy `GetPlayerMapPosition(unit)` API is not a generic entity-position
API: its documented supported unit classes are `player`, `partyN` and `raidN`.
`target` and `mouseover` NPCs are therefore not a legal substitute for an
entity coordinate feed.

## Decision

`PerfectAssassinObserver` records `UPDATE_MOUSEOVER_UNIT` as a bounded,
read-only `mouseover_snapshot`. The payload may contain GUID, name, player/NPC
kind, health, hostility and dead state. The SavedVariables schema and adapter
label every resulting fact `client_observed` through `mouseover_state`.

The payload must not contain server coordinates, memory-derived values,
guessed distance, or an execution command. The movement engine may use the
snapshot as an identity/state witness only; screen-space nameplates and a
separate selected-target range witness remain the sources for local geometry.

## Consequences

- The observer can preserve one additional public client signal without
  claiming ESP or hidden server state.
- Exact 3D awareness of every nearby entity remains unavailable unless a
  separately verified public client API is discovered and negotiated.
- Existing Champion and execution boundaries are unchanged; current clients
  need an addon update before this event appears in a new capture.
