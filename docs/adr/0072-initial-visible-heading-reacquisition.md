# ADR-0072: Require visible heading before initial locomotion

- Status: Accepted
- Date: 2026-09-01
- Scope: standalone Movement Engine, bounded LAB runner

## Context

The v7 bounded holdout reached Brill, then began the return leg with no facing
in the first fresh coordinate observations. The steering controller correctly
used its legacy `CALIBRATE_HEADING` behavior: one natural forward stride and a
displacement-derived heading. At a semantic handoff that stride was unsafe,
because it moved south while the target corridor was elsewhere and exhausted
the bounded recenter budget.

## Decision

Before the first movement input and after a route-planning refresh, the runner
reacquires fresh observations without holding any controls. It accepts exact
coordinate-HUD facing or the explicitly provenance-tagged minimap fallback. The
bound is four attempts; persistent absence raises a fail-closed error and does
not invoke natural-forward calibration.

## Consequences

- A compositor frame that temporarily omits facing can recover without input.
- A client that cannot expose a trustworthy heading stops before locomotion,
  preserving the deny-by-default execution boundary.
- Existing displacement heading estimation remains available for later
  diagnostics, but cannot be used as an implicit first-direction command.
- The live temporal-quality gate and combat handoff policy are unchanged.

## Verification

- Focused tests: `249/249`.
- Full regression: `1341/1341`.
- `compileall` and `git diff --check`: clean.
- No live input was sent after this decision.
