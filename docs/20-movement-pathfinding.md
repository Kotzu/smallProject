# 20 — Movement și pathfinding portabil

## Răspunsul scurt

Folosim un nucleu de navigație propriu peste contracte semantice și Recast/Detour pentru navmesh. Steering-ul live va fi un controller predictiv PA-MPPI/MPC, nu waypoint following sau DetourCrowd direct. MaNGOS nu conduce Championul. Pe alte servere se schimbă numai target adapters, pose provider, motion calibration și map profile.

Movement Engine este standalone: emulator mmaps, playerbots, realm database și
server movement APIs sunt permise numai ca evaluatori LAB, niciodată ca
dependențe runtime. Adaptoarele sunt legate de client build/expansion, în timp
ce creierul de mișcare rămâne comun. Vezi ADR 0034.

Instalarea clientului este doar sursa unui import offline. După bake,
Movement Engine consumă un WorldPack autonom și verificabil; nu caută și nu
citește clientul live. Astfel aceeași capsulă poate fi folosită cu orice realm
compatibil cu acel build, iar un alt expansion cere un nou adapter/WorldPack,
nu un alt creier de mișcare.

Și poarta de regresie folosește acum aceeași limită standalone. Butonul Start
acceptă numai gate-ul v2 legat simultan de profilul WorldPack, hash-ul complet
al pachetului, target profile, versiunea/buildul clientului, nav profile,
workerul Detour și hash-ul rezultatului de validare. Vechiul gate legat doar de
un folder loose de navmesh nu mai acordă autoritate live. Un profil `2.4.3.8606`
nu poate valida accidental un client modern din familia Anniversary `2.5.5+`.

Butonul `3D la Predator` folosește același WorldPack verificat. Viewerul este
pornit în modul `--world-pack`: citește `*.map`, tile-urile Detour și BVH-ul din
pachet, nu folderul `Data` al jocului și nu inițializează arhivele MPQ. Modul
vechi cu geometrie decorată din client rămâne numai ca artefact de rollback și
comparație vizuală.

Movement Engine indexează acum și tabela statică `MAP1` din WorldPack. WMO-urile
oferă limitele clădirilor și incintelor mari, iar doodad-urile oferă candidații
de obstacole statice precum copaci, garduri sau torțe. Toolul extern poate face
containment 3D și căutări locale până la 1.000 yd fără să adauge frame-uri în
clientul WoW.

Existența și reachability rămân fapte separate. Fiecare structură primește
`FULL`, `PARTIAL` sau `NONE` după suprapunerea cu tile-urile nav declarate de
catalogul activ. Numele assetului rămâne indiciu, nu dovadă pentru o ușă,
ieșire, localitate sau poziția curentă. Entitățile dinamice continuă să provină
numai din observații vizibile în client și `last_seen` cu expirare. Expirarea
oprește folosirea tactică, nu șterge experiența: întâlnirile mature sunt
păstrate append-only în SQLite ca poziție a observatorului plus cue
screen-space, niciodată ca poziție 3D inventată a entității. Vezi ADR
0035.

```text
QuestPlanner / PvP Brain / CorpseRun
                 |
           MovementGoal
                 v
          Route Planner
                 v
       Global Navmesh Planner
      Recast tiles + Detour query
                 v
           PathProposal
                 v
   PA-MPPI + Dynamic Actor Model
                 v
          MovementIntent
                 v
      Safety / Execution Gateway
                 v
 Keyboard+mouse adapter | optional CTM adapter
```

## De ce Recast/Detour

- navmesh derivat din geometrie, nu dintr-un anumit emulator;
- tiled streaming pentru continente și instanțe;
- path queries, polygon filters și traversal costs;
- off-mesh connections pentru sărituri, uși, lifturi sau treceri speciale;
- bibliotecă C++ mică, zlib, fără dependency asupra serverului WoW.

Recast/Detour este backendul global, nu întreaga navigație. Alegerea completă, inclusiv pose fusion și controllerul local, este în [ADR 0012](adr/0012-production-navigation-stack-and-buy-gate.md). Client integrity și input transport sunt blocate în [ADR 0013](adr/0013-client-integrity-and-input-execution-boundary.md). Scenariile și metricile sunt în [Navigation Quality Benchmark](21-navigation-quality-benchmark.md).

Checkout-ul nostru extern este pin-uit la commit `9f4ce64458dfae86e1239c525ddc219c4e9e06f1`. Nu intră în repo sau în fișierele serverului.

## Atlas complet și coridor semantic

Movement Engine folosește atlasul Tirisfal complet explorat extras din același
client 2.4.3. Pozițiile world sunt proiectate cu limitele exacte din
`WorldMapArea.dbc`; transformarea este bidirecțională și testată cu ancorele
Deathknell și Brill. Coordonata afișată sub cursor în tool este aceeași
coordonată X/Y folosită de telemetria din joc, nu un sistem grafic separat.

Ruta globală nu este o listă scrisă manual. Straturile `MTEX/MCLY/MCAL` din ADT
identifică textura reală de road/path, sunt reduse într-un grid semantic și un
A* ponderat produce automat coridorul. Micile întreruperi ale alpha-map-ului pot
fi traversate cu un cost off-road mare și rămân raportate ca `bridge_cells`.
Waypoints rezultate sunt numai propuneri globale fără execution authority.

Fiecare waypoint este apoi verificat de navmesh-ul 3D. Eticheta 2D de drum se
aplică exclusiv poligoanelor `Ground` outdoor; nu se propagă la cripte, tuneluri,
WMO, lichid sau doodads aflate la același X/Y. Pantele peste 42° și ledge-urile
peste 0,6 yd sunt eliminate fizic în build, nu doar penalizate. Dacă poziția
observată nu mai aparține componentei sigure, plannerul emite `RESET_REQUIRED`
și reia misiunea de la spawn/cimitir; nu improvizează o rută peste deal.

Profilul `tbc243-human-road-corridor-v6` (format navmesh `0015`) include
ADT-urile 28_27 până la 31_28 cu geometria WMO a criptei și clearance de
0,90 yd. Poarta offline validează
coordonata canonică din interiorul criptei → Brill în 129 de coridoare locale,
Deathknell outdoor → Brill în 115 și Brill → Deathknell în 116; fixture-ul
poziției blocate pe deal emite `RESET_REQUIRED` la prima etapă. Centrele
punctelor funnel Detour sunt reproiectate pe poligonul 3D exact cu rezoluție
verticală de 0,25 yd înainte de verificarea pantei; astfel nu schimbă etajul și
nici nu mai urmează zig-zagul artificial al centrelor de portal, în timp ce
pantele reale lungi rămân limitate la 42°.

Workerul promovat este `pa_nav_probe-v25` (SHA-256
`DD202B941B7F4D5E9525A9F4A0103D570C26B3CB02062E34A8916338A7DB1F1A`). v24
rămâne separat ca rollback. Pe lângă inset-ul de portal, workerul verifică
fiecare segment ca un tunel de mișcare, nu ca o
rază infinit de subțire: cinci probe doodad/M2 acoperă centrul, capsula de
0,82 yd și toleranța laterală controlată de 0,85 yd la înălțimea corpului. Pentru
un ocol M2 caută mai întâi și o marjă statică suplimentară de 0,50 yd pe fiecare
latură, plus cinci probe joase la 0,35 yd pentru soclurile late ale obiectelor
mici precum torțele. Proba joasă este numai o preferință de clearance: dacă
spațiul legitim este îngust, păstrează drept fallback tunelul capsulei deja
demonstrat, astfel încât podelele și portalurile WMO să nu fie închise
artificial. Punctele locale de
ocolire își aleg înălțimea din stratul client-side cel mai apropiat; nu cer mai
întâi o rută directă prin obstacolul pe care încearcă să-l evite. După inset,
fiecare segment este revalidat, primul blocker static este localizat, iar
backend-ul reexecută Detour incremental cu poligoanele intersectate excluse.
Un segment M2/WMO rămas nerezolvat este returnat `complete=false`, niciodată
trimis controllerului live. v25 revalidează suplimentar tranziția verticală
dintre punctele funnel deja acceptate: dacă un segment depășește 42°, adaugă un
blocker local de 1,5 yd și cere un coridor alternativ. Interogarea client-side
de înălțime la marginea exactă dintre două sub-quad-uri ADT returnează acum
`false` fail-closed; nu mai poate opri workerul printr-un `assert` de debug.

Proba live v15 din 26 august 2026 a parcurs Deathknell → Brill și retur fără
rută hardcodată și fără intervenție manuală. Sosirile au fost `ARRIVED` la
1,66 yd, respectiv 1,80 yd de coordonatele semantice. Dusul a folosit 8.005
cadre de control, returul 7.181, ambele cu `recovery_attempts=0`,
`local_recovery_attempts=0` și `partial_replans=0`. Aceste contoare demonstrează
că traseul nu s-a blocat, nu că a fost lipsit de orice contact: replay-ul de
retur și corecția operatorului au identificat o atingere a torței, iar
telemetria din jurul coordonatei `(1912, 1579)` conține un început de
`collision_slide_s`. v24 schimbă automat coridorul local următor din zona
contactului spre `y≈1590`, în locul continuării vechi spre `y≈1583`, fără a
introduce ruta sau coordonata incidentului în planner. Dovezile brute pentru
proba v15 sunt `navmesh-roaming-06dd875e-0a53-4773-8850-6d63f58b27d3.json` și
`navmesh-roaming-3cb6c8e7-1299-4400-bc5a-5a4ec4a2d2c7.json`; replay-urile sunt
`Desktop 2026.08.26 - 02.10.57.35.DVR.mp4` și
`Desktop 2026.08.26 - 02.16.03.36.DVR.mp4`. v24 trece poarta offline completă
în ambele sensuri și păstrează cripta traversabilă.

Proba live separată v24 din 26 august 2026 a închis și această incertitudine.
Deathknell → Brill a sosit la `1.676 yd` după 7.341 cadre/312,69 s, iar Brill →
Deathknell a sosit la `1.963 yd` după 6.554 cadre/277,66 s. Ambele sensuri au
avut zero recovery, zero local recovery și zero replan. Pe retur, cele 149 de
cadre din raza de 15 yd a vechiului contact au trecut la minimum `2.552 yd` de
punctul lui, cu `collision_slide_s=0`; secvența video arată ocolirea continuă a
copacilor și a grupului de torțe, fără oprire sau frecare. Dovezile sunt
`navmesh-roaming-516c036e-50e7-4371-8c8c-95a4e91162d4.json`,
`navmesh-roaming-1aafa1e2-0211-4f90-85e1-291647f3fb40.json`, replay-urile
`Desktop 2026.08.26 - 03.24.25.37.DVR.mp4` și
`Desktop 2026.08.26 - 03.31.14.38.DVR.mp4`, plus contact-sheet-urile din
`data/runtime/operator/video-review-return-v24`. Acesta este primul rezultat
live care promovează probele joase pentru soclurile doodad; nu afirmă încă
rezolvarea generică a tuturor claselor de obiecte mici.

Proba holdout v25 a ales din atlas, fără rută codificată, destinația semantică
`landmark:brill-south-road-bend` la `(2043.75, 285.416656)`. Supervisorul a
pornit dintr-un dialog real de disconnect, s-a reconectat fail-closed și a
ajuns la 1,699 yd după 2.176 cadre și 90,56 s. La panoul indicatorului de pe
drum a existat un singur contact client-observat; manevra bounded
`JUMP → MOVE_BACKWARD → STRAFE_RIGHT` a eliberat actorul, iar excluderea locală
a 5 poligoane a produs un coridor complet. Rezultatul este
`navmesh-roaming-ab30af7a-c7a1-45bf-a9d6-9ecdea7758a3.json`, iar replay-ul este
`Desktop 2026.08.26 - 08.21.47.40.DVR.mp4`. Acest run dovedește recuperarea
generică într-o zonă nouă, nu absența contactului.

Contactul acceptat este păstrat de Experience Map în
`learned-obstacles-tbc243.json`, legat de buildul 8606, hartă și zone index.
O observație este provizorie și expiră după 7 zile; două observații o confirmă
pentru 90 de zile. Plannerul încarcă cel mult cele mai apropiate 8 marcaje în
300 yd, iar fiecare rămâne `execution_authority=false`. Proba inversă
holdout → Brill a încărcat exact acest marcaj și a ajuns la 1,699 yd în 79,38 s,
cu 1.992 cadre, 7/7 waypoints, zero recovery, zero local recovery și zero
replan. Cele 113 cadre din raza de 15 yd au trecut la minimum 2,066 yd de
marcaj, cu `collision_slide_s=0`; replay-ul arată trecerea continuă pe lângă
indicator. Dovezile sunt
`navmesh-roaming-686d31bd-a1e7-44b6-aaf7-f34d849282c7.json`,
`data/runtime/navigation-f3b/continuity/holdout-return-memory-v25.json` și
`Desktop 2026.08.26 - 08.51.17.41.DVR.mp4`. Politica completă este în
[ADR 0031](adr/0031-client-observed-obstacle-memory.md).

Executorul extern primește numai ID-ul destinației semantice. El citește poziția
X/Y observată, verifică faptul că acel catalog declară
`tbc243_client_world_xy` și calibrarea `WorldMapArea.dbc:Tirisfal`, generează
coridorul global și schimbă coridoarele Detour locale într-o singură sesiune
closed-loop. Fișierul vechi cu o succesiune revizuită manual nu mai este în
lanțul butonului Start. Poarta offline rămâne distinctă de autoritatea live.

Continuitatea clientului rulează într-un supervisor extern separat. Fiecare
cadru este clasificat fail-closed ca `IN_WORLD`, `DEAD_IN_WORLD`,
`DISCONNECTED_DIALOG`, `LOGIN_SCREEN`, `CHARACTER_SELECT` sau `UNKNOWN`; numai
stările certe pot produce acțiunea bounded corespunzătoare. Intenția semantică
rămâne aceeași, iar după revenirea în world traseul este recalculat din poziția
vizibilă actuală, nu reluat prin inputuri vechi. Prima probă live a pornit chiar
din dialogul real de disconnect, a recunoscut dialogul cu confidence `0.69`,
ecranul de login cu `0.89`, a așteptat fail-closed un frame tranzitoriu cu
confidence mic și a revenit în world; abia după confirmarea God mode a parcurs
Deathknell → Brill și a emis `ARRIVED`. Recuperarea generică de corp/cimitir
este acum portabilă în același supervisor: HUD protocol v3 expune numai
`UnitIsDeadOrGhost`/`UnitIsGhost`, salvează poziția world exactă a corpului,
execută o singură apăsare bounded pentru Release Spirit, navighează fantoma la
un goal normalizat calculat din acea poziție, recuperează corpul o singură dată
și reia intenția semantică inițială. Runnerul de corpse-run este strict
ghost-only; dacă vede playerul viu, oprește inputul înainte de a relua misiunea.

Proba live din 26 august 2026 a parcurs întregul ciclu într-o singură execuție:
`DEAD_IN_WORLD → RELEASE_SPIRIT → ghost ARRIVED → RETRIEVE_CORPSE →
RESUME_MISSION → Brill ARRIVED`. Corpul a fost memorat la
`(1845.991, 1590.105)`, fantoma a ajuns la `2.800 yd`, fără recovery, replan sau
collision slide, iar după înviere Predator a ajuns din nou în Brill la
`1.832 yd`, în 7.865 cadre, tot cu zero recovery/replan/collision. Dovada
supervisorului este
`data/runtime/navigation-f3b/continuity/corpse-recovery-live-v3.json`; runurile
atomice sunt `navmesh-roaming-c331a806-e00f-4b90-814f-2a968416fe22.json`,
`navmesh-roaming-d4681da3-79a3-4051-9c67-a209e65eb30e.json` și
`navmesh-roaming-b7650b4c-58d0-4584-8db5-0010f6a5478c.json`. Comanda
`labkill` folosită pentru a produce moartea este exclusiv un trigger de test al
realmului local; recuperarea observă numai clientul și nu depinde de MaNGOS.

## Vizualizarea navmesh-ului

`Navigation Debug Visualizer` are trei moduri: `OFF`, `ROUTE` și `MESH`.
Randarea este externă, transparentă și click-through, legată de fereastra exactă
a clientului. Addonul poate oferi butonul/toggle-ul, dar nu primește ori desenează
direct poligoanele Recast; flagul său client-visible este citit de sidecar, iar
sidecar-ul desenează corridorul și mesh-ul.

Prima versiune este un inset top-down Direct2D/DirectComposition peste fereastra
exactă a jocului și arată: player pose + uncertainty, target,
Detour corridor, poligoane, tactical costs, blocked links și stuck heat. După
camera calibration adăugăm proiecția world-aligned peste teren. `ROUTE` rămâne
varianta curată pentru stream/video; `MESH` este pentru QA. Niciun mod nu intră
în decision evidence și niciunul nu acordă execution authority.

Paleta Experience Map este stabilă: gri pentru geometrie neverificată, cyan
pentru ruta curentă, verde pentru coridoare familiare, portocaliu pentru risc și
roșu pentru stuck/death heat. Faptele dinamice expirate nu rămân colorate ca
adevăr curent.

Frontendul exact pentru asseturi, pin-urile și rendererul sunt blocate în
[ADR 0020](adr/0020-client-asset-navigation-pipeline-and-debug-overlay.md).

## Hartă stratificată

Pathfinding-ul geometric singur nu este suficient. Fiecare poligon/edge poate primi costuri dinamice:

- distanță și timp estimat;
- terrain/slope/water/fall risk;
- mobs și aggro corridors observate;
- enemy-player sightings și opponent memory;
- stealth exposure și line-of-sight;
- death history/stuck history;
- quest relevance și route-teacher preference;
- party/dungeon constraints.

Astfel „drumul cel mai bun” poate fi mai lung geometric, dar mai sigur sau mai rapid pentru Journey.

### Awareness static local

Fiecare query client-asset produce și un snapshot polar în jurul începutului
rezolvat al coridorului: suprafața fizică, clearance vertical și 16 distanțe până
la coliziune pe 360°, limitate la 12 yd. Snapshotul permite separarea generică
între teren deschis, structură WMO/tranziție și spațiu static strâmt. O direcție
liberă devine deschidere candidate numai după un raycast Detour complet pe
suprafața navigabilă. Pentru starturile WMO, componenta locală de 60 yd produce
separat pereți, tranziții brute de suprafață și ieșiri topologice. O ieșire este
acceptată numai la trecerea acoperit→plafon liber, dacă spațiul liber continuă
navigabil minimum 4 yd și există un coridor Detour complet de la actor; sortarea
folosește distanța reală a acelui traseu, nu distanța 2D care poate traversa
etaje. Nici snapshotul, nici portalul nu oferă execution authority. Contractul
și limitele sunt în [ADR 0032](adr/0032-client-asset-local-static-awareness.md).

Același snapshot este publicat read-only în protocolul v2 al viewerului 3D.
Stratul extern opțional desenează pereții roz, tranzițiile brute portocalii și
ieșirile route-verified verzi. Awareness-ul este X-ray pentru ca geometria unui
interior să rămână inspectabilă sub terrain/WMO, însă săgeata Predatorului își
păstrează depth-testul normal și nu este mutată ori desenată peste obstacole.

Probe locale verificate pot fi agregate într-un `Structure Access Graph` legat
de build și WorldPack. Muchiile Detour adiacente devin lanțuri conectate, iar
tranzițiile covered→open route-verified devin deschideri conectate pe structură
și floor. Graful nu inventează semantică fizică: un lanț este barieră statică
numai când BVH îl coroborează, iar o deschidere nu este numită ușă și nu primește
stare open/closed fără observație.

Scanarea nu este specializată pentru Deathknell, Brill sau Shadowfang. Pentru
fiecare hartă dintr-un WorldPack, `structure_access_scan_plan` enumeră toate
WMO-urile indexate și generează seed-uri 3D din bounds + intersecția exactă cu
tile-urile nav disponibile. Detour trebuie să rezolve fiecare seed și să confirme
containment-ul înainte ca el să devină observație. Celulele neobservate se
rafinează adaptiv; structurile fără nav coverage rămân explicit `deferred`.
Detaliile, limitele și probele curente sunt în
[ADR 0037](adr/0037-generic-structure-access-scan-and-worldpack-coverage.md).

Execuția planului este resumabilă per seed. Fiecare checkpoint separă punctele
confirmate în WMO, rezolvările în afara structurii, lipsa unui poligon nav și
erorile reale. Agregatorul refuză scope-uri incomplete sau cu erori și unește
numai evidence-ul acceptat. Cripta Deathknell are 27/27 checkpointuri, 5
observații acceptate și 4 deschideri geometrice unice. Scanarea globală a ajuns
la 3.324/3.324 seed-uri și 121 structuri complete, fără erori de worker;
snapshotul atomic curent include cele 66 de structuri cu observații confirmate,
cu 171 probe, 896 boundary chains și 240 de deschideri. Alte 55 structuri sunt
complete fără WMO confirmat, iar 46 de seed-uri păstrează explicit semantică
statică incompletă; nimic din aceste două categorii nu este inventat în graf.
Protocolul și corecția de floor grouping sunt în
[ADR 0039](adr/0039-resumable-structure-access-scan-checkpoints.md).

### Catalogul 3D pe build și expansiune

Movement Engine nu mai acceptă un nav root numai fiindcă include un fișier cu
numele `Azeroth`. Înainte de mișcare, catalogul extern verifică launch receipt-ul,
versiunea/buildul clientului, hash-ul `Map.dbc`, relația Map ID→nume intern,
fișierul 3D `.map` și setul exact de tile-uri `.nav`. Coverage-ul este declarat
separat pentru hartă, interioare și semanticile de drum. Fiecare tile trebuie
să aibă exact o mască `.road` pe aceleași coordonate ADT; fișierele și seturile
sunt verificate prin hash. Profilul activ TBC are 24 tile-uri și 24 semantici și
este intenționat `partial/partial/partial`.

Rendererul, awareness-ul local și plannerul rămân comune tuturor expansiunilor.
MPQ/WDBC și CASC/DB2-WDC intră prin adaptoare versionate și primesc catalog
propriu; nicio familie nu moștenește mesh-ul alteia. Contractul și gate-urile de
extindere sunt în [ADR 0033](adr/0033-versioned-client-world-catalog.md).

În terminologia proiectului, „TBC Anniversary” nu înseamnă clientul original
`2.4.3`. Este linia modernă pornită de la `2.5.5`, cu asset/container și API
moderne; suportul se declară numai pentru buildul complet observat. Clientul
oficial a avansat deja la `2.5.6`, deci `2.5.5` descrie o familie/bază utilă,
nu un pin etern. Ascension, Turtle sau alt realm care adoptă această linie va
primi profil separat dacă buildul ori conținutul diferă.

Profilul candidat `tbc243-tirisfal-silverpine-v1` are 24 de ADT-uri din
Tirisfal și Silverpine, cu semantică de drum inclusă în bake. Un query Detour
unic Deathknell→Shadowfang poate alege un frontier local greșit; acesta nu este
tratat ca rută lipsă și nici reparat prin `via Brill`. Plannerul global A* dă
ordinea semantică, iar validatorul adaptiv încearcă ținte locale la 60 yd. La
un frontier parțial revine monoton la celulele fine ale aceleiași rute, apoi
reia orizontul mare. Proba offline completă a ajuns exact la Shadowfang după 86
de coridoare locale și o singură rafinare. Profilul rămâne `partial`, iar
profilul v1 nu a fost activat deoarece a regresat startul din criptă.

Profilul promovat `tbc243-tirisfal-silverpine-v2` combină cele 16 tile-uri
suplimentare cu cele 8 tile-uri corectate din profilul stabil și re-sigilează
întregul set. Cele cinci regresii au trecut atât loose, cât și direct din
WorldPack. UI-ul și runnerul folosesc acest profil pentru pornirile noi; detaliile
și hash-urile sunt în
[ADR 0038](adr/0038-promote-24-tile-worldpack-with-crypt-regression-preserved.md).

Pipeline-ul de coverage nu mai pornește de la dreptunghiuri ghicite. Inventarul
MPQ citește toate cele 83 de map ID-uri TBC din `Map.dbc` și a găsit 3.610
ADT-uri pe 35 de hărți, plus 74 WDT-uri. Fiecare hartă poate fi extrasă bulk
într-o destinație nouă, apoi trece separat prin semanticile de suprafață, BVH,
navmesh, catalog și probe. `Shadowfang` este primul profil de instanță al
acestui flux: manifestul cere exact 25 ADT-uri și un WDT, inclusiv tile-uri
textureless cu road affinity neutră.

Extinderea aflată acum în bake nu este o extindere Shadowfang sau
Deathknell–Brill, ci întregul `map_id=0` din clientul TBC 2.4.3.8606: 687 ADT-uri
distincte din Azeroth și 687 sidecar-uri de drum. Se construiește într-un root
staging separat, fără să modifice WorldPack-ul activ de 24 tile-uri. Un profil
care declară terrain coverage `complete` nu mai poate genera catalog doar din
fișierele găsite: trebuie să prezinte inventarul pin-uit și coada de bake
recalculată, iar fiecare coordonată ADT, nav și road trebuie să coincidă exact.
După bake urmează aceleași regresii stabile, indexarea tuturor structurilor și
scanarea generică; abia apoi poate fi schimbat un default. Strategia de
promovare este în
[ADR 0040](adr/0040-full-azeroth-staged-worldpack-promotion.md).

Coverage-ul static se extinde în același staging și la celelalte continente
playable ale clientului pin-uit: `Kalimdor` (`map_id=1`, 1.018 ADT-uri) și
`Expansion01`/Outland (`map_id=530`, 800 ADT-uri). Aceste numere provin din
inventarul MPQ exact, nu dintr-un dreptunghi presupus. Fiecare hartă trece
separat prin extracție, semanticile de drum, MapBuilder, audit structural,
catalog și sigilare; nu primește autoritate doar fiindcă alta a trecut.

Comportamentul controllerului are un al doilea coverage, distinct de existența
geometriei. `world_steering_corpus` generează până la 50 de cursuri locale
uniforme în fiecare ADT, validează capetele cu o hartă încărcată persistent și
acceptă numai coridoare Detour complete. Fiecare coridor acceptat rulează cel
puțin 100 de variații ale poziției, facingului, vitezei și intervalului de
observație. Curbele ascuțite, portalurile înguste, pantele, spațiile închise,
inseturile și detururile de doodad urcă la 1.000; hairpinurile și portalurile
la scara capsulei urcă la 10.000. Raportul separă explicit ADT selectat,
endpoint indisponibil, query eșuat, coridor parțial, simulare și quality gate;
un tile de coastă fără curs circulabil nu este declarat fals eșec de steering.
Fiecare tile finalizat este scris atomic ca checkpoint validat. Identitatea lui
include hash-urile WorldPack-ului, contractului, runnerului și controllerului;
o reluare nu repetă tile-urile identice, dar recalculează automat dovada când
se schimbă codul ori politica. Raportul păstrează și geometria brută a
coridorului, astfel încât un caz-limită poate fi reprodus fără o nouă extracție
sau query Detour.

În coverage-ul default curent de 24 tile-uri, Azeroth are 197 de WMO-uri
indexate: 121 au intersecție nav și au primit 3.324 seed-uri generice, iar 76
sunt raportate `NAV_COVERAGE_ABSENT`. Shadowfang are separat 29 de WMO-uri
eligibile și 825 seed-uri produse de același planner. Acestea sunt cozi de lucru
verificabile, nu declarații că toate interioarele au fost deja descoperite. Coada
default de 3.324 seed-uri este acum completă; 66 structuri au dovezi agregate,
55 sunt complete fără WMO confirmat, iar coverage-ul rămâne parțial la nivel de
continent și volum interior.

## Editorul atlasului și demonstrația manuală

Atlasul extern păstrează aceeași transformare `WorldMapArea.dbc:Tirisfal` la
orice zoom și pan: coordonata afișată sub cursor este coordonata folosită de
joc, navmesh și planner. Operatorul poate desena waypoints, zone de roaming,
obstacole candidate, rute interioare și puncte de reintrare după moarte.

Modul `START — merg eu cu personajul` înregistrează o demonstrație direct din
mersul manual. Filtrul păstrează puncte la minimum `0.75 yd`, respinge salturile
sau pierderea continuității, deduce orientarea din tangenta deplasării înainte
și afișează traseul cu săgeți de sens pe atlas. La `STOP`, rezultatul devine
`manual_demonstration` cu `execution_authority=false`: este prior de cost și
exemplu de învățare, nu coridor executat orbește. Contractul complet este în
[ADR 0030](adr/0030-manual-demonstrations-are-navigation-priors.md).

## Poziționare fără omnisciență

În ordinea confidence:

1. API client-visible verificat pentru pose/zone coordinates.
2. Minimap și landmark localization.
3. Dead reckoning din comenzile executate, timp și facing observat.
4. Semantic navigation: „în apropierea NPC-ului”, „la intrarea clădirii”, „pe drumul dintre două POI-uri”.

Plannerul păstrează uncertainty. Când eroarea crește, încetinește, caută un landmark, recapturează sau cere takeover; nu inventează coordonate.

## Controlul mersului

Plannerul nu ține taste apăsate direct. Produce intenții scurte și expirabile, de exemplu:

```text
turn.right for <= 120 ms
move.forward for <= 250 ms
observe pose/collision
replan or continue
```

PA-MPPI simulează secvențe scurte de astfel de primitive cu modelul de mișcare calibrat pentru target și alege traiectoria cu cel mai mic cost sigur. Implementarea vectorizată rulează implicit 1.000 de traiectorii × 56 pași pe o fereastră de 2,8 secunde, cu regularizare path-integrală, warm start și obstacole dinamice extrapolate. Filtrul de comandă cere confirmare înaintea inversării RMB, dar permite microcorecția persistentă când actorul s-a depărtat de centru; astfel nu confundă tremuratul de sampling cu recadrarea necesară înaintea unei curbe. Execution Gateway verifică mode, focus, timeout, pose state, obstacle/stuck state și takeover înainte de fiecare segment. `MANUAL` anulează imediat coada. Dacă planul asincron nu este gata ori nu mai corespunde observației, sistemul folosește followerul geometric determinist sau se oprește.

Baseline-ul geometric implementat după proba live nu mai trimite pași open-loop
de 650–950 ms. Rulează la aproximativ 20–25 Hz, proiectează monoton poziția pe întreaga
polilinie, folosește look-ahead în timp și emite cel mult un tick de forward și
o microcorecție de mouse de 1–8 pixeli. La un colț care nu poate fi tăiat în
  siguranță oprește forward numai pentru pivot și reobservă. PA-MPPI este
  implementat și validat offline; baseline-ul closed-loop este fallback-ul
  determinist și comparatorul lui, nu o coborâre la waypoint walking.

Facing-ul de combat folosește aceeași axă camera-coupled, dar alt controller și
alt gate. Decizia, diagnosticarea externă și criteriul de promovare sunt în
[ADR 0026](adr/0026-continuous-facing-servo-and-movement-lab.md).

## Journey întrerupt de combat

Runnerul de navigație observă starea de combat înainte de primul input și la
fiecare frame de control. Implicit, când apare combatul, el eliberează toate
controalele și predă `COMBAT_HANDOFF_REQUIRED`; nu încearcă să casteze sub
runtime arm-ul de movement.

Pentru deplasarea LAB, supervisorul poate primi explicit
`--continue-through-routine-aggro` și `--minimum-travel-health-fraction 0.55`.
În acest profil, un aggro de rutină nu oprește W cât timp fracția de viață
observată rămâne peste prag; scopul este pierderea leash-ului prin continuarea
drumului. Opțiunea nu acordă cast, target sau combat authority, iar direct
runnerul rămâne fail-closed dacă flagul lipsește. Un health gate încălcat,
rezultat necunoscut sau incident non-rutină cere în continuare handoff/stop.

Supervisorul extern pornește Combat Engine cu gate separat. Numai o victorie
demonstrată prin `TARGET_DEFEATED` pornește un nou ciclu de navigație. Modul
autonom păstrează aceeași destinație semantică și face A*/Detour din nou din
poziția live; ruta desenată reia de la cel mai apropiat waypoint logic. Nu se
salvează un ocol sau un punct special pentru locul luptei. Timeoutul, rezultatul
necunoscut și eșecul opresc fail-closed. Contractul complet este în
[ADR 0045](adr/0045-separate-authority-journey-combat-handoff.md).

## Stuck recovery

Recovery escaladează bounded:

1. stop + fresh observation;
2. micro-turn și step;
3. strafe/backstep;
4. jump numai dacă traversal profile permite;
5. local replan cu obstacle temporar;
6. global replan;
7. fail-safe/manual takeover.

Nu există rotație infinită sau spam de jump.

## LAB vs Champion

CMaNGOS mmaps pot spune evaluatorului LAB dacă o rută era validă și cât de aproape a fost de optimum. Championul primește numai scor/skill promovat după teste, nu ruta oracle, coordonate DB, spawn paths sau hidden collision state.

## Pașii de implementare

1. `PA-024A`: MovementGoal/PathProposal contracts și grid A* deterministic — implementat.
2. `PA-024B1–B4`: capture, pose contracts, visible self coordinates și client-asset 2D calibration — implementate la scope-ul documentat.
3. `PA-024B5`: synchronized pose/action recorder și motion calibration.
4. `PA-024F1/F2`: Execution Gateway și Win32 user-mode adapter — implementate,
   review independent CLEAN și validate cu runner live bounded.
5. `PA-024F3a`: first-displacement gate pe envelope LAB mic, fără combat sau claim de navigation completion.
6. `PA-024C`: Recast tile builder și Detour query adapter.
7. `PA-024C2`: top-down Navigation Debug Visualizer, apoi world-aligned projection.
8. `PA-024E0`: geometric curvature-limited spline follower baseline.
9. `PA-024D/E1/E2/E3`: tactical costs, common benchmark, PA-MPPI și behavior-tree recovery.
10. `PA-024F3b`: bounded production-navigation LAB course cu takeover instant.
11. `PA-024G`: corpse-run portabil implementat și validat live; event-hunt și
    PvP pursuit benchmark rămân următoarele extensii.

Ordinea accelerată și auditul proiectelor similare sunt blocate în [ADR 0019](adr/0019-clean-room-prior-art-and-first-movement-gate.md). Primul gate demonstrează controlul closed-loop și calibrarea; nu înlocuiește Recast/MPPI și nu coboară standardul de producție.
