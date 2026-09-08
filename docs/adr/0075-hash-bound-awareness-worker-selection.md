# ADR-0075 — Hash-bound worker selection for structure awareness

- Status: Accepted
- Date: 2026-09-01
- Scope: Control Center read-only structure-awareness service

## Context

The promoted Azeroth access graph is bound to nav probe v34, while the
continental candidate graphs were produced with v35. A single global worker
constant makes one of those valid graph identities fail to load.

## Decision

Select the awareness worker by matching the graph's recorded worker hash
against an explicit local allowlist containing only the pinned v34 and v35
binary paths. The graph supplies an identity to verify, never a path to run.
Any missing, malformed or unmatched hash aborts awareness startup fail-closed.

## Consequences

All registered candidate graphs can be inspected through the read-only service
without weakening the semantic live gate or execution authority. New workers
must be added to the allowlist and covered by tests before use.

## Rollback

Restore the global v34 worker argument in the awareness service launcher and
remove candidate graph references from the registry; autonomous Azeroth
behavior and the live gate remain unchanged.
