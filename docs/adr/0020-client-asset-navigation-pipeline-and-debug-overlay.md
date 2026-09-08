# ADR 0020 — Pipeline client-asset pentru Recast și NAV DEBUG

- Status: accepted
- Date: 2026-08-23
- Extends: ADR 0011, ADR 0012, ADR 0013 și ADR 0019

## Context

Recast/Detour este motorul global ales, dar nu citește direct formatele WoW.
Perfect Assassin are nevoie de geometrie TBC 2.4.3 reproductibilă fără server
GPS, gameobject database ori mmaps CMaNGOS în deciziile Championului. Avem și
nevoie să vedem exact mesh-ul și corridorul folosite de planner, inclusiv când
rulăm mai multe instanțe ale clientului.

## Decizie

Adoptăm un pipeline nativ C++ cu un contract neutru între asset parsing și
Recast:

```text
MPQ-uri client 2.4.3, manifest ordonat și hash-uit
                 |
          pa-wow-geometry
   parser Namigator + StormLib
                 |
      pgeom v1: triunghiuri + provenance
                 |
        pa-nav-bake / pa_recast
     upstream Recast + Detour pin-uit
                 |
       pnav v1: tiled navmesh
                 |
       worker Python izolat
          |               |
 NavigationMeshPort   DebugRenderSnapshot
                          |
             overlay NAV DEBUG Direct2D
```

Pin-urile inițiale sunt:

- RecastNavigation `9f4ce64458dfae86e1239c525ddc219c4e9e06f1`, Zlib;
- Namigator `54eae6957753c3ca47b73402df9f8d1d52a2721e`, MIT;
- StormLib `37000d13927f52c96d7ead3f9bca4fe421894fcf`, MIT.

Folosim din Namigator numai frontendul pentru MPQ/ADT/WMO/M2, adaptat să emită
`pgeom`; nu folosim runtime-ul, pathfinder-ul ori formatul său `Map.nav`.
Recast rămâne upstreamul pin-uit. DotRecast nu intră în runtime: ar adăuga un
toolchain .NET fără să rezolve parsingul asseturilor WoW.

Workerul nativ este izolat într-un subprocess și expune un C ABI minim:
`create`, `destroy`, `load_tile`, `unload_tile`, `nearest_point`,
`find_corridor`, `straight_path` și `debug_snapshot`. Crash-ul, un hash greșit
sau un profile mismatch opresc query-ul fail-closed.

Înainte de `load_tile`, boundary-ul Python validează integral structura Detour
v7 pin-uită: counts și byte layout, `dtPoly` vertex/neighbour indices, link
chains, detail mesh/triangles, BV bounds și off-mesh references. JSON-ul are
bugete pre-parse/pre-allocation, iar number categories și coordinate matrix
sunt normalizate semantic înainte de wire hash. Un header aparent valid nu este
suficient pentru a ajunge la `dtNavMesh::addTile`.

## NAV DEBUG

Addonul va avea controlul vizibil `NAV DEBUG: OFF | ROUTE | MESH`; el transmite
doar starea controlului printr-un marker client-visible. Nu primește și nu
desenează poligoanele.

Randarea este făcută de un overlay Windows C++ Direct2D/DirectComposition,
transparent și click-through, legat de PID, HWND și identitatea procesului
instanței selectate. Prima versiune este un inset top-down peste joc:

- `ROUTE`: pose, uncertainty, țintă și corridorul ales;
- `MESH`: adaugă tile-uri/poligoane, costuri tactice, blocked links și stuck heat;
- `OFF`: overlay-ul nu desenează nimic.

Reutilizăm `DebugUtils` și `duDebugDrawNavMesh*` din Recast printr-un sink
`duDebugDraw` propriu. Nu legăm RecastDemo, SDL, OpenGL ori `DebugDrawGL`.
Proiecția 3D peste teren rămâne după camera calibration și testele de
DPI/resize/occlusion. Overlay-ul nu acordă execution authority și nu devine
decision evidence.

### Viewer 3D extern

Movement Engine expune separat un viewer 3D diagnostic construit peste
frontendul Namigator pin-uit. El încarcă numai navmesh-ul Stable și asseturile
clientului 2.4.3, randând în aceeași scenă terrain, WMO, M2/doodads și
poligoanele Detour. Toolul pornește direct pe `map + world X/Y/Z` din
telemetria read-only și centrează camera fără marker/sferă implicită; nu citește
memoria clientului, nu trimite input și nu furnizează decision evidence.

Viewerul nu este echivalent cu overlay-ul world-projected din joc: este o
fereastră externă interactivă pentru inspecția geometriei, interioarelor și
mesh-ului. Fluxul upstream cu numai cele două directoare ca argumente rămâne
compatibil, iar coordonatele de pornire sunt opționale.

Protocolul live v2 poate transporta separat pereții locali, tranzițiile brute
de suprafață și ieșirile topologice verificate din `start_awareness`. Controlul
`Local awareness (walls / exits)` activează un strat diagnostic X-ray: roz
pentru pereți, portocaliu pentru tranziții și verde pentru ieșiri. X-ray-ul
păstrează XYZ-ul exact, dar rămâne vizibil prin teren/etajele superioare pentru
inspecția interioarelor. Markerul Predatorului nu folosește acest depth state;
el rămâne depth-tested și nu este desenat peste un obstacol aflat în fața lui.

Deschiderea din Movement Engine nu reutilizează orbește ultima poziție a unui
journey terminat. Înainte de lansare, un probe separat și strict read-only
citește o poziție fresh din HUD-ul client-visible, iar viewerul alege înălțimea
navmesh cea mai apropiată de hint-ul observat anterior. Un bridge read-only
publică apoi pose-ul HUD la 5 Hz și coridorul activ într-un fișier atomic;
viewerul validează protocolul, proiectează Z pe navmesh, încarcă tile-urile ADT
traversate și desenează coridorul într-un buffer separat de liniile Detour.
Pozițiile identice nu produc redraw, iar camera interpolează temporal între
observațiile HUD fără să inventeze pose-uri.

Fereastra 3D prezintă cu VSync și este event-driven: scena statică nu este
randată repetat, iar mișcarea camerei folosește timp real, nu pași dependenți de
FPS. `Lock live pose`, `Center live pose (R)` și `Clear markers` rămân controale
exclusiv diagnostice. Dacă WoW nu este foreground sau nu este în world, bridge-ul
se pune în pauză și viewerul păstrează ultima poziție validă. Ferestrele 3D se
deschid `SW_SHOWNOACTIVATE`, iar panoul de layere este andocat sub scenă, astfel
încât să nu acopere HUD-ul clientului.

Overlay-ul transparent `Predator Movement Lab` este o singură instanță
click-through/`WS_EX_NOACTIVATE`. El reține ultima semnătură vizuală și nu șterge
canvas-ul la fiecare poll; un crash are restart cu backoff, nu un loop care fură
focusul. Viewerul 3D și overlay-ul vizualizează world model-ul, dar nu sunt
world model-ul și nu dobândesc execution authority.

### Catalog versionat de lumi

Viewerul și Movement Engine nu vor identifica hărțile prin nume de zonă sau
coordonate hardcodate. Artefactele sunt catalogate prin identitatea clientului
(product/build/expansion), manifestul asseturilor, `Map.dbc` map ID și hash-ul
navmesh-ului. Același contract world-space și același renderer sunt reutilizate,
dar fiecare familie de formate client are extractor și compatibility gate
versionate. Un navmesh TBC nu este reutilizat pentru altă expansiune.

Dropdownul viewerului nu mai conține o listă manuală de continente și instanțe.
El enumeră numai fișierele `.map` existente în profilul nav activ și rezolvă
fiecare nume intern la map ID prin `Map.dbc` din clientul încărcat. Un map file
fără identitate în client oprește catalogarea în loc să apară ca hartă posibilă;
adăugarea unui bake valid îl introduce automat în viewer.

Movement Engine aplică acum gate-ul executabil separat din
[ADR 0033](0033-versioned-client-world-catalog.md): identitatea launch receipt,
hash-ul `Map.dbc`, Map ID-ul, fișierul `.map` și lista exactă a tile-urilor sunt
verificate înainte de orice input. Catalogul TBC curent declară explicit
`partial/partial`; dropdown discovery nu este echivalent cu suport runtime.

Suportul confirmat în acest ADR rămâne clientul TBC 2.4.3/build 8606. Extinderea
la alte expansiuni este acceptată ca direcție arhitecturală, nu declarată
funcțională înainte ca atlasul, ADT/WDT/WMO/M2, map catalogul și interioarele
fiecărui build să treacă rebuild determinist și probe vizuale/geometrice.

## Provenance și limite

- `pgeom` pornește numai dintr-un manifest exact al asseturilor clientului;
- terrain, holes, liquids, WMO și M2/doodads fac parte din primul tile real;
- gameobjects/coordonați din server DB nu intră în pipeline;
- CMaNGOS maps/vmaps/mmaps sunt numai oracle post-episode în LAB;
- tile-urile generate local nu intră în Git și nu se distribuie;
- transporturile, lifturile și jump links cer observații dinamice și contracte
  off-mesh separate;
- targetul inițial pentru overlay este windowed/borderless; Moonlight,
  ShadowPlay, DPI și multi-instance au gate separat.

## Primul vertical slice

Construim numai envelope-ul Deathknell/Tirisfal, verificăm rebuild determinist,
tile seams, nearest point și un corridor scurt. Abia după acel gate adăugăm
world-aligned rendering și streaming de tile-uri open-world.

La 2026-08-26, viewerul extern a fost verificat controlat la poziția Deathknell
`1843.554466, 1591.415232, 93.680946`: ADT, WMO, doodads și navmesh au fost
randate împreună. Bridge-ul a avansat 16 secvențe în 3 secunde la ținta de 5 Hz,
WoW a rămas foreground, iar viewerul static a consumat numai `0.02 s CPU` în
aceeași fereastră de măsurare.

## Surse

- [RecastNavigation](https://github.com/recastnavigation/recastnavigation)
- [Namigator](https://github.com/namreeb/namigator)
- [StormLib](https://github.com/ladislav-zezula/StormLib)
