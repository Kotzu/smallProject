# ADR 0015 — Coordonate proprii prin API legitim și HUD vizibil

- Status: accepted
- Date: 2026-08-22
- Scope: PA-024B3, TBC 2.4.3 LAB adapter și adaptoare viitoare

## Context

Movement-ul de calitate cere localizare repetabilă. Numai analiza minimapului este sensibilă la skin, UI scale, occlusion și rotația hărții; SavedVariables este potrivit pentru audit/replay, dar nu pentru un control loop live. Server DB/mmaps poate evalua LAB clone-ul, însă nu poate furniza Championului coordonate ori rute.

## Decizie

Pentru orice target care expune legitim poziția propriului caracter, sursa primară este `ClientAdapter.self_map_position`. Pe TBC 2.4.3, addonul citește exclusiv `GetPlayerMapPosition("player")` după stabilirea contextului curent de hartă cu API-ul public al clientului.

Transportul live este un HUD deliberat vizibil și etichetat `PA OBSERVER`. El conține:

- text lizibil cu X/Y, map indices și sequence;
- patru fiducials colorați pentru localizare și calibrare la translație/UI scale;
- un grid 16×6, 96 biți, MSB-first;
- packet v1: `magic`, `version`, `flags`, `sequence`, `x_u16`, `y_u16`, `continent_u8`, `zone_u8`, `crc16`;
- CRC-16/CCITT-FALSE, polynomial `0x1021`, init `0xFFFF`.

Golden vector v1 pentru cross-language parity:

```text
sequence=23 flags=available+map_ready x=0.42125 y=0.61875 continent=1 zone=14
a50103176bd79e66010ea064
```

Sidecar-ul găsește geometria din fiducials, reconstruiește packetul și validează magic/version/reserved bits/CRC înainte să publice coordonate. `execution_authority=false` rămâne obligatoriu.

## Fail-closed

- API absent, hartă deschisă, context invalid sau poziție `(0,0)`: `DEGRADED`, fără coordonate;
- fiducials absenți: `NOT_FOUND`;
- packet, magic, version sau CRC invalid: `INVALID`;
- build/profile mismatch: captura este respinsă;
- orice stare în afară de `VALID` interzice folosirea observației pentru movement;
- HUD-ul nu exportă pozițiile altor unități și nu acceptă câmpuri server-side.

## Rolul minimap vision

Detectorul de minimap PA-024B2b rămâne independent, ca verificare de consistență, heading/landmark provider și fallback cu uncertainty. Nu este sursa primară de coordonate cât timp API-ul legitim și HUD-ul v1 sunt disponibile.

## Portabilitate

Brain-ul consumă contractul semantic `self_map_position`, nu API-ul WoW ori layoutul HUD. Fiecare ClientAdapter poate oferi propriul provider legitim; targeturile fără coordonate se degradează către visual localization/dead reckoning și nu primesc o implementare inventată.

## Gate de promovare

Rasterul real, freshness, două UI scales/dimensiuni, world map open/close,
relog, corupere/replay și parity offline au trecut PA-024B3b pe addonul exact
`0.3.5`, în matricea inițială, un relaunch/relog independent și un al treilea
current-source resmoke după hardening. PA-024B3b este închis pentru exact-version
smoke; profilul rămâne prudent `synthetic_verified` până la PA-024B3c: o
tranziție reală de zonă pe un LAB clone separat de Champion Journey. Până
atunci observația nu alimentează actuatorul.

## Migrare contract 0.1 → 2.0

v1.0 a făcut obligatorii `decision_context`, timpul capturii/observației,
freshness/expiry, originea capturii și identitatea/hash-ul profilului. v2.0
adaugă `actor_binding` neschimbat din captura autorizată și
`authorization_sha256`, apoi le include în observația individuală și gate-ul
multi-frame. Hash-ul fixează bytes exacți ai autorizației validate, astfel
încât un ID reutilizat sau două clone să nu poată fi amestecate. Numele
personajului rămâne `expected_character_name` cu assurance configurată, nu fapt
observat. Replay-urile vechi trebuie regenerate; nu există conversie implicită.
Detectorul brut nu poate emite `champion_eligible`; promovarea către un contract
Champion aparține unui gate separat, după PA-024B3c și verificarea client-visible
a actorului.
