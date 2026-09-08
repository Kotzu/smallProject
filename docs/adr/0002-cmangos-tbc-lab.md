# ADR-0002 — CMaNGOS TBC as the first LAB host

- Status: Accepted
- Date: 2026-08-22
- Owners: Project Manager / Maintainers

## Context

Predator needs repeatable PvE/PvP encounters, controllable resets and a populated private world before Anniversary portability can be proven. The host must not define Predator's domain model.

## Decision

Use official `cmangos/mangos-tbc`, `cmangos/tbc-db` and `cmangos/playerbots` as the initial 2.4.3 LAB. Playerbots provide opponents and controlled assistance only. Connect Predator later through the compatibility adapter and telemetry boundary. Keep upstream source, integration, build, runtime, database and extracted client data in separate directories.

## Alternatives considered

- Build directly for Anniversary first: unknown core and addon/API parity can block the entire project.
- Embed Predator into Playerbots from the start: reduces initial plumbing but couples decisions to 2.4.3 internals and server ground truth.
- Use only prebuilt binaries: faster, but weakens provenance, patchability and reproducibility.

## Consequences

We need a Windows C++/CMake/Boost/database toolchain and legitimate 2.4.3 client data. Compatibility remains explicit work, but Predator can progress against a stable host without pretending LAB parity is already proven.

## Verification

Record exact upstream SHAs, obtain green standard and Playerbots builds, then run a bounded login/world smoke test before any Predator integration.

