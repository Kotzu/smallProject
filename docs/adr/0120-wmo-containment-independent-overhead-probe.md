# ADR 0120: WMO containment is independent of the short overhead probe

## Status

Accepted.

## Context

The local awareness worker has two different observations:

- the resolved nav polygon's physical surface and its exact 3D containment in
  an indexed WMO;
- a short vertical line-of-sight probe used for ceiling and camera clearance.

The vertical probe is bounded to 12 yards. A tall dungeon room can therefore
return `overhead_clear=true` even though the actor is standing on a WMO floor.
Treating that result as proof that the actor is outside the WMO caused every
Razorfen Downs probe to be rejected even when the WMO surface and immutable
3D bounds agreed.

## Decision

`build_local_environment_awareness` classifies a pose as
`INSIDE_STATIC_WMO` when both of these independent facts are present:

1. the resolved point is inside an indexed WMO's 3D bounds; and
2. the client nav polygon reports the `wmo` physical surface.

`overhead_clear` remains in the observation and continues to control ceiling,
camera, and egress semantics. It is not a room-height measurement and cannot
erase a confirmed WMO containment fact. A WMO surface without indexed
containment remains `WMO_TRANSITION_OR_UNRESOLVED`, so an AABB alone still
cannot claim an interior.

## Evidence

The offline Razorfen Downs scan was repeated in a new output directory after
this change. It verified `39/39` probes with `8` accepted WMO observations,
`31` expected open-ground observations, and `0` probe errors. The resulting
candidate graph contains `81` boundary chains, `0` access openings, and keeps
`coverage_state=PARTIAL_OBSERVED_COMPONENTS` and `execution_authority=false`.
The old `COMPLETE_NO_CONFIRMED_WMO` scan remains preserved for rollback and
comparison.

## Consequences

- Tall WMO rooms are no longer falsely rejected by a short ceiling probe.
- Ceiling visibility is still explicit and available to the movement safety
  gates; this change does not grant execution authority or create a route.
- Candidate geometry remains read-only and is not promoted to autonomous use
  without semantic and controlled verification.
