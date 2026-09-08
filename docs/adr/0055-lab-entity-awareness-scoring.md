# ADR-0055: LAB-only entity awareness scoring

## Context

The client-visible observer can identify only the units that the public UI
exposes (for example target, focus, mouseover and visible nameplates). The
LAB may also have exact server spawn coordinates, but those coordinates must
not enter Champion decisions.

## Decision

Add `perfect_assassin.lab.entity_awareness.evaluate_entity_awareness` as a
scoring-only boundary. It matches client witnesses by exact observed ID,
reports identity recall/precision, and computes a position error only when the
client witness itself includes coordinates. Anonymous screen-space witnesses
remain unlocalized; no coordinate is inferred from pixels, map priors or
server truth.

The result is explicitly marked `LAB_EVALUATION_ONLY`, records separate
`server_ground_truth` and `client_observed` origins, and always has
`execution_authority=false`. The evaluator is not imported by `brain`,
`movement`, `adapter` or `observer`.

## Consequences

- We can quantify how far the public observer is from “100% awareness” in a
  reproducible LAB fixture.
- Exact server positions remain useful for recall/position scoring without
  becoming an ESP feed or route input.
- A future public client capability must be added through a new versioned
  contract; it cannot silently change this evaluator's semantics.
