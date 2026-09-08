# ADR-0005 — Verified TBC 2.4.3 `PARTY_KILL` mapping

- Status: Accepted
- Date: 2026-08-22
- Scope: M1 / PA-019

## Context

The first real TBC 2.4.3 LAB export contains legacy `COMBAT_LOG_EVENT_UNFILTERED` payloads. Their positional fields vary by sub-event. Interpreting the entire stream from modern assumptions would create false knowledge and violate the client-observed provenance boundary.

## Decision

Only `PARTY_KILL` is semantically mapped in PA-019. The adapter emits `target.dead=true` and the destination target identity only when:

1. the event has the verified legacy base layout;
2. a client-observed active target is already known;
3. the event destination GUID exactly equals that active target GUID.

All raw events remain archived. Every event reports whether it was interpreted. No damage, miss, cast, unit-death or loot semantics are inferred from the remaining raw payloads.

When `target.dead=true` is applied to effective state, stale `target.health_pct` is removed. The system does not invent a zero-health observation.

## Consequences

- The observed Duskbat kill can close a PvE encounter as victory without server-only knowledge.
- Unrelated kills cannot be attributed to the selected target.
- The adapter becomes stateful within one ordered export, while deterministic replay remains based on emitted observations.
- Additional sub-events require their own captured evidence, mapping tests and capability update.

## Rejected

- treating `UNIT_DIED` as the active target death without a verified identity rule;
- decoding all legacy events through one positional schema;
- deriving quest completion, loot, damage totals or ability success from unverified fields;
- retaining stale target health after a verified death observation.

## Rollback

Revert the PA-019 commit. Raw combat events remain sufficient for a future remap; no Champion identity memory depends on this LAB capture.
