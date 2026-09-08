# ADR-0077: Restore the saved camera composition after autonomous movement

## Context

The v45 live video kept a normal view while Predator moved, but a checkpoint
after the fail-closed stop showed the camera aimed at the floor/ceiling. The
trace contains no vertical mouse input. The final WMO profile changed client
camera settings without restoring the operator's saved view.

## Decision

After all movement input is released, the navigation runner restores native
view slot 3 with `cameraPivot=0`. It does this for fail-closed and arrived
terminal states, but skips the restore after a manual takeover so the operator
keeps control of the camera. A failed restore is recorded and does not turn a
failed route into a success.

## Limits

This is a presentation recovery only. It does not add waypoints, infer server
coordinates, or claim that Crypt→Brill is live-successful. The next live run
must still pass the bounded route gate with combat handoff disabled.
