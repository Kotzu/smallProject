# PA-017 — TBC 2.4.3 offline addon intake

## Result

`PASS — contract_tested + replay_tested + addon_static_checked`

## Implementat

- addon read-only `Interface 20400`, buffer bounded la 5.000 events;
- contract JSON Schema pentru exportul SavedVariables;
- parser restricted Lua data-only cu limite de bytes, tokens și nesting;
- adapter target-specific cu field allowlist și provenance `client_observed`;
- raw legacy combat log archive fără semantic decoding;
- comandă offline către pipeline-ul Observer/telemetry/replay/Journal;
- world zone/subzone adăugate semantic și gated prin capability profile.

## Verificare

- 26/26 teste unit/contract/integration: PASS;
- dependency check: PASS;
- Python compile check: PASS;
- malicious function expression: rejected;
- wrong SavedVariables root: rejected;
- forbidden addon execution/transport API scan: PASS;
- synthetic addon export: 5 observații, 5 decizii read-only, 1 encounter;
- raw combat events archived, not interpreted: 1;
- replay SHA-256: `99155c0f25341a3642c635ac403e6cacb0aa18321e1979263e08df70ab0e036d`;
- addon TOC SHA-256: `2a80d2841f2a279ddd1769c6e08a12909fe0a4fcead90775b4daeb2cb5d74eb2`;
- addon Lua SHA-256: `d487851e0341d886c93458ac4d5e857e51e51cb15ed8dec7f0abb49b9b5856cb`;
- execution mode: `OBSERVE_ONLY`.

## Nu este încă demonstrat

- addon încărcat de clientul local/repack;
- payload real produs de build `2.4.3.8606`;
- login/combat/loot bounded pe TBC LAB;
- `lab_integrated` sau `controlled_live_verified`;
- orice movement, cast, input ori AI control.

## Rollback anchor

Stable înainte de PA-017: Git commit `efc653c` (`Implement observe-only M0 M1 vertical slice`). PA-017 se promovează numai după testele de mai sus; deployment-ul client rămâne separat.
