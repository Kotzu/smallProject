# 05 — Predator Journal, HUD și replay

## Layout-uri

- `PLAYER`: target, threat, intent, cooldown summary, route și takeover state.
- `STREAM_DEBUG`: plus facts/sources/confidence, candidate scores, opponent/world memory, decision reason și brain version.

## Journal panels

`Live`, `Target`, `Decision`, `Memory`, `World`, `Journey`, `Weaknesses`, `Supervisor`.

World este o hartă tactică învățată: patrol observations, dangerous roads, LOS breaks, choke points, escape spots, traffic, guard risk, leash estimates și tactical recipes. Nicio rută server-side nu este expusă Brainului.

Opponent memory păstrează observații cu confidence: gear/spec observat legitim, trinket timing, fake casts, chase tendency, defensive timing și alte obiceiuri. Datele se degradează în timp.

## Replay și ShadowPlay

Fiecare encounter poate produce un marker pentru rolling buffer și referințe la clip. Evenimente: kill/death, near-death, firsts, 1vN, escape, environmental play, discovery și anomaly. Implementarea concretă ShadowPlay rămâne adapter separat; v0.1 definește numai hook-ul.

Replay bundle include observations, decisions, versions, timestamps și clip refs. LAB poate rula ghost fights/counterfactuals; rezultatele sunt evidență de skill, nu Champion identity.

## Level diary

La fiecare level: PvE/PvP encounters, kills/deaths, adversari recunoscuți, locuri tactice, tactic nou, slăbiciune curentă, talent/gear/spell decisions și motive.

