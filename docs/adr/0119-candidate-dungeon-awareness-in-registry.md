# ADR-0119 — Candidate dungeon awareness in the map registry

- Status: Accepted
- Date: 2026-09-03
- Scope: TBC 2.4.3 map registry and read-only structure awareness

## Context

MonasteryInstances and Stratholme now have client-derived structure indexes and
partial access graphs from bounded offline probes. Keeping those artifacts out
of the registry would hide useful geometry from the Control Center, while
putting them in the executable movement path would be unsafe because coverage
is partial and semantic destinations are absent.

## Decision

Reference the candidate runtime profiles, indexes and partial access graphs for
map IDs `189` (MonasteryInstances) and `329` (Stratholme) from the registry.
They are read-only awareness only: `semantic_catalog` stays `null`,
`execution_authority` stays `false`, and no candidate graph can arm input or
make a map `autonomous_ready`.

## Consequences

The Control Center can inspect nearby client WMO/BVH evidence for these two
dungeons and can show the partial coverage state. Identity checks reject stale
or cross-map artifacts. No server truth, process memory, client modification or
synthetic input is introduced.

## Rollback

Set the two new registry structure references and runtime profiles back to
`null`; the inventory identities and the existing Stable maps remain unchanged.
