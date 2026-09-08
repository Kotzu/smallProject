# 06 — Milestones M0–M7

## M0 — Foundation

Repo, terminology/invariants, versioning, capability matrix, schemas, config, fixtures, test harness și rollback manifest. Exit: contractele sunt validate și un fixture interzis server-only este respins.

## M1 — Observer

Read-only addon/client intake, normalization și telemetry. Exit: putem reconstrui ce știa Predatorul la un timestamp; zero input/control.

## M2 — Predator Journal

HUD `PLAYER`/`STREAM_DEBUG`, memories, decisions, encounters, tactical world map, Journey diary și clip markers. Exit: un encounter fixture este explicat end-to-end.

## M3 — Movement

Route planning, Recast/Detour navmesh, uncertainty-aware pose fusion, PA-MPPI local trajectory control, facing/camera, dynamic crowd avoidance, obstacle recovery, corpse run și takeover modes. Exit: benchmark holdout trecut, traseu bounded + takeover instant + audit, întâi în fixture/replay/sandbox; server mmap este numai LAB oracle.

## M4 — Level 1 Intelligence

`select mob -> approach -> attack -> available ability -> loot -> recover -> continue`. Exit: benchmark-ul primelor 100 mobs, level-up, o moarte/corpse run și explicații complete.

## M5 — Knowledge Broker

Zygor route teacher, cache Wowhead, gated Armory/inspect și Gear Intelligence prin evaluator local + WoWSims adapter. VoiceOver/NarrativeCue oferă prezentare cinematică fără autoritate. Exit: level-up review alege obiectiv/talent/spell/upgrade cu provenance, fără web în combat loop, iar o alegere de reward este reproductibilă.

## M6 — Supervisor

Event-driven diagnosis, PatchManifest, replay regression, Candidate/Stable promotion și rollback. Începe `REVIEW_ONLY`; categorii autonome se aprobă ulterior. Exit: patch sigur promovat și rollback demonstrat.

## M7 — Predator Journey

Champion pornește la nivel 1 și continuă legitim până la 70 cu checkpoints, PvE/PvP, world learning, talents/gear, death/corpse run și biografie/voiceover opțional. Exit: level 70 cu identity chain intact și artifacts verificabile.

## Post-M7 — Predator Pack / Hunt Party (future)

După stabilizarea Championului individual, un squad de cinci AI players —
inițial patru Rogue Predators și un Druid healer capabil de stealth — poate
coordona hunting și o serie video multi-perspectivă. Fiecare actor rămâne izolat
ca identitate, memorie, client și Executor Worker; Pack Coordinatorul folosește
numai facts observabile legitim sau comunicate în joc. Capabilitatea are gates
proprii și nu modifică scope-ul v0.1 ori exit criteria M0–M7. Vezi
[ADR 0018](adr/0018-predator-pack-hunt-party.md).
