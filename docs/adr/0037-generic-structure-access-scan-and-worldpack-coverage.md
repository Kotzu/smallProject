# ADR 0037: Scanare generică a accesului în structuri și coverage explicit

## Status

Accepted.

## Context

Primele probe locale au fost făcute în cripta Deathknell și în Shadowfang Keep.
Aceste două locuri sunt utile deoarece primul reproduce blocajul real de la
spawn, iar al doilea are geometrie interioară mai complexă. Totuși, un rezultat
corect într-un exemplu nu demonstrează un Movement Engine general. Nu acceptăm
rute, coordonate, nume de zone sau reguli speciale pentru Brill, Deathknell ori
Shadowfang în algoritmul de awareness.

Un index static al WMO-urilor indică bounds și intersecția cu tile-urile nav,
dar nu dovedește că un punct din acel volum este navigabil. În mod similar, o
muchie Detour nu este automat un perete fizic, iar o tranziție covered→open nu
este automat o ușă sau ieșirea completă a clădirii.

## Decizie

Fiecare hartă sigilată într-un WorldPack primește două artefacte distincte:

1. `structure_access_scan_plan` enumeră toate WMO-urile indexate. Pentru fiecare
   WMO cu `FULL`, `PARTIAL` sau `GLOBAL_WMO`, generează seed-uri exclusiv din
   bounds-ul clientului și intersecția cu tile-urile nav prezente. WMO-urile cu
   `NONE` sunt păstrate explicit în `deferred_structures`; nu dispar din raport
   și nu sunt prezentate ca suportate.
2. `structure_access_graph` agregă numai probe Detour/BVH rezolvate. Muchiile
   brute sunt unite în lanțuri conectate, iar tranzițiile route-verified sunt
   unite în deschideri conectate, pe structură și nivel vertical.

Planul folosește un bootstrap lattice 3D și o politică de rafinare adaptivă:
Detour rezolvă fiecare seed, probele care nu aparțin structurii sunt respinse,
iar celulele încă neobservate se subdivid până la limitele declarate. Seed-urile
nu sunt waypoints și nu acordă autoritate de mișcare.

Ambele artefacte sunt legate strict de:

- ID-ul și SHA-256-ul WorldPack-ului;
- catalog, profil țintă, versiune/build client și profil nav;
- hartă și SHA-256-ul artefactului `.map`;
- ID-ul și hash-ul canonic al indexului de structuri;
- contractul probei și SHA-256-ul workerului nativ.

Orice schimbare a buildului, asseturilor, indexului sau workerului invalidează
planul și graful. Runtime-ul folosește numai graful verificat pentru WorldPack-ul
activ. Planul rămâne read-only și `execution_authority=false`.

Semantica este intenționat conservatoare:

- `NAVMESH_BOUNDARY_CHAIN_ONLY` nu este numit perete;
- numai corroborarea geometrică BVH poate promova un lanț la barieră statică;
- `COVERED_TO_OPEN_ROUTE_VERIFIED` nu este numit ușă;
- starea dinamică a unei uși rămâne necunoscută fără observație client-visible;
- coverage-ul unei probe locale nu devine coverage global al clădirii sau hărții.

## Dovezi controlate

Cu workerul stabil `pa_nav_probe-v26`, SHA-256
`1e22947ff15e4202831e6a233ca54619a05a5204dc4989a6bce414446e7d20a0`:

- WorldPack-ul activ Azeroth/Tirisfal indexează 55 de WMO-uri. Planul generic a
  creat 29 de taskuri și 783 seed-uri pentru WMO-urile care intersectează cele
  8 tile-uri nav active; celelalte 26 sunt declarate `NAV_COVERAGE_ABSENT`.
- WorldPack-ul Shadowfang indexează 29 de WMO-uri. Același cod a creat 29 de
  taskuri și 825 de seed-uri, fără coordonate sau reguli Shadowfang în planner.
- WorldPack-ul promovat Azeroth/Tirisfal/Silverpine v2 extinde același pipeline
  la 197 WMO-uri: 121 taskuri eligibile cu 3.324 seed-uri și 76 structuri
  deferred din cauza coverage-ului nav încă absent.
- Execuția completă a celor 3.324 seed-uri a închis toate cele 121 taskuri cu
  zero erori de worker. 66 structuri au observații confirmate și formează un graf
  cu 896 boundary chains și 240 deschideri; 55 rămân complete fără WMO confirmat.
- O probă reală în cripta Deathknell a redus 128 de muchii brute la 11 lanțuri
  și 15 muchii de egress la 4 deschideri conectate.
- O probă reală Shadowfang a redus 128 de muchii brute la 2 lanțuri și 31 de
  muchii de egress la 4 deschideri conectate.

Aceste numere demonstrează pipeline-ul comun și coverage-ul lui curent. Nu
demonstrează încă scanarea completă a celor 35 de hărți/3.610 ADT-uri din
inventarul TBC.

## Consecințe

- Deathknell–Brill rămâne traseul activ de regresie, nu o specializare.
- Shadowfang rămâne un benchmark de interior complex, nu centrul arhitecturii.
- Extinderea unei hărți în WorldPack mută automat WMO-urile din `deferred` în
  coada eligibilă la regenerare; nu cere cod nou pentru zonă.
- Pentru alt client sau expansion se rulează același pipeline peste propriile
  asseturi și propriul build pin; nu se reutilizează mesh-ul TBC 2.4.3.
- Coverage complet va fi declarat numai după probele și agregarea tuturor
  componentelor eligibile, nu pe baza existenței unui viewer 3D.
