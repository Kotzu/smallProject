# ADR-0093 — RazorfenKraul v2 ca profil topografic offline

## Context

RazorfenKraul v1 avea tile-uri problematice și un profil de dovadă vechi.
Am construit v2 într-o rădăcină WorldPack separată, cu builder-ul pinned și
cu verificare geometrică înainte de sigilare.

## Decizie

Registry-ul folosește profilul `world-pack-runtime:tbc243:razorfen:v2` pentru
map ID `47`. Profilul v2 este singurul profil topografic folosit de queue-ul
nou; v1 și profilul vechi rămân păstrate pentru rollback și comparație.
Pachetul este sigilat, verificabil și `execution_authority=false`, dar graful
de acces rămâne `PARTIAL_OBSERVED_COMPONENTS`, iar catalogul semantic lipsește.
Prin urmare Razorfen este `topographic_ready`, nu `autonomous_ready`.

## Consecințe

- Bake-ul și geometria pot fi testate fără client, server sau input.
- O hartă nouă nu primește autonomie doar pentru că navmesh-ul este complet.
- Promovarea ulterioară cere graph de acces complet, catalog semantic și
  regresie offline; abia apoi se poate cere o probă live bounded.
