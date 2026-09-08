# ADR-0079: Restore the reviewed camera before navigation

## Context

The TBC 2.4.3 client can retain a camera pitch left by a previous collision.
The navigation runner disabled Smart Pivot but deliberately preserved the
current pitch, so a new run could begin looking at the ceiling before the first
movement input.

## Decision

After the initial read-only combat check and `/stand`, navigation restores the
operator-reviewed native view slot 3 with `cameraPivot=0`, then applies the
navigation CVars. The same restoration remains at terminal stop. No vertical
mouse input or hardcoded pitch is introduced.

## Consequences

- A stale ceiling/floor view cannot be carried into the first movement frame.
- Operator framing comes from the reviewed saved slot, not from invented angles.
- The change is still OBSERVE_ONLY with no new execution authority.
