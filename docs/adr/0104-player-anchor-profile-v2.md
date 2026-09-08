# ADR-0104: Profil v2 pentru ancora vizibilă a Predatorului

## Context

În filmarea ShadowPlay nouă, Predatorul era vizibil, dar capul putea sta puțin
la stânga centrului ecranului. Profilul v1 cerea `head_center_x >= 0,50`, ceea
ce transforma unele cadre vizibile în `LOST`.

## Decision

Păstrăm profilul v1 neschimbat pentru rollback și adăugăm
`config/pose/player-actor-anchor-tbc243-predator-v2.json`. Singura lărgire
geometrică este axa orizontală a capului (`0,44..0,60`); cerința pentru cap,
suportul inferior, luminanță și confidence rămân neschimbate. Deadline-ul
bounded este documentat separat în ADR-0105. Runner-ul folosește v2 ca
`retained_video_candidate`; v2 nu este încă
`controlled_live_verified`.

## Evidence and limits

Auditul este păstrat în
`data/runtime/operator/live-video/player-actor-profile-v2-audit-me339.json`:
pe `38` de cadre selectate, aceeași logică cu v2 a găsit `17` cadre cu actor
vizibil, față de `5` cu v1; cadrele `28-38`, în care camera era în tavan, au
rămas `LOST` în ambele variante. Comparația a folosit un deadline de `100 ms`
doar ca să separe geometria profilului de timpul Python al diagnosticului;
matricea ulterioară a ales `12 ms` pentru runtime-ul bounded. Numărul este
dovadă offline din cadre selectate,
nu etichetare live completă. Orice lipsă persistentă încă eliberează controlul
prin poarta camerei și nu acordă autoritate de input.
