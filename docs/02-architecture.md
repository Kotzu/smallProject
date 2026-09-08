# 02 — Arhitectură și module

```text
Game Target -> Compatibility Adapter -> Observer -> ObservationEnvelope
                                                   |
 Knowledge Broker + PvE/Gear Analysts -> World Model/Memory
                                                   |
                                  Predator Brain + Movement Brain
                                                   |
                                     DecisionRecord/ActionProposal
                                         |                 |
                                  Journal/HUD       Execution Gateway
                                         |
                              Telemetry + Replay + Supervisor
                                         |
                                  Candidate -> LAB -> Stable
```

## Limite de modul

- `adapter`: traduce IDs, events, capabilities și semantics pentru `tbc_243_lab`, `tbc_anniversary` sau alt target. Nu conține tactică.
- `observer`: normalizează numai ce a fost observat legitim și atașează provenance.
- `capture`: port read-only pentru frame metadata/pixel views și replay intake; implementările Windows rămân sidecars în `integrations`, iar raw pixels nu intră în telemetry.
- `brain`: selectează intent și acțiuni; nu citește API-uri de joc, DB, web sau input direct.
- `movement`: hierarchical route planning, Recast/Detour navmesh queries, PA-MPPI local trajectory control, facing/camera, distance, dynamic actor avoidance, obstacle/corpse recovery și takeover. Nu selectează spell-uri și nu citește server pathfinding.
- `memory`: separă `identity`, `opponent`, `world`, `mistake` și `skill` knowledge.
- `knowledge`: conectori și cache; nu poate executa acțiuni de combat.
- `analysis`: evaluatori puri și porturi către simulatoare locale; rezultatele sunt advisory, versionate și counterfactuale.
- `narrative`: context și cues pentru Journey/stream; nu selectează questuri sau acțiuni.
- `journal`: proiecție read-only a telemetry; modurile `PLAYER` și `STREAM_DEBUG`.
- `replay`: reproduce stări și testează counterfactuale fără a falsifica Champion history.
- `lab`: clone, opponent pools, arena/duel reset și experimente.
- `supervisor`: observă, diagnostichează, propune și promovează numai prin pipeline.

## Compatibility adapter contract

Fiecare adapter declară o matrice de capabilități (`available`, `restricted`, `unavailable`, `unknown`) pentru inspect, positional data, combat log, addons, route guidance și execution modes. Brainul folosește semantic IDs (`rogue.kick`, `state.stealthed`), nu patch-specific numeric IDs.

Targetul este ales prin fingerprint + capability probes, nu prin presupuneri după numele serverului. Un build necunoscut rămâne `OBSERVE_ONLY`/deny până când un adapter trece golden replays și controlled LAB probes. Detalii: [Perfect Assassin standalone](18-standalone-portability.md).

Execution capability nu autorizează singură input. Execution Gateway cere și un `ExecutionTargetAuthorization` activ: exact client hash, realm fingerprint, environment scope, restrictions, bounded approval și runtime arm. Emulatorul poate fi local/LAN/remote; PTR este separat de public live.

Movement folosește hărți semnate și surse cu provenance. CMaNGOS mmaps sunt permise numai evaluatorului LAB; contractul respinge rutele oracle în context Champion. Detalii: [Movement și pathfinding](20-movement-pathfinding.md).

Pose este un belief versionat cu uncertainty, freshness și provenance, nu o coordonată implicit adevărată. Stackul de producție și gate-ul comercial sunt în [ADR 0012](adr/0012-production-navigation-stack-and-buy-gate.md); criteriile de acceptare sunt în [Navigation Quality Benchmark](21-navigation-quality-benchmark.md).

Windows capture este o sursă de evidence, nu pose și nu execution. Boundary-ul, privacy rules și backends sunt în [ADR 0014](adr/0014-read-only-windows-capture-boundary.md) și [Windows capture și pose intake](25-windows-capture-and-pose-intake.md).

## Takeover modes

`FULL_AI | MOVEMENT_ONLY | COMBAT_ONLY | OBSERVE_ONLY | MANUAL`

Tranziția spre `MANUAL` trebuie să fie imediată, auditată și să anuleze comenzile pending. Default pentru M0–M2: `OBSERVE_ONLY`.
