# Sonar geometric: suprafețe verticale alternative

Status: extensie de observație compilată separat și verificată offline pe
geometria reală. Nu este instalată în locul v34, afișată în CC sau dovadă de
etaj al personajului. Goal-ul spațial complet rămâne activ.

## Implementare

Workerul `--awareness-server` adaugă `vertical_candidates`: versiune 1, sursa
`CLIENT_ASSET_HEIGHT_QUERY`, lista înălțimilor și suprafața aleasă înaintea
proiecției Detour. Reutilizează interogarea existentă, fără altă încărcare de
hartă sau alte raze. Lista rămâne explicit neexhaustivă chiar cu un candidat.
Biblioteca verificată refuză un buffer insuficient; limita locală este 64.

Adaptorul păstrează lista în `PersistentAwarenessSample`, separat de Z rezolvat
și de awareness. Worker vechi → `None`, nu etaj presupus. Date invalide sau
surse diferite sunt refuzate. Publicarea păstrează `observed_actor_z=null`,
`confirmed_floor_id=null`, `execution_authority=false`.

Nu se schimbă selecția, plannerul/controllerul, addonul, camera sau anti-AFK.

## Integrare offline cu asset-uri reale

WorldPack: `E:/WoWserver/PerfectAssassin-Runtime/worldpacks/tbc243-azeroth-full-v3`.

| XY | Z sugerat | Înălțimi găsite | Z proiectat Detour |
| --- | --- | --- | --- |
| 1676,369629 / 1677,466919 | 121,797379 | 121,670326; 138,451950 | 121,797379 |
| același XY | 138,729095 | aceleași două | 138,729095 |
| 1809,58 / 1592,79 | 100 | 98,474403 | 98,876709 |

La XY identic, hint-ul selectează niveluri diferite. Diferența dintre height
query și proiecția Detour este păstrată, nu tratată ca două măsurători ale
personajului. Nicio comandă nu a fost trimisă jocului.

Toate câmpurile vechi coincid exact cu `pa-nav-clearance-test` pentru cele
trei cereri. Nu este echivalență globală cu v34. Sursa repo păstrează istoricul
candidatului respins: build-ul nou este pentru observație, nu înlocuiește
workerul de mers și nu este selectat de niciun gate.

Build separat: `data/runtime/native-build/pa-nav-spatial-observer/Debug/pa_nav_probe.exe`.
SHA256: `ABB4A3A24D6DA8F6E300FE2E9734BC105AB0E5E1BE2CF701A9B0899FDF4D50F8`.
Compilat VS17 2022 x64 Debug cu NAMIGATOR_ROOT și NAMIGATOR_BUILD_ROOT din
configurația v34 existentă, fără modificări în dependențe.

**365 PASS în 12,43 s**: vertical_candidates, movement_engine, world_pack_viewer,
spatial_trace_replay, spatial_context, location_hud, stay_online_guard.
Testele acoperă alternative/sursă/limite/numeric, lipsa confirmării etajului
și ingestia în mostra de awareness. Ruff pe fișierele noi și diff-check trec.

## Continuare și rollback

Urmează legarea mostrei de WorldPack/client/poziție și timpul original al
interogării, apoi afișarea asincronă a alternativelor și estimării în CC.
Un cache geometric poate rămâne util, fără a deveni observație nouă a actorului.
Limitele/direcțiile, trecerile și obstacolele mobile rămân în scope-ul goal-ului.
Nicio probă de mers nouă. Rollback: revert dedicat; executabilul este izolat.
