# ADR 0028: Operator-authored paths are non-executable knowledge

## Status

Accepted

## Context

Movement Engine needs an external, visual way to record a reviewed sequence of world waypoints. A recorded path must not silently become a hardcoded patrol or bypass the execution gateway.

## Decision

The external Movement Engine can create, edit and save `operator_authored_path` records. Points may be captured from the latest observed player position or placed on the currently rendered world map. Every point carries `operator_authored_external_tool` provenance.

Saved records always contain `execution_authority: false`. Loading or saving a path cannot arm input and cannot start navigation. A separate planner and execution-gateway decision is required before Predator may use the record as a navigation hint or reviewed route.

The editor uses a versioned JSON contract and atomic file replacement. Clearing an existing draft requires operator confirmation.

## Consequences

- Operator waypoints remain visible and editable outside the game client.
- Video capture can keep the in-game overlay disabled.
- Authored knowledge is reusable without coupling it to MaNGOS or a specific server runtime.
- Future route execution must preserve map compatibility, provenance and normal input authorization checks.
