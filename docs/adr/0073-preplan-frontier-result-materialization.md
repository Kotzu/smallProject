# ADR-0073: Materialize ready frontier results before semantic handoff

- Status: Accepted
- Date: 2026-09-01
- Scope: standalone Movement Engine, bounded LAB runner

## Context

The v7 outbound trace reached the frontier but still contained one unexplained
observation gap. The frontier worker had completed its read-only navmesh query,
yet the first `Future.result()` was consumed in the same control iteration that
applied the semantic bypass. Result handoff/materialization then aged the last
pose beyond the control budget while the actor was stationary for a turn.

## Decision

When the frontier Future is already `done()` during the preplan phase, consume
its result once before the handoff boundary and retain the Future for the
existing ordered handoff logic. Record the bounded duration and status. Do not
wait for an in-flight Future, invent a candidate, or alter the worker's
read-only authority.

## Consequences

- Any result-materialization cost is paid while the current corridor remains
  authoritative, where measured locomotion can explain a capture interval.
- The handoff path performs no duplicate expensive materialization.
- An exception remains visible and is handled by the existing fail-closed
  frontier fallback.
- The temporal quality gate remains unchanged and still requires live proof.

## Verification

- Focused tests: `250/250`.
- Full regression: `1342/1342`.
- Semantic offline validation v52: `PASS` (`4xARRIVE`, hill `RESET_REQUIRED`).
- `runtime_arm_present=false`; no live input sent after this change.
