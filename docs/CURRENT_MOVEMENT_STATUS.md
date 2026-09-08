# Predator — punct de continuare pentru stabilitate

Actualizat: 2026-09-07. Acest document este punctul de intrare curent; handoff-ul
lung rămâne arhivă. Nu conferă permisiuni de execuție.

## Stare curentă — reper pentru continuare

Nou: evaluator continuu al volumului corpului, numai offline; 153 teste PASS.
32 segmente din virajul ebd340cd evaluate pe 1947 triunghiuri WMO verificate.
Segmentul 85→86 are separare estimată 0.181 yd față de o față aproape verticală;
Z minus 0.25 yd schimbă rezultatul în suprapunere −0.043 yd. Sensibilitate
ilustrativă, nu eroare calibrată și nu dovadă de coliziune reală.
Z provine din proiecția traseului, corpul este o ipoteză; nu există autoritate
de mișcare sau integrare live/CC. v34/controller/cameră rămân neschimbate.
Urmează sprijinul și suprafața din cadrele 83–87, apoi o corecție delimitată;
nu încă un reglaj de yaw. Detalii: `adr/2026-09-07-continuous-body-volume-evaluator.md`.

Istoricul ultimei probe live (starea clientului nu a fost reverificată în audit):

Ultima intervenție: candidat de rezervă de rotire 8aa5af8, probă filmată
59fe4963, NEPROMOVAT. Reducere modestă a abaterii interioare 2.161→1.981 yd,
schimbări de semn 7→9, fără câștig de timp; zero recuperări în ambele probe.
Controllerul este restaurat exact la 7b0dfe0, cu 292 teste relevante PASS
după revenire. Nu s-au retras indexul memoriei, Stop robust, v34 sau Anti-AFK.
Predator readus la startul Shadow Grave și godmode LAB ON.
Urmează evaluarea volumului corpului/distanțelor în primul palier pe traseul
efectiv, nu o nouă creștere de yaw sau cosmetizarea camerei.
Geometria ebd340cd se reproduce exact pe 140 cadre; maximul global 2.995 yd
este la handoff, cel interior este 2.161 yd. Sursa nativă curentă nu trebuie
confundată cu executabilul v34: candidatul nativ mai vechi a fost respins.
Detalii: `adr/2026-09-07-geometric-turn-budget-trial.md`.

Nou: optimizare a memoriei dinamice validată live pe bd3f37e/v34, proba
ebd340cd-ba97-4a5b-a726-40246ce9d0eb, OPERATOR_STOPPED, film păstrat.
Maximul etapei dinamice 307.8 → 10.635 ms; cicluri peste 200 ms: 9 → 0.
298 cadre/294 forward/zero recuperări. 344 teste relevante PASS.
Prima probă post-index a pierdut raportul din cauza unui PermissionError la
fișierul Stop; corectat separat fail-closed și repetat cu raport complet.
Nu s-au schimbat controllerul/camera/v34. Abaterea maximă 2.807 → 2.995 yd,
deci humanlike NU este acceptat. Urmează corelarea C03/C04/C05 pe filmul
crypt-summary-index-repeat/crypt-c09-20260907-165019.mp4 și traseul efectiv,
nu alte funcții și nu încă un audit general. ADR:
`adr/2026-09-07-dynamic-summary-covering-index.md`.
Paragrafele de mai jos păstrează cronologia anterioară; proba instrumentată
și optimizarea pe care le anunțau sunt acum făcute.

Corelarea C09 a identificat o lacună de cronometrare: 266.7 ms înaintea
deciziei 80 nu intrau în durata raportată a cadrului. Adăugate măsurători pe
etape și post→post, 283 teste PASS; fără schimbări de mers/cameră. Urmează
proba delimitată instrumentată, nu încă un reglaj de viraj. Detalii:
`adr/2026-09-07-control-cycle-timing.md`. Geometrie replay 100/100 exactă.

Probă C09 nouă pe 1a00290: ieșire filmată, oprire deliberată după segmentul
delimitat; 255 cadre, 248 FOLLOW/7 PIVOT, zero recuperări. Film valid; estimare
vizuală prudentă 11–12 s pentru criptă, fără cronometrare geometrică certificată.
Camera și trecerile strânse rămân neacceptate humanlike. Detalii și următorul
pas: `LIVE_CRYPT_C09_2026-09-07.md`. Nota offline de mai jos este pre-probă.

Lista unificată cerută de operator: `PREDATOR_BACKLOG.md`. Ordinea activă este
cripta înaintea generalizării, fără alte funcții ca substitut pentru acceptare.
Corecție nouă offline: cache-ul controllerului identifica traseul numai prin XY
și păstra Z vechi când se schimba nivelul. Teste roșii înainte, verzi după
semnătura XYZ; 302 teste relevante PASS și replay v34 80/80 exact. La acel pas
nu exista probă live; C09 de mai sus o completează, fără acceptare humanlike.
Detalii, limite și rollback:
`adr/2026-09-07-steering-xyz-cache-identity.md`. Urmează C09, proba delimitată
filmată; nu schimbăm altă componentă simultan.

### Prioritate reconfirmată cu operatorul — 2026-09-07

Corecție importantă de raportare: 33.543/33.571 s reprezintă durata de control
până la raza destinației Deathknell, NU timpul exclusiv al ieșirii din criptă.
Auditul nou al probei 8544bb3c plasează handoff-ul plannerului la 9.625–9.667 s
de la prima observație de decizie, încă la 2.926 yd de reperul deschiderii.
Acesta nu certifică trecerea întregului corp în exterior. Timpul ieșirii complete
rămâne necunoscut până la delimitarea vizuală sincronizată. Referința operatorului
este maximum 10 s; nu o comparăm cu drumul complet prin Deathknell.

Predator readus efectiv la spawn-ul canonic Shadow Grave pe 2026-09-07 și
godmode reafirmat ON; locația a fost verificată vizual în client. Nicio probă
nouă de navigație sau îmbunătățire humanlike nu este revendicată din acest reset.
Prioritatea imediată este exclusiv segmentul spawn–scară–ieșire, filmat și
măsurat separat de preflight și de drumul exterior. Nu trecem la alte medii
până la probe repetabile acceptate. `adr/2026-09-07-crypt-egress-timing-scope.md`.

Shadow Grave și ieșirea sunt scenariul de acceptare curent, nu o excepție
hardcodată. Scopul imediat este ieșirea repetabilă cu distanță verificată față
de obstacole și mișcare acceptabilă vizual. Nu extindem acum la roaming mondial,
hunting sau alte funcții auxiliare. Sonarul este mijloc pentru acest scop;
afișarea razelor în CC nu închide navigația sau localizarea verticală.

Reverificare offline curentă pe baseline v34: primele 80 de cadre din proba
8544bb3c-f0f6-41f1-84d5-8e7952458f56 se reproduc geometric exact (eroare 0).
Sonde suplimentare în cadrele 1/20/40/68/80, fără input. La cadrul 20,
cross-track = 1.662044 yd, peste marja presupusă 0.30 yd. Distanțele radiale
reinterogate sunt condiționale pe proiecția navmesh, nu distanțe fizice
certificate la corp/zid; proiecția schimbă Z în unele mostre. Acest rezultat
nu identifică etajul și nu dovedește singur contactul cu zidul.
Raport local: `data/runtime/operator/crypt-return-baseline-20260907.json`.

Pasul următor delimitat: evaluare integrată a traseului efectiv netezit,
followerului și marjei pe apropiere/viraj/scară. Auditul cu un colț sintetic
brusc nu înlocuiește această verificare. Se alege apoi o singură corecție
generală, cu test pe întreg coridorul și probă LAB filmată. Problema etajului
rămâne explicit deschisă; nu calibrăm din nou pe repere vizuale deja respinse.
După acceptarea criptei: porniri/orientări diferite, apoi alt interior/scară,
pod și exterior. Aceleași algoritme, date geometrice specifice fiecărei hărți.

Anti-AFK în antetul CC: implementat în e5a20b4, verificat on/off și lăsat activ;
278 teste relevante trecute. Este suport operațional, nu progres de navigație.
În această reverificare nu au fost schimbate v34, controllerul sau clientul.

Goal-ul complet este în `SPATIAL_AWARENESS_PLAN.md`; nu este realizat.
Navigatorul păstrat este v34, candidatul de clearance respins nu se reactivează.

- Driverul manual pregătește cursorul înainte de RMB și verifică HWND-ul
  de sub cursor. Prima probă după reconectare: focus păstrat, dar salt mare
  de cameră, respinsă. Lipsea pauza de după RMB-up deja folosită de motor.
  Corecție: 20 ms după down / 50 ms după up, 33 teste PASS. Probă live cu
  pași mici fără saltul anterior, XY neschimbat; camera readusă spre sol,
  nu exact la încadrarea inițială. Controlul final dezactivat. Nu este
  calibrare geometrică sau etaj confirmat. Conectorul persistent poate avea
  încă modulul vechi; testul a folosit proces proaspăt și hash verificat.
  `adr/2026-09-07-driver-camera-cursor-ownership.md`.

- Ultima integrare CC verificată: sonar asincron, 64 raze, API interior/exterior
  și asociere WMO opt-in cu acoperire parțială. Proba staționară: 12/12 mostre
  valide, fără erori. Acestea sunt ultimele dovezi, nu garanție asupra proceselor
  după o repornire. `adr/2026-09-06-wmo-evidence-control-center.md`.
- Z/etaj încă neconfirmate; plafon nedetectat nu înseamnă infinit. Nu există
  încă o calibrare vizuală reală. Proba de proiecție este numai offline.
- Compoziție geometrică a minimapei, comparată cu 3 cadre
  reale și coordonatele addonului decodate cu CRC. Deplasarea conturului și
  cea prezisă din XY diferă cu 0.165/0.707 pixeli pe segmentul verificat.
  Nu este precizie metrică certificată sau identificare de etaj. Centroidul
  săgeții nu este ancoră exactă. `adr/2026-09-06-minimap-geometric-composition.md`.
- Tranziția arhivată a fost verificată: imaginea minimapei se schimbă între
  97–98s, textul subzonei între 99–100s. La 98/99s există încă suprafețe WMO
  suprapuse; proiecția cu seed fix 100 alege nivelul inferior, nu actorul vizibil
  sus. Nu este o regresie live demonstrată. Detalii și limite:
  `adr/2026-09-06-minimap-stair-transition-evidence.md`.
- Continuitate verificată prin 8 interogări offline v34: la 99→100s ruta
  superioară are 7.2 yd, cea subterană 89.1 yd, cea de pe acoperiș e incompletă.
  Proiecțiile pot muta suprafața cerută; nu s-a ales etajul sau impus viteză.
  `adr/2026-09-06-vertical-corridor-continuity-audit.md`.
- Serviciu persistent de continuitate, numai observație.
  8 perechi reale offline: prima cerere 245 ms, apoi 0.2–0.3 ms. Păstrează
  proiecțiile și alternativele; nu confirmă etajul. Executabil separat,
  neactivat în CC și interzis ca înlocuitor de mișcare v34.
  `adr/2026-09-06-persistent-vertical-continuity.md`.
- Cel mai recent pas: integrare opțională `--spatial-sonar-continuity` în
  observerul asincron și prezentarea CC. 94 teste PASS; replay nativ real
  98–100s: așteptare, apoi 16 și 4 rânduri de comparații, fără etaj confirmat.
  Ambii workeri de replay închiși cu cod 0.
  `adr/2026-09-06-vertical-continuity-control-center.md`.
- Opțiunea este acum activă și verificată vizual live, staționar. Publicarea
  raportului LIVE a fost accelerată opt-in, fără creșterea ritmului geometric.
  Proba repetată: 30/30 mostre cu comparație validă, zero erori, XY neschimbat;
  vechime maximă raport 0.324s față de 1.163s înainte. Etaj încă neconfirmat.
  `adr/2026-09-06-live-continuity-publication.md`.
- Urmează dovezi independente despre nivelul actorului la suprafețe suprapuse.
  Nu extindem căutarea de texturi sau auditul latenței fără un defect concret.
  Proiecția camerei este acum separată de contactul actorului. Prima ipoteză
  manuală pentru 8+4 colțuri reale pe platformă este respinsă: 16.492 px fit,
  345.914 px verificare. Nu există încă perechi pixel/vertex confirmate.
  Nu repeta fituri pe aceleași aproximări; sunt necesare asocieri mai sigure.
  `adr/2026-09-06-camera-only-landmark-check.md`.
  Proiecția plană singură nu distinge două niveluri cu același XY.
  Nu promova maximul de corelație la localizare.
  Calea alternativă 3D–pixeli păstrează referințele exacte grup/vertex → world
  și exportul 164 puncte/269 muchii. Nu există încă perechi vertex/pixel validate.
  Nu folosi XYZ-ul proiectat al actorului drept adevăr de calibrare.
- Defectul condițional al enumerării este reprodus numai în fixture; 49 coloane
  reale nu au arătat omisiuni. Nu îl declara cauza ambiguității actuale.
- Anti-AFK și addon0.5.10 au fost păstrate; această etapă nu le-a modificat.
  Traversabilitatea volumetrică, localizarea verticală reală, obstacolele mobile
  și proba de navigație filmată rămân cerințe neînchise ale goal-ului.

## Istoric al etapelor — stările „urmează” de mai jos sunt istorice

Planul etapizat cerut de operator: `SPATIAL_AWARENESS_PLAN.md`.
Probă nouă offline de proiecție vizuală: fit 3D–pixeli cu repere separate de
verificare, fără dependențe noi; 68 teste relevante PASS. Cazul privirii verticale
poate rămâne nediscriminativ. Două cadre reale inspectate: contact ascuns la 85s,
mers/cameră diferită la 92s. Nu există încă repere reale asociate și calibrare
validată; nu conectăm un Z presupus în CC. Urmează perechi vertex/pixel verificate.
`adr/2026-09-06-visual-vertical-projection-probe.md`.
Audit nou al enumerării nivelurilor: ramura nativă cu hit repetat poate omite
suprafețe inferioare, reprodusă în fixture C++ cu corp identic sursei. Totuși,
49 coloane reale în jurul reperului criptei nu arată omisiuni ale suprafețelor
WMO orientate în sus. Nu este cauza live demonstrată și nu schimbăm workerul.
Urmează observație independentă/calibrare pentru etaj, nu filtru geometric
arbitrar. `adr/2026-09-06-height-enumeration-conditional-audit.md`.
Integrarea WMO este acum activată opt-in în sesiunea CC și verificată vizual
staționar, inclusiv redimensionare. 176 teste relevante PASS; 12/12 mostre live
cu bundle corect, fără erori, XY neschimbat. Cripta verificată offline în
prezentare; nu este probă live de identificare a etajului. Urmează dovezi care
diferențiază nivelurile, nu selecție după potrivire statică.
`adr/2026-09-06-wmo-evidence-control-center.md`.
Bundle WMO cu hash extern construit/reîncărcat și integrat opțional în observerul
de fundal; acoperire explicit parțială, fără modificarea CC activ. 168 teste
relevante PASS și integrare offline reală pentru criptă/exterior. Etajul rămâne
neconfirmat, lipsa plafonului nu produce infinit. Urmează configurare și afișare
CC, apoi verificare staționară. `adr/2026-09-06-pinned-wmo-observer-bundle.md`.
Asociere native→WMO verificată offline cu WorldPack complet, index de instanțe
reconstruit și worker verificat. Candidatul inferior se potrivește cu triunghiul
4901/grup1490, abatere numerică ~0,000015 yd; candidatul superior fără hit WMO
rămâne păstrat. 247 teste relevante PASS. Nu este precizia actorului și nu
confirmă etajul. `adr/2026-09-06-native-wmo-surface-association.md`.
Asociere geometrică nouă offline: parser per grup WMO și intersecții pe
triunghiuri, nu bounds. Cele 1947 triunghiuri păstrate din cele cinci grupuri
ale clădirii de referință coincid exact cu BVH existent; două hit-uri distincte
la același XY. 226 teste relevante PASS. Nu certifică etajul și nu este încă
în CC. `adr/2026-09-06-wmo-triangle-group-association.md`.
Audit nou al grupurilor WMO originale: metadatele interior/exterior nu sunt
păstrate în geometria workerului; un parser offline le citește fără rebuild.
Proba criptei pune ambele Z alternative în aceeași cutie interior; proba
Goldshire suprapune cutii exterior/interior. Nu permitem alegerea etajului
după asemenea bounds. Urmează asocierea per suprafață/grup, nu filtru AABB.
`adr/2026-09-06-wmo-group-semantic-audit.md`. Nicio modificare live.
Observație API nouă, addon 0.5.10: interior/exterior și disponibilitatea
funcțiilor de poziție/orientare, prin pachet versionat compatibil cu v1.
477 teste relevante PASS; reload LAB și ambele taburi CC verificate staționar.
Exteriorul actual: IsIndoors=nil, IsOutdoors=1; UnitPosition/GetPlayerFacing
nu sunt funcții disponibile. Nu confirmă etajul sau plafonul, nu produce
infinit. Backup 0.5.9 verificat, v34 neschimbat. Detalii și următorul pas:
`adr/2026-09-06-client-environment-api.md`.
Extensie nouă: 64 raze la patru înălțimi, intervale geometrice până la blocaj,
worker separat și activ numai în sonar. Test nativ și 400 teste Python PASS;
comparare legacy în trei puncte și verificare vizuală CC staționară reușite.
În exterior detectează blocaje joase absente la 1,20 yd. Nu identifică sigur
obiectele, etajul sau volumul liber. `adr/2026-09-06-sonar-height-scan.md`.
Tabul „Sonar” afișează acum distanțe/direcții condiționale, limite, deschideri
și sonde radiale, separat de harta de mers. 373 teste relevante PASS;
verificat vizual staționar în CC, inclusiv redimensionare. Detalii, limite și
rollback: `adr/2026-09-06-sonar-details-panel.md`. Fără schimbare de v34.
În lucru: sonar legat de sesiune/hartă/timp și integrat asincron în CC.
Proba offline cu WorldPack verificat trece; CC repornit și verificat vizual
staționar în LAB: altitudine estimată 98,88 yd, etaj neconfirmat. În 12 mostre
live: fără erori sonar, vârsta poziției sonar 1,24–2,24 s, clock API avansează.
Altitudine, etaj și plafon sunt explicit separate, fără infinit pentru cer:
`adr/2026-09-06-sonar-session-binding.md`.
Goal-ul complet pentru sonar geometric este activ. Extensia de observație
returnează acum nivelurile alternative din asset-uri, validată cu build
izolat pe trei interogări reale; 365 teste relevante PASS. Nu este promovată
în workerul v34; candidatele sunt afișate separat în CC:
`adr/2026-09-06-sonar-vertical-candidates.md`.
Pasul curent: proveniență verticală auditată și alternativele inițiale
păstrate în replay. Proba reală avea două niveluri cu traseu complet, la
121,797379 și 138,729095 yd; alegerea nu este Z observat/etaj confirmat.
99 teste relevante PASS, fără schimbare live. Continuare și riscul priorului
vechi din CC: `adr/2026-09-06-vertical-evidence-lineage.md`.
Nume zonă/subzonă confirmate din API-urile addonului, nu OCR. Importul real
reparat pentru două câmpuri booleene deja exportate; modelul păstrează numele
din SavedVariables drept istoric, nu locație live. 125 teste relevante PASS.
Detalii: `adr/2026-09-06-api-location-labels.md`. Transportul live/afișarea CC
sunt acum implementate și verificate staționar în LAB: Tirisfal Glades /
Deathknell din API, addon 0.5.9, citire asincronă și expirare după 2 secunde.
Nu certifică Z/etajul sau navigația. Detalii, probe și rollback:
`adr/2026-09-06-live-api-location-transport.md`.
Operatorul a clarificat: API prioritar, OCR complementar
sau fallback, păstrarea transportului util preciziei. Regula completă și
următorul pas delimitat sunt în `SPATIAL_AWARENESS_PLAN.md`.

Context spațial: adaptor read-only verificat pe înregistrarea reală, 626
decizii / 166 actualizări, 620 asocieri cu geometrie anterioară. Formatul nu
oferă încă poziție XYZ/etaj/eroare metrică completă; valorile nu sunt inventate.
97 teste relevante PASS. Detalii: `adr/2026-09-06-spatial-trace-adapter.md`.
Următorul pas este dovada de localizare completă și afișarea CC asincronă;
adaptorul nu este încă legat la runtime sau UI.

Intervenție separată cerută de operator: AFK observat în addon → un singur
Space, fără timer sau deplasare. 423 teste relevante PASS și o tranziție AFK
controlată reușită live. Pornire opt-in locală din CC; sesiune delimitată,
nu serviciu Windows nelimitat. Detalii, limite și rollback:
`adr/2026-09-06-observed-afk-single-space.md`. Navigația rămâne v34.

Context spațial read-only adăugat offline: leagă poziția de sesiune/hartă/etaj,
incertitudine și vârsta datelor; recalculează distanțe la limitele raportate,
fără a transforma razele separate în spațiu liber. Nu este conectat la CC
sau motor. Urmează adaptorul de dovezi în replay, fără valori presupuse:
`adr/2026-09-06-observed-spatial-context.md`.
Verificare: 19 teste noi + 68 existente relevante, **87 PASS** în 2,13 s;
verificarea statică trece. Numai dovezi offline, nicio validare live nouă.

Audit generic nou, numai offline: 600/600 sosiri, dar 403/600 depășiri ale
marjei presupuse de 0,30 yd, inclusiv colțuri cu pornire perfect aliniată.
Instrumentul raportează FAIL și cod de ieșire 1; 297 teste relevante PASS
validează instrumentul și comportamentele existente, nu clearance-ul.
Nicio schimbare în motorul activ sau CC. Limite și următorul pas:
`adr/2026-09-06-generic-tracking-clearance-audit.md`.

Ultimul diagnostic confirmă mecanismul: un singur punct inset mutat cu
0,391215 yd schimbă scurtătura aleasă din start de la 0→6 la 0→7.
v34 refuza 0→7 la sonda joasă, mostra 22; candidatul o acceptă.
Rezultatele integrale ale build-urilor instrumentate coincid cu originalele.
Detalii: `adr/2026-09-06-inset-shortcut-causal-trace.md`.

Progres diagnostic ulterior: replay geometric exact în 80/80 cadre pentru
fiecare probă; sursa pre-candidat recompilată izolat reproduce exact primul
coridor v34. Candidatul modifică nefavorabil și apropierea de scară, nu doar
colțul vizat. Detalii și limite: `adr/2026-09-06-first-stall-replay.md`.
Filmarea manuală funcționează; testul automat fără screenshot încă eșuează.

Proba `9d231880-b9fa-40f9-b738-c94c2342799c` a ajuns la Deathknell, dar
evaluatorul existent raportează FAIL: 84,461 s, 87 cadre de mers fără progres,
116 cadre de pivotare și 4 recuperări, față de 33,571 s / 0 / 9 / 0 anterior.
Gate-ul și memoria obstacolelor au fost restaurate byte-exact din copiile
pre-probă; CC este relansat normal, fără candidat, motor oprit. Nu este Stable.
NVIDIA a oprit captura după circa 0,45 s cu `Protected Content`; nu există
film salvat al probei. Verificarea inițială a timerului a fost insuficientă.
Raport și limite: `LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`.
Nu se repetă automat proba și nu se ocolesc protecțiile capturii.

### Istoric — pregătirea înaintea probei (depășit de rezultatul de mai sus)

Actualizare ulterioară: operatorul s-a autentificat; Predator este în world,
resetat canonic în Shadow Grave, godmode și stay-online ON. CC este lansat
temporar cu candidatul exact validat, după commit `922f160` (separarea
producătorului grafului de navigator; 384 teste relevante PASS). Graful și v34
rămân nemodificate; gate-ul original este arhivat pentru rollback în
`data/runtime/operator/live-evidence/20260906-corner-candidate/gate-before-live-trial.json`.
CC: Deathknell, drum autonom, control manual Codex OFF, verificare staționară
21 citiri / 4 secunde BINE. Mersul NU a fost pornit. Alt+F9 a deschis cererea
NVIDIA de activare a capturii desktopului; computer-use nu acceptă permisiuni
de captură. Operatorul trebuie să rezolve acea fereastră înaintea probei.
Nu există încă rezultat live pentru candidat; nu este Stable.

### Dovezile offline anterioare

Stare: candidat de corecție a razei la colțuri comune orizontale, numai offline.
Cod candidat: `7015e3f`; nicio instalare în runtime. Trec 18 cazuri C++,
417 teste Python relevante și toate cele 6 cazuri semantice (529 etape).
Nu este rezolvarea tuturor
colțurilor scării: mostra 108 rămâne neschimbată. Experimentul Recast arată
că erodarea globală ar elimina și pasaje înguste; nu a fost aplicată.
Worker-ul activ v34, CC și WorldPack-ul rămân neschimbate. Clientul afișează
`Disconnected from server`; proba filmată necesită reintrarea în world.
Detalii și condiții de instalare:
`adr/2026-09-06-shared-corner-inset-candidate.md`.

Lista de lucru și ordinea obligatorie: `STABILITY_TASKS.md`.
Analiza video/trace a identificat limitele dovezilor, nu cauza fizică definitivă.
Jurnalul separă acum observația folosită în decizie de poziția după comandă și
păstrează geometria awareness actualizată. 391 teste relevante trec, inclusiv
9 noi; nu s-au schimbat controller/camera/navmesh. Repetarea filmată pe `89e5d56`
a ajuns în 33,571 s: 626/626 decizii și 166/166 actualizări geometrice complete.
Sonde scurte și treceri strânse persistă la scară; nu este aprobare humanlike.
Replay-ul primelor 140 cadre reproduce exact metricile geometrice. La două
mostre, abaterea consumă spațiul disponibil; la alta traseul are el însuși o
sondă scurtă. Testul capsulei/marjei a dus la candidatul restrâns documentat
mai sus, fără reglarea virajelor. Detalii replay: `adr/2026-09-06-egress-geometry-replay.md`.
Raport live: `LIVE_CRYPT_DIAGNOSTIC_2026-09-06.md`;
implementare jurnal: `adr/2026-09-06-movement-decision-evidence.md`.

## Corecție UI după prima probă — 2026-09-06

Harta CC are acum încadrare proporțională și centrare automată la resize,
urmărire limitată de marginile atlasului și resetare persistentă „Toată harta”.
Verificate vizual normal/maximizat, zoom și urmărire; 362 teste relevante trec,
inclusiv 13 noi pentru hartă. Nu s-a pornit mersul. Detalii și rollback:
`adr/2026-09-06-responsive-control-center-map.md`.

Control Center separă acum prospețimea raportului motorului de poziția live.
Raportul vechi nu mai poate rămâne FOLLOW doar fiindcă poziția se actualizează;
oprirea/pauza/pregătirea au prioritate la afișare. Rezultatul verificării
staționare este explicit istoric. Aplicația a fost redeschisă și afișajul
„Motor oprit” verificat vizual cu poziție live, fără pornirea mersului.
343 de teste relevante trec, inclusiv 14 teste noi pentru această regresie;
nu reprezintă rularea întregii suite sau o nouă validare live a mișcării.
Decizie, teste și limite: `adr/2026-09-06-control-center-freshness.md`.

Anti-AFK LAB a fost activat și confirmat pentru sesiunea actuală Predator prin
`Set-LabStayOnline.ps1`. La fiecare nouă intrare în world, se reaplică explicit
godmode și stay-online; acestea nu sunt presupuse persistente peste relogare.
Nu s-au schimbat mișcarea, camera sau harta. Proba de 33,543 s rămâne reușită
tehnic, dar utilizatorul a semnalat mișcare nenaturală și contact scurt cu zidul;
nu este aprobată vizual ca humanlike și nu se promovează Stable.

## Prima verificare live după preluare — 2026-09-06

Prima probă autorizată după preluare: Shadow Grave (spawn canonic) → raza
destinației Deathknell, pornită din Control Center pe codul `bd353f1`, inclusiv
corecția geometrică `ce71543`. Rezultat ARRIVED, 623 cadre, 33,543 s de control,
zero blocaje și zero recuperări. Verificarea tehnică strictă a traseului trece.
Godmode confirmat ON, combat automat zero. Nu s-a schimbat codul controlerului
sau al camerei pentru probă; profilurile existente de cameră au rămas active.

Este **o singură probă reușită**, nu promovare Stable și nu reproducerea mesei
din ME503. Aprobarea vizuală a utilizatorului nu a fost presupusă. Detalii,
artefacte și observațiile rămase: `LIVE_CRYPT_CHECK_2026-09-06.md`.
Secțiunile de mai jos descriu cronologic starea anterioară probei.

## Ce este salvat și ce este validat

- Punct de revenire: tag `checkpoint/pre-stability-20260905`, commit
  `616c19312569be04ae68cb6bde71220513a2bf4e`. Este un checkpoint al muncii,
  **nu o versiune declarată validată live**.
- Ultima schimbare de movement la preluare: respingerea ocolirilor valabile
  numai pentru punctul central, ME-503. Cele 1605 teste sunt raportul istoric;
  nu există probă live ulterioară acestei schimbări în conversația originală.
- Etalon arhivat ME452: verificat din nou read-only pe 2026-09-05, PASS,
  5 artefacte, 76.850.561 bytes. Verificarea hash-urilor confirmă păstrarea
  dovezilor, nu comportamentul codului actual.
- ME485–ME494: zece probe cu PASS tehnic, documentate în
  `movement-engine-problem-log.md`. Aprobarea vizuală rămâne separată.
- `config/movement-lab/crypt-egress-live-trials.json` are zero probe introduse.
  Nu completăm aprobarea utilizatorului din presupuneri și nu mutăm automat
  rezultatele istorice pe versiunea curentă.
- La preluare, `master` era cu 13 commituri înaintea referinței locale
  `origin/master`. Conectivitatea remote nu a fost verificată din nou.

## Primul pas implementat: raportarea din Control Center

Un raport JSON cu rădăcină `null`, listă, număr sau text producea
`AttributeError` în `_crypt_trial_gate_text`, înainte de verificarea tipului.
Funcția este apelată din actualizarea interfeței; eroarea putea întrerupe acea
actualizare. Am reprodus defectul cu teste înainte de corecție.

Acum raportul greșit/missing/incomplet afișează indisponibilitatea, iar raportul
valid afișează explicit probe **aprobate vizual** și limita: istoricul nu
certifică versiunea curentă. Nu s-au schimbat permisiunile, navigația, camera,
memoria obstacolelor sau pragurile evaluatorului. Nu s-a relansat aplicația;
interfața deja deschisă nu trebuie prezentată drept actualizată.

Verificări pentru această schimbare: `test_movement_engine.py` — 255 teste
trecute în 19,278 s; `test_live_trial_gate.py` — 3 trecute;
`test_movement_live_baseline.py` — 2 trecute. Total: 260 teste distincte,
offline, fără client. Suita întregului proiect nu a fost rerulată pentru această
corecție limitată de afișare. `git diff --check` este curat.

## Al doilea pas: pornire numai mers

Tab-ul Mers lansează supervisorul existent cu buget de combat zero. După
clarificarea utilizatorului, continuarea prin aggro este activă, iar godmode
trebuie confirmat ON pentru Predator înainte de armarea mersului. Finalizarea
combatului nu îl mai dezactivează automat. La orice login condus de agent,
se confirmă intrarea efectivă în lume, apoi se activează/verifică godmode;
nu se presupune că simplul Login a ajuns deja în world. Nu există monitor
global nou pentru loginurile manuale. Start verifică din nou înainte de mers.
Tab-ul de combat rămâne separat. Decizia și proba de integrare sunt descrise în
`adr/2026-09-05-movement-only-control-center.md`. Nici această versiune nu a
fost încărcată într-o aplicație live; codul și verificarea offline nu trebuie
confundate cu actualizarea unei ferestre deja deschise.

Prima versiune a separării (`fef2cc1`) a trecut 280 teste. Corecția pentru
aggro și godmode adaugă verificarea că o confirmare eșuată nu poate lansa
mișcarea și că UI nu mai dezactivează automat protecția. Verificarea corecției:
5 teste de lansare, 22 de supervisor și 255 MovementEngine trecute — total 282.
`git diff --check` este curat. Nu s-a rulat întreaga suită și nu s-a făcut probă live.

## Al treilea pas: distanța întregului segment de ocolire

Verificarea offline a corecției `616c193` a demonstrat o lacună geometrică:
testul anterior `test_boundary_sample_clearance_adapts_to_valid_narrow_corridor`
trecea, dar producea punctele `(8,25; -1,75)` și `(11,75; -1,75)` în jurul
obstacolului `(10; 0)`. Distanța segmentului dintre ele este `1,75 yd`, sub
raza obstacolului `1,0` plus marja corpului `1,25`, adică `2,25 yd`.
Reproducerea a executat testul existent și a capturat rezultatul funcției reale,
fără input, procese live sau modificări ale controlerului. Verificarea diagonalei
colțurilor nu demonstrează clearance-ul întregului segment. Aceasta este o
lacună confirmată offline, nu dovada că explică singură tot eșecul live ME503.

Corecția verifică acum segmentele ghidajului real, inclusiv proiecțiile și
continuările reutilizate, nu numai colțurile. Candidatul conservator respectă
raza obstacolului plus marja existentă a corpului. Testul vechi, cu datele
neschimbate, cere acum respingere. Cele 7 teste noi verifică și arcuri sigure,
rotație/translație și variante nesigure de continuare. Trec și cele 255 teste
MovementEngine, 5 de lansare, 22 de supervisor și 12 pentru memoria obstacolelor:
301 teste relevante. Nu s-a rulat întreaga suită a proiectului.
Decizia și limitele sunt în `adr/2026-09-05-clearance-segment-validation.md`.
Nu s-a făcut probă live și nu s-a promovat această versiune Stable.

## Următorul pas delimitat după prima probă

Nu schimbăm controlerul sau camera. Utilizatorul a autorizat probele LAB;
următoarele verificări sunt repetabilitatea ieșirii, apoi reproducerea
mesei/ocolirii sub scară din ME503. Înainte de
input se confirmă profilul, clientul LAB, poziția de început, camera, armarea și
filmarea. Oprirea și sursa observațiilor rămân protejate. Nu se execută un bake
global, nu se schimbă controlerul și nu se extind dungeon-urile în această etapă.

## Reguli pentru continuare

O schimbare mică → teste relevante → probă live autorizată dacă schimbă mersul
→ acceptare sau revenire. Commiturile de diagnostic nu sunt promovări Stable.
Păstrăm separat codul, configurația, identificarea WorldPack-ului, memoria
inițială și dovezile. UI, video și testele sintetice nu dovedesc singure autonomie.
