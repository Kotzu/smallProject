# ADR 0019 — Prior art clean-room și primul movement gate

- Status: accepted
- Date: 2026-08-23
- Extends: ADR 0011, ADR 0012 și ADR 0013

## Context

Perfect Assassin are deja perception/capture, self-position HUD, pose contracts,
client-asset world-map calibration și un operator fixed-UI verificat. Următorul
risc nu mai este lipsa fundației, ci amânarea gameplay-ului vizibil până când
întregul stack de navigație este perfect.

Înainte de primul movement live am auditat proiecte publice care încearcă să
controleze WoW prin addon/screen/input, framework-uri player-AI din emulatoare și
tooling Recast pentru lumi WoW. Scopul auditului a fost accelerarea fără downgrade
arhitectural, contaminare de licență sau introducerea de server-only knowledge.

## Constatări

### Cel mai apropiat proiect public

[Xian55/WowClassicGrindBot](https://github.com/Xian55/WowClassicGrindBot),
snapshot `fab9f92580f90e482ee048f7ab04265c24ff74e8`, confirmă că următoarea
separare funcționează la scară mult mai mare decât un proof of concept:

```text
Lua pixel telemetry -> DXGI/WGC -> state readers -> GOAP
                    -> DotRecast corridor -> WASD spline follower -> input
```

Proiectul are route generation/recording, corpse recovery, loot, vendor/trainer,
stuck recovery, UI web, headless mode și multi-instance. Totuși:

- este un grind player, nu un Journey autonom 1–70 cu poveste, quest reasoning,
  world/opponent memory, PvP learning și Supervisor;
- dungeons sunt declarate nesuportate, iar PvP este o opțiune de engagement, nu
  un sistem tactic învățat;
- repo-ul nu declară o licență la rădăcină; codul și asset-urile sale sunt
  `reference_only`, nu sursă de copiere;
- suportul public pentru legacy TBC 2.4.3 nu este demonstrat end-to-end. Core-ul
  conține o ramură `Legacy_TBC`, dar lista publică de clienți se concentrează pe
  TBC Classic 2.5.x, iar TOC-ul TBC livrat este `20500`, nu `20400`.

Concluzia nu este „folosim alt produs”, ci „seam-urile noastre sunt validate, iar
standardul minim de comparație a crescut”.

### Alte proiecte screen/input

- [doaneruby970-hub/wow-bot](https://github.com/doaneruby970-hub/wow-bot),
  snapshot `3ef5bf2dd73eaed300708ffb7473e2dfa46b484d`, combină addon pixels,
  YOLO, OCR, waypoint recording și un FSM combat/loot/recovery. Coordonatele
  fixe, rutele manuale, modelele nelivrate și lipsa testelor îl fac benchmark,
  nu fundație.
- [Bourn23/wow_bot](https://github.com/Bourn23/wow_bot), snapshot
  `d7f373c894a18779b5c5369ee3a5a161732ef67b`, este util ca referință pentru
  înregistrarea sincronizată frame/state/input. Politica demonstrativă nu este
  un AI player funcțional.
- [ber84130/wow-ai-complete](https://github.com/ber84130/wow-ai-complete),
  snapshot `fd3c8a57530007abb6cc1e2b54d5609e636decb6`, are licență MIT, dar
  afirmațiile de autonomie depășesc implementarea verificabilă: conține pași
  hard-coded, detecții lipsă și placeholder-e. Este un avertisment să măsurăm
  capabilitățile prin replay/live evidence, nu prin numele feature-ului.
- [MatthewOglesby/MKOAgent](https://github.com/MatthewOglesby/MKOAgent),
  snapshot `433ee11094cfaab7bedb000c0656fdc421fa0887`, demonstrează un loop
  screenshot -> VLM local -> acțiune finită, dar ritmul și controlul grosier nu
  sunt potrivite pentru movement sau PvP fluid.

Proiectele care folosesc memory read, injection, hooks, packet control ori
kernel/HID rămân exemple negative și nu sunt rulate ori integrate.

### Framework-uri server-side

[CMaNGOS Playerbots](https://github.com/cmangos/playerbots), snapshot
`076045efa835da9aab7caa943bca752aebe1baad`, rămâne alegerea corectă pentru
oponenți, party help, quest scenario actors și oracle post-run în LAB-ul TBC
2.4.3. Travel graph-ul ierarhic peste Recast/Detour, strategy engine-ul și
test hooks sunt referințe bune de design.

[mod-playerbots](https://github.com/mod-playerbots/mod-playerbots), snapshot
`5397110cba484a9b7209bc9f632652e9d4bd6a70`, este un corpus mai bogat de
strategii raid/dungeon, dar cere fork-ul AzerothCore WotLK 3.3.5. Nu justifică
migrarea LAB-ului TBC.

Ambele familii decid cu server truth. Nicio poziție, rută, quest DB fact, threat,
LOS ori spawn information din ele nu intră în `PerceptionState` sau în decizia
Championului. LAB-ul le poate folosi numai ca actori și evaluator după episod.

## Decizie

### 1. Perfect Assassin rămâne produsul de bază

Nu facem fork și nu introducem un al doilea brain. Păstrăm ports/adapters,
versioned contracts, provenance, Champion/LAB separation, Journal, memory,
Supervisor și planul M0–M7.

### 2. Reutilizarea este permisivă și izolată

Candidații eligibili pentru implementare directă sunt:

- [Recast/Detour upstream](https://github.com/recastnavigation/recastnavigation),
  Zlib;
- [DotRecast upstream](https://github.com/ikpil/DotRecast), Zlib;
- [Xian55/DotRecast `wow-mods`](https://github.com/Xian55/DotRecast/tree/wow-mods),
  snapshot `eae9562f4d2cd238294be7a3b5afd3a42190d3d3`, numai după pin, license
  inventory și benchmark identic cu upstream;
- [namigator](https://github.com/namreeb/namigator), MIT, ca posibil parser/
  offline geometry builder pentru TBC, nu ca movement controller.

Nu importăm cod, pre-baked tiles, profiles ori addon packets din repo-uri fără
licență. Geometria de producție se construiește din asset-urile clientului exact,
cu build/map signature și provenance. CMaNGOS mmaps rămân oracle LAB.

### 3. Controllerul final nu este waypoint follower

Un follower geometric closed-loop devine baseline și deadline fallback, deoarece
este cea mai scurtă cale către mișcare măsurabilă. El folosește pose proaspăt,
look-ahead, heading error, hysteresis, turn-rate/acceleration limits, hairpin
braking și release-all.

PA-MPPI rămâne candidatul de producție pentru local trajectory control. Prior
art-ul nu justifică înlocuirea lui cu GOAP, DetourCrowd, random delays sau un
VLM care decide fiecare keypress. GOAP/behavior tree orchestrează moduri și
recovery; nu înlocuiește controllerul continuu.

### 4. Primul movement live este decuplat de navmesh-ul complet

Primul gate rulează într-un envelope LAB mic, vizual verificat și fără quest sau
combat:

```text
fresh valid pose
  -> semantic local displacement target at 5-10 yd
  -> turn in place
  -> 100-250 ms forward primitives, bounded cumulative duration
  -> observe coordinate delta after every primitive
  -> stop inside tolerance or fail closed
  -> release all + replay + Journal evidence
```

Acesta calibrează input latency, speed și turn response. Nu pretinde navigation
completion și nu folosește server route/oracle. Urmează, în ordine: două puncte,
hairpin, obstacle/replan, stuck recovery, apoi quest approach.

## Ordinea accelerată M3

1. `PA-024B5` — synchronized pose/action trace și model de mișcare calibrat per
   client/target; manual traces sunt permise și etichetate.
2. `PA-024F1` — Execution Gateway cu fake sink, lease, expiry, release-all și
   takeover tests.
3. `PA-024F2` — Win32 user-mode input adapter, exact target-bound; fără PostMessage
   background shortcut în Champion.
4. `PA-024F3a` — first-displacement gate descris mai sus.
5. `PA-024C` — client-asset Recast tile builder + Detour query adapter.
6. `PA-024C2` — Navigation Debug Visualizer: `OFF | ROUTE | MESH`, întâi
   top-down, apoi world-aligned după camera calibration.
7. `PA-024E0` — geometric spline follower baseline + two-point/hairpin course.
8. `PA-024D/E1/E2/E3` — tactical costs, common benchmark, PA-MPPI și recovery BT.
9. `PA-024F3b` — bounded route course complet, apoi `PA-024G` pursuit/corpse run.

## Navigation Debug Visualizer

Mesh-ul și ruta trebuie să fie observabile pentru QA și video, dar vizualizarea
nu intră în decision path și nu poate acorda execution authority.

```text
Recast tiles + Detour query + PoseEstimate
                  |
          DebugRenderSnapshot
                  |
       transparent external overlay
        OFF | ROUTE | MESH
```

Lua 2.4.3 nu primește direct date live din procesul extern și nu oferă un world
renderer generic pentru poligoanele Recast. De aceea:

- addonul poate expune un control `NAV DEBUG` și un flag client-visible;
- procesul extern citește flagul prin protocolul vizibil și controlează overlay-ul;
- mesh-ul este desenat de o fereastră transparentă, click-through, legată de
  PID/HWND/build și de același `PoseEstimate` ca plannerul;
- prima versiune este top-down/Control Panel și funcționează fără camera pose;
- world-aligned 3D projection este permisă numai după calibrarea body/camera și
  teste de resize/DPI/occlusion;
- `ROUTE` arată numai corridorul ales pentru stream; `MESH` adaugă poligoane,
  uncertainty, tactical costs, blocked links și stuck heat;
- server mmap/oracle se poate afișa numai într-o vedere LAB separată, etichetată,
  niciodată în overlay-ul Championului.

Ordinea nu reduce hard gates și nu promovează movement după un singur clip. Ea
separă prima dovadă de deplasare de construcția controllerului final.

## Consecințe

- primul rezultat vizibil apare înainte de întregul navmesh/MPPI stack;
- munca de foundation rămâne reutilizată integral, nu este aruncată;
- benchmarkul include de acum `xian_wowclassicgrindbot_design_baseline` ca
  referință externă documentară, nu ca executabil sau cod vendored;
- orice adoptare ulterioară de cod cere licență explicită, dependency manifest,
  pin, SBOM, teste și rollback;
- nicio afirmație „autonom” nu este acceptată fără contract/replay/LAB/live
  evidence corespunzătoare.

## Surse primare

- [WowClassicGrindBot architecture](https://github.com/Xian55/WowClassicGrindBot/blob/dev/docs/architecture.md)
- [WowClassicGrindBot README](https://github.com/Xian55/WowClassicGrindBot)
- [Legacy client classifier](https://github.com/Xian55/WowClassicGrindBot/blob/dev/SharedLib/StartupConfig/StartupClientVersion.cs)
- [TBC addon TOC](https://github.com/Xian55/WowClassicGrindBot/blob/dev/Addons/DataToColor/DataToColor_TBC.toc)
- [CMaNGOS Playerbots TravelNode](https://github.com/cmangos/playerbots/blob/master/playerbot/TravelNode.h)
- [CMaNGOS Playerbots strategy engine](https://github.com/cmangos/playerbots/blob/master/playerbot/strategy/Engine.h)
- [mod-playerbots](https://github.com/mod-playerbots/mod-playerbots)
- [Recast/Detour](https://github.com/recastnavigation/recastnavigation)
- [DotRecast](https://github.com/ikpil/DotRecast)
- [namigator](https://github.com/namreeb/namigator)
