# ADR 0012 — Stackul de navigație de producție și buy gate-ul comercial

- Status: accepted
- Date: 2026-08-22
- Supersedes: nu înlocuiește ADR 0011; îl specializează
- Amended by: ADR 0013 elimină Havok și fixează limita comercială/input boundary

## Context

Predator trebuie să navigheze natural prin open world, clădiri, poduri, peșteri, quest hubs aglomerate, corpse runs și urmăriri PvP. El controlează un client WoW închis din exterior și nu are acces la engine physics, character controller sau server GPS. De aceea, un SDK bun în interiorul unui motor de joc nu este automat cea mai bună soluție pentru Perfect Assassin.

Problema are trei părți diferite:

1. alegerea unei rute globale valide;
2. estimarea poziției și a mișcării din observații legitime, cu întârziere și incertitudine;
3. transformarea rutei într-o secvență naturală și sigură de input-uri keyboard/mouse.

## Decizie

Adoptăm următorul stack hibrid:

```text
Client-visible observations + GPU window capture
                       |
             Pose/Actor Belief Fusion
                       |
    Hierarchical Route Graph + Tactical Costs
                       |
       Recast tiles + Detour path corridor
                       |
   PA Local Trajectory Controller (MPPI/MPC)
                       |
       Behavior Tree Recovery Supervisor
                       |
             Safety/Takeover Shield
                       |
      bounded keyboard/mouse primitives
```

### 1. Backend global: Recast/Detour

`RecastDetourBackend` este backendul inițial de producție pentru navmesh și path corridors:

- Recast construiește tiled navmeshes din geometria permisă și semnată a fiecărui build;
- Detour face queries, corridor planning și traversal filters;
- un graf ierarhic Perfect Assassin leagă zone, continente, instanțe și transporturi;
- costurile tactice acoperă terrain, fall/water risk, aggro, stealth exposure, opponent memory, deaths și stuck history.

Backendul rămâne în spatele `NavigationMeshPort`:

```text
NavigationMeshPort
├── RecastDetourBackend       # production baseline
├── ExperimentalBackend       # numai sub budget/benchmark gate
└── LabOracleBackend          # evaluator LAB, niciodată Champion input
```

Grid A* din PA-024A este numai contract/test fixture. Nu este pathfinderul live.

### 2. Controller local: PA-MPPI

DetourCrowd nu va conduce direct clientul. Construim un controller receding-horizon bazat pe Model Predictive Path Integral / Model Predictive Control, adaptat la input-uri discrete reale.

Starea include pose belief, covariance, body yaw, camera yaw/pitch/zoom, viteză estimată, corridor progress, dynamic actor tracks și target envelope. Acțiunile simulate sunt primitive expirabile, nu viteze ideale:

`forward | backward | strafe_left | strafe_right | mouse_yaw | stop | jump_when_link_allows`

Modelul de mișcare se calibrează separat per client/build/profile. Controllerul evaluează un orizont scurt și penalizează coliziuni, căderi, abaterea de la corridor, aggro/stealth exposure, pierderea line-of-sight, range greșit, jerk, key tapping excesiv și pose uncertainty. Un follower geometric determinist rămâne fallback dacă MPPI depășește latency budget-ul.

### 3. Pose și percepție

Pose nu este o coordonată presupusă, ci un belief cu provenance, freshness și covariance:

1. coordonate client-visible legitime expuse de adapter/addon;
2. minimap registration față de atlasul targetului;
3. landmark/keyframe localization;
4. dead reckoning din comenzile emise, calibrare și optical flow.

Captura principală va folosi `Windows.Graphics.Capture` targetat pe fereastra clientului, cu DXGI Desktop Duplication ca fallback. Fuziunea rapidă pornește cu EKF/UKF și relocalizare cu particle filter. Matching-ul vizual avansat poate folosi ALIKED + LightGlue după baseline-ul OpenCV. Full visual SLAM nu intră în calea critică; poate fi evaluat izolat pentru interiors/dungeons.

`ANCHORED | TRACKED | DEGRADED | LOST` sunt stări explicite. În `LOST` nu se emite movement.

### 4. Mulțimi și urmărire PvP

Playerii/mobii observați devin tracklets cu viteză, heading și incertitudine. Controllerul urmărește un punct de intercept sau un offset tactic, nu ultima coordonată brută a țintei.

DetourCrowd și RVO2/ORCA rămân benchmark-uri și surse de idei, nu controllerul final. ORCA presupune evitare reciprocă; un player real poate să nu coopereze. Predatorul poate prelua conservator întreaga responsabilitate de evitare și poate ceda, încetini, opri sau alege alt corridor.

### 5. Mișcare naturală

Nu introducem jitter aleator pentru a imita un om. Naturalitatea rezultă din:

- curbe și turn-rate compatibile cu clientul;
- anticipare, camera lead/lag și corecții rare, ferme;
- route diversity la nivel de corridor, nu zig-zag local;
- încetinire contextuală la uși, poduri, colțuri și crowd bottlenecks;
- verificarea rezultatului după fiecare burst de control;
- abandonarea temporară a unei destinații blocate.

Imitation learning poate apărea numai după colectarea unor trasee umane consimțite și numai ca strat rezidual de stil, sub safety shield. Nu promovăm inițial o politică end-to-end în Champion.

## Decizia comercială

ADR 0013 elimină Havok și fixează limita la sub USD 500 per componentă fără o nouă decizie explicită. Nu avem momentan un middleware comercial candidat. Orice componentă viitoare trebuie să ruleze prin același port și să treacă aceleași holdout benchmarks; prețul mic nu înlocuiește dovada de calitate.

## Information boundary

- geometry/map assets permise au build signature și provenance;
- CMaNGOS mmap/pathfinder poate calcula ground truth în LAB;
- Champion nu primește waypoint-uri, collision truth, spawn paths sau coordonate server-only;
- toate input-urile trec prin Execution Gateway și sunt anulabile imediat prin `MANUAL`;
- orice confidence collapse oprește sau degradează controlul, nu inventează stare.

## Consecințe

- cea mai mare investiție inițială merge în geometry QA, pose/perception, replay-uri etichetate și benchmark, nu în licență;
- navigation backend, pose providers, local controller și actuator pot fi înlocuite independent;
- nicio mișcare live nu este autorizată de această decizie; PA-024F rămâne gate-ul bounded LAB;
- „merge pe Recast” nu înseamnă „arată uman”; ambele dimensiuni se măsoară separat.

## Surse primare

- Recast/Detour: <https://github.com/recastnavigation/recastnavigation>
- DetourCrowd: <https://recastnav.com/classdtCrowd.html>
- RVO2/ORCA: <https://gamma.cs.unc.edu/RVO2/>
- Nav2 MPPI design: <https://github.com/ros-navigation/navigation2/blob/main/nav2_mppi_controller/README.md>
- Windows Graphics Capture: <https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture>
- DXGI Desktop Duplication: <https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api>
