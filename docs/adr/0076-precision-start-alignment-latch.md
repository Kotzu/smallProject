# ADR-0076: Precision-start alignment is one-shot per corridor

## Context

The v43 live trace entered a valid Crypt egress corridor, aligned with RMB,
and then re-entered the same stationary alignment rule after noisy heading
observations. W was released repeatedly until the fail-closed progress limit
was reached. The issue was controller state, not a missing route waypoint.

## Decision

For a corridor whose client-local awareness says WMO/closed overhead or whose
validated path contains a doodad detour, the continuous follower may hold only
RMB while the initial tangent error is large. Once the error enters the small
resume window, the follower marks that alignment complete for the current
corridor signature. Later visual noise cannot restart the same initial gate.
A new corridor signature resets the state and may request a new alignment.

The decision uses only corridor geometry and client-local awareness. It does
not contain zone names, coordinates, executable operator waypoints, server
truth, or combat authority.

## Evidence and limits

- The synthetic regression covers pivot, release, and a later noisy sample.
- The full offline suite is `1349/1349`; the v44 steering report has
  `1,000/1,000` quality passes for each of six scenarios.
- The v43 live trace remains a failed bounded run; this ADR does not claim
  that the patch is live-certified. A future live check must stay bounded and
  keep combat handoff disabled.
