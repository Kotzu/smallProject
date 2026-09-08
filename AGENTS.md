# Perfect Assassin — repository rules

## Language and terminology

- Documentation for the operator is Romanian; code, identifiers, paths, schemas and configuration keys stay English.
- Use `AI player`, `Rogue Predator`, `Predator`, `Champion` and `LAB clone`.
- Do not describe Predator as repetitive farming automation.

## Architectural invariants

1. `brain` consumes versioned domain contracts only. It must not import game, addon, server, database, web or input implementations.
2. `adapter` and `observer` are the only game-facing ingestion boundary.
3. Server ground truth may be used by LAB evaluators, never by Champion decision input.
4. `movement` and `brain` produce proposals; only an execution gateway may cause input.
5. `journal` is read-only. `supervisor` cannot mutate Stable or Champion directly.
6. LAB-derived skill may be promoted after tests; LAB events never become Champion identity memory.
7. Every fact used in a decision carries provenance, confidence and observation time.
8. Combat remains functional when Knowledge Broker, Journal or Supervisor is unavailable.
9. Patch-specific numeric IDs terminate inside compatibility adapters. Domain logic uses semantic IDs.
10. Every deployed change has a tested previous Stable artifact and rollback path.
11. Client integrity is absolute: no process memory read/write, DLL/code/packet injection, kernel/virtual-HID input or anti-detection mechanism.
12. Synthetic input is user-mode and deny-by-default; it requires an exact allowlisted emulator or specifically authorized PTR target, bounded approval and runtime arm. Public live targets remain denied.

## Dependency direction

```text
contracts/domain
      ^
      |
brain, movement, memory
      ^
      |
application orchestration
      ^
      |
adapter, observer, knowledge, journal, replay, lab, supervisor, execution
```

Dependencies may point inward, never outward. Cross-module communication uses explicit interfaces/events, not shared mutable globals.

## Change rules

- Add or update tests with every behavior change.
- Contract-breaking changes require a new major schema version and migration notes.
- New external capabilities default to denied until documented in a capability profile and tested.
- Record architectural choices in `docs/adr/`; do not bury durable decisions in commits or chat.
- Report evidence precisely as contract, replay, LAB integration or controlled-live verification.
- Never commit secrets, licensed addon contents, raw player-identifying exports, clips or runtime telemetry.

## Initial delivery order

Implement only the M0/M1 vertical slice first: fixture adapter -> observer -> provenance firewall -> append-only telemetry -> replay -> read-only Journal. Execution stays `OBSERVE_ONLY`.
