# ADR 0026 — Facing servo continuu și Movement Lab extern

- Status: accepted pentru implementarea LAB; promovarea Champion cere benchmark
- Data: 2026-08-25

## Context

Primele probe live au demonstrat că targetarea și damage-ul pot funcționa, dar
mișcarea vizibilă a rămas slabă: observația era actualizată la 200 ms,
controllerul trimitea segmente open-loop de 650–950 ms, iar fiecare corecție de
facing apăsa și elibera RMB separat. Acest comportament produce oscilații,
cadre pierdute, opriri și aspectul de turelă descris de operator.

Research-ul de implementare a confirmat aceeași separare întâlnită în proiectele
mature:

- [Recast/Detour](https://github.com/recastnavigation/recastnavigation) rezolvă
  navigabilitatea și traseul global; `dtPathCorridor` păstrează și optimizează
  incremental coridorul local;
- [WowClassicGrindBot](https://github.com/Xian55/WowClassicGrindBot) folosește
  addon/pixeli pentru observație și DotRecast pentru rutare, iar followerul său
  actual este closed-loop, cu proiecție monotonă pe spline, look-ahead în timp,
  histerezis și frânare la curbură;
- [AmeisenNavigation](https://github.com/Jnnshschl/AmeisenNavigation) netezește
  ruta cu Chaikin, Catmull-Rom sau Bezier în loc să urmeze brut colțurile
  navmesh-ului;
- steering-ul local și pathfinding-ul sunt probleme diferite, conform modelului
  clasic de steering behavior al lui Craig Reynolds.

## Decizie

Problemele observate și rezolvările lor reproductibile sunt urmărite în
`docs/movement-engine-problem-log.md`; acel jurnal este obligatoriu pentru
orice corecție declarată rezolvată în gameplay.

Movement Engine și Combat Engine rămân module separate. Ele partajează numai
contractele pentru pose, target bearing, route corridor și execution gateway.

Bucla rapidă este deterministă:

1. addonul publică datele client-visible la 20 Hz;
2. pose/target perception produce o observație nouă și expirabilă;
3. followerul proiectează monoton poziția pe coridor și alege un look-ahead bazat
   pe aproximativ 0,6 s de deplasare, limitat la 3–15 unități world;
4. facing servo folosește eroarea orizontală filtrată, PD, histerezis și
   microcorecții de maximum 8 pixeli;
5. executorul păstrează RMB și W/A/S/D ca stări ținute, actualizate la 50 ms,
   dar emite input numai când starea se schimbă ori servo-ul cere o corecție;
6. fiecare tick verifică observația nouă, progresul și takeover-ul.

## Urmărirea coridorului și prevenirea orbitării

Ruta semantică de drum rămâne un prior extras din atlasul clientului, nu o
listă hardcodată de coordonate. Pentru execuție, priorul este eșantionat la
aproximativ 12 yd și fiecare țintă locală este validată din nou de navmesh-ul
3D. O coardă locală poate devia cel mult 1 yd de la geometria semantică înainte
ca punctul de curbă să devină obligatoriu. Astfel Detour poate ocoli un obstacol
real, dar nu poate scurta o curbă de drum prin terenul din interior.

Controllerul păstrează W prin curbe obișnuite de până la aproximativ 90 de
grade. O eroare mai mare de aproximativ 100 de grade este tratată ca pierdere a
direcției, nu ca o curbă executabilă în alergare, fiindcă ar produce o orbită
largă în jurul geometriei statice.

Un guard generic păstrează o fereastră bounded din traiectoria observată. El
cere replanificare curată numai când toate dovezile coincid: revenire în raza
de 2,5 yd a unui punct vechi, arc parcurs de minimum 18 yd, rotație cumulată de
minimum 1,5π și progres de cel mult 3 yd spre ținta locală. O curbă sau un
hairpin productiv nu este clasificat drept buclă. Evenimentul nu inventează un
obstacol și nu scrie memorie permanentă; replanificarea pornește din pose-ul
client-visible curent.

RMB persistent nu se modelează ca o succesiune de click-uri. Va fi o sesiune
mouse-look bounded care ține RMB cât targetul vizibil este valid, inclusiv în
deadband, și îl eliberează garantat la pierderea targetului, expirarea lease-ului,
focus change, eroare, finalul encounterului sau takeover manual. Această sesiune
este un gate separat; controllerul pur nu deține input.

## Portabilitate între realm-uri

Motorul nu depinde de MaNGOS și nu citește baza de date ori API-ul serverului.
Captura clientului, addon telemetry, target bearing, navmesh, steering, facing și
combat policy sunt partea portabilă. Teleport, spawn, godmode și reset sunt
servicii opționale de LAB folosite numai pentru repetabilitatea benchmarkului.

Ascension, Turtle WoW, Firemaw și alte realm-uri primesc profile de client/build:
layout UI, capabilități addon disponibile, spellbook/ranks, binding-uri și reguli
specifice realm-ului. Profilele nu pot introduce apeluri server-side în
Movement Engine sau Combat Engine; lipsa serviciilor LAB nu trebuie să oprească
roaming-ul, targeting-ul ori combatul client-only.

## Movement Lab

Instrumentul extern, transparent și click-through, afișează opțional:

- cercul controllerului sub Predator;
- cyan: axa de facing a Predatorului;
- magenta: direcția targetului selectat;
- verde: direcția următorului look-ahead/waypoint;
- starea controllerului și eroarea numerică.

Cyan și magenta trebuie să se suprapună în lock. Overlay-ul nu este evidence de
decizie și nu acordă execution authority. Este oprit în profilul video curat.
Waypoint-urile introduse manual sunt unelte de test/repetabilitate și seed-uri
pentru benchmark; ele nu înlocuiesc Recast, obstacle recovery ori exploration.

## AI local

Ollama/Hermes poate propune obiective semantice, alege între rute cunoscute,
interpreta quest/habitat context și propune recovery după eșec repetat. Nu intră
în servo-ul de 20 Hz, nu ține taste și nu decide fiecare pixel de mouse. Dacă
modelul întârzie sau lipsește, movement și combat rămân funcționale.

## Gate de acceptare

Nu numim facing-ul „magnetic” și nu promovăm controllerul până când un clip live
arată simultan:

- target vizibil păstrat în deadband în timp ce Predator face strafe/orbit;
- fără spam RMB down/up și fără target schimbat accidental;
- fără keyboard turning pentru facing;
- fără opriri open-loop mai lungi de un tick în regim normal;
- eliberare imediată și verificată la takeover;
- statistici de eroare, overshoot, reacquisition și frame time în limitele
  benchmarkului de navigație.
