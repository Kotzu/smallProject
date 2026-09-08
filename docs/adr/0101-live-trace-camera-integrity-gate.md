# ADR-0101: Camera-integrity gate for live steering traces

## Context

Offline replays can use a valid pose even when the live camera no longer shows
the player. A route may therefore look correct in replay while the real client
is looking at a wall or the sky. The runtime already releases input when its
screen-space player anchor is missing or below the reviewed confidence floor,
but old traces did not prove that this gate stayed healthy on every frame.

## Decision

`LiveSteeringTraceQuality` records three diagnostic values for each continuous
frame: the camera-integrity state, its confidence, and the existing body/camera
heading fields. The optional strict flag `--require-camera-integrity` accepts a
frame only when `camera_integrity_state` is `VISIBLE` and confidence is at least
`0.55` and at most `1.0`. Missing, `UNKNOWN`, `LOST`, low-confidence, or
malformed evidence is incomplete and fails the strict report with
`missing_camera_integrity`.

The facing gate also accepts only the two sources emitted by the current
runtime (`COORDINATE_HUD_EXACT` and `MINIMAP_VISION_FALLBACK`) and requires a
finite raw body yaw. The recorded body/camera delta must match the wrapped
values within `0.001` radian. A familiar label or a hand-written delta cannot
turn an incomplete trace into a pass.

The read-only heading replay uses the same source allowlist and raw-yaw check,
so its `client_facing_source_complete` result cannot disagree with the strict
trace evaluator merely because a label was present.

The default diagnostic mode remains compatible with historical traces. This
gate does not infer camera pitch, read client memory, or grant input authority;
it mirrors the visible actor-anchor safety rule already used by the runtime.

## Consequences

- A future bounded live trace cannot be called complete while the player anchor
  disappears from the captured client view.
- The old ME-328 trace is correctly marked incomplete because it predates the
  camera-integrity fields; it is not silently upgraded by replay.
- No live input, addon reload, or client modification is required to run the
  evaluator.
