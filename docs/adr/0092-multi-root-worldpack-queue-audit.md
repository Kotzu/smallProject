# ADR-0092 — Audit pentru queue-uri WorldPack din rădăcini separate

## Context

Continentele și dungeon-urile pot fi construite în WorldPack-uri independente.
Un singur queue nu trebuie să pretindă că toate artefactele au aceeași rădăcină
de fișiere, iar Control Center nu trebuie să afișeze o hartă deja sigilată ca
`READY_FOR_EXTRACTION` doar pentru că apare într-o altă coadă.

## Decizie

`audit_world_map_registry.py` acceptă unul sau mai multe `--queue`. Pentru
același `map_id`, se păstrează recordul cu starea cea mai completă. Două recorduri
cu aceeași stare, dar cu valori funcționale diferite, sunt respinse fail-closed;
diferențele de cale rămân permise deoarece queue-urile pot avea rădăcini
WorldPack diferite. Auditul păstrează toate referințele în `queue_references`.

Această îmbinare este doar pentru audit read-only. Nu unește directoare, nu
mută artefacte și nu acordă `execution_authority`. `topographic_ready` și
`autonomous_ready` rămân calculate separat.

## Consecințe

- Un queue continental și unul de dungeon pot fi auditate împreună fără copierea
  navmesh-ului sau BVH-ului.
- O hartă este raportată `COMPLETE` numai dacă cel puțin un queue verificat o
  declară astfel.
- O semantică sau un graph parțial nu deschide autonomia; acesta rămâne un
  indicator de pregătire pentru lucrul offline.
