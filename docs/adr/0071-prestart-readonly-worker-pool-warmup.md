# ADR-0071: Prestart read-only worker pools before the pose clock

- Status: Accepted
- Date: 2026-09-01
- Scope: standalone Movement Engine, bounded LAB runner

## Context

The semantic frontier fast-path removed speculative tail work, but the first
`ProcessPoolExecutor.submit()` on Windows still starts a child process lazily.
In live holdout v6b that startup occurred while the capture/control loop held
the movement lease and contributed to unexplained observation gaps.

## Decision

Before `pose_source.open()`, the runner submits and awaits one picklable no-op
per configured read-only worker in the primary preplan, advisory and frontier
process pools. The warmup has a bounded timeout and fails closed before any
input is emitted. The no-op has no client, navmesh or actuator access.

## Consequences

- The first real preplan/frontier query does not also pay Python child startup.
- Five bounded read-only workers may be resident for a navigation session.
- A worker-start failure prevents the session from opening its pose/control
  clock, preserving the deny-by-default execution boundary.
- The temporal quality gate remains unchanged; live revalidation is required.

## Verification

- Focused tests: `247/247`.
- Full regression: `1339/1339`.
- Semantic offline validation v51: `PASS` (`4×ARRIVE`, hill fixture
  `RESET_REQUIRED`).
- No live input was sent after this change.
