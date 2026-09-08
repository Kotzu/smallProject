# 10 — Repository conventions

## Target layout as implementation begins

```text
src/
├── domain/         # entities, value objects, semantic IDs; no I/O
├── application/    # use cases and ports
├── adapter/        # target-specific game compatibility
├── observer/       # raw events to permitted observations
├── brain/          # intent and action proposal policy
├── movement/       # route/navmesh/steering/recovery proposals; no input
├── memory/         # isolated memory stores and decay
├── knowledge/      # Zygor/Wowhead/Armory ports and cache
├── analysis/       # gear evaluator + simulator ports; no game I/O
├── narrative/      # Journey context/cues; no planning authority
├── execution/      # mode gates and target-specific output
├── journal/        # read models and HUD
├── replay/         # deterministic reconstruction
├── lab/            # clones, opponents and evaluators
└── supervisor/     # candidate lifecycle and promotion
```

Folders are introduced only when the first real type belongs there. Avoid generic `utils`, `helpers`, `common` and cyclic service layers. Shared code must have one clear domain owner.

## Naming

- Domain types: `ObservationEnvelope`, `DecisionRecord`, `EncounterRecord`, `MemoryRecord`, `PatchManifest`.
- Interfaces/ports describe capability, not implementation: `ObservationSource`, `TelemetrySink`, `KnowledgeCache`.
- Adapter implementations include target: `Tbc243ObservationSource`.
- External analyzer implementations include engine: `WowSimsTbcPveSimulator`.
- Events use past tense: `EncounterStarted`, `LevelReached`, `ActionProposed`.
- Commands use imperative form: `RecordObservation`, `BuildReplay`, `PromoteCandidate`.

## Configuration

Configuration is validated at startup, contains no secrets and is split by responsibility. Defaults are safe: unavailable external services, deny unknown capabilities and `OBSERVE_ONLY` execution.

## Commits and versions

- Small commits that leave contract tests green.
- Brain artifacts, adapters, schemas and configs have explicit versions/hashes in telemetry.
- A release tag identifies one reproducible set of these artifacts.

## Data placement

- `data/fixtures`: reviewed synthetic inputs committed to Git.
- `data/runtime`: local mutable state, ignored.
- `data/telemetry`, `data/replays`, `data/clips`: ignored, with retention configured outside domain logic.
- Third-party source/audio packages nu intră în Git; versiunea, upstream URL, license și hash sunt păstrate într-un manifest reproducibil.
