# ADR 0051 — Adaptive trajectory steering for narrow turns

## Context

The deterministic geometric follower is the preferred controller on ordinary
roads and open ground. Offline replay showed that a very narrow portal followed
by a sharp turn can require more anticipation than that follower can safely
provide. Applying MPPI to every corridor is not acceptable: on wider S-gates it
adds unnecessary plan churn and can increase cross-track error.

## Decision

Add `AdaptiveTrajectorySteeringController` as an explicit runtime option. It
selects MPPI only when the current client corridor is geometry-aware, has a
portal no wider than 3.5 yards, and contains a turn of at least 1.35 radians in
the first 12 yards. Otherwise it uses `PredictiveSteeringController` with the
same client geometry and closed-loop gates as the existing geometric runtime.

The decision is derived from the current corridor and is latched for that
corridor signature. It contains no map name, coordinate, waypoint, or emulator
rule. MPPI startup, stale plans, partial frontiers, and planner errors fall back
to the deterministic follower; they never become movement authority.

### ME-121 amendment

A narrow portal can also be the dangerous part of a steep stair/WMO or
clearance-inset transition even when the funnel turn in the first 12 yards is
modest. Such a corridor now selects MPPI when its minimum portal is at most
3.5 yards and the attached client geometry records either a clearance inset or
a polygon slope of at least 30 degrees. The rule remains geometry-only and is
latched with the same corridor signature.

The adaptive runtime profile uses `yaw_smoothness_weight=6.0` and
`replan_interval_ticks=3`. The Control Center launch uses the validated
`256 x 56` MPPI shape; direct `pa_mppi_v1` keeps its independent baseline
configuration until it has its own corpus-wide promotion evidence.

The runtime constructor must pass the CLI `mppi_batch_size` and
`mppi_time_steps` values into both adaptive and direct PA-MPPI controllers.
The effective values are emitted in telemetry so a UI-launched run cannot
silently use constructor defaults different from the reviewed profile.

Ordinary road steering keeps the deterministic follower. After a small camera
correction it uses a bounded 16-tick settle window to suppress only small
counter-pulses; a real error above 0.40 rad, precision corridor, hard recenter
or safety pivot remains authoritative immediately.

## Verification

- Adaptive benchmark v13: 6,000/6,000 trials passed quality without collision
  across six classes (1,000 per class) using `128 x 24`.
- Narrow hairpin replay: adaptive steering passed 1,000/1,000 quality trials.
- Wide S-gate replay: deterministic steering remains the preferred path.
- Selector unit tests cover narrow sharp turns, wide turns, missing geometry,
  narrow steep/clearance transitions, safe fallback and effective runtime
  parameter wiring.
- Razorfen Kraul v3 p1 interior holdout: the geometry-only selector chooses
  MPPI and the reviewed adaptive profile passes `1,000/1,000` risk trials,
  with zero collisions, maximum cross-track error `1.591 yd` and at most four
  steering-sign changes. This is offline evidence; it does not authorize a
  live run by itself.
- The bounded LAB supervisor reached both Deathknell and Brill on generated
  semantic routes. In the final arrived cycle
  `f6fa485d-bfa0-4ea6-92a8-a196359ea2f3`, the quality evaluator reports zero
  rapid reversals, zero pivots, zero observation gaps and `passed=true`.
- A subsequent bounded Crypt→Brill holdout started inside the live WMO crypt,
  resolved route-verified egress portals, and reached Brill with zero combat
  handoffs. Its arrived cycle `b50bd331-52b0-4d5c-bf9e-002dcb07b76d` passed
  quality with zero observation gaps, maximum gap 0.167324 s and zero pivots.
- The immediately preceding budget cycle retains one 0.3008658 s observation
  interval and is not relabelled as a quality pass. This is capture evidence,
  not a reason to weaken the 300 ms gate.
