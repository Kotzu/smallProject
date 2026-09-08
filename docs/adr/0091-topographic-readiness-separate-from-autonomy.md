# ADR-0091 — Topographic readiness is separate from autonomous readiness

## Status

Accepted for offline validation.

## Context

A TBC 2.4.3 WorldPack may already contain client-derived floors, heights,
walls, structures, bridges, stairs and clearance evidence while its semantic
destination catalog is still incomplete. Showing such a map as only
`OBSERVE_ONLY` hides useful progress; showing it as autonomous would be unsafe.

## Decision

`WorldMapProfileReadiness` exposes two separate states:

1. `topographic_ready` means the runtime WorldPack, structure index and
   structure-access graph all match the selected map identity.
2. `autonomous_ready` means `topographic_ready` plus a valid semantic location
   catalog.

The registry audit records the topographic state and count. Control Center
shows `TOPOGRAFIC • catalog semantic lipsă` for the first state and keeps the
autonomous start gate closed. No state grants execution authority.

## Limits

Topographic readiness proves only read-only geometry availability and bounded
adapter queries. It does not prove a route in the live client, actor heading,
camera integrity, combat or leveling completion.
