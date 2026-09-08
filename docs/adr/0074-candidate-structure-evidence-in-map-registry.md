# ADR-0074 — Candidate structure evidence in the map registry

- Status: Accepted
- Date: 2026-09-01
- Scope: TBC 2.4.3 map registry and read-only structure awareness

## Context

Kalimdor and Expansion01 have client-derived structure indexes and partial
access graphs produced by bounded local probes. Keeping them outside the map
registry makes the Control Center unable to inspect that evidence, even though
it can safely serve nearby-structure queries without execution authority.

## Decision

Reference the candidate index and partial access graph from the registry for
map IDs `1` (Kalimdor) and `530` (Expansion01). The registry readiness model
continues to require a map-bound semantic catalog as well; therefore these
profiles remain `OBSERVE_ONLY` and cannot start autonomous movement. The
candidate graph state is explicitly `PARTIAL_OBSERVED_COMPONENTS` and is
never promoted to an executable route or live gate.

## Consequences

The Control Center may load read-only structure awareness for both continents
and display local WMO/BVH evidence while their semantic destinations and full
coverage are still being built. Missing or stale candidate files fail closed
through the existing identity checks. No server truth, process memory, or
synthetic input is introduced.

## Rollback

Set the two registry structure references back to `null`; the map identities,
route-teacher counts and autonomous Azeroth profile remain unchanged.
