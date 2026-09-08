# ADR-0105: Deadline bounded pentru detectorul ancorei Predatorului

## Context

Profilul v2 al ancorei vizibile este verificat pe cadre ShadowPlay păstrate.
La deadline-ul runtime de `8 ms`, cadrul `sample_0026.jpg` a produs un
`PlayerActorAnchorError`, deși silueta Predatorului este vizibilă. Un timeout
este tratat corect ca pierdere de dovadă, dar în client poate opri inutil o
observație bună.

## Decision

Păstrăm profilul v1 neschimbat pentru rollback și folosim în v2
`detector_deadline_ms=12.0`. Detectorul rămâne bounded și sub perioada de
control de `50 ms`; nu se relaxează pragurile de vizibilitate, confidence sau
integritatea camerei. Un cadru fără actor vizibil rămâne `LOST`, iar orice
eroare rămâne fail-closed.

## Evidence and limits

Matricea offline este în
`data/runtime/operator/live-video/player-actor-profile-runtime-deadline-audit-me341.json`.
Pe aceleași `38` de cadre, `8 ms` a avut un timeout (`sample_0026.jpg`), iar
`10 ms` și `12 ms` au avut aceleași rezultate deterministe (`17 VISIBLE`,
`21 LOST`) în câte trei treceri. Deadline-ul mai mare nu repară cadrele în
care camera arată peretele sau tavanul; acestea rămân pierdere reală de
vedere. Măsurarea este offline și nu promovează profilul la verificat live.
