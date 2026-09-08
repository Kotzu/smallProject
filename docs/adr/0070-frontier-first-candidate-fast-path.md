# ADR 0070: Frontier first-candidate fast path

## Status

Accepted — offline implementation, pending bounded live revalidation.

## Context

The Crypt→Brill v5 live trace reached the repeated navmesh frontier while the
ordered semantic bypass worker was still running. The first ordered road cell
was the valid candidate, but the worker submitted all candidates to a
`ThreadPoolExecutor`. Returning from the executor context waits for every
speculative child, so a valid first result still carried the latency of the
remaining cold WorldPack queries into the control loop. The temporal evaluator
correctly recorded the resulting observation gap as unexplained.

## Decision

Probe the first candidate alone before starting the bounded fan-out. If it is
navmesh-valid, return immediately. If it fails, probe the remaining candidates
concurrently, consume results in route order, and wait for explicit read-only
teardown. No geometric point is invented and no quality-gate threshold is
changed.

## Consequences

- The common frontier path avoids speculative tail latency before handoff.
- Candidate ordering and fail-closed validation remain deterministic.
- The multi-failure path can still be slower, but it is off the realtime
  control loop and remains bounded.
- Offline validation is green; one live holdout is still required to verify
  temporal quality after the client is visibly `InWorld`.
