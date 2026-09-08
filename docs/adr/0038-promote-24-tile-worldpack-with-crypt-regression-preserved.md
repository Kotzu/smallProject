# ADR 0038: Promovarea WorldPack-ului de 24 tile-uri cu regresia criptei păstrată

## Status

Accepted.

## Context

Profilul `tbc243-tirisfal-silverpine-v1` conținea 24 de tile-uri și extindea
coverage-ul geografic față de cele 8 tile-uri ale profilului stabil. Totuși,
validarea lui direct din WorldPack a trecut doar patru dintre cele cinci cazuri:
startul canonic din cripta Deathknell s-a oprit cu
`partial_local_navmesh_corridor`. Cele opt tile-uri comune aveau hash-uri și
geometrie mai vechi decât corecția WMO din
`tbc243-human-road-corridor-v6-worldpack-v2`.

Mărimea coverage-ului nu justifică o regresie de interior. Profilul v1 nu este
promovat în runtime.

## Decizie

Profilul `tbc243-tirisfal-silverpine-v2` păstrează:

- cele 16 tile-uri suplimentare ale candidatului extins;
- cele 8 tile-uri corectate și deja validate ale profilului stabil;
- `.map`, BVH și semanticile celor 24 de tile-uri din setul extins;
- un catalog, WorldPack, runtime profile și hash aggregate complet noi.

Artefactele nu sunt selectate după numele zonei. Suprapunerea este determinată
prin coordonatele ADT comune, iar întregul rezultat este rehash-uit și sigilat.
WorldPack-ul rezultat are ID
`wow.tbc.2.4.3.8606.tirisfal-silverpine-worldpack-v2`, 602 artefacte și SHA-256
aggregate `4ceee9a44381f027972c4e4e528569330556858631899caaea024c69d134bdb2`.

UI-ul extern și runnerul folosesc v2 ca default pentru pornirile noi. Un proces
UI deja pornit nu este restartat automat și continuă cu asseturile pe care le-a
verificat la startup.

## Dovezi controlate

Validarea semantică a fost rulată mai întâi pe setul loose și apoi repetată
direct din WorldPack-ul sigilat. Ambele execuții au trecut:

1. start canonic în criptă → Brill;
2. Deathknell → Brill;
3. Brill → Deathknell;
4. Brill → south-road holdout;
5. hill fixture → `RESET_REQUIRED` fail-closed.

Gate-ul live v2 este legat de profil, WorldPack, rezultatul validării și workerul
`pa_nav_probe-v26`; o modificare a oricăruia invalidează Start.

Indexul static rezultat conține 13.059 structuri: 197 WMO-uri și 12.862 doodads.
121 WMO-uri intersectează coverage-ul nav actual și primesc 3.324 seed-uri în
coada generică de access scan; 76 rămân explicit deferred. Proba criptei pe noul
pack confirmă o structură WMO containing, 128 boundary edges, 11 boundary chains,
15 egress edges și 4 deschideri conectate. Topologia rămâne parțială.

Scanarea resumabilă ulterioară a terminat toate cele 27 de seed-uri ale criptei:
5 au fost confirmate în WMO, iar agregarea multi-observation a produs 13 boundary
chains și aceleași 4 deschideri geometrice unice. Scanarea generică a continuat
până la 3.324/3.324 seed-uri și 121/121 structuri eligibile, fără erori de worker;
snapshotul final include 66 structuri confirmate, 896 boundary chains și 240
deschideri. Detaliile sunt în ADR 0039.

## Consecințe

- Coverage-ul default crește de la 8 la 24 de tile-uri fără să pierdem ieșirea
  din criptă.
- `tirisfal-silverpine-v1` rămâne evidence de regresie, nu profil activ.
- 24 de tile-uri sunt încă coverage parțial pentru Azeroth; nu declarăm suport
  complet pentru continent sau client.
- Următoarele extinderi trebuie să păstreze toate cazurile existente și să
  adauge probe pentru noile regiuni înainte de promovare.
