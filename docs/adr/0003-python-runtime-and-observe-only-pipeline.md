# ADR-0003 — Python runtime și pipeline M0/M1 observe-only

- Status: Accepted
- Date: 2026-08-22

## Context

Primul slice trebuie să valideze contracte JSON, provenance, capability gates, telemetry append-only și replay determinist fără să depindă de client, CMaNGOS, web, UI sau input. Runtime-ul trebuie să rămână ușor de testat pe Windows și suficient de portabil pentru adaptere viitoare.

## Decizie

M0/M1 folosește Python 3.11+ cu package layout `src/`, `jsonschema` Draft 2020-12 și testele standard `unittest`. Telemetry și replay folosesc JSON Lines UTF-8, câte un record versionat pe linie.

Pipeline-ul inițial este:

```text
synthetic fixture
  -> FixtureObservationSource
  -> compatibility mapping
  -> provenance/capability firewall
  -> ObservationEnvelope
  -> read-only decision stub
  -> append-only JSONL telemetry
  -> EncounterRecord
  -> deterministic replay
  -> Markdown Journal projection
```

`execution_mode` este fixat la `OBSERVE_ONLY`. Nu există package de input, hook de client, movement execution sau control CMaNGOS în acest slice.

## Consecințe

- Domain/application code nu importă API-uri de joc sau server.
- Fișierele JSONL sunt inspectabile, hash-uibile și ușor de migrat; nu sunt încă store-ul final de producție.
- `jsonschema` este singura dependență runtime M0/M1.
- Un adapter real TBC poate înlocui fixture adapterul fără schimbarea Brainului sau a contractelor.
- O eventuală schimbare de runtime cere ADR nou și probe de replay parity.
