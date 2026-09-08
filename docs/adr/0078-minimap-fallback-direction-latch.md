# ADR 0078 — Conservative minimap fallback direction

## Context

The TBC 2.4.3 client does not expose a usable facing value in the current
observer path. The runner therefore uses the client-visible neutral minimap
marker as a fallback. The marker is rendered from a very small model, and its
measured major axis can jump to the opposite end between two frames.

In live v45, the fusion code resolved that jump against the mouse prediction.
The controller then believed the actor was aligned with the Crypt egress and
held `W`, while the observed world displacement went in the opposite direction.
The route stopped fail-closed later; no combat handoff was used.

## Decision

Use the minimap fallback only to obtain the first visible heading. Once a
mouse-integrated heading exists, keep that heading instead of allowing a
single minimap frame to select the opposite axis end. When a displacement
chord is available, accept it as a correction only if the visible minimap
heading agrees with that chord within `0.75` radians. A disagreeing chord stays
diagnostic and does not replace the integrated heading.

The exact coordinate-HUD facing path remains authoritative when available.
This rule is generic: it contains no map, zone, destination, coordinate or
waypoint data. It does not add input authority and does not change the
`OBSERVE_ONLY`/fail-closed boundaries.

## Verification

- Targeted heading and navigation tests cover initial fallback, an opposite
  axis jump, an agreeing displacement chord, and a disagreeing slide chord.
- The full offline suite must remain green before another bounded live route.
- The next live attempt, if authorised, remains camera-only navigation with
  combat handoff disabled; this ADR does not certify a route.
