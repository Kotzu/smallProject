# ADR 0011 — Navigație ierarhică portabilă și movement fără server GPS

- Status: accepted
- Date: 2026-08-22
- Amended: 2026-08-23 — Experience Map și fog of experience

## Context

Predator trebuie să meargă prin open world, quest routes, PvP, corpse runs și ulterior dungeons pe clienți/servere diferite. CMaNGOS are mmaps/pathfinding, dar folosirea rutelor sau pozițiilor interne ale serverului în decizia Championului ar încălca information boundary și ar lega produsul de emulator.

## Decizie

Movement este împărțit în patru niveluri portabile:

1. `Route Planner`: obiective semantice între zone/POI/quest steps.
2. `Global Path Planner`: tiled navmesh; Recast construiește mesh-ul, Detour face path query și smoothing.
3. `Local Steering`: heading, strafe, obstacle avoidance, dynamic replan și distance control din observații curente.
4. `Recovery Controller`: stuck, fall, wrong floor, combat interruption, corpse run și manual takeover.

Brain-ul și Movement Brain emit numai `MovementGoal`, `PathProposal` și ulterior `MovementIntent`. Numai Execution Gateway poate produce input.

Actuatorul universal minim folosește acțiuni semantice umane:

`move.forward | move.backward | move.strafe_left | move.strafe_right | turn.left | turn.right | jump | interact`

Backend-ul implicit este input keyboard/mouse aprobat și auditat. Click-to-move poate exista ca adapter separat dacă targetul îl expune legitim. Nu folosim packet injection, memory reading/writing, teleport sau comenzi server pentru Champion.

## Pose și surse de hartă

Pose provider este ales prin capability negotiation:

- coordonate client-visible, dacă API-ul targetului le expune legitim;
- minimap/vision landmarks și world observations;
- dead reckoning corectat periodic de observații;
- semantic anchors când poziția metrică nu este disponibilă.

Nav sources permise pentru Champion sunt `client_asset_derived`, `client_observed`, `champion_learned`, `external_research` și `route_teacher`, fiecare cu map signature/provenance. Un mismatch de build/map invalidează tile-ul.

`lab_oracle` (CMaNGOS mmaps/DB/pathfinder) poate calcula ground truth pentru collision, reachability și optimality evaluation. Nu poate genera waypoint-uri consumate de Champion și nu intră în Champion world memory.

## Experience Map și fog of experience

Predatorul păstrează trei straturi cu provenance și politici de expirare diferite:

1. `StaticGeometryMap`: terrain, holes, liquids, WMO/M2 și navigability derivate
   din asseturile exacte ale clientului. Un tile poate fi cunoscut geometric, dar
   rămâne `unverified` până când o observație sau o traversare îl confirmă.
2. `ExperienceMap`: celule/coridoare vizitate, `first_seen`, `last_seen`, număr
   de traversări, timp observat, succes, stuck/fall/death/aggro/stealth heat și
   confidence. Acest strat persistă per build/map signature și per actor memory
   namespace.
3. `DynamicTacticalMap`: mobi, playeri, crowds, uși, obstacole și pericole
   observate. Fiecare fapt are TTL; după expirare devine necunoscut, nu adevăr
   permanent.

Acesta este un `fog of experience`, nu orbire artificială asupra asseturilor pe
care clientul le deține. Geometria statică poate informa planificarea, însă
costurile dinamice și familiaritatea se câștigă numai prin observații legitime.
Zygor este `route_teacher`, iar Wowhead este Knowledge Broker; recomandările lor
nu confirmă că un corridor este liber acum.

Memoria Championului nu primește evenimente LAB. Într-un Predator Pack, actorii
pot partaja numai observații comunicate prin blackboard-ul versionat, cu sursă,
confidence și TTL; nu își unifică automat memories.

## Consecințe

- Nucleul este același pe orice target, dar perception/execution/geometry adapters trebuie verificate per client.
- Lipsa coordonatelor exacte reduce confidence și viteza; nu activează automat server knowledge.
- Dungeon routes sunt scenario packs peste același planner, nu scripturi care ocolesc movement safety.
- Traseele familiare pot deveni mai fluide, dar un fapt dinamic expirat obligă
  re-observare/replan, nu presupunere.
- Prima implementare este un A* determinist pur peste grid fixtures. Recast/Detour intră după contract/golden replay, înainte de movement live.
