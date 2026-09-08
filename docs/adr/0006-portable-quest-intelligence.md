# ADR-0006 — Portable quest intelligence and narrative voice

- Status: Accepted
- Date: 2026-08-22
- Scope: PA-020 / M1 foundation for M4 and M5

## Context

Questing must work on a CMaNGOS TBC 2.4.3 LAB, a separate Anniversary adapter and future targets without making the Predator Brain dependent on emulator code. Zygor routes can diverge from emulator quest data. Playerbots can quest using server internals, but that knowledge is unavailable to a legitimate client and cannot be the production Brain contract.

The 2.4.3 client UI itself reads quest offers, narrative text, objective text, quest-log entries and objective progress through addon APIs. These are valid `client_observed` inputs.

## Decision

Quest intelligence is split into four ports:

1. `QuestObserver` — client truth: NPC dialog, offers, quest detail, quest log and objective progress.
2. `RouteTeacher` — advisory route steps from Zygor or another licensed guide provider.
3. `QuestPlanner` — portable Brain policy that reconciles observed truth, route suggestions, memory and current capability.
4. `QuestNarrator` — asynchronous personality/commentary generated only from observed quest text and known Journey context.

`QuestPlanner` owns the decision. A Zygor step is a hypothesis, never proof that a quest exists. If the client does not expose the expected offer/objective, the reconciler marks the step `blocked`, records adapter/realm drift and replans. Server DB and Playerbots may diagnose the LAB or generate candidate `lab_skill`, but their internal facts never enter a Champion observation.

The narrator has no execution authority and cannot add objectives, coordinates or rewards. Its output is tagged as interpretation, references the source observation and may be regenerated without altering decision history. The gameplay loop must continue if the narrator or cloud provider is unavailable.

## Provider roles

- Zygor: optional, licensed route teacher. Current Anniversary packages are not assumed compatible with the legacy `2.4.3.8606` client.
- Wowhead: cached research between encounters, with source timestamp; never the fast combat loop.
- Playerbots: LAB opponents, controlled party help and benchmark teacher; never a runtime dependency of Predator.
- CMaNGOS database: Supervisor diagnostics/evaluation only; forbidden as Brain observation.

## Consequences

- Emulator deviations become visible route-drift evidence instead of hidden failures.
- The same QuestPlanner can run with different client adapters and route providers.
- Predator can read and react to story text without letting generated prose control play.
- A cloud API key is optional and stored outside Git; local narration remains a valid provider.

## Rejected

- embedding the CMaNGOS Playerbots quest kernel into Predator;
- treating Zygor steps as authoritative state;
- reading emulator quest tables for decisions;
- sending narrative-model output directly to the execution gateway;
- installing an Anniversary addon build into 2.4.3 without compatibility evidence.

## Evidence

The 2.4.3 FrameXML uses quest events and APIs for quest detail, quest log and objective progress. Zygor's official product describes an in-game step viewer, waypoint arrow and progress detection. CMaNGOS Playerbots explicitly supplies open-world/PvE behavior and configurable autonomous questing; this makes it useful in LAB while also confirming its emulator coupling.

## Rollback

Disable individual knowledge providers. `QuestObserver` telemetry stays replayable, and the planner falls back to client-observed quest state without fabricating a route.
