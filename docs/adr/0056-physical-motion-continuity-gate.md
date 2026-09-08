# ADR-0056: Physical-motion continuity gate for projected progress

## Status

Accepted — 2026-08-31

## Context

The Movement Engine tracks journey progress from a navmesh corridor and the
remaining semantic-goal distance. During the v38 Crypt→Brill trace, one
observation interval near the Brill approach lasted `1.25 s` while the client
advanced only about `0.55 yd` with `MOVE_FORWARD` still held. Corridor
projection could otherwise classify that interval as meaningful progress and
reset the no-progress clock, hiding a visible pause.

## Decision

Add the pure helper `observed_motion_is_continuous()` in the movement domain
and apply it after each observed control frame. A forward request requires at
least `0.08 yd` displacement; intervals longer than `0.30 s` additionally
require at least `1.50 yd/s` average displacement. When this evidence is not
present, projected corridor progress cannot reset the no-progress clock. The
append-only frame record exposes `physical_motion_continuous` for replay and
quality analysis.

## Consequences

- A real pause or observer stall is visible and eventually eligible for the
  existing bounded recovery/replan path.
- Short HUD quantization frames do not by themselves trigger recovery; a later
  moving frame resets the clock.
- No A/D fallback, hardcoded waypoint, server ground truth, or execution
  authority is introduced.
- The change is offline-verified only until a new bounded live run is explicitly
  authorized.

## Evidence

- `tests/test_client_navigation_runtime.py`: continuity and pause cases.
- Targeted navigation tests: `83/83`.
- Full offline regression after this ADR: `1259/1259`.
