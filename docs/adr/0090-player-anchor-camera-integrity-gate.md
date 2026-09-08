# ADR-0090 — Player-anchor gate for camera integrity

## Status

Accepted for offline validation; the TBC 2.4.3 profile is not yet promoted as
controlled-live verified.

## Context

The CRC coordinate HUD can remain valid after a third-person camera is pressed
against a wall or ceiling. In that state the Movement Engine still knows X/Y,
but the player is no longer visible in the game view. Continuing to lease W or
RMB would hide a camera failure behind apparently good position telemetry.

## Decision

1. Add a read-only scene-vision adapter that looks for a bounded, central
   player-anchor pattern (head plus lower body support). It returns only
   screen-space evidence, confidence and provenance; it never returns world
   coordinates or execution authority.
2. The navigation pose source publishes this evidence inside the validated
   coordinate observation as `camera_integrity`.
3. Navigation arms the gate only after the saved camera view and navigation
   camera preferences have settled. Once armed, missing, `LOST` or low-confidence
   actor evidence causes immediate release and a fail-closed terminal result.
4. Navigation frames are level-only: vertical mouse impulse and vertical mouse
   velocity must both be zero. The bounded vertical pitch recovery remains a
   separate operator presentation action and is never part of route following.
5. Read-only viewers and manual recording may observe the evidence without
   enabling the movement gate. The current profile is explicitly
   `retained_video_candidate` and must be recalibrated if model, gear, UI scale
   or camera composition changes.

## Evidence

The retained ME-306 frames classify `frame-0s` and `frame-30s` as `VISIBLE`,
and `frame-60s`, `frame-90s`, `frame-120s`, `frame-150s` and `frame-170s` as
`LOST`. This matches the visible recording: Predator is present at the start,
then the view contains only the Crypt ceiling/wall. The result is an offline
replay of an existing recording, not a new live run.

## Limits

This gate does not claim that the camera can be autonomously repaired in every
scene. It proves only that control will stop when the current calibrated actor
anchor disappears, while all input, server truth, memory access and injection
remain outside the adapter.
