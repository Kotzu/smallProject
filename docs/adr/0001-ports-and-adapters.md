# ADR-0001 — Ports and adapters around the Predator domain

- Status: Accepted
- Date: 2026-08-22
- Owners: Project Manager / Maintainers

## Context

Predator must transfer between a TBC 2.4.3 LAB, Anniversary and possible future targets without teaching the Brain patch-specific APIs or server-only information.

## Decision

Domain and application code depend on semantic, versioned contracts. All game APIs, numeric IDs, addon events, execution mechanisms and external knowledge sources live behind ports implemented by outer adapters. Unknown capabilities are denied. Brain and Movement return proposals; the execution boundary applies target policy.

## Alternatives considered

- Direct core integration: faster initially, but couples policy to one emulator and exposes ground truth.
- One shared service layer with target checks: tends to spread patch conditionals and weakens test isolation.

## Consequences

Initial vertical slices require more explicit contracts and fixtures. In return, decision policy is replayable, capability-limited and portable, with each target independently testable.

## Verification

M0 requires the same domain decision fixture to run through two adapter profiles and requires a negative test proving that a server-only fact is rejected before reaching Brain.

