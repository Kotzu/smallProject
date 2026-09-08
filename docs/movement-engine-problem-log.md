# Jurnal probleme și soluții — Movement Engine

Acest jurnal separă observația din gameplay de presupuneri. O problemă este
marcată rezolvată numai după ce are cauză reproductibilă, soluție generică,
regresie automată și verificare live. Coordonatele de mai jos sunt probe de
regresie, nu trasee executabile hardcodate.

## ME-001 — Buclă de zeci de yarzi între două puncte apropiate

- **Observat:** pe drumul Deathknell–Brill, Predator părăsea brusc drumul la
  aproximativ 90°, intra în pădure, ocolea un copac și revenea la același drum.
- **Probă:** două obiective semantice consecutive erau la aproximativ 12,5 yd,
  dar Detour/A* furniza un coridor de peste 200 yd, cu 128 de poligoane și o
  excursie laterală de peste 100 yd.
- **Cauză:** două suprafețe cyan fizic continue nu aveau legătura topologică
  corectă în navmesh. Ruta era validă pentru graf, dar absurdă pentru mediul
  vizibil. Nu era o decizie intenționată de a folosi pădurea.
- **Soluție:** pentru un coridor local exagerat de lung se încearcă o reparare
  directă numai dacă este dovedită fizic la fiecare 0,75 yd: există sol pe
  același strat, panta respectă exact profilul cu care a fost construit
  WorldPack-ul, tunelul complet al capsulei este liber și nu există obstacol
  jos (gard, căruță, buturugă) sau la nivelul corpului. Pragul duplicat de
  pantă, mai strict decât profilul WorldPack, a fost eliminat.
- **Fără hardcoding:** regula nu conține nume de zonă, drum, copac ori
  coordonate. Pădurea rămâne walkable și poate fi aleasă când reprezintă o
  scurtătură coerentă.
- **Regresie:** cazul defect este redus la 18 eșantioane coliniare pe cei 12,5
  yd, cu `topology_gap_direct_shortcut_applied=true`; o secțiune vecină cu
  căruță păstrează deturul și raportează `doodad_detour_count>0`.
- **Verificare live:** Brill–Deathknell cu workerul v34 a ajuns la destinație în
  4.607 cadre, 115/115 obiective semantice, fără recovery, fără replan de
  coliziune și fără rută hardcodată.
- **Stare:** soluția generică este verificată offline și în sens invers live;
  traversarea completă din spawnul criptei spre Brill rămâne regresia live
  obligatorie înainte de închiderea problemei.

## ME-004 — Ocoliri alternante și traseu care se încrucișa lângă obiecte

- **Observat:** în apropierea unei căruțe, fiecare segment al coridorului putea
  alege independent altă parte a aceluiași obiect; rezultatul era o buclă sau
  un traseu în X, deși fiecare segment era izolat valid.
- **Cauză:** tunelul fizic folosea 1,67 yd ca rază efectivă și trata toleranța
  de steering ca volum corporal. În plus, alegerea primului detur valid nu
  compara rezultatul complet al alternativelor stânga/dreapta.
- **Soluție standalone:** profilul corpului folosește raza standard de 0,389
  yd plus o marjă separată de 0,30 yd. Alternativele de la nivelul superior
  sunt comparate după lungimea totală, iar după evitare se elimină orice
  inversare numai dacă întregul chord este redovedit pe sol, pantă, rază joasă
  și tunelul capsulei.
- **Fără hardcoding:** nu există ID de căruță, coordonată sau nume de zonă;
  aceeași regulă operează pentru orice M2/WMO din orice WorldPack compatibil.
- **Regresie:** cazul forward păstrează ocolirea cu un singur detur, cazul
  reverse cu două detururi; ambele au zero segmente fizice nerezolvate.
- **Stare:** verificat offline și trecut live în sens invers fără recovery;
  calitatea vizuală rămâne urmărită în traversările repetate.

## ME-005 — Validarea „a ajuns” nu este suficientă

- **Observat:** un test putea raporta `ARRIVED` chiar dacă în interiorul lui
  existau o abatere mare, pivotări sau o recuperare vizibil robotică.
- **Soluție:** fiecare rulare păstrează traiectoria pe cadre și este evaluată
  separat prin: recovery/replan, pivotări, abatere de coridor, regres de
  distanță și filmarea gameplay. `ARRIVED` dovedește funcționalitate, nu
  humanlike quality.
- **Stare:** criteriu activ; rularea Brill–Deathknell v34 are zero recovery și
  zero replan, dar pivotările și trecerea pe lângă căruță rămân probe vizuale,
  nu sunt ascunse sub statusul final.

## ME-006 — Ocolirea învățată pornea prea târziu și tăia colțul

- **Observat:** la pasajul îngust, personajul atingea marginea, începea o
  ocolire corectă, dar trecea la al doilea braț când încă se afla la aproape
  1,5 yd de primul reper. Astfel, pure pursuit tăia din nou interiorul curbei.
- **Cauze generale:** raza de sosire la un reper de clearance era cât raza
  aproximativă a unui player, iar direcția coliziunii putea fi calculată din
  camera încă în rotație în locul intenției curente de mers. În plus, memoria
  confirmată era încărcată și raportată, dar nu modifica preventiv ruta.
- **Soluție standalone:** reperul de degajare trebuie atins în limita a 0,5 yd;
  raza coliziunii urmează mai întâi lookahead-ul curent, apoi facingul observat.
  La planificarea oricărei rute, fiecare obstacol local confirmat care
  intersectează tubul traseului generează ambele ocoliri laterale. Cele trei
  brațe locale ale fiecărei variante sunt reproiectate și validate pe
  navmesh-ul clientului, iar motorul inserează numai varianta validă cu
  lungimea totală minimă. Orice eșantion rar al atlasului aflat deja în
  anvelopa obstacolului este înlocuit, astfel încât curbura începe din ultimul
  punct liber, nu după contact. O ocolire locală este memorată numai după ce
  toate brațele ei au fost validate și parcurse complet. Pentru a nu confunda
  un NPC/player mobil cu geometria statică, priorul permanent cere două
  observații independente. Nicio experiență confirmată nu mai expiră.
- **Fără hardcoding:** algoritmul nu cunoaște Deathknell, porți, torțe sau
  coordonate. Testul automat folosește o hartă sintetică numită
  `SyntheticWorld`, unde o latură este blocată, și dovedește că motorul alege
  cealaltă latură numai după validarea geometrică.
- **Probe:** `c07dadfc` a demonstrat recuperarea după contact. `ccf97b4a` a
  evitat contactul, dar două repere ascuțite au produs 40 de cadre de pivot.
  După eliminarea eșantionului din anvelopa obiectului, `00120cd6` și
  `0d61cf93` au trecut pasajul cu zero coliziune, 1–2 cadre de pivot, maximum
  0,142 s fără progres și 3,63–3,74 yd distanță minimă. Rularea finală a ajuns
  la Brill cu 132/132 obiective, zero recovery și zero replan. După protecția
  de separare static/dinamic, suita completă are 995 teste trecute.
- **Stare:** rezolvat și verificat live pentru clasa generică de obstacol static
  confirmat; separarea entităților dinamice este urmărită distinct în ME-007.

## ME-007 — O entitate mobilă poate semăna cu un obstacol static

- **Observat:** la aproximativ 2210/635, prima traversare a declanșat o ocolire
  locală. Filmarea arată în același interval un abomination cu nameplate verde
  care traversează drumul. Aceasta este o inferență vizuală puternică, nu încă
  o identitate de entitate citită structural.
- **Risc:** promovarea imediată ar înscrie poziția unui NPC/player în harta
  permanentă și ar crea ocoliri inutile atunci când entitatea a plecat.
- **Protecție standalone aplicată:** o singură ocolire reușită rămâne
  provizorie și nu poate modifica rutele viitoare; expiră din setul activ după
  șapte zile. Numai observațiile repetate pot confirma geometria în schema
  actuală. Rularea `0d61cf93`, în care priorul experimental fusese activ, este
  păstrată ca probă: a evitat coliziunea, dar a produs 42 de cadre de pivot și
  nu este acceptată drept humanlike.
- **Soluție standalone implementată:** `DynamicEntityTracker` primește un
  contract screen-space independent de adaptor, asociază observațiile,
  estimează viteza și incertitudinea și le elimină după 0,8 s fără observație.
  `DynamicCollisionAvoidance` anticipează ocuparea culoarului, păstrează W+RMB,
  alege latura numai dacă probele navmesh statice îi acordă clearance și
  cedează trecerea dacă ambele laturi sunt nedovedite. Urmele nu au API de
  scriere în WorldPack, navmesh ori memoria obstacolelor statice.
- **Adaptor curent:** TBC 2.4.3 citește read-only nameplate-uri roșii, galbene
  și verzi din același frame DXGI. Profilul de culoare este în afara nucleului;
  alte versiuni de client pot furniza același contract prin alt adaptor fără
  să schimbe trackerul sau logica de steering. Analiza folosește un eșantion
  scalat și a măsurat aproximativ 15 ms pe dimensiunea ferestrei curente.
- **Regresie:** 11 teste noi acoperă trei reacții, excluderea UI, respingerea
  texturilor verzi mari, identitatea temporară, viteză, TTL, maturitatea de cel
  puțin două cadre, alegerea celeilalte laturi când geometria blochează
  preferința și yield când nicio latură nu este dovedită. În plus, o urmă nouă
  nu poate ascunde un risc matur, iar corecția coridorului nu poate inversa
  stânga/dreapta în timpul aceleiași ocoliri active.
- **Verificare live filmată:** rularea `6bccfe9b` Brill–Deathknell a ajuns cu
  116/116 obiective, zero recovery și zero scrieri statice; a produs 36 cadre
  `AVOID` și 5 `YIELD`. După stabilizarea arcului, rularea `0944666a` spre
  Brill a ajuns cu 82/82 obiective, zero recovery/replan și zero scrieri
  statice. Toate cele 38 cadre în care `DYNAMIC_AVOID` controla efectiv
  mișcarea au păstrat aceeași direcție a arcului. Filmarea arată yield-ul de
  0,76 s în fața unei entități care venea din sens opus pe un pod îngust;
  ambele laterale erau nedovedite, deci oprirea a fost intenționată.
- **Stare:** implementat și verificat live în ambele sensuri pe entități reale,
  fără mutație statică. Nu este încă declarat universal/humanlike: criteriul de
  portabilitate cere încă o probă într-un alt context de hartă/client.

## ME-008 — Preview-ul putea uni un coridor complet cu un frontier parțial

- **Observat:** prima reluare autonomă Deathknell–Brill s-a oprit sigur cu
  `partial corridor must retain its requested stop` înainte să poată finaliza
  traseul.
- **Cauză generală:** rolling preview-ul presupunea implicit că ambele picioare
  Detour erau complete. Când piciorul curent era parțial, `replace()` moștenea
  `complete=false`, dar ștergea destinația solicitată. Dincolo de eroarea de
  contract, o astfel de îmbinare ar fi ascuns un gol topologic nedovedit.
- **Soluție standalone:** un preview de curbă se formează numai dacă ambele
  coridoare sunt independent complete. Orice frontier parțial rămâne vizibil
  și este predat replannerului generic deja existent; nu este legat printr-un
  chord, waypoint sau prag local inventat.
- **Fără hardcoding:** regula verifică exclusiv `NavCorridor.complete`; nu
  cunoaște harta, zona, podul ori coordonatele incidentului.
- **Regresie:** testul sintetic respinge separat un picior curent parțial și o
  continuare parțială, dar păstrează îmbinarea a două coridoare complete. Cele
  56 de teste relevante trec.
- **Verificare live:** după remediere, rularea `0944666a` a continuat din
  poziția live și a ajuns în Brill în 2.679 cadre, 82/82 obiective semantice,
  zero recovery, zero partial replan și zero obstacole persistate.
- **Stare:** cauza și remedierea generică sunt verificate la locul incidentului;
  proba de portabilitate într-un context de hartă diferit rămâne deschisă.

## ME-009 — O remediere locală putea părea în mod fals o soluție standalone

- **Observat:** ME-007 și ME-008 treceau regresiile și rulările Deathknell–Brill,
  dar aceeași zonă, același continent și același WorldPack nu puteau demonstra
  că Movement Engine nu depinde accidental de contextul testului.
- **Cauză generală:** o probă repetată într-o singură zonă poate valida efectul,
  însă nu separă o regulă de mediu de o coordonată, un nume sau un artefact
  local. În plus, vechiul WorldPack Shadowfang fusese sigilat înaintea
  obligativității auditului geometric exact și a fost respins corect de
  verificatorul actual.
- **Soluție standalone:** validatorul de portabilitate deschide minimum două
  WorldPack-uri sigilate și independente, derivă probele numai din grila
  navmesh și volumele WMO ale fiecărei hărți, interoghează adaptorul real
  `ClientAssetNavmeshQuery`, apoi alimentează aceeași politică de evitare
  dinamică. O evitare este acceptată doar dacă latura aleasă este accesibilă și
  are clearance static; când ambele laterale sunt nedovedite, singurul rezultat
  acceptat este `YIELD`. Validatorul nu are autoritate de input.
- **Integritatea hărții secundare:** buildul vechi Shadowfang a eșuat înaintea
  probei, deoarece nu avea dovada geometrică cerută. Un build curat cu
  corecțiile generale Recast a produs 25/25 tile-uri, toate 25 fiind validate
  structural. Rezultatul a fost sigilat imuabil ca
  `wow.tbc.2.4.3.8606.shadowfang-worldpack-v2`, fără dependență de client,
  server sau emulator la runtime. Pachetul vechi nu a fost suprascris.
- **Fără hardcoding:** sursa validatorului nu conține `Deathknell`, `Brill`,
  coordonate de traseu ori ramuri după numele hărții. Testul automat păstrează
  explicit această interdicție. Scriptul generic de rebuild poate fi lansat
  direct, iar regresia sa verifică entrypoint-ul real, nu doar importul Python.
- **Probă cross-map:** evidența
  `standalone-movement-portability-azeroth-shadowfang-v1.json` este `PASS`
  pentru două pachete și două hărți distincte. Azeroth a ales `YIELD` într-un
  WMO fără laterală sigură; Shadowfang a ales `LEFT`, cu 12 yd clearance și
  accesibilitate navmesh confirmată. În ambele cazuri memoria statică a rămas
  nemodificată, iar toate dependențele runtime externe sunt `false`.
- **Stare:** nucleul și proba offline cross-map sunt implementate și trecute.
  Aceasta nu dovedește încă toate continentele, expansiunile ori adaptoarele de
  client și nu este prezentată ca probă live Shadowfang. Conform criteriului de
  mai jos, o rulare live într-un context diferit rămâne necesară înainte ca
  ME-007/ME-008 să fie declarate universal rezolvate.

## ME-010 — Cunoașterea ieșirilor exista, dar nu participa la planificare

- **Observat:** indexul full-Azeroth și `Structure Access Graph` puteau arăta că
  actorul este într-un WMO și puteau lista deschideri verificate, însă această
  informație apărea numai în Control Center. Un coridor parțial continua să
  intre în fallback/recovery fără să consulte cunoașterea structurală.
- **Cauză generală:** pipeline-ul de scanare și cel de execuție aveau un contract
  de afișare, nu un contract de planificare. În plus, scanarea one-shot încărca
  harta nativă pentru fiecare seed; acest cost nu se putea extinde sănătos la
  cele 42.594 de probe ale continentului.
- **Soluție standalone implementată:** motorul consultă graficul numai pentru
  un traseu direct parțial și numai când awareness-ul confirmă exact structura
  care conține actorul. Fiecare ieșire este reinterogată pe navmesh-ul activ,
  apoi este reinterogată și continuarea spre destinația originală. O ieșire
  imposibilă, prea îngustă, de pe alt etaj, fără progres sau deja încercată este
  respinsă. Un traseu direct complet nu este niciodată înlocuit.
- **Scalare generică:** scannerul reutilizează maximum patru procese native cu
  harta încărcată, păstrează o fereastră bounded de futures și clasifică strict
  fallbackul one-shot. Checkpointurile rămân atomice și resumabile; agregarea
  finală rămâne interzisă cât timp lipsește un seed sau există `PROBE_ERROR`.
- **Fără hardcoding:** testele folosesc `PortableContinent`,
  `PortableDungeon` și identități WMO arbitrare. Nucleul și runnerul nu conțin
  nume de zonă, destinații sau coordonate pentru această regulă.
- **Regresie curentă:** suita completă a proiectului are 1.045 de teste trecute;
  subsetul Movement Engine + Structure Access include două nume de hartă
  distincte, refuzul unei deschideri inaccesibile și protecția traseului direct
  complet. Scanarea full-Azeroth este resumabilă și rulează cu zero erori de
  probă la momentul acestei intrări.
- **Probă cross-WorldPack:** scanarea finală Azeroth are 42.594/42.594 probe,
  1.676 observații confirmate și zero `PROBE_ERROR`; graful rezultat are 10.187
  contururi și 4.754 deschideri. Shadowfang v2 a trecut același pipeline cu
  825/825 probe, 73 observații, 274 contururi, 65 deschideri și zero erori.
  Validatorul a selectat primul candidat derivat geometric pe fiecare hartă:
  pe Azeroth a redus frontiera de la 16,38 la 1,82 yd, iar pe Shadowfang a
  produs o continuare completă. Ambele dovezi declară explicit că nu au folosit
  rute ori coordonate salvate.
- **Stare:** implementat și verificat offline cross-WorldPack. Control Center
  încarcă fail-closed graful final full-Azeroth și îl transmite explicit
  runnerului; proba live humanlike rămâne separată și nu este presupusă din
  validarea offline.

## ME-011 — Contururile globale puteau depăși contractul unei observații locale

- **Observat:** prima agregare intermediară full-Azeroth a fost refuzată de
  schema `structure-access-graph`: două boundary chains conectate aveau mai mult
  de 129 puncte.
- **Cauză generală:** o observație locală este limitată corect la 128 segmente,
  însă agregatorul unește segmente compatibile din observații diferite. Un zid,
  pasaj sau contur lung poate depăși astfel limita unui singur record chiar dacă
  fiecare probă sursă este validă.
- **Soluție standalone:** orice contur conectat este împărțit determinist în
  bucăți de maximum 128 segmente. Bucățile vecine împart exact endpointul;
  niciun punct nu este inventat, niciun segment nu este eliminat sau repetat,
  iar lungimea, corroborarea BVH și hash-urile observațiilor se recalculează
  separat pentru fiecare bucată.
- **Fără hardcoding:** regula operează numai pe cardinalitatea poliliniei și pe
  ordinea topologică. Testul folosește un contur sintetic de 299 segmente și
  obține 128 + 128 + 43, independent de hartă și coordonate.
- **Probă reală:** aceeași agregare care eșuase a trecut apoi schema strictă:
  326 structuri complet închise, 840 observații, 5.304 boundary chains și 2.502
  deschideri. O probă navmesh pe primul candidat derivat geometric a validat
  accesul până la ieșire și a redus distanța de frontier de la 18,729 la 0,906
  yd, fără rută sau coordonată salvată.
- **Probă finală:** agregarea completă full-Azeroth a trecut același contract
  cu 1.676 observații, 10.187 boundary chains și 4.754 deschideri; Shadowfang
  v2 a trecut independent cu 73 observații, 274 chains și 65 deschideri.
- **Stare:** rezolvat offline cross-WorldPack pentru clasa generică de contur
  peste limită.

## ME-012 — Reluarea unei scanări mari recompila aceeași schemă pentru fiecare seed

- **Observat:** după o întrerupere de curent, toate cele 24.563 de checkpointuri
  full-Azeroth erau intacte și fără `PROBE_ERROR`, dar reluarea consuma minute
  înainte să pornească din nou worker-ele native.
- **Cauză generală:** încărcarea fiecărui fragment construia din nou validatorul
  JSON Schema pentru observație, iar verificarea fiecărui awareness construia
  din nou al doilea validator. Schema este identică pentru întregul plan, deci
  recompilarea per seed nu adăuga integritate.
- **Soluție standalone:** scanarea creează o singură instanță verificată pentru
  fiecare schemă și o reutilizează la toate checkpointurile. Aceeași optimizare
  este aplicată raportării și agregării. Fiecare JSON este în continuare citit,
  validat, comparat cu seed-ul din plan și verificat prin hash; nu a fost
  eliminată nicio barieră fail-closed.
- **Fără hardcoding:** API-ul de încărcare acceptă un validator precompilat,
  independent de hartă, numărul de seed-uri, client sau WorldPack.
- **Regresie:** 23 teste Structure Access trec, inclusiv dovada că validatorul
  furnizat este reutilizat și că parserul nu construiește unul ascuns; suita
  completă are acum 1.045 teste trecute.
- **Probă reală:** aceeași reluare full-Azeroth a terminat verificarea și a
  continuat de la checkpointul 24.563 la 26.460 fără rescanarea datelor deja
  acceptate și fără erori de probă.
- **Stare:** rezolvat și folosit pentru reluarea, raportarea și agregarea
  completă a ambelor WorldPack-uri.

## ME-013 — O pană poate lăsa clientul deschis fără identitatea LAB precedentă

- **Observat:** după întreruperea de curent, `Wow.exe` răspundea, dar listener-ele
  LAB 3307/3724/8085/3443 erau oprite. După repornirea serverului, receipt-ul
  clientului indica alt PID/FILETIME decât procesul WoW curent.
- **Cauză generală:** autorizația, receipt-ul de proces, poarta semantică și
  serverul sunt lease-uri/binding-uri independente. Revenirea unui singur
  proces nu demonstrează continuitatea celorlalte după reboot sau power loss.
- **Soluție standalone aplicată:** serviciile au fost repornite numai prin
  launcherele oficiale `Start-LabDatabase`, `Start-LabRealm` și
  `Start-LabWorld`, fiecare cu verificarea propriului listener loopback. Poarta
  semantică a fost regenerată pentru workerul v34 după ce toate cele cinci
  cazuri offline au trecut; cazul invalid a cerut `RESET_REQUIRED`.
- **Protecție păstrată:** `RenewSessionIdentity` poate relega un HWND recreat al
  aceluiași proces, dar nu poate adopta alt PID/creation FILETIME. Nici
  `AcknowledgeWindowRebind`, nici authorization rebind nu ocolesc această
  identitate. Nu a fost relaxat contractul pentru a face testul să pornească.
- **Stare:** stack-ul LAB și Control Center sunt din nou active, iar graful
  final Azeroth este încărcabil și verificat. Testul cu input rămâne oprit până
  la relansarea explicit autorizată a clientului; procesul curent nu este închis
  sau relogat automat.

## ME-014 — Control Center putea rearma Start după pierderea awareness-ului

- **Observat:** încărcarea inițială valida `World Structure Index` și `Structure
  Access Graph`, dar unele ieșiri din proces și erori de lansare configurau din
  nou butonul Start ca activ fără să reevalueze acele artefacte.
- **Cauză generală:** poarta semantică și readiness-ul structural erau tratate
  separat în UI, deși motorul autonom are nevoie de ambele contracte.
- **Soluție standalone:** o singură funcție pură calculează acum readiness-ul
  din poarta semantică, indexul WorldPack, configurarea și încărcarea Access
  Graph-ului, plus orice eroare de binding/hash. Inițializarea, apăsarea Start,
  revenirea după eroare și terminarea unui journey folosesc aceeași decizie.
- **Comportament:** orice artefact lipsă, vechi sau incompatibil ține butonul
  dezactivat și afișează motivul; nu există fallback „autonom fără awareness”.
- **Regresie:** 86 teste Movement Engine trec, inclusiv toate combinațiile de
  refuz și reverificarea fail-closed chiar în handlerul Start; suita completă
  are acum 1.045 teste trecute.
- **Stare:** rezolvat generic; nu conține coordonate, nume de zonă sau excepții
  pentru Deathknell.

## ME-015 — Validarea full-WorldPack bloca interfața Control Center

- **Observat:** după pornire, fereastra apărea dar rămânea `Not Responding`
  aproximativ 40–45 s. Mutarea încărcării într-un thread a redus timpul, nu și
  starvation-ul firului Tk, deoarece validarea era CPU-bound și ținea GIL-ul.
- **Măsurare:** pe full-Azeroth, binding-ul WorldPack dura 10,762 s, indexul
  structural 24,642 s și Access Graph 5,233 s. Din index, validarea JSON Schema
  generică reprezenta 22,473 s, reconstruirea/binding-ul 1,646 s și construirea
  spatial index numai 0,350 s.
- **Soluție standalone:** `jsonschema-rs==0.50.1` este pin-uit ca validator
  compilat Draft 2020-12; meta-schema și regula internă NaN/Infinity rămân
  active. Încărcarea a scăzut la 10,570 s WorldPack + 3,886 s index + 1,514 s
  graph. Validarea și indexul locuiesc acum în serviciul read-only
  `run_structure_awareness_service.py`, într-un proces separat.
- **Protocol:** serviciul emite un receipt `READY` legat de WorldPack/index/
  graph/worker/semantic-gate și răspunde la `NEARBY` pentru raze de până la
  1.000 yd. Răspunsurile compacte sau complete au permanent
  `execution_authority=false`; Control Center cere compact 100 yd.
- **Probă reală:** serviciul a verificat 96.024 structuri și 4.754 deschideri,
  apoi a răspuns la query și `SHUTDOWN` în 16,319 s. După integrare, Control
  Center a răspuns `True` în 20/20 mostre consecutive; CPU-ul UI a rămas la
  aproximativ 0,5 s, în timp ce serviciul lucra separat.
- **Stare:** rezolvat la nivel de proces și protocol, independent de zonă/hartă.

## ME-016 — Snapshotul monotonic vechi supraviețuia unui reboot logic

- **Observat:** după pana de curent, `latest.json` conținea un timestamp
  monotonic din boot-ul precedent. Cum noul ceas era mai mic, expresia
  `now - observed > 1.5` devenea falsă și poziția veche părea proaspătă la
  nesfârșit; UI recalcula inutil ruta și WorldPack-ul pentru acea poziție.
- **Cauză generală:** verificarea avea numai limita superioară a vârstei, nu și
  limita inferioară care separă epocile monotonic diferite.
- **Soluție standalone:** snapshotul este acceptat numai când vârsta este în
  intervalul închis `0..1,5 s`. O vârstă negativă este tratată drept epoch/boot
  diferit și snapshotul este eliminat înainte de planificare sau desenare.
- **Regresie:** test explicit pentru timestamp viitor, proaspăt și expirat;
  suita completă are 1.045 teste trecute.
- **Stare:** rezolvat generic pentru orice reboot, suspend/resume sau fișier
  runtime copiat între sesiuni.

## ME-017 — Entitățile dinamice observate nu ajungeau în Control Center

- **Observat:** runnerul autonom detecta nameplate-uri și menținea track-uri cu
  reacție, viteză și incertitudine, dar publica în `latest.json` numai numărul
  lor final. Panoul Awareness afișa permanent un text generic, deci operatorul
  nu putea verifica ce vede efectiv Predatorul.
- **Cauză generală:** detectorul, trackerul și UI-ul nu aveau un contract comun
  pentru starea dinamică observată. Geometria statică și entitățile vizibile
  fuseseră corect separate conceptual, dar nu și conectate operațional.
- **Soluție standalone implementată:** runnerul publică acum un record
  `dynamic_entity_awareness` validat Draft 2020-12. Recordul conține numai
  track-uri din viewport aflate în visibility-set-ul serverului, etichetate
  `HOSTILE`, `NEUTRAL`, `FRIENDLY` sau `UNKNOWN`, cu timestamp monotonic,
  confidence și incertitudine. Nu are autoritate de input.
- **Fără informații inventate:** fiecare track declară explicit
  `world_position=null` și `distance_yards=null`. Mărimea unui nameplate nu este
  transformată într-o distanță falsă; o distanță de target va putea proveni
  numai dintr-un range witness separat și verificabil.
- **Rezistență la reboot:** Control Center acceptă recordul numai 0..1,5 s de
  la observație. Timestampurile dintr-un boot anterior, datele expirate,
  coordonatele fabricate și `execution_authority=true` sunt refuzate.
- **Regresie:** 97 teste Movement Engine și toate cele 1.045 teste ale
  proiectului trec.
- **Stare:** integrarea standalone și UI sunt implementate și verificate
  sintetic; confirmarea live rămâne în așteptarea unei sesiuni WoW relansate și
  legate explicit de autorizația LAB.

## ME-018 — Un target selectat nu are un telemetru exact în API-ul 2.4.3

- **Observat:** combat HUD avea `IsActionInRange` pentru Attack, Sinister Strike
  și Eviscerate, dar această informație nu era publicată Movement Engine-ului.
  Cerința „câți yards până la target” risca astfel să fie rezolvată printr-o
  estimare vizuală prezentată greșit drept măsurătoare exactă.
- **Cauză generală:** API-ul clientului oferă martori tri-state per acțiune —
  în range, în afara range-ului sau neaplicabil — nu distanța numerică dintre
  două unități.
- **Soluție standalone:** `selected_target_range_awareness` fuzionează numai
  abilitățile legate exact și intervalele lor semantice versionate. Pentru
  Rogue melee rezultatul demonstrabil este `0–5 yd`, `>5 yd`, `UNKNOWN` sau
  `INCONSISTENT`; ultima stare refuză acțiunea în loc să ghicească.
- **Binding de identitate și timp:** recordul conține CRC-ul targetului și
  expiră odată cu observația combat HUD (maximum 600 ms). Control Center îl
  respinge dacă targetul s-a schimbat, timestampul aparține altui boot,
  recordul a expirat ori pretinde `execution_authority`/distanță exactă.
- **Fără hardcoding de bară:** range-ul aparține ability ID-ului semantic, nu
  slotului. Același contract rămâne valabil când spell-urile sunt mutate pe
  alte pagini sau adaptoare de client.
- **Regresie:** contract JSON Schema, fuziune normală și contradictorie,
  publicare în runner și randare/refuz UI; suita completă are 1.045 teste
  trecute.
- **Stare:** implementat și verificat sintetic; confirmarea vizuală live va fi
  făcută în următoarea sesiune LAB autorizată.

## ME-019 — Expirarea track-ului activ nu trebuie să șteargă experiența

- **Observat:** track-urile screen-space expiră corect după 0,8 s pentru a nu
  trata un NPC/player plecat ca obstacol prezent, însă ele nu alimentau nicio
  memorie persistentă. După închiderea runnerului sau o pană, întâlnirea era
  uitată complet.
- **Separare semantică:** starea tactică și memoria nu au aceeași durată.
  `DynamicEntityTrack` rămâne scurt și poate influența evitarea numai cât timp
  este proaspăt. `DynamicEncounterObservation` este append-only și păstrează
  permanent faptul istoric că Predatorul a văzut o entitate.
- **Fără poziție inventată:** nameplate-ul nu demonstrează coordonatele 3D ale
  entității. Jurnalul păstrează poziția X/Y observată a Predatorului, facingul
  vizibil/estimat, reacția, poziția screen-space, confidence și incertitudinea;
  `entity_world_position` rămâne obligatoriu `null`.
- **Persistență standalone:** `dynamic-experience-v1.sqlite3` folosește
  tranzacții SQLite, WAL, `synchronous=FULL`, versiune de schemă și
  `quick_check` la deschidere. Event ID-urile sunt content-bound și inserarea
  repetată este idempotentă; aceeași identitate cu alt conținut este refuzată.
- **Controlul zgomotului:** se memorează numai track-uri mature observate în cel
  puțin două cadre. Baza este legată de numele hărții și hash-ul navmesh, iar
  sumarul pe reacții este publicat read-only în Control Center.
- **Regresie:** validare contract, reopen WAL, idempotency, coliziune de
  identitate, supraviețuirea după expirarea track-ului, integrarea runnerului și
  randarea GUI; suita completă are 1.045 teste trecute.
- **Stare:** implementat și verificat offline; prima observație live va fi
  înscrisă după relansarea autorizată a clientului LAB.

## ME-020 — Combatul întrerupea journey-ul fără reluare autonomă

- **Observat:** operator path avea deja alegerea celui mai apropiat waypoint
  după deplasare, iar modul semantic putea replana din poziția curentă, însă
  runnerul de navigație nu consuma continuu semnalul `in_combat`. Control Center
  pornea direct Movement Engine ori Combat Engine și nu exista o tranziție
  contractată între ele.
- **Cauză generală:** plannerul știa cum să continue, dar lipsea orchestrarea
  dintre două autorități de execuție diferite. Amestecarea lor într-un singur
  loop ar fi lăsat risc de taste ținute și acțiuni emise sub gate-ul greșit.
- **Soluție standalone:** fiecare frame valid primește observația combat HUD.
  La combat, movementul și mouse-look-ul sunt eliberate înainte de publicarea
  `COMBAT_HANDOFF_REQUIRED`. Supervisorul extern, fără backend de input, pornește
  Combat Engine sub acknowledgement separat și acceptă reluarea numai după
  `TARGET_DEFEATED`.
- **Reluare fără hardcoding:** pentru journey autonom se păstrează numai ID-ul
  destinației și se recalculează ruta din poziția live de după luptă. Pentru
  traseu authored se folosește regula generică nearest-logical-waypoint; locul
  luptei nu adaugă coordonate în cod.
- **Fail-closed:** timeout, rezultat copil necontractat, combat eșuat, stop
  operator și bugete epuizate opresc lanțul. Rezultatul supervisorului este
  atomic și validat prin JSON Schema; niciun proces copil nu deschide terminale
  vizibile.
- **Regresie:** sunt acoperite NAV→COMBAT→NAV→ARRIVED, păstrarea destinației,
  separarea acknowledgement-urilor, pornirea deja în combat, bugetele și lipsa
  unui backend direct de input în supervisor. Suita completă are acum 1.054 de
  teste trecute în 79,503 s.
- **Stare:** implementat și verificat offline; neverificat încă live după pana
  de curent și schimbarea identității procesului client.

## ME-002 — 3D Mesh Map rămânea în urmă la poarta Deathknell

- **Observat:** săgeata și harta live rămâneau la poarta Deathknell în timp ce
  personajul continua spre sat.
- **Probă:** viewerul era încă pornit, însă fișierul live rămăsese la secvența
  8979. Procesul bridge se închisese exact după 1.800 secunde.
- **Cauză:** bridge-ul read-only avea o limită implicită de 30 de minute.
- **Soluție:** durata implicită este acum legată de durata de viață a
  viewerului; o limită explicită rămâne disponibilă pentru teste bounded.
  Bridge-ul a fost repornit ascuns și a publicat din nou poziția actuală la
  5 Hz.
- **Regresie:** parserul verifică explicit valoarea implicită `0`, care
  înseamnă „până la închiderea viewerului”.
- **Stare:** rezolvat; poziția live a fost resincronizată.

## ME-003 — Invitațiile de party întrerup testele

- **Observat:** playerbots trimit invitații în timpul testelor de navigație.
- **Soluție:** operatorul are o acțiune fixă și auditată `SetDnd`, care trimite
  exclusiv `/dnd Movement Engine test in progress` după confirmarea vizuală că
  personajul este în world și chatul este închis.
- **Stare:** rezolvat și aplicat sesiunii curente.

## Semantica vizuală a 3D Mesh Map

- **Cyan:** suprafață traversabilă; aceasta este baza A*.
- **Roșu:** geometrie/volum fizic. Influențează traseul numai dacă intersectează
  tunelul ales al corpului; nu declanșează automat ocolirea fiecărui obiect din
  apropiere.
- **Galben:** structură/WMO. Intrarea și ieșirea nu sunt presupuse din culoare;
  trebuie demonstrate prin portaluri, etaje conectate și egress către exterior.

Modurile de navigație rămân separate: Free A*, Road-aware, rută desenată
asistată și demonstrație manuală transformată într-un prior reutilizabil. Peste
ele se aplică ulterior stratul configurabil de risc pentru entități.

## Criteriu de portabilitate standalone

Nicio remediere din acest jurnal nu poate depinde de numele unei zone, de un
server, de un emulator sau de o listă de coordonate din lumea live. Un caz
concret poate apărea într-un test de regresie, însă algoritmul acceptat trebuie
să opereze numai pe proprietăți generale ale WorldPack-ului: topologie,
suprafață, pantă, clearance, portaluri, geometrie și risc observabil.

O problemă observată local este acceptată drept rezolvată numai dacă are toate
cele patru dovezi:

1. este formulată ca o clasă de cauze, nu ca nume de hartă sau obiect;
2. remedierea se află în nucleul standalone ori într-un adaptor versionat, nu
   într-o listă de coordonate;
3. există regresii sintetice care schimbă harta, orientarea și latura liberă;
4. după regresii, o probă live în locul original și una într-un context diferit
   confirmă că soluția generalizează.

Până la îndeplinirea tuturor celor patru, jurnalul spune explicit
„implementat, neverificat live” și nu „rezolvat”.

## ME-021 — Supervisorul journey-combat refuza poziția finală validă

- **Observat:** navigația a avansat autonom din cryptă până la coordonatele
  aproximative `2114, 884`, a eliberat inputul, iar supervisorul s-a oprit când
  încerca să publice rezultatul primului ciclu.
- **Cauză:** contractul supervisorului declara eronat `final_world` drept obiect,
  deși contractul navigatorului standalone îl definește și îl emite drept
  pereche numerică `[world_x, world_y]`.
- **Soluție:** schema supervisorului acceptă acum exclusiv o pereche numerică de
  exact două elemente sau `null`. Nu există excepție de hartă, zonă ori rută.
- **Regresie:** testele supervisorului folosesc forma reală produsă de
  navigator; suita de frontieră operator + supervisor are 66 teste trecute.
- **Probă LAB după remediere:** reluarea din poziția curentă, cu aceeași
  destinație semantică `settlement:brill`, a ajuns la `2258.05, 291.33` cu
  status `ARRIVED`, fără teleport și fără rută desenată.
- **Stare:** rezolvat la nivel de contract standalone și verificat în LAB.

## ME-022 — Client pornit explicit din NVIDIA nu putea fi legat de operator

- **Observat:** clientul corect 2.4.3 era pornit de utilizator din NVIDIA App,
  însă receipt-ul vechii sesiuni aparținea altui PID și operatorul refuza corect
  orice input.
- **Soluție:** acțiunea zero-input `BindOperatorLaunch` acceptă numai un singur
  client cu path/hash/window/realm LAB validate, parent viu exact `NVIDIA App`,
  semnătură Authenticode NVIDIA validă, aceeași sesiune Windows și o fereastră
  temporală de maximum 30 minute. Cere ambele confirmări explicite de risc și
  identitate și recreează receipt-ul înainte de runtime arm.
- **Regresie:** verificările de frontieră demonstrează că binding-ul nu trimite
  input și nu acceptă un launcher generic.
- **Probă LAB:** PID-ul 5824 a fost legat, login/world au trecut checkpoint-urile,
  iar ShadowPlay a produs clipuri H.264 2560×1440/120 FPS în directorul dedicat
  `NVIDIA\Wow.exe`, nu în captura desktop.
- **Stare:** rezolvat și verificat în LAB pentru launcherul NVIDIA explicit.

## ME-023 — Variantele de rută blocau personajul înainte de plecare

- **Observat:** Brill → Deathknell a rămas aproximativ două minute pe loc
  înainte să înceapă mișcarea, deși rezultatul final al plannerului era valid.
- **Cauză generală:** cele trei profiluri risk-aware încărcau din nou toate
  sidecar-urile atlasului și reconstruiau aceeași dilatare near-road. Costul
  identic era plătit de trei ori fără informație nouă.
- **Soluție standalone:** gridul semantic imuabil este încărcat și expandat o
  singură dată per instanță de planner, apoi toate profilurile îl reutilizează.
  Nu există cache global, stare de server sau coordonate de zonă.
- **Măsurare pe atlasul complet:** calculul rece Brill → Deathknell pentru trei
  variante durează 17,788 s; recalcularea inversă pe același atlas durează
  0,274 s. Testul anterior observase aproximativ două minute înainte de input.
- **Regresie:** testul instrumentează loaderul și dilatarea și dovedește câte un
  singur apel după `plan_variants` plus un plan ulterior.
- **Stare:** optimizarea este verificată offline; timpul rece va fi reverificat
  în următorul test LAB filmat.

## ME-024 — Un mob prea puternic oprea definitiv journey-ul

- **Observat:** la `2117,940`, un NPC peste limita sigură a intrat în combat.
  Combat Engine a refuzat corect atacul cu `target_level_out_of_bounds`, dar
  supervisorul nu avea o tranziție sigură și a oprit journey-ul.
- **Cauză generală:** „nu ataca” nu este o strategie de supraviețuire când
  combatul a început deja. Reluarea oarbă a navigației ar fi mers înainte prin
  aceeași amenințare, iar backpedalul fără geometrie putea intra într-un zid.
- **Soluție standalone:** Navigation Engine păstrează maximum 120 yd de
  breadcrumbs rarefiate, provenite exclusiv din pozițiile client-visible pe
  care Predator le-a traversat efectiv. O discontinuitate de coordonate șterge
  urma. Combat Engine poate urma înainte coridorul invers maximum 30 yd, sub
  propria autoritate, cu RMB și steering continuu; nu emite niciun spell sau
  damage. Numai un frame proaspăt `in_combat=false` produce
  `ESCAPED_RISKY_AGGRO` și permite replanul aceleiași destinații.
- **Fail-closed:** lipsa facingului, o urmă insuficientă/detașată, lipsa
  progresului, epuizarea coridorului încă în combat sau deadline-ul de 18 s
  eliberează inputul și opresc lanțul. Godmode nu participă la decizie.
- **Regresie:** sunt acoperite proveniența și continuitatea urmei, resetul la
  teleport, eliminarea zgomotului, steeringul invers, eliberarea out-of-combat,
  lipsa facingului și secvența NAV → ESCAPE → NAV → ARRIVED. Suita completă are
  1.068 teste trecute în 79,869 s.
- **Stare:** verificat live: tranziția NAV → ESCAPE → REPLAN s-a executat de
  trei ori fără teleport, iar fiecare retragere completă a eliberat combatul.

## ME-025 — Contextul valid de retragere lungă era refuzat la handoff

- **Observat:** în proba autonomă Brill → Deathknell, navigația a intrat în
  combat la aproximativ `2125, 961` și a predat corect controlul. Combat Engine
  s-a oprit înaintea primei decizii cu `safe retreat breadcrumb count is
  invalid`.
- **Cauză generală:** producătorul păstrează implicit maximum 120 yd la o
  distanță de eșantionare de 1,5 yd, adică aproximativ 81 puncte, dar
  consumatorul accepta cel mult 64. Limitele celor două module nu descriau
  aceeași capacitate a contractului.
- **Soluție standalone:** validatorul acceptă maximum 96 de mostre, suficient
  pentru capacitatea implicită cu endpoint-uri, și validează separat că
  lungimea fizică însumată nu depășește 122 yd. Astfel nu confundă numărul de
  puncte cu distanța și nu permite unui context dens să devină o rută
  arbitrară.
- **Regresie:** este acoperită urma completă de 81 puncte produsă de valorile
  implicite și este refuzată o urmă de 126 yd chiar dacă are numai 64 puncte.
- **Probă LAB intermediară:** după fix, handoff-ul a consumat urma și Predatorul
  s-a retras aproximativ 90 yd pe drumul parcurs. Darkhound-ul era însă încă la
  aproximativ 17 yd și combatul nu se încheiase, deci oprirea fail-closed a fost
  corectă.
- **Ajustare bazată pe probă:** coridorul implicit de retreat folosește acum
  întreaga memorie validată de maximum 120 yd, nu numai primii 90 yd. Aceasta
  depășește un leash de aproximativ 100 yd fără să inventeze geometrie și fără
  să permită deplasare dincolo de pașii observați ai Predatorului.
- **Reluare după fail-closed:** dacă execuția se întrerupe pe mijlocul urmei,
  un nou handoff poate porni numai de lângă unul dintre breadcrumbs (maximum
  8 yd). Consumatorul taie secțiunea deja parcursă și inversează numai prefixul
  rămas; o poziție din afara urmei este refuzată.
- **Stare:** retragerea completă de aproximativ 120 yd și reluarea journey-ului
  au fost verificate live; repetarea aceleiași zone a devenit problema ME-026.

## ME-026 — Replanul revenea în zona din care tocmai evadase

- **Observat:** Brill → Deathknell a executat corect de trei ori secvența
  NAV → ESCAPE → REPLAN, dar fiecare plan nou traversa din nou regiunea în care
  un adversar prea puternic declanșase retragerea.
- **Cauză generală:** memoria permanentă conținea întâlniri vizuale regionale,
  însă rezultatul semantic `ESCAPED_RISKY_AGGRO` nu producea nicio dovadă de
  risc pentru următorul ciclu de planificare.
- **Soluție standalone:** supervisorul persistă poziția verificată a
  Predatorului de la handoff ca `escaped_risky_aggro_observation`. Nu inventează
  coordonata entității. Evenimentul este legat de hartă, hash-ul navmesh-ului,
  journey, encounter și run, are zero autoritate de input și devine o zonă de
  risc permanentă de 45 yd pentru toate planurile ulterioare.
- **Migrare:** baza SQLite append-only trece automat de la versiunea 1 la 2 prin
  adăugarea tabelului `escaped_risk_observations`; vechiul tabel și toate
  observațiile sale rămân intacte. Contractul sumarului este majorat la `2.0`,
  iar Control Center refuză forma veche în loc să o interpreteze ambiguu.
- **Regresie:** sunt verificate migrarea, idempotency, persistența după reopen,
  lipsa unei poziții inventate pentru entitate și consumul zonei de risc de
  către route policy. Suita completă are 1.079 teste trecute în 79,963 s.
- **Dovadă offline pe traseul real:** cu zona permanentă, cele două profile
  care traversează regiunea primesc risc `5,796`, în timp ce varianta care o
  evită rămâne la `3,501` și este selectată. Diferențierea vine din geometria
  fiecărei rute față de observație, nu dintr-o rută ori coordonată hardcodată.
- **Stare:** implementat și verificat offline; proba LAB completă filmată
  Brill → Deathknell urmează.

## ME-027 — Preview-ul lung a reintrodus zig-zag în interior

- **Observat:** ieșirea din cryptă fusese repetată de 3–4 ori la aproximativ
  90% calitate, apoi o versiune ulterioară a început să meargă înainte și
  înapoi pe aceeași porțiune. În clipul local corespunzător, regresia începe în
  jurul secundei 71 și coincide cu un preview semantic de 68 puncte.
- **Cauză generală:** două coridoare Detour complete și local conectate puteau
  fi lipite pentru steering doar pe baza continuității endpointului și a
  unghiului inițial. Continuarea putea reveni ulterior peste o zonă deja
  parcursă la aceeași înălțime; controllerul urma fidel bucla rezultată.
- **Soluție standalone:** ghidajul elimină reîntoarcerile spațiale pe aceeași
  podea, iar preview-ul refuză complet o îmbinare dacă viitoarea bucată revine
  lângă suprafața anterioară. Vecinii direcți ai îmbinării sunt excluși din
  test, iar suprapunerile XY aflate pe niveluri Z diferite rămân permise pentru
  scări, poduri și interioare suprapuse. Nu există nume de zonă, coordonate sau
  excepții pentru cryptă.
- **Regresie:** sunt verificate separat bucla pe aceeași podea, curba obișnuită,
  coridorul deconectat/invers, frontiera parțială și switchback-ul suprapus pe
  altă înălțime. Suita focalizată are 153 teste trecute.
- **Stare:** rezolvat offline; urmează comparația LAB filmată cu ieșirile bune
  anterioare.

## ME-028 — Selectorul confunda stealth-ul cu abilitatea de a traversa teren

- **Observat:** în proba filmată cryptă → Brill, Predatorul a părăsit drumul,
  a intrat repetat prin pădure și a încercat să urce dealuri. Snapshotul live
  dovedește `profile=shortcut`, numai 39,6% celule de drum și
  `road_polygons_preferred=0`; varianta rutieră avea 97,9% celule de drum.
- **Cauză generală:** dificultatea topografică era multiplicată cu factorul de
  vulnerabilitate în combat. Stealth și escape micșorau artificial costul unui
  traseu necunoscut, deși aceste abilități nu fac o pantă ori o pădure mai ușor
  de navigat.
- **Soluție standalone:** terenul este evaluat independent de vulnerabilitatea
  la adversari. O variantă cu dificultate off-road mare este eligibilă numai
  după validare topografică de minimum 95%; scurtăturile ușoare ori validate
  rămân disponibile. Astfel nu alegem mereu drumul lung, dar nici nu presupunem
  că orice suprafață cyan produce mișcare humanlike.
- **Regresie:** un rogue capabil nu mai selectează un deal neverificat, iar o
  scurtătură validată integral rămâne selectabilă când economisește timp real.
- **Stare:** verificat offline pe ruta reală: `shortcut` este neeligibil, iar
  ruta selectată are 97,9% celule de drum; urmează proba LAB filmată.

## ME-029 — Un centru de raster fără poligon oprea călătoria

- **Observat:** după primul frontier replan din aceeași probă, workerul a
  răspuns `corridor endpoint has no polygon` pentru o mostră semantică și
  întregul journey s-a oprit.
- **Cauză generală:** centrul unei celule din atlas poate cădea într-un prop,
  într-o gaură mică a mesh-ului sau între suprafețe. Punctul intermediar era
  tratat ca destinație fizică obligatorie.
- **Soluție standalone:** dacă punctul intermediar nu are poligon, plannerul
  caută limitat numai înainte pe aceeași rută atlas și acceptă prima mostră cu
  un coridor Detour complet. Nu inventează coordonate laterale și nu sare în
  afara traseului semantic.
- **Regresie:** endpointul invalid este înlocuit cu următorul punct forward
  valid; lipsa oricărui punct valid continuă să eșueze fail-closed.
- **Stare:** implementat și verificat offline; urmează proba LAB filmată.

## ME-030 — Planul și traseul real nu puteau fi comparate live

- **Observat:** o abatere prin pădure ori un zig-zag devenea clar abia după
  analiza filmării și a telemetriei; linia din 3D Mesh Map arăta numai
  coridorul activ, nu și locul pe unde trecuse efectiv Predatorul.
- **Cauză generală:** snapshotul extern publica poziția și centerline-ul
  planificat, dar nu păstra o urmă vizuală distinctă a observațiilor client.
- **Soluție standalone:** Movement Engine păstrează o urmă diagnostică
  eșantionată exclusiv din poziții client-visible. Cyan rămâne planul curent,
  iar magenta este deplasarea reală, atât în harta 2D cât și în 3D Mesh Map.
  Urma nu are autoritate de input, se resetează la discontinuități de tip
  teleport și se decimează progresiv la călătorii foarte lungi.
- **Regresie:** sunt verificate serializarea read-only, protocolul live v4,
  limita de memorie și lipsa unei linii false peste o teleportare.
- **Stare:** implementat, viewerul nativ reconstruit; proba LAB urmează.

## ME-031 — Recovery-ul nu modela inerția rotației RMB

- **Observat:** în rularea v24, ieșirea a oscilat de două ori în cryptă. La
  cross-track 0,4 yd urmărea corect înainte, dar la 1,4 yd ținta de steering
  revenea la numai 0,65 yd în față; următorul pas traversa din nou centerline-ul
  și declanșa pivotul opus. Mărirea carrot-ului în v25 nu a rezolvat problema:
  în primele 28,6 s au existat 20 schimbări de sens și 78 cadre de pivot, iar
  pe pod 11 schimbări de sens în 24,5 s.
- **Cauză parțială:** recovery-ul pentru spațiu închis fusese făcut atât de
  agresiv încât punctul de pure pursuit era mai aproape decât deplasarea dintre
  două observații. Corectarea distanței a eliminat această eroare geometrică,
  dar nu cauza comună a oscilației.
- **Cauză generală confirmată de v25:** clientul continuă rotația RMB dintre
  două observații. Servo-ul calcula comanda numai din unghiul instantaneu și
  începea frânarea după depășirea bearingului; apoi repeta în sens opus.
- **Soluție standalone:** corecția WMO începe gradual la 0,6 yd, ajunge completă
  la 0,9 yd și păstrează un punct de urmărire la 1,35 yd înainte. Un heading
  periculos continuă să oprească W, iar pereții și colțurile rămân protejate de
  corner-cap și hard recenter. Controllerul estimează acum viteza unghiulară
  din headingurile client-visible și proiectează un orizont scurt, limitat,
  pentru a frâna înainte de traversarea bearingului. Modelul aparține
  controllerului standalone, nu input sink-ului, și nu conține coordonate,
  hartă sau nume de zonă.
- **Regresie:** sunt acoperite carrot-ul mai lung decât un pas, abaterea severă,
  frânarea înainte de overshoot și cel mult o singură contravirare într-o
  traversare sintetică a centerline-ului.
- **Probă v26:** un singur journey a ajuns în Brill fără collision/recovery
  replan. În primele 250 cadre, inversările au scăzut de la 20 la 11 și
  pivoturile de la 78 la 36; pe pod, de la 11 la 8 și de la 29 la 14. Operatorul
  a confirmat că vechiul zig-zag dur a devenit o corecție cursivă în formă de S,
  dar încă vizibilă de la mijlocul podului. Prin urmare v26 este progres, nu
  criteriu de acceptare.
- **Rafinare generală pentru v27:** distanța de recovery folosește un orizont
  de timp derivat din viteza observată, nu o distanță fixă. Lungirea se activează
  progresiv numai după ieșirea din banda normală; lângă centerline rămâne
  conservatoare, iar corner-cap-ul și fixture-ul torței continuă să prevină
  tăierea colțurilor.
- **Stare:** modelul de yaw momentum și recovery-ul dependent de viteză trec
  1.102 teste; necesită proba filmată v27 în cryptă și pe pod înainte ca
  problema să poată fi declarată rezolvată.

## ME-032 — Memoria obstacolului nu includea capsula actorului

- **Observat:** v27 a urmat ruta rutieră până în zona `2182, 1060`, apoi a
  repetat două clearance-uri locale și două backtrack-uri, a ieșit lateral în
  pădure și s-a oprit corect `STUCK_REPLAN_REQUIRED` înainte de pod.
- **Cauză generală:** obstacolul era deja confirmat permanent în memorie, cu
  centrul la aproximativ `2178, 1059` și raza observată de 3 yd. Coliziunea nouă
  s-a produs la 3,88 yd de centru. Workerul excludea numai volumul obiectului,
  ca și cum actorul ar fi fost un punct; ruta putea trece între raza obiectului
  și marginea capsulei vizibile a personajului.
- **Soluție standalone:** memoria continuă să păstreze raza observată, fără să
  falsifice experiența. Numai proiecția folosită de planner adaugă clearance-ul
  capsulei actorului (1,25 yd), rezultând un blocker de 4,25 yd pentru exemplul
  confirmat. Formula se aplică oricărui copac, indicator, căruță sau prop și nu
  conține coordonate ori nume de zonă.
- **Regresie:** este verificat separat că raza brută serializată rămâne 3 yd,
  în timp ce blockerul de planning devine 4,25 yd; valori de clearance invalide
  sunt refuzate.
- **Stare:** implementat și verificat offline; necesită rerulare filmată.

## ME-033 — „A ajuns” ascundea un traseu robotic

- **Observat:** toate probele sintetice puteau ajunge la destinație, deși
  filmarea reală arăta pivoturi, curbe în S și corecții repetate. Un criteriu
  binar de sosire declara astfel succes înainte ca mersul să fie humanlike.
- **Cauză generală:** fiecare reglaj era validat prea târziu în client și pe o
  singură poziție/facing. Latența, viteza și poziția inițială nu erau variate
  sistematic, iar durata unei călătorii limita numărul de încercări.
- **Soluție standalone:** un simulator cinematic determinist închide chiar
  controllerul de producție peste același model calibrat de yaw RMB, W,
  viteză și interval de observație. Fiecare tip de geometrie rulează minimum
  100 de variații reproductibile. Acceptarea cere simultan sosire, cross-track
  limitat, fracție mică de pivot și puține schimbări ale sensului de steering;
  sosirea singură nu mai este suficientă.
- **Probă inițială:** 4.000 încercări (1.000 pe situație) au rulat în 17,66 s.
  Dreapta interioară și podul drept au trecut 1.000/1.000. Curba/scara
  interioară a trecut numai 17/1.000, iar poarta în S 0/1.000, deși toate au
  ajuns. Simulatorul a reprodus astfel diferența dintre funcțional și fluid.
- **Stare inițială:** harnessul și pragurile sunt implementate; curbele dificile sunt
  intenționat blocate de quality gate până la corectarea controllerului.
- **Corecție generală:** corner preview-ul folosește acum portalul local
  asociat spațial apexului, nu cel mai îngust portal din întregul coridor.
  Bearingul actual către pursuit point este interpolat spre tangenta de ieșire,
  iar curba rămâne activă cât timp capsula încape în clearance-ul local dovedit.
  Accelerația RMB mai rapidă și slew-ul mai larg există numai în această
  anvelopă geometrică; pe dreaptă și la handoff rămân limitele lente anterioare.
- **Probă finală offline:** 4.000/4.000 încercări au trecut quality gate în
  30,76 s: câte 1.000 pentru dreaptă interioară, scară/curbă, poartă în S și
  pod. Poarta a avut zero pivoturi, maximum 1,65 yd cross-track și maximum două
  schimbări de sens; scara a rămas sub 1,46 yd. Nicio regulă nu conține nume de
  hartă, zonă sau coordonate.
- **Confirmare v18:** 50.000/50.000 încercări au trecut quality gate: câte
  10.000 pentru dreaptă interioară, scară/curbă, poartă în S, poartă cu
  obstacol static și pod drept. Suita completă are 1.112 teste trecute.
  Călătoria LAB filmată cryptă → Brill a terminat toate cele 132 de segmente
  într-un singur run, fără collision, recovery ori replan. Abaterea live
  maximă de 4,43 yd pe o zonă largă și cele 106 cadre de pivot din 3.282 rămân
  indicatori de fluiditate de redus; succesul nu este reclasificat drept
  „flawless”.
- **Stare:** simulatorul și regresia live de continuitate sunt verificate;
  fine-tuningul de fluiditate pe trasee lungi continuă.

## ME-034 — Steeringul rotunjea deturul navmesh înapoi prin obstacol

- **Observat:** în proba filmată v12, ruta nativă ocolea corect stâlpul porții
  Deathknell, dar personajul a tăiat interiorul curbei și a lovit stâlpul.
  Recovery-ul ulterior executa separat ancora laterală și ancora de depășire,
  producând o întoarcere vizibil robotică și o nouă apropiere de poartă.
- **Cauză generală:** controllerul vedea teren deschis și trata polilinia
  Detour ca pe o curbă cosmetică. Pure pursuit putea privi dincolo de apex și
  rotunji prin anvelopa obiectului, deși `doodad_avoidance_applied` dovedea că
  acel apex reprezenta clearance fizic pentru capsula actorului. Simulatorul
  vechi măsura doar sosirea/cross-track, nu și contactul cu obiectul.
- **Soluție standalone:** detururile de doodad devin secțiuni de precizie
  indiferent dacă sunt în exterior. Look-ahead-ul recunoaște și coturi mai
  puțin ascuțite din asemenea detururi, nu aplică fillet fără geometria completă
  a obstacolului și accelerează controlat yaw-ul numai în acea anvelopă.
  Simulatorul modelează separat raza actorului și raza obstacolului și refuză
  orice swept contact. Când recovery-ul are două coridoare Detour complete și
  compatibile, le urmărește ca un singur coridor continuu până dincolo de
  obiect; fallback-ul cu două etape rămâne numai când îmbinarea nu este
  demonstrată sigură.
- **Regresie:** fixture-ul derivat din geometria reală a porții a trecut
  10.000/10.000 variații, zero coliziuni; toate cele cinci situații au trecut
  50.000/50.000. Testul LAB cryptă → Brill a trecut poarta, drumul și podul în
  același run, 132/132 segmente, fără collision/recovery/replan și fără abatere
  repetată prin pădure. Filmarea brută este
  `C:\Users\LabUser\Videos\NVIDIA\Wow.exe\Wow.exe 2026.08.29 - 00.35.20.44.mp4`.
- **Limită păstrată explicit:** această dovadă validează Tirisfal și reflexele
  geometrice testate, nu afirmă cunoaștere centimetru cu centimetru pentru
  toate continentele. Acea proprietate vine din coverage-ul WorldPack, iar
  fiecare geometrie nouă ori eșec live devine fixture reproductibil.
- **Stare:** coliziunea porții rezolvată și confirmată live; reducerea
  pivoturilor/cross-track pe trasee lungi rămâne deschisă.

## ME-035 — Un viraj îngust era uitat chiar în apex

- **Observat:** în proba v18 cryptă → Brill, abaterea maximă de 4,43 yd a
  apărut într-o singură corecție rară. Personajul a început pivotul corect,
  apoi a reluat W înainte să fie orientat pe ieșirea virajului și a recuperat
  târziu, după ce traversase lateral coridorul.
- **Cauză generală:** coridorul standalone extras din WorldPack conținea un
  viraj de aproximativ 128° într-un portal local de 2,20362 yd. Scanarea
  colțurilor privea numai înainte. Când proiecția actorului ajungea în apex,
  colțul trecea în spatele ferestrei de scanare și profilul de precizie era
  șters, deși rotația fizică nu se terminase. Tangenta calculată direct din
  punctul eșantionat amesteca, în plus, segmentul de intrare cu cel de ieșire.
- **Soluție standalone:** un colț prea îngust pentru o curbă verificată creează
  un angajament geometric scurt, legat de progresul coridorului. Tangenta este
  măsurată integral după fereastra colțului și rămâne autoritară din apropierea
  apexului până când capsula a trecut 2 yd pe segmentul de ieșire. Identitatea
  se resetează la schimbarea coridorului; nu există nume de zonă, coordonate,
  waypoint ori rută hardcodată.
- **Regresie:** geometria exactă a evenimentului live este acum situația
  `narrow_outdoor_hairpin`. Înainte de corecție avea 0/100 treceri de calitate
  și aproximativ 4,01 yd abatere maximă. După corecție, 10.000/10.000 variații
  au trecut, cu maximum 1,78 yd cross-track, maximum două schimbări de sens și
  maximum 26,93% cadre de pivot. Împreună cu celelalte cinci situații,
  rularea v19 a trecut 60.000/60.000 și zero coliziuni.
- **Stare:** corectat și verificat în simulator; necesită comparația filmată
  v19 pe aceeași călătorie înainte de a declara efectul confirmat în client.

## ME-036 — Un singur punct fix nu reprezintă un ADT întreg

- **Observat:** prima probă automată pe Azeroth a ales centrul primului ADT
  din catalog (`24_53`). Niciunul dintre cele 50 de cursuri locale uniforme
  nu a găsit două capete circulabile; tile-ul de coastă conține artefactul
  complet, dar punctele încercate nu au poligoane Detour eligibile.
- **Cauză generală:** existența unui ADT și validitatea structurală a fișierului
  `.nav` nu garantează că o coordonată arbitrară din acel pătrat este teren
  circulabil. Un centru presupus ar transforma apa, marginea de continent sau
  un tile aproape gol într-un fals eșec al steeringului.
- **Soluție standalone:** corpusul generează aceeași rețea deterministă de 50
  de cursuri locale în fiecare ADT și folosește un worker persistent pentru a
  valida capetele fără să reîncarce harta la fiecare probă. Se oprește după
  numărul cerut de coridoare Detour complete. Tile-urile fără capete valide,
  erorile de query, coridoarele parțiale și eșecurile de control sunt raportate
  ca stări diferite; niciuna nu este ascunsă ori declarată acoperire.
- **Regresie:** pe ADT-ul Deathknell `29_27`, prima probă data-derived a produs
  un coridor complet și controllerul de producție a trecut 100/100 variații,
  zero coliziuni și maximum 1,21 yd cross-track. Același coridor a fost
  clasificat `RISK` pe baza pantei, deturului de doodad, insetului de clearance
  și spațiului de tranziție, deci politica completă îl escaladează la 1.000 de
  încercări. Pe ADT-ul de margine `24_53`, toate cele 50 de candidate sunt
  raportate explicit `ENDPOINT_UNAVAILABLE`, fără 50 de reporniri ale hărții.
- **Stare:** generatorul generic, clasificarea BASE/RISK/EXTREME și smoke-urile
  sunt verificate pe WorldPack-ul complet Azeroth/Kalimdor/Expansion01.
  Acoperirea fiecărui ADT rămâne o rulare separată, reluabilă.

## ME-037 — MapBuilder putea amesteca fișiere din patch-uri MPQ diferite

- **Observat:** inventarul clientului 2.4.3 declara 800 de ADT-uri active pentru
  `Expansion01`, dar primul bake complet producea reproductibil numai 776
  fișiere `.nav` și raporta 198.656 sub-tile-uri, adică exact 776 × 256. Cele
  24 de coordonate absente formau dreptunghiul `x=42..47, y=6..9`.
- **Cauză generală:** Namigator păstra arhivele, încărcate în ordinea de
  prioritate a patch-urilor, într-un `std::unordered_map`. `OpenFile()` itera
  apoi hash buckets, nu ordinea declarată, astfel încât WDT-ul putea proveni
  dintr-un patch mai vechi în timp ce inventarul și ADT-urile proveneau din
  patch-ul prioritar. Un singur navmesh putea deveni un amestec nedeterminist
  de versiuni ale aceluiași client.
- **Soluție standalone:** lista arhivelor este acum un vector ordonat de perechi;
  căutarea păstrează strict precedența patch-urilor. Patch-ul reproductibil se
  află în `patches/namigator/0001-deterministic-mpq-patch-precedence.patch`.
  Toate continentele sunt reconstruite într-un root curat; navmesh-urile
  produse înainte de corecție nu sunt promovate în WorldPack-ul comun.
- **Probă izolată:** după recompilare, construirea individuală a ADT-ului
  `Expansion01 (42, 6)` s-a terminat cu exit code 0 în cinci secunde și a
  produs `42_06.nav` de 532.001 bytes. Același ADT lipsea din ambele treceri
  complete ale executabilului vechi.
- **Regresie:** rebuild-ul curat a produs exact Azeroth 687/687, Kalimdor
  1.018/1.018 și Expansion01 800/800. Toate cele 24 de tile-uri anterior
  absente (`x=42..47, y=6..9`) există. Auditul Detour profund a validat toate
  cele 641.280 de subtile declarate, cu zero ADT-uri defecte. Pack-ul comun a
  fost sigilat și redeschis independent cu 9.514 artefacte și SHA-256 agregat
  `d8a1b65e71602e6513b0d8e711001a23cdfc98ceb2109834ba8a86fa5ef689ac`.
- **Stare:** rezolvat și verificat pentru toate cele trei continente TBC.

## ME-038 — Auditorul continentelor putea acumula memorie sau rămâne fără workeri

- **Observat:** auditul structural serial al unui continent dura mult și nu
  publica progres. Prima paralelizare cu `ProcessPoolExecutor` a validat
  Azeroth și Expansion01, dar un worker Kalimdor s-a închis brusc. Activarea
  `max_tasks_per_child` pe Python 3.14 pentru Windows a produs apoi un
  coordinator rămas activ după ce toate procesele copil se retrăseseră.
- **Cauză generală:** ADT-urile dense au vârfuri mari de memorie decomprimată,
  iar allocatorul poate păstra high-water marks între taskuri. Executorul ales
  nu înlocuia fiabil workerii retrași pe runtime-ul curent. Parserul mai copia
  și blocuri heightfield care trebuiau numai validate ca lungime și sărite.
- **Soluție standalone:** auditul distribuie fiecare ADT ca task izolat prin
  `multiprocessing.Pool` cu context Windows `spawn`, ordine deterministă,
  maximum 16 procese și reciclare reală după un număr configurabil de ADT-uri.
  `_PayloadReader.skip()` avansează peste blocurile diagnostice deja delimitate
  fără copii temporare; payloadurile Detour inspectate rămân verificate integral.
- **Regresie:** raportul paralel este identic cu cel serial; un test cu mai
  multe loturi obligă înlocuirea workerilor. Suita dedicată are 9/9 teste
  trecute. Kalimdor a terminat ulterior 1.018/1.018, zero failures.
- **Stare:** rezolvat; auditul complet este reutilizabil pentru continente și
  instanțe fără procese vizibile sau dependențe runtime.

## ME-039 — Corpusul lung pierdea progresul și nu putea reproduce exact un eșec

- **Observat:** o rulare pe toate continentele putea fi întreruptă după ore, iar
  raportul agregat exista numai la final. Primele rapoarte păstrau statistica
  unui coridor, dar nu geometria necesară pentru a relua exact trialurile rare.
- **Cauză generală:** unitatea de persistență era întregul job, iar identitatea
  dovezii nu includea implementarea controllerului, runnerul și contractul.
- **Soluție standalone:** fiecare ADT terminat primește un checkpoint atomic și
  schema-valid. Reluarea cere aceeași identitate WorldPack/policy/cod; o dovadă
  veche este ignorată, iar una coruptă care pretinde identitatea curentă oprește
  fail-closed. Punctele brute, funnel path-ul, poligoanele, portalurile și
  atributele de steering sunt păstrate pentru replay local fără requery.
- **Regresie:** prima rulare a tile-ului are `checkpoint_hits=0`; reluarea
  identică are `tiles_to_query=0`. Replay-ul coridorului Kalimdor reproduce
  aceleași rezultate trial-cu-trial ca raportul de origine.
- **Stare:** rezolvat și acoperit de contract/teste.

## ME-040 — Primul PA-MPPI ajungea, dar tremura stânga–dreapta

- **Observat:** prima probă reală Kalimdor a ajuns în 100/100 variații, dar toate
  au picat criteriul humanlike: până la 41 schimbări de sens și 2,663 yd
  cross-track. Telemetria a confirmat că 86,92% dintre cadre proveneau realmente
  din MPPI, deci fallback-ul nu putea ascunde problema.
- **Cauză generală:** fiecare replan folosea alt nor aleator, warm start-ul avea
  prea multă inerție față de poziția nou observată, preview-ul pornea târziu, iar
  conversia yaw→mouse transmitea inclusiv zgomotul de un pixel. Eliminarea
  completă a acelui pixel a scos tremuratul, dar a păstrat actorul paralel la un
  yard de centru înaintea unui hairpin.
- **Soluție standalone:** replanuirile folosesc common random numbers, seed-ul
  proaspăt domină warm start-ul, costul include regularizarea path-integrală și
  continuitatea yaw, iar preview-ul acoperă aproximativ o secundă de mers.
  Filtrul cere trei observații înaintea inversării și suprimă microcomanda numai
  aproape de centru; la abatere de minimum 0,5 yd, corecția mică persistentă
  rămâne activă. Nicio regulă nu conține hartă, zonă sau coordonate.
- **Regresie:** coridorul EXTREME Kalimdor (hairpin 114,95°, portal 0,595 yd)
  trece 100/100, maximum 1,775 yd abatere, maximum șase schimbări de sens și zero
  coliziuni. Azeroth EXTREME trece 100/100 cu maximum 1,381 yd; Expansion01 BASE
  trece 100/100 cu maximum 1,232 yd. Testul sintetic closed-loop trece separat
  100/100 și confirmă că MPPI controlează peste 80% dintre observații.
- **Stare:** rezolvat în LAB/replay; promovarea live așteaptă călătoria filmată
  de holdout, fără reglare după acea filmare.

## ME-041 — Un frontier Detour parțial oprea PA-MPPI cu excepție

- **Observat:** primul holdout filmat Brill → Deathknell s-a oprit fail-closed
  cu `ValueError: PA-MPPI planning snapshot is invalid` după ce navigatorul a
  întors legitim un coridor parțial, utilizabil până la frontierul următoarei
  replanuiri.
- **Cauză generală:** steeringul geometric știa să urmărească o propunere
  parțială, dar facade-ul MPPI încerca să construiască un snapshot care cere
  explicit un coridor complet. Contractele erau corecte separat; tranziția
  dintre ele nu avea fallback.
- **Soluție standalone:** controllerul sincron și cel asincron trimit orice
  coridor parțial la steeringul geometric și publică motivul
  `geometric_state:PARTIAL_CORRIDOR`. MPPI nu primește și nu poate publica o
  traiectorie cu topologie incompletă.
- **Regresie:** ambele facade-uri sunt testate cu un coridor parțial; retry-ul
  filmat din poziția rămasă a ajuns în Deathknell, 14/14 obiective semantice,
  fără recovery ori replan parțial.
- **Stare:** rezolvat și confirmat live.

## ME-042 — Marginea unui drum muta waypoint-ul în iarbă

- **Observat:** în holdout-ul filmat Deathknell → Brill, personajul a părăsit
  pavajul în pădure. La etapa 49, Detour a produs un traseu de 59,24 yd pentru
  o țintă semantică aflată la numai 13,60 yd; cadrul capturat arată pavajul în
  dreapta și actorul între copaci.
- **Cauză generală:** atlasul de 1024×1024 pixeli era redus la celule de 8×8
  prin regula „oricare pixel”. Dacă numai 3/64 pixeli atingeau marginea
  drumului, întreaga celulă de 4,17 yd devenea drum, iar waypoint-ul era pus în
  centrul ei geometric. Două asemenea centre au traversat o zonă cu arbori și
  o cusătură ADT, deși textura reală de drum era în altă parte. Separat,
  extractorul de straturi folosea `max()` și putea păstra un strat de bază
  road/path chiar când straturile MCAL superioare îl acopereau.
- **Soluție standalone:** reducerea este acum vectorizată și cere ca media
  contribuției pe întreaga celulă să atingă pragul semantic. Pentru fiecare
  celulă acceptată, waypoint-ul este centrul de masă al afinității reale, nu
  centrul pătratului. Straturile ADT folosesc contribuția reziduală a bazei și
  ponderile independente MCAL ale straturilor superioare. Nu există nume de
  zonă, coordonate ori rută hardcodată.
- **Regresie:** celulele live defecte aveau numai 3/64 și 10/64 pixeli peste
  prag și nu mai sunt promovate. Cele patru coridoare 3D din aceeași zonă au
  acum raport lungime/direct 1,00. Validarea completă a trecut: crypt spawn →
  Brill 131/131, Deathknell → Brill 117 etape până în raza destinației, returul
  117 etape, Brill → south road 32 etape; fixture-ul de deal rămâne corect
  `RESET_REQUIRED`. Încărcarea atlasului complet a scăzut la aproximativ două
  secunde.
- **Confirmare live:** holdout-ul complet Brill → Deathknell a terminat
  116/116 obiective semantice, iar returul Deathknell → Brill 117/117. Ambele
  au rulat într-un singur ciclu, fără replanificare parțială, recovery sau
  local recovery. Cadrele eșantionate din ambele clipuri rămân pe potecă,
  inclusiv fereastra care înainte producea ocolul prin pădure; noua rută nu se
  mai apropie de centrul grosier defect.
- **Dovezi:** `holdout-brill-deathknell-road-centroid-v2.json`,
  `holdout-deathknell-brill-road-centroid-v2.json` și clipurile NVIDIA
  `Wow.exe 2026.08.29 - 06.27.29.48.mp4`, respectiv
  `Wow.exe 2026.08.29 - 06.34.53.49.mp4`.
- **Stare:** rezolvat și confirmat live în ambele sensuri.

## ME-043 — Sosirea pe drum ascundea prea multe fallback-uri de steering

- **Observat:** cele două holdout-uri live ajung fără blocaje și rămân vizual
  pe pavaj, dar telemetria nu justifică încă eticheta „flawless”. Turul are
  1.125 cadre MPPI active și 1.488 fallback-uri, 50 cadre de pivot și 257
  schimbări de sens ale microcomenzii mouse; returul are 1.127 cadre active,
  1.571 fallback-uri, 65 cadre de pivot și 284 schimbări de sens. P95
  cross-track este 2,551 yd, respectiv 2,600 yd.
- **Cauză confirmată parțial:** 2.929 dintre fallback-uri provin din
  `all_sampled_trajectories_violate_topology_or_clearance`; controllerul
  geometric menține progresul, dar maschează faptul că samplerul predictiv nu
  găsește suficient de des o traiectorie acceptabilă. Pivotul inițial și
  inversările mici rămân separat de corecția semantică ME-042.
- **Direcție de rezolvare:** calibrare generică a modelului de clearance și a
  proiecției footprint-ului pe coridor, apoi replay pe aceleași coridoare și
  holdout filmat. Criteriul nu este doar `ARRIVED`: trebuie să scadă
  fallback-urile, pivotarea staționară și inversările rapide fără a pierde
  clearance-ul ori fidelitatea față de drum.
- **Stare:** deschis; nu necesită coordonate, waypoint-uri sau reguli specifice
  Deathknell/Brill.

## ME-044 — Facingul exact era suprascris, iar corecția laterală balansa camera

- **Observat:** holdout-urile ajungeau la destinație, dar camera alterna vizibil
  stânga–dreapta inclusiv pe suprafețe drepte. v8 a avut 109 inversări în 223,35
  secunde, adică 29,28/minut, deși a raportat `ARRIVED`.
- **Cauză generală:** pachetul addon conținea `GetPlayerFacing()` cuantizat pe
  16 biți, însă sursa live îl suprascria cu orientarea inferată din câțiva
  pixeli ai markerului de minimap. Separat, orice abatere laterală mică era
  corectată prin RMB yaw, deși un player păstrează camera/facingul și folosește
  impulsuri scurte W+A/W+D pe o suprafață dreaptă.
- **Soluție standalone:** facingul exact are prioritate; markerul vizual este
  numai fallback când acel câmp lipsește. Pe secțiuni largi, drepte și fără
  colț/obstacol apropiat, corecția sub-yard folosește strafe confirmat, un singur
  cadru, urmat de cooldown și observație nouă. Crypta, porțile, detururile și
  curbele păstrează steeringul geometric de precizie. Nicio condiție nu conține
  hartă, zonă sau coordonate.
- **Regresie:** 86 teste trec; 1.000 replay-uri pe coridorul real Azeroth
  `31_31:p0` trec 1.000/1.000, fără coliziuni sau pivot, cu maximum trei
  inversări și P95 două. Noul gate peste telemetria clientului respinge toate
  cele trei holdout-uri istorice chiar dacă au `ARRIVED`: 44,73/min, 47,05/min
  și 29,28/min, plus pauzele lor de observație.
- **Stare:** reparat și confirmat offline; confirmarea live rămâne obligatorie
  și nu poate fi înlocuită de `ARRIVED` ori de replay-ul cinematic.

## ME-045 — Nucleul autonom nu avea o limită explicită pentru observații

- **Observat:** runnerul live construia direct DXGI, detectoarele HUD/minimap și
  nameplate detection în același fișier care orchestrează navmesh, steering și
  input. Astfel, un core descris drept standalone depindea implicit de pixel
  read, iar un replay sau un provider privat nu putea fi injectat curat.
- **Cauză generală:** lipsea un port minim de observație. Implementarea concretă
  devenise contractul accidental al buclei de mișcare.
- **Soluție:** `MovementObservationPort` definește numai observația validată,
  facing provenance, travel capability și entitățile dinamice. Fabrica din
  runner păstrează adaptorul optic în integration layer și permite înlocuirea
  lui cu replay sau server telemetry fără modificarea motorului.
- **Clarificare:** captura read-only și HUD-ul optic validat sunt permise ca
  adaptoare; nu sunt motor de navigație și nu introduc logică pixel-click.
- **Limită explicită:** dacă lipsesc simultan adaptorul optic și orice altă
  sursă autorizată, iar memory/injection/packets rămân interzise, nu există
  feedback live extern pentru poziție/facing. În acel mod, live autonomy trebuie
  să refuze fail-closed, nu să pretindă precizie din dead reckoning.
- **Stare:** port implementat și testat; adaptoarele replay/private telemetry
  și selecția explicită de provider rămân deschise.

## ME-046 — Orizontul MPPI nu corespunde duratei reale a comenzii

- **Observat:** modelul predictiv simulează pași de 50 ms, dar W și viteza RMB
  rămân active până la următoarea observație sau lease-ul de 450 ms. La cadre
  lente, aceeași corecție este aplicată de câteva ori mai mult decât a fost
  simulată, favorizând overshoot și inversări stânga–dreapta.
- **Cauză generală:** planning time, observation time și actuator hold time sunt
  trei ceasuri diferite, iar durata reală nu este feedback pentru rollout.
- **Direcție de rezolvare:** runtime persistent, timestamp comun, model step
  derivat din latența măsurată și comenzi cu valabilitate explicită; MPPI va
  primi și obstacolele înainte de selecție, nu doar avoidance post-procesat.
- **Stare:** cauză arhitecturală documentată; implementarea urmează după portul
  de observație, cu replay pe coridoarele holdout înainte de test live.

## ME-047 — Închiderea Codex oprea Control Center-ul și serverul LAB

- **Observat:** Control Center, MariaDB, `realmd` și `mangosd` dispăreau când se
  închidea taskul Codex, deși launcherele intermediare foloseau `Start-Process`.
- **Cauză generală:** primul proces PowerShell rămânea în job-ul Windows al
  terminalului Codex; copiii moșteneau aceeași limită de lifetime. Ascunderea
  ferestrei cu `CREATE_NO_WINDOW` nu detașează procesul de job.
- **Soluție:** `Start-StandaloneLab.ps1` apelează launcherul Python, care creează
  bootstrapul cu `CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP |
  CREATE_NO_WINDOW`. Bootstrapul pornește și validează database → realm → world,
  apoi Control Center-ul vizibil, după care poate ieși fără să închidă copiii.
- **Confirmare live:** bootstrap PID 25884 a ieșit; MariaDB PID 36724,
  `realmd` PID 27860, `mangosd` PID 26044 și Control Center PID 33640 au rămas
  active. Porturile loopback 3307, 3724, 8085 și 3443 sunt toate `LISTEN`.
- **Stare:** rezolvat și confirmat live; persistența după reboot nu este
  activată automat.

## ME-048 — Demonstrația manuală era oprită de aggro și rămânea nefinalizată

- **Observat:** demonstrația operatorului Crypt → Brill → Crypt a păstrat
  386,93 secunde de video și 11.152 evenimente sincronizate, dar procesul s-a
  oprit pe retur când HUD-ul a raportat combat. Fișierul sumar a rămas în
  `RECORDING`, deși timeline-ul și MP4-ul fuseseră închise corect.
- **Cauză generală:** recorderul read-only reutiliza adaptorul de observație al
  motorului care deține input. Acesta cere corect handoff către Combat Engine
  la aggro, însă o cameră de măsurare nu deține mișcarea și nu trebuie să
  întrerupă omul care conduce.
- **Soluție standalone:** sursa de poziție separă acum explicit observarea
  read-only de autoritatea de mișcare. Recorderul continuă prin combat fără să
  trimită input; motorul autonom păstrează handoff-ul fail-closed. Orice altă
  eroare finalizează dovada ca `INTERRUPTED`, nu o lasă fals `RECORDING`.
  Fiecare sesiune viitoare primește director propriu cu timeline, path și
  manifest, astfel încât următoarea captură nu o suprascrie. Facingul exact din
  HUD este inclus separat de tangenta geometrică a traseului.
- **Regresie:** 70 teste de recording și runtime navigation trec, inclusiv
  observator read-only în combat și păstrarea handoff-ului pentru runtime-ul
  care controlează clientul.
- **Dovezi păstrate:**
  `operator-crypt-brill-return-partial-20260829-173329`; traseul ajunge la
  2,31 yd de destinația Brill și returul este păstrat până la 869 yd de punctul
  de start.
- **Stare:** defectul recorderului este rezolvat și testat; captura curentă este
  validă pentru sistem identification, dar returul complet necesită o nouă
  demonstrație numai dacă vrem și porțiunea lipsă drept referință.

## ME-049 — Controllerul confunda un viraj mare cu obligația de a opri

- **Observat:** demonstrația sincronizată arată ieșirea din cryptă și drumul
  exterior cu mers continuu: RMB era deja apăsat la pornirea capturii, W a fost
  ținut 14,24 secunde până la primul autorun, iar virajele au folosit nouă
  impulsuri A și patru D. În schimb, controllerul autonom avea 14 secvențe de
  `PIVOT` pe ultimul retur, deși coridorul cyan era corect.
- **Cauză generală:** o eroare unghiulară mare era tratată singură ca dovadă că
  mersul înainte nu este sigur. Ea descrie însă direcția viitoare, nu o
  coliziune. Asta producea stop-turn-go chiar în spațiu liber.
- **Soluție standalone:** cât timp capsula este încă în coridorul topografic
  verificat, followerul păstrează W/RMB și adaugă impulsuri scurte A/D în sensul
  arcului. Pivotul staționar este rezervat recuperării după ieșirea reală din
  anvelopa sigură. Hairpin-urile cu clearance insuficient păstrează vechea
  protecție; regula nu conține hartă, zonă sau coordonate.
- **Regresie:** 82 teste controller/MPPI/simulation trec. Monte Carlo v20 a
  trecut 60.000/60.000 rulări în șase clase (drept confined, scară, S-gate,
  doodad gateway, pod drept și hairpin îngust), fără coliziuni și fără eșecuri
  de calitate. Podul drept, S-gate și doodad gateway au pivot maxim zero;
  hairpin-ul îngust păstrează pivotarea de siguranță sub pragul de 0,30.
- **Stare:** candidat validat offline; confirmarea vizuală live și comparația
  cu demonstrația operatorului rămân obligatorii înainte de promovare.

## ME-050 — Navmesh-ul structural valid trasează printr-un perete din cryptă

- **Observat:** testul filmat cu `continuous_trajectory_v1` a păstrat W/RMB și
  zero viraje discrete, dar Predatorul a intrat repetat în zidul interior.
  Detour a întors un coridor complet din numai două puncte între
  `(1676.37, 1677.47, 138.73)` și `(1677.38, 1668.41, 136.92)`.
- **Cauză generală:** tile-ul `Azeroth 28_28` este structural încărcabil, însă
  cele două poligoane sunt etichetate `ground` și înglobează greșit obstacolul
  WMO. Testul geometric offline simula chiar această coardă falsă, deci scorul
  100/100 nu reprezenta traversabilitate în client.
- **Protecție implementată:** o memorie confirmată care intersectează traseul,
  dar pentru care niciun bypass nu trece validarea, produce
  `CONFIRMED_CLEARANCE_PRIOR_UNRESOLVED` și oprește planul înainte de input.
  Nu se mai repetă o coliziune cunoscută doar fiindcă Detour spune `complete`.
- **Corecție generală a memoriei:** contactele locale formează celule de
  frontieră independente; nu se mai unesc într-un cerc crescător care poate
  acoperi atât zidul, cât și ieșirea lui reală. Cunoașterea confirmată nu
  expiră. Datele vechi sunt păstrate; migrarea lor în celule trebuie derivată
  din evenimentele brute de contact, nu inventată.
- **Corecție topologică standalone:** dacă și numai dacă o coardă autonomă
  intersectează celule confirmate, motorul poate folosi o demonstrație continuă
  din același build drept dovadă de suprafață traversată. Folosește doar
  porțiunea locală dintre poziția curentă și primul punct unde reintră în ruta
  autonomă; destinația și restul traseului rămân alese de planner. Segmentele
  sunt păstrate la maximum aproximativ 1,25 yd, astfel încât Detour/smoothing
  să nu reinventeze o coardă prin perete. Fără contradicție confirmată,
  demonstrația nu schimbă ruta.
- **Regresie:** 121 teste pentru Movement Engine și obstacle memory trec,
  inclusiv perete lung în celule și bypass imposibil raportat fail-closed.
- **Stare:** repetarea oarbă este eliminată, memoria istorică a fost refăcută
  în celule din 14 evenimente brute, iar stratul local de corecție topologică
  reintră în ruta autonomă fără coordonate scrise în cod. Urmează o singură
  probă filmată; tile-ul rămâne defect și trebuie reconstruit ulterior.

## ME-051 — Spike-urile DXGI întrerupeau startup-ul înainte de movement

- **Observat:** două probe live au eșuat la prima captură cu latențe de 891 ms,
  respectiv 304 ms, peste deadline-ul nominal de 250 ms. Runnerul se oprea
  înainte de primul frame de control.
- **Soluție generică:** `LiveCoordinatePoseSource` retrimite acum și
  `CaptureDeadlineExceededError` în aceeași fereastră bounded de observație,
  exact ca un frame lipsă. După retry-uri și o singură repornire DXGI, sistemul
  rămâne fail-closed și nu folosește un cadru vechi.
- **Regresie:** testul dedicat pentru spike-ul de deadline și suita Movement
  trec. O probă fără recorder a depășit ulterior problema de captură.

## ME-052 — Controller adaptiv pentru hairpin-uri înguste

- **Observat:** geometric follower avea eșecuri rare pe hairpin-uri înguste,
  în timp ce MPPI era mai stabil acolo, dar mai slab pe S-gate-uri largi.
- **Soluție standalone:** `adaptive_trajectory_v1` selectează MPPI numai din
  geometria corridorului curent (portal local îngust și turn ascuțit), iar în
  rest folosește geometric follower. Selectarea este latched per corridor;
  planurile stale, frontierele parțiale și erorile MPPI revin la fallback.
- **Regresie offline:** șase clase de traseu, câte 1.000 de rulări fiecare,
  au avut 6.000/6.000 completion și zero coliziuni. Quality pass a fost
  5.997/6.000 (99,7%); cele trei excepții sunt în `narrow_s_gate`, ajung la
  destinație și depășesc doar pragul conservator de patru schimbări de semn
  (cinci), fără abatere sau pivotare excesivă. Hairpin-ul îngust a trecut
  1.000/1.000.
- **Probă LAB bounded:** clientul a ajuns la `(1894.39, 1587.42)` înainte de
  expirarea bugetului de 300 de frame-uri. Rezultatul este în
  `holdout-adaptive-crypt-brill-20260830-retry.json`; confirmă progresul live,
  nu sosirea în Brill și nu înlocuiește încă o probă filmată completă.

## ME-053 — Recording-ul manual reintroducea bucle în egress-ul autonom

- **Observat:** după resetarea la spawn, rularea autonomă a oscilat în cryptă
  și a ajuns `STUCK_REPLAN_REQUIRED`. Recording-ul operatorului avea reveniri
  și corecții de cameră la început, dar era injectat ca prefix executabil până
  la primul punct de reintrare.
- **Cauză:** dovada de suprafață traversată era confundată cu autoritate de
  rutare. Astfel, buclele observate manual deveneau waypoints invizibile și
  produceau zigzag/pivotări chiar înainte de poartă.
- **Soluție standalone:** recording-ul poate fi încărcat ca prior de
  traversabilitate, dar nu mai are niciodată autoritate de execuție. Trece prin
  filtre generice de detur, revenire în bazinul de start și backtracking;
  înregistrările zgomotoase rămân doar dovezi pentru anularea obstacolelor
  false, fără puncte executabile. Obstacolele fără bypass navmesh rămân
  fail-closed și sunt raportate cu ID-ul lor.
- **Regresie:** suita Movement/Navigation de 183 teste trece; au fost
  adăugate teste pentru demonstrații zgomotoase și pentru opțiunea autonomă
  fără recording. Două probe LAB au fost oprite înainte de mișcare: prima la
  geometrie confirmată fără bypass (`c7d030808bec03c9`), a doua la lease-ul
  vechi de 180 ms. Fereastra de frame este acum aliniată bounded la 300 ms.
- **Stare:** regresia de injectare este eliminată offline; egress-ul necesită
  încă o probă live după reînnoirea autorizației LAB.

## ME-054 — Selectorul de etaj a preferat coarda exterioară scurtă

- **Observat:** după eliminarea buclei din recording, egress-ul bounded a ieșit
  din cryptă, dar a raportat trei replannări de coliziune în primii metri.
  Query-ul de navmesh pentru aceeași poziție oferea două suprafețe complete:
  WMO/interior la `z≈121,8` cu detururi de doodad și ground/exterior la
  `z≈138,7` cu o coardă directă de 9 yd.
- **Cauză:** selectorul compara mai întâi lungimea și numărul de poligoane;
  alegea coarda exterioară doar fiindcă era mai scurtă, ignorând faptul că
  observația locală marca actorul într-un WMO acoperit.
- **Soluție standalone:** ordinea generică este acum: coridor complet, suprafață
  care corespunde mediului local (WMO sau overhead închis), diferența față de
  înălțimea observată, apoi stretch/topologie și lungime. Nu există coordonate
  sau excepții pentru cryptă.
- **Regresie:** 200 teste Movement/Navigation trec. Probe offline pe WorldPack
  real au selectat `z=121,797379` și au identificat `WMO_STRUCTURE_WITH_EGRESS`,
  nu coarda exterioară `z=138,729095`.
- **Stare:** cauza de etaj este corectată și verificată offline; nu declar încă
  traseul Crypt→Brill complet până la o viitoare probă live explicită. Proba
  bounded post-fix este în
  `data/runtime/navigation-f3b/results/navmesh-roaming-0840e90a-352e-4065-b2a5-5a893088b80f.json`:
  a selectat WMO-ul corect, a ieșit din cryptă până la `x≈1834`, a atins patru
  waypoint-uri semantice și a avut zero `OBSERVED_COLLISION_REPLAN` și zero
  acțiuni `STUCK`. S-a oprit la plafonul de 600 frame-uri, deci nu dovedește
  încă sosirea în Brill.

## ME-055 — Control Center pornea un profil diferit de proba validată

- **Observat:** proba bounded care a trecut egress-ul folosea
  `adaptive_trajectory_v1`, în timp ce butonul din Control Center pornea
  `continuous_trajectory_v1`. Astfel, rezultatul verificat offline/live nu era
  reproductibil din UI și putea părea o regresie a criptei.
- **Soluție standalone:** pornirea autonomă din UI folosește acum profilul
  adaptiv verificat: geometric pe teren normal și MPPI doar pentru turnuri
  înguste/aspre, cu fereastră bounded de 128 probe × 24 pași. Nicio rută sau
  coordonată de cryptă nu este adăugată în cod.
- **Regresie:** 196 teste relevante trec, inclusiv verificarea că UI transmite
  exact controllerul și parametrii bounded; pycompile și verificarea de
  whitespace trec.
- **Stare:** trebuie făcută o nouă probă live doar după ce UI este repornit,
  deoarece procesul vechi nu își schimbă controllerul în memorie.

## ME-056 — Micro-reversările de RMB făceau S-gate-ul să pară instabil

- **Observat:** pe `narrow_s_gate`, trei din 1.000 de rulări completau traseul,
  dar aveau cinci schimbări de semn ale mouse-ului. Primele schimbări erau
  pulsații de un pixel separate de câte un tick neutru; nu indicau o coliziune,
  însă făceau camera să vibreze.
- **Soluție standalone:** controllerul păstrează prima corecție și aplică
  histerezis doar unei inversări sub două pixeli, când actorul este aproape de
  axa corridorului și există o curbă topologică în preview. Corecțiile mai mari,
  driftul real și pivotul de siguranță rămân neatinse.
- **Regresie:** benchmark-ul adaptiv de 6.000 de rulări (1.000 pentru fiecare
  din cele șase scenarii) are acum 6.000/6.000 quality pass, zero coliziuni și
  maximum trei schimbări de semn pe S-gate. Suitele Movement/Navigation de 196
  teste trec.

## ME-057 — Verificarea finală a WorldPack-ului standalone

- **Observat:** după modificările de controller, era necesară o verificare că
  sursa de hartă rămâne independentă de client, server și emulator.
- **Regresie:** profilul WorldPack `tbc243-azeroth-full-v3` este `VERIFIED`, iar
  validarea de portabilitate standalone este `PASS` pentru harta disponibilă.
  Suita combinată Movement/Navigation relevantă are 200 teste verzi; nu au
  rămas procese de benchmark, validator sau runtime armate. Probe-ul local
  bounded al poziției de spawn a rezolvat actorul la `z≈121,797379`, a găsit
  structura WMO și 15 egress-uri topologice verificate; artefactul este
  `data/runtime/navigation-f3b/crypt-local-environment-final.json`.

## ME-058 — Revalidare după repornirea Control Center-ului

- **Observat:** procesul vechi al Control Center-ului păstra profilul de
  steering anterior, deși codul fusese actualizat la `adaptive_trajectory_v1`.
- **Soluție:** fereastra veche a fost închisă controlat, fără a opri WoW sau
  serverul, apoi Control Center-ul și serviciul de awareness au fost relansate
  din workspace-ul curent. Procesul nou folosește WorldPack-ul TBC 2.4.3
  `tbc243-azeroth-full-v3`; runtime arm-ul a rămas dezarmat.
- **Regresie:** 211 teste Movement/Navigation trec cu runtime-ul proiectului,
  inclusiv portalurile condiționale și supervisorul de călătorie;
  WorldPack-ul este `VERIFIED`, iar verificarea de portabilitate standalone este
  `PASS` (`map_count=1`, `worldpack_count=1`). Nu s-a pornit un al doilea test
  live: limita de validare live rămâne un singur test bounded, deja executat.
- **Stare:** configurația finală este încă nevalidată live după această
  repornire; rezultatul bounded existent dovedește egress-ul din cryptă, nu și
  sosirea completă la Brill.

## ME-059 — Audit offline extins al controllerului adaptiv

- **Observat:** verificarea de bază trebuia completată cu testele dedicate
  pentru adaptive steering, MPPI, quality gate, WorldPack runtime și
  portabilitate.
- **Regresie:** suita extinsă a trecut 25/25 teste, iar împreună cu suita
  Movement/Navigation principală rezultă 236 teste verzi în runtime-ul
  proiectului. Benchmark-ul existent rămâne 6.000/6.000 rulări quality-pass,
  cu zero coliziuni.
- **Stare:** dovezile offline sunt consistente cu versiunea curentă; singura
  limită rămasă este confirmarea live a codului de steering după ultima
  repornire a UI-ului.

## ME-060 — Quality-gate-ul respinge trace-ul live anterior

- **Observat:** evaluarea oficială a trace-ului bounded existent a raportat
  `arrived=false`, 77 schimbări de semn (74,2/min), 75 cadre `PIVOT` din 600
  (12,5%), nouă goluri de observație peste 300 ms și un gol maxim de 1,81 s.
- **Interpretare:** acesta este un eșec real al rulării istorice, nu o dovadă
  că traseul este stabil. Trace-ul a fost capturat înainte de ultima modificare
  de histerezis și înainte ca UI-ul să fie repornit cu profilul adaptiv; nu este
  folosit ca acceptanță pentru versiunea curentă.
- **Acțiune:** quality-gate-ul rămâne fail-closed, iar benchmark-urile offline
  și suitele curente sunt păstrate separat de acest rezultat live. Nu se
  pornește automat un al doilea test live.

## ME-061 — Recenter în mers pentru abaterea moderată din spații înguste

- **Observat:** trace-ul istoric intra în pivot staționar la 3,0–3,4 yd
  abatere într-un coridor WMO, cu eroare de direcție sub 1 radian. Asta crea
  opriri repetate, deși navmesh-ul încă oferea un coridor valid.
- **Soluție standalone:** în profilele acoperite, abaterea aflată într-o bandă
  generică de 1 yd peste pragul hard-recenter și cu eroare sub 1,4 rad este
  corectată în mers cu W+RMB. Abaterile severe și unghiurile mari păstrează
  pivotul staționar de siguranță; nu există coordonate de cryptă în regulă.
- **Regresie:** testul nou pentru recenter moderat și testul de limită severă
  trec. Benchmark-ul adaptiv v4 are 6.000/6.000 quality-pass și zero
  coliziuni; scenariile confined_straight, confined_stair_bend,
  narrow_s_gate și straight_bridge au pivot fraction maxim 0.0.
- **Stare:** 238 teste relevante trec. Schimbarea este validată offline;
  trace-ul live nou nu este pornit automat.

## ME-062 — Revalidare locală a frontierei WMO după recenter

- **Observat:** după schimbarea de steering era necesar să verificăm separat
  că rezolvarea verticală și egress-ul din structura acoperită nu au fost
  afectate.
- **Regresie:** proba standalone a rezolvat poziția la
  `z=121,797379`, a identificat un singur WMO, coridor complet și 15 egress-uri
  topologice verificate, cu încredere 0,95. Au fost raportate 77 obstacole
  statice locale; nicio autoritate de execuție nu a fost acordată.
- **Stare:** selecția de suprafață și frontieră rămâne stabilă după corecția
  de recenter; dovada este în
  `data/runtime/navigation-f3b/crypt-local-environment-current-v2.json`.

## ME-063 — Portabilitate după recenter

- **Regresie:** validarea pe sursa actuală a trecut din nou cu
  `execution_authority=false`, `map_count=1` și `worldpack_count=1`; nu este
  necesară instalarea clientului, rularea emulatorului sau pornirea serverului.
- **Stare:** artefactul post-recenter este
  `data/runtime/navigation-f3b/standalone-portability-post-recenter.json`.

## ME-064 — Recenter-ul în mers este limitat la coridoare complete

- **Observat:** o corecție în mers este sigură doar când navmesh-ul a dovedit
  întregul coridor; pe o frontieră parțială, continuarea poate fi necunoscută.
- **Soluție standalone:** banda soft de recenter cere acum
  `corridor.complete`; coridoarele parțiale rămân fail-closed și folosesc
  pivot/replan până la o nouă frontieră verificată.
- **Regresie:** 239 teste relevante trec, inclusiv cazul de coridor parțial;
  nu sunt introduse hărți sau coordonate speciale.

## ME-065 — Separarea cunoașterii manuale de execuția autonomă

- **Regresie:** testele de arhitectură, operator path, demonstrații și
  navigație semantică au trecut 25/25. Rutele desenate și demonstrațiile sunt
  tratate ca dovezi/prioruri, nu ca micro-waypoint-uri executabile de autonom.
- **Stare:** auditul confirmă separarea în codul actual; nu au fost pornite
  procese live.

## ME-066 — Sosirea autonomă la Brill nu a trecut încă gate-ul de steering

- **Observat:** rularea bounded
  `navmesh-roaming-8a37d798-bdf7-438e-a484-70edaa6fab92.json` a ajuns la Brill
  în 3.004 cadre și a terminat 44/44 waypoint-uri semantice. Nu a folosit
  operator path și a avut zero collision replans, recovery, evenimente `STUCK`
  sau replannări parțiale.
- **Quality gate:** sosirea nu a fost tratată ca acceptanță. Trace-ul a avut 167
  schimbări de semn (52,24/min), 21 cadre `PIVOT` și două goluri de observație
  peste 300 ms; gate-ul a eșuat la `camera_left_right_balance` și
  `control_observation_gap`.
- **Diagnostic:** 166/167 inversări porneau cu impulsuri de 1-3 pixeli, de
  regulă în interiorul unei abateri de 3 yd. Traseul nu selectase MPPI;
  balansul provenea din follower-ul geometric pe curbele deschise.
- **Stare:** rezultatul confirmă ruta autonomă și sosirea, nu calitatea finală
  a camerei. Artefactul oficial de calitate este
  `quality-navmesh-roaming-8a37d798-bdf7-438e-a484-70edaa6fab92.json`.

## ME-067 — Histerezis pentru micro-inversări pe curbe deschise

- **Soluție generică:** follower-ul geometric frânează la zero o inversare de
  1-3 pixeli pe o curbă deschisă când bearing-ul geometric stabilizat este deja
  în toleranța de recenter și actorul rămâne în envelope-ul de recovery derivat
  din geometrie. O abatere reală, o eroare mai mare, un coridor de precizie sau
  un `PIVOT` trece imediat. Segmentele drepte păstrează condiția conservatoare
  asupra solicitării brute, pentru a nu întârzia recenter-ul pe pod.
- **Regresii respinse:** o variantă care aplica regula și în spații de precizie
  a depășit marginal abaterea pe scară și hairpin; alta, bazată numai pe eroarea
  geometrică inclusiv pe drept, a redus `straight_bridge` la 850/1.000 quality
  pass. Niciuna nu a fost păstrată.
- **Regresie finală:** suita completă trece 1.207/1.207. Benchmark-ul adaptiv
  trece 6.000/6.000, cu zero coliziuni; hairpin-ul îngust trece 1.000/1.000,
  iar toate cele șase clase au quality pass 100%.
- **Probă live limitată:** revizia intermediară a parcurs aproximativ 95 yd în
  248 cadre, fără goluri de observație, collision replan sau `STUCK`, apoi s-a
  oprit corect la `COMBAT_HANDOFF_REQUIRED`. Nu s-a acordat autoritate de
  combat. Trace-ul `navmesh-roaming-8320fbb8-036b-4963-903f-fa19837085d6.json`
  a condus la condiția finală bazată pe bearing-ul geometric și nu validează
  încă exact codul final.
- **Stare:** runtime arm-ul a fost eliminat după expirarea autorizării
  temporale. Rămâne o singură probă bounded completă pe codul final, pornită
  dintr-o stare fără handoff de combat, urmată de quality gate-ul oficial.

## ME-068 — O comandă directă a oprit călătoria la aggro de rutină

- **Observat:** Predatorul s-a oprit la un Darkhound, deși godmode era activ și
  personajul nu murise.
- **Cauză:** comanda diagnostică directă omisese
  `--continue-through-routine-aggro`. Control Center și supervisorul aveau deja
  această politică împreună cu `--minimum-travel-health-fraction 0.55`.
- **Soluție:** testele complete folosesc supervisorul cu politica explicită.
  Direct runnerul rămâne fail-closed; godmode nu este confundat cu autoritate
  de combat și nu se adaugă cast/target input.
- **Verificare live:** traversările ulterioare au ajuns în Deathknell și Brill
  cu `combat_handoffs_used=0`.

## ME-069 — Metrică separată pentru balans rapid și curbe lente legitime

- **Observat:** numărul brut de schimbări de semn penaliza și o curbă S lungă,
  unde direcția camerei se schimbă legitim după mai multe secunde.
- **Soluție:** trace-ul păstrează toate `steering_sign_changes`, dar gate-ul de
  balans folosește `rapid_steering_reversals`: numai inversări opuse separate de
  maximum 0,50 s. Trace-ul istoric defect rămâne respins, cu 50 inversări rapide
  și 16,69/min; o curbă lentă nu este cosmetizată drept vibrație.
- **Regresie:** testele acoperă separat balansul rapid și S-curve-ul lent.

## ME-070 — Schimbarea profilului camerei elibera W în mijlocul rulării

- **Cauză:** comenzile de profil WMO/outdoor erau trimise sincron prin chat și
  necesitau eliberarea controalelor, producând pauze vizibile de 0,25-0,51 s.
- **Soluție:** schimbarea este memorată ca
  `CAMERA_PIVOT_PROFILE_DEFERRED` și aplicată numai după statusul terminal și
  `release_all()`. Nu mai întrerupe mersul pentru o preferință de prezentare.
- **Verificare live:** segmentele finale nu mai conțin opririle de profil.

## ME-071 — Replanificarea Detour sincronă producea goluri de peste o secundă

- **Observat:** trace-urile complete aveau pauze de 1,20-1,59 s exact la
  rafinarea unei linii semantice grosiere.
- **Soluție standalone:** spacing-ul semantic este 25 yd, un coridor complet
  respins numai pentru fly-by este reutilizat la handoff-ul exact, iar
  midpoint-ul de rafinare este preplanificat speculativ de doi workeri. Future-ul
  devine autoritativ numai după ce ruta grosieră completă dovedește gate-ul de
  abatere. Nu există nume, coordonate sau recording executabil.
- **Verificare:** testul cere ca midpoint-ul speculativ să fie identic cu cel
  derivat ulterior. Traversările v14 și v15 nu mai au goluri semantice de
  1,2-1,6 s.

## ME-072 — Fereastra de opt tick-uri rezona cu servo-ul camerei

- **Observat:** rularea v14 a ajuns în Deathknell, dar segmentul final a avut
  zece inversări rapide în 24,4 s. Ele reapăreau la fiecare 8-9 observații
  nenule, exact la expirarea histerezisului inițial.
- **Soluție:** settle-ul este 16 tick-uri la 25 Hz și suprimă numai o mică
  contrapulsație. O eroare reală peste 0,40 rad sau un hard recenter trece
  imediat.
- **Regresie:** benchmark-ul adaptiv v13 trece 6.000/6.000, zero coliziuni.

## ME-073 — Traversarea finală Deathknell–Brill și limita rămasă

- **Verificare live filmată:** supervisorul
  `holdout-adaptive-deathknell-brill-20260831-v15.json` a ajuns în Brill în două
  cicluri bounded, cu zero handoff-uri de combat. Filmarea ShadowPlay arată zona
  căruței, drumul principal, podul și sosirea fără orbită prin pădure.
- **Quality final:** ciclul ajuns `f6fa485d` are zero inversări rapide, zero
  pivoturi, zero goluri, gap maxim 0,078963 s și `passed=true`.
- **Limită raportată exact:** ciclul anterior de 5.000 frame-uri nu ajunsese
  încă la destinație și are un singur interval de observație de 0,3008658 s,
  cu 0,0008658 s peste prag. Gate-ul său rămâne corect `false`; intervalul nu
  coincide cu replanificarea semantică ori eliberarea W și nu este ascuns prin
  mărirea pragului.
- **Stare:** regresia de oprire lungă și rezonanța finală sunt remediate;
  abaterea izolată de capture rămâne urmărită separat.

## ME-074 — Scanarea nameplate-urilor putea concura cu ceasul de captură

- **Observat:** un ciclu bounded avea un singur interval de observație de
  `0,3008658 s`, fără eveniment de replanificare sau eliberare W. Detectorul
  read-only de entități copia cadrul complet și era pornit imediat ce future-ul
  anterior termina, uneori în aceeași fereastră de 50 ms ca DXGI.
- **Soluție generică:** scanarea dinamică este programată la fiecare patru cadre
  de control (aproximativ 5 Hz), iar trackerul păstrează TTL-ul independent de
  ritmul pose/control. Combat HUD și poziția rămân pe calea sincronă; nameplate-
  urile nu pot autoriza input și nu schimbă ruta.
- **Regresie:** testul pentru intervalul bounded și suita completă verifică
  ritmul; nu se mărește pragul strict de 300 ms și nu se elimină dovada din
  trace.
- **Stare:** corecția este validată offline; orice confirmare live viitoare
  trebuie să rămână bounded și să folosească o autorizare LAB nouă.

## ME-075 — Holdout live Crypt → Brill după throttling-ul detectorului

- **Verificare live:** cu autorizare LAB temporală nouă, Predator a fost resetat
  la spawn-ul canonic, observat viu în interiorul crypt-ului și apoi rulat prin
  supervisorul bounded către `settlement:brill`, cu `--maximum-combat-handoffs 0`
  și continuarea aggro-ului de rutină explicită. Rezultatul
  `holdout-adaptive-crypt-brill-20260831-v16.json` este `ARRIVED`, cu zero
  handoff-uri de combat.
- **Frontieră crypt:** primul ciclu a început la `z=121.797` în
  `WMO_STRUCTURE_WITH_EGRESS`; awareness-ul static a raportat portaluri de
  ieșire route-verified către teren. Ciclul de 5.000 frame-uri a fost marcat
  corect `CONTROL_FRAME_BUDGET_EXHAUSTED`, nu sosire falsă.
- **Quality arrival cycle:** ciclul
  `b50bd331-52b0-4d5c-bf9e-002dcb07b76d` are 3.201 frame-uri, zero goluri de
  observație, gap maxim `0.167324 s`, zero pivoturi și cinci inversări rapide;
  evaluatorul oficial raportează `passed=true`.
- **Stare:** comportamentul de oprire la aggro nu se reproduce când politica
  explicită a supervisorului este prezentă; după test, runtime arm este absent,
  Predator este viu în Brill, iar procesul WoW rămâne neatins. HP-ul final nu
  este însă dovadă de survivability: starea `labgod` nu a fost emisă în artefactul
  v16, iar protecția server-side putea proveni dintr-o sesiune de combat
  anterioară. Prin urmare, v16 validează rutarea/sosirea, nu rezistența la damage.
## ME-076 — Doodad static pe intersecția de la ieșirea din Deathknell

- **Observat:** filmarea v15 arată că Predator atinge signpost-ul de la
  intersecție, deși poligonul de navmesh rămâne traversabil. Acesta este un
  `DOODAD` indexat în WorldPack, nu o coordonată specială de traseu.
- **Soluție offline:** următorul orizont de cel mult opt obiective semantice
  interoghează indexul spațial al structurilor și adaugă cel mult opt discuri
  de clearance pentru doodad-urile ale căror bounds intersectează coridorul.
  Detour trebuie să demonstreze ocolirea; geometria nu devine waypoint și nu
  autorizează input.
- **Regresie:** testul sintetic include un signpost pe axa coridorului și unul
  în afara coridorului; numai primul este propus ca blocker bounded.

## ME-077 — Pauză scurtă la predarea dintre obiectivele semantice

- **Observat:** după pod, la aproximativ 50 yd, o predare de coridor putea
  elibera W înainte de alegerea următorului obiectiv.
- **Soluție:** când există o continuare semantică bounded și nu este activă o
  recuperare sau o ieșire de structură, lease-ul de mișcare este păstrat în
  timpul handoff-ului; watchdog-ul rămâne limita fail-closed. Evenimentul
  `SEMANTIC_HANDOFF_MOTION_HELD` face cauza verificabilă în trace.
- **Stare:** validat offline; confirmarea live rămâne amânată până la următorul
  test bounded cu protecția de combat explicit `OFF`.

## ME-078 — Secvențe semantice bounded pentru patrulare între destinații

- **Soluție:** supervisorul acceptă `semantic_destination_sequence` cu 2–16
  identificatori și 1–32 repetări. Fiecare legătură este replănuită din poza
  live proaspătă; fișierul nu conține waypoints executabile. Control Center
  poate construi aceeași secvență și o trimite supervisorului.
- **Limită:** secvența este un mecanism de rută/patrulare bounded, nu o
  autoritate de combat și nu promite cunoaștere server-side în Champion.

## ME-079 — Holdout live Crypt → Brill → Crypt cu radius semantic runtime extins

- **Verificare live:** supervisorul `holdout-crypt-brill-crypt-20260831-v19.json`
  a executat secvența `[settlement:brill, landmark:deathknell-crypt]` și a raportat
  `ARRIVED` pentru ambele legături, cu `combat_handoffs_used=0` și fără autoritate de
  execuție. Brill s-a atins în primul ciclu, iar întoarcerea în crypt s-a încheiat la
  aproximativ 15,9 yd de centrul semantic, în raza de 22 yd.
- **Observație:** niciuna dintre sosiri nu trece încă evaluatorul strict de capture:
  prima legătură are trei goluri peste 300 ms (maxim `1,1277306 s`), iar a doua are
  unul (`0,3126866 s`). Golurile sunt între cadre `FOLLOW`, nu sunt mascate ca sosiri
  și nu provin din schimbarea destinației.
- **Stare:** rutarea multi-destinație și revenirea în crypt sunt confirmate live;
  calitatea temporală a capturii rămâne `false` și necesită diagnostic separat înainte
  de orice concluzie de stabilitate. Combat nu a fost pornit.

## ME-080 — Coliziune târzie cu cartul de la Deathknell și preplanarea izolată

- **Observat:** holdout-ul `holdout-crypt-brill-crypt-20260831-v20.json` a
  ajuns la ambele destinații, dar evaluatorul strict a păstrat un gap maxim de
  `0,3412151 s` pe Brill și `0,3165173 s` la întoarcere. Trecerea de la
  ThreadPool la ProcessPool a eliminat competiția GIL din preplanare, însă
  holdout-ul următor (`v21`) a întâlnit o coliziune reală în zona finală.
- **Dovadă statică:** primul blocker din trace (`1995,29;1547,17`) este în
  bounds-ul WorldPack pentru `0:doodad:336181`, asset
  `world/azeroth/karazahn/passivedoodads/brokencart/kn_brokencart.mdx`.
  Nu este dovadă de aggro sau de coordonate server-side.
- **Soluție generică:** structurile DOODAD sunt acum reinterogate bounded la
  fiecare preplan semantic, numai pe următorul segment. Obstacolul este unit
  cu blocker-ele observate și transmis unui query Detour nou; nu devine
  waypoint și nu acordă autoritate de execuție.
- **Regresie:** suita motorului `123/123`, suita completă `1.230/1.230`, iar
  validarea semantică offline pentru Crypt→Brill și Brill→Deathknell este
  `PASS` (131, respectiv 117 etape validate).
- **Stare live:** `v21` s-a oprit `STUCK_REPLAN_REQUIRED` după patru
  recuperări bounded în aceeași concavitate; Predator a rămas viu, cu HP
  complet, iar combat handoff a fost `0`. Nu declarăm încă stabilitate live;
  următorul holdout trebuie să confirme ocolirea cartului și calitatea de
  captură, cu protecția explicit `OFF`.

## ME-081 — Opening WMO putea lăsa handoff-ul pe partea acoperită

- **Observat:** `v24` s-a oprit în interiorul Crypt după patru coliziuni locale
  lângă shell-ul WMO. Midpoint-ul opening-ului era o mărturie de frontieră,
  dar rezoluția navmesh putea rămâne pe suprafața `wmo` chiar dacă aceeași
  coordonată era declarată portal de ieșire.
- **Soluție generică:** motorul păstrează abordarea către opening-ul grafului,
  apoi caută numai pe raza derivată din centrul structurii o ancoră bounded,
  revalidată de Detour. Ancora este acceptată doar dacă awareness-ul de început
  al continuării expune `ground` și nu `wmo`; nu există coordonate hardcodate.
- **Regresie:** suita completă rulează `1.233/1.233`; verificarea offline reală
  pornește din spawn (`1676.320,1677.470,121.797`), ajunge la opening-ul
  `1666.369,1662.649,141.876`, iar ancora rezolvată este
  `1666.711,1661.981,141.940`, cu continuare `ground` completă.

## ME-082 — Holdout live corectat: blocaj ulterior pe prop static în aer liber

- **Verificare live:** `holdout-crypt-brill-crypt-20260831-v26.json` a folosit
  WorldPack-ul și graful Azeroth corecte, reset la spawn, protecție combat
  `OFF`, două cicluri bounded și zero combat handoff-uri.
- **Rezultat:** ieșirea din Crypt nu a mai repetat blocajul v25; Predator a
  parcurs 26/68 obiective semantice către Brill și s-a oprit fail-closed la
  `PARTIAL_CORRIDOR_FRONTIER_STUCK` în jurul `2156.319,1301.749`, cu 3465
  frame-uri și fără recuperări locale suplimentare. Imaginea checkpoint arată
  un prop/arbore static mare în fața personajului; nu este dovadă de aggro.
- **Limită:** v26 nu validează Crypt→Brill→Crypt și nu justifică o altă rerulare
  live în acest turn. Este progres de egress, dar rămâne un blocker generic de
  frontieră statică ce trebuie diagnosticat offline înainte de următoarea
  autorizare.

## ME-083 — Frontieră semantică în interiorul unui outpost WorldPack

- **Dovadă:** la waypoint-ul 25→26, Detour a rezolvat frontieră la
  `2156.845,1299.999`, iar ținta semantică următoare era
  `2161.291,1293.502`. Indexul static arată că ținta cade în bounds-ul
  `0:doodad:140804`, asset `world/lordaeron/tirisfalglade/passivedoodads/
  outposts/tirisfalloutpost06.mdx` (bounds x `2118.042..2201.752`, y
  `1261.120..1294.854`).
- **Interpretare:** `v26` nu indică un eșec de ieșire din Crypt și nici aggro;
  plannerul a primit o țintă semantică ce intersectează un prop static mare și
  a oprit fail-closed după un frontier replan. Următoarea corecție trebuie să
  înlocuiască generic ținta ocupată cu un punct rutier ulterior verificat de
  Detour, păstrând secvența fără waypoint executabil hardcodat.

## ME-084 — Bypass bounded pentru prop-uri largi și ținte ocupate

- **Soluție offline:** discurile pentru props cu rază circumscrisă mare sunt
  reduse la 90% din cea mai îngustă jumătate de amprentă orizontală; Detour
  aplică separat clearance-ul actorului. Înainte de testarea fiecărui bypass,
  WorldPack respinge țintele care cad în bounds-ul unui `DOODAD`.
- **Dovadă:** pe segmentul real v26, țintele atlas 49–51 sunt marcate ocupate,
  iar punctul exterior 52 (`2169.054,1256.341`) are coridor complet cu
  blocker-ele statice recalibrate (`r=15.18` yd pentru outpost). Extensia este
  limitată la opt eșantioane ordonate și nu promovează niciun punct la
  waypoint executabil.
- **Regresie:** suita completă `1.237/1.237`, validarea semantică v27 `PASS`.

## ME-085 — WMO de margine la Deathknell nu era în orizontul static

- **Dovadă live:** holdout-ul `holdout-crypt-brill-crypt-20260831-v29.json`,
  cu patru cicluri permise, s-a oprit `RESET_REQUIRED` după 1236 frame-uri și
  10/69 obiective semantice la `1853.621,1560.456`. Predator a rămas viu,
  protecția a fost `OFF`, iar combat handoff a fost `0`.
- **Cauză confirmată în WorldPack:** poziția intră în WMO-ul
  `0:wmo:143396`, asset `world/wmo/azeroth/buildings/duskwood_humantwostory/
  duskwood_humantwostory.wmo`, bounds x `1848.488..1881.346`, y
  `1546.959..1584.312`. Orizontul static interoga numai `DOODAD`, astfel
  clădirea nu ajungea în query-ul Detour înainte de coliziune.
- **Corecție generică offline:** orizontul include acum și WMO-uri care
  intersectează segmentul următor; un WMO care conține poziția de start este
  exclus, pentru a nu concura cu planul verificat de egress al Crypt-ului.
  Nu există coordonate sau asset-uri hardcodate.
- **Regresie:** suita completă `1.239/1.239`; testele motor + runtime client
  `211/211`; următorul live nu se
  pornește în această etapă. Este necesară o verificare offline a coridorului
  Deathknell înainte de o nouă autorizare bounded.

## ME-086 — Registry-ul de hărți devine sursa Control Center-ului

- **Schimbare:** registry-ul TBC păstrează acum, pentru fiecare mapă, căile
  opționale către semantic catalog, structure index și access graph. Control
  Center-ul afișează toate profilele declarate și folosește binding-ul ales
  pentru serviciul de awareness, viewer și launch-ul supervisorului.
- **Siguranță:** profilele fără catalog semantic și graph complet (în prezent
  Kalimdor și Expansion01) sunt vizibile ca inventar, dar rămân
  `OBSERVE_ONLY`; nu sunt prezentate ca rutare autonomă validată. Azeroth și
  Shadowfang au artefacte structurale declarate, însă Shadowfang încă nu are
  catalog semantic de destinații în Control Center.
- **Regresie:** testele registry/UI/runtime relevante `94/94`. Aceasta elimină
  hardcodarea implicită din binding, dar nu pretinde acoperire live pe toate
  hărțile înainte de generarea și validarea cataloagelor lor.

## ME-087 — Holdout v30: WMO-ul nou este depășit, aggro-ul rămâne gate separat

- **Verificare live unică după patch:** `holdout-crypt-brill-crypt-20260831-v30.json`
  a pornit din Crypt cu protecția `OFF`, patru cicluri maxime, 12.000 frame-uri
  pe ciclu și `maximum-combat-handoffs=0`.
- **Rezultat:** Predator a trecut de zona WMO `duskwood_humantwostory` care
  blocase v29 și a ajuns la `2217.778,691.113` pe drumul spre Brill. Runner-ul
  a eliberat inputul la primul aggro și supervisorul a închis
  `STOPPED_COMBAT_BUDGET`/`COMBAT_HANDOFF_REQUIRED`; nu este dovadă de buclă
  completă. Checkpoint-ul final confirmă moartea la `Ravaged Corpse`, deci
  protecția `OFF` și limita de survivability sunt reale.
- **Concluzie:** corecția WMO este susținută de acest segment live, însă
  Crypt→Brill→Crypt încă nu este acceptat. Sesiunea a fost disarmată și
  Predator resetat la spawn; nu se pornește o a doua încercare în această
  rundă.

## ME-088 — Control Center-ul propagă explicit politica de travel aggro

- **Schimbare offline:** launch-ul semantic din Control Center include acum
  `--continue-through-routine-aggro`. Runner-ul păstrează coridorul numai peste
  pragul de sănătate verificat; sub prag eliberează și supervisorul poate face
  handoff către combat sau recovery. Nu se mărește autoritatea combat și nu se
  activează godmode.
- **Motivație:** supervisorul injecta deja acest flag în comanda runnerului;
  v30 s-a oprit la primul aggro deoarece handoff-ul a fost cerut când pragul
  de sănătate nu mai permitea continuarea, iar rezultatul vechi nu păstra
  `health_fraction`. Control Center-ul îl propagă acum explicit pentru a
  elimina orice abatere între launch-uri, dar această corecție de consistență
  nu dovedește bucla și nu justifică un al doilea live în aceeași rundă.
- **Regresie:** testele supervisor/client relevante `91/91`.

## ME-089 — Handoff-ul combat păstrează dovada pragului de sănătate

- **Schimbare offline:** rezultatul `COMBAT_HANDOFF_REQUIRED` include acum
  `in_combat`, `health_fraction` și `minimum_travel_health_fraction`. Astfel,
  o oprire la aggro poate fi deosebită de o eroare de captură sau de
  coliziune, fără a deduce sănătatea dintr-o captură video.
- **Regresie:** testul de runtime pentru contractul de handoff trece; suita
  completă `1.241/1.241` este verde.

## ME-090 — Control Center afișează capabilitatea reală a fiecărei hărți

- **Schimbare:** registry-ul expune un rezumat read-only pentru fiecare profil:
  runtime profile, semantic catalog, structure index și access graph. UI-ul
  etichetează explicit `AUTONOM` numai când toate patru artefactele există;
  altfel afișează `OBSERVE_ONLY`.
- **Stare curentă:** Azeroth este completă pentru fluxul validat; Shadowfang
  are WorldPack/structură dar nu semantic destination catalog; Kalimdor și
  Expansion01 sunt inventariate, dar nu au încă index/graph/catalog semantic.
  Nu sunt fabricate destinații sau coordonate pentru a umple golurile.
- **Regresie:** testele registry/UI `15/15`; selecția nu schimbă autoritatea de
  execuție și nu permite amestecarea dovezilor între hărți.

## ME-091 — Supervisorul propagă dovada de health-floor în fiecare ciclu

- **Schimbare offline:** când runner-ul închide un ciclu la combat handoff,
  supervisorul păstrează în pasul `NAVIGATION_CYCLE` câmpurile
  `in_combat`, `health_fraction` și `minimum_travel_health_fraction`. Schema
  rezultatulului le validează fără a le face obligatorii pentru ciclurile
  normale.
- **Motivație:** v30 a produs handoff și moarte reală, dar rezultatul vechi nu
  păstra pragul numeric. Următoarea analiză poate separa direct „aggro peste
  floor” de „health breach”, fără interpretare video.
- **Regresie:** testele supervisor/runtime `91/91`; nu este o autorizare live.

## ME-092 — Sequence și supervisor leagă explicit map_id-ul

- **Schimbare:** o secvență semantică poate declara `map_id`; supervisorul o
  respinge înainte de primul child dacă nu corespunde map-ului selectat, iar
  rezultatul supervisorului publică `map_id`. Control Center include map-ul
  profilului activ în secvențele generate.
- **Scop:** mai multe destinații și loop-uri rămân identifier-only și bounded,
  dar nu mai pot amesteca accidental coordonate din hărți diferite. Tranzițiile
  între hărți necesită încă cataloage și o politică de loading verificate; nu
  sunt simulate prin teleport sau waypoint-uri inventate.
- **Regresie:** testele destination-sequence/supervisor trec; full suite
  `1.241/1.241` este verde.

## ME-093 — Dovada v30 este aliniată cu comanda reală și suita curentă

- **Corecție documentară:** handoff-ul nu mai spune că v30 a omis
  `--continue-through-routine-aggro`. Supervisorul îl injecta deja; oprirea
  observată rămâne un handoff la aggro/health-floor, iar rezultatul vechi nu
  păstra `health_fraction`.
- **Verificare:** au trecut 107 teste țintite pentru registry, sequence,
  supervisor, UI și runtime client, compilarea modulelor atinse și
  `git diff --check`; suita completă curentă este `1.241/1.241`.
- Validatorul semantic offline a trecut din nou toate cele cinci cazuri
  (`canonical_crypt_spawn_to_brill`, dus/întors Deathknell–Brill,
  holdout-ul de la sudul lui Brill și fixture-ul de reset controlat).
- **Limită:** nu s-a pornit un nou test live și nu se revendică încă bucla
  Crypt→Brill→Crypt sau survivability.

## ME-094 — Secvențele necunoscute sunt refuzate înainte de execuție

- **Schimbare offline:** supervisorul verifică fiecare ID dintr-o secvență
  identifier-only în catalogul semantic al profilului activ înainte să
  pornească primul child. Un ID lipsă, duplicat sau un catalog invalid produce
  `SystemExit`; nu se emite input și nu se scrie o tranziție de destinație.
- **Regresie:** testul de refuz pentru ID necunoscut și secvența bounded trec;
  suita completă curentă este `1.242/1.242`.
- **Limită:** validarea nu creează cataloage pentru hărțile incomplete și nu
  transformă datele semantice în waypoints executabile.

## ME-095 — Travel aggro necesită dovadă HP proaspătă

- **Schimbare de test:** fluxul input-owner este acoperit explicit pentru
  continuarea aggro-ului peste pragul `0.55` și handoff sub prag. Absența
  dovezii de sănătate rămâne fail-closed; nu se deduce HP din captura video
  sau dintr-o valoare veche.
- **Regresie:** testul runtime țintit trece; suita completă curentă este
  `1.243/1.243`.
- **Limită:** nu este autorizare live și nu activează protecție de combat în
  timpul navigării.

## ME-096 — v31 confirmă un frontier-stuck la căruța spartă

- **Dovadă live bounded:** după reautorizare LAB, login și reset canonical la
  spawn, o singură rulare v31 Crypt→Brill a fost lăsată să se oprească
  fail-closed. A ajuns la `16/70` obiective, apoi a raportat
  `PARTIAL_CORRIDOR_FRONTIER_STUCK` la `[1993.961,1552.251]`; nu a existat
  combat handoff și nu există dovadă de moarte în această rulare.
- **Cauză map-evidence:** interogarea WorldPack în jurul poziției finale
  identifică doodad-ul `0:doodad:336181`, `kn_brokencart.mdx`, cu centru
  `[1993.696,1547.196]` și bounds `[1990.896..1996.496] ×
  [1543.501..1550.890]`. Plannerul semantic trece prin acest eșantion de
  drum, iar bypass-ul generic nu a găsit încă un coridor complet validat până
  la următorul eșantion.
- **Stare:** runtime arm a fost dezarmat imediat după test. Următoarea acțiune
  a fost un repro offline și un fix generic pentru clearance/route frontier,
  cu test înainte de revalidare live.

## ME-097 — Discurile doodad-urilor moderate sunt restrânse la footprint

- **Schimbare offline:** pentru doodad-uri a căror rază circumscrisă depășește
  semnificativ jumătatea minimă a bounds-ului, blockerul Detour folosește
  footprint-ul local cu marjă de 10%, nu discul circumscris. Astfel un copac
  lung sau o căruță nu închid celula de drum vecină.
- **Regresie:** testul nou pentru copac moderat și suita completă trec (`1245/1245`);
  validatorul semantic v29 rămâne `PASS` în toate cele cinci cazuri.
- **Live:** v33 a eșuat din cauza expirării autorizației în timpul rulării și
  nu este dovadă de navigare. După corecție, v34 a rămas
  `PARTIAL_CORRIDOR_FRONTIER_STUCK` la `[1966.334,1568.316]`, înainte de
  căruță; query-ul offline arată că aici limita este un frontier de navmesh
  existent, nu doar raza doodad-ului. Runtime arm a fost dezarmat.
  Revalidarea v35 a trecut această zonă și a ajuns la `58/74` obiective, apoi
  a oprit `RESET_REQUIRED` la `[2192.542,657.120]` după o coliziune locală
  rezolvată prin portal recenter; bucla Crypt→Brill→Crypt nu este încă
  completă. Runtime arm a fost dezarmat și după v35.

## ME-098 — WMO traversabil nu mai este exclus fără dovadă de blocaj

- **Schimbare offline:** la preplanarea următorului segment, un WMO nou
  adăugat pe orizont este testat cu un baseline local fără acel blocker. Dacă
  navmesh-ul clientului produce un coridor complet până la următorul obiectiv,
  WMO-ul rămâne suprafață traversabilă și nu se exclude întregul component;
  clădirile fără coridor complet rămân obstacole bounded.
- **Dovadă:** repro-ul WorldPack pentru podul acoperit `0:wmo:127329` elimină
  blockerul de 30 yd și obține coridor complet `[2185.095,675.461] →
  [2202.083,647.917]`. Testul unitar pentru filtrare și suita completă
  (`1246/1246`) sunt verzi.
- **Limită:** această schimbare este offline-only în această iterație; v35 a
  fost ultima revalidare live și runtime arm rămâne dezarmat.

## ME-099 — Regresia semantică offline v30 trece după filtrarea WMO

- **Dovadă offline:** `scripts/validate_semantic_road_journey.py` a fost rulat
  cu WorldPack-ul runtime `worldpack-runtime:tbc243:azeroth-full:v3` și worker-ul
  nativ `pa_nav_probe-v34`.
- **Rezultat:** fișierul
  `data/runtime/navigation-f3b/semantic-road-journey-validation-v30.json`
  raportează `PASS`, toate cele cinci cazuri așteptate, inclusiv
  Crypt→Brill, dus/întors Brill–Deathknell, holdout-ul sudic și reset-ul
  controlat pentru fixture-ul de deal.
- **Limită:** este contract/replay/LAB evidence, nu verificare live; nu schimbă
  faptul că v35 rămâne ultima rulare cu input și bucla Crypt→Brill→Crypt nu este
  încă confirmată în client.

## ME-100 — V36 ajunge în ambele destinații, dar quality-gate-ul temporal respinge trace-ul

- **Dovadă live bounded:** secvența identifier-only
  `settlement:brill → landmark:deathknell-crypt`, pornită din spawnul Crypt
  canonical după reset LAB, a raportat `ARRIVED` pe ambele cicluri, cu
  `combat_handoffs_used=0` și `execution_authority=false`.
- **Trace:** outbound are 7.031 cadre și return 7.000 cadre, fără turnuri
  discrete; ambele au sosit la destinație. Captura finală confirmă Predator viu
  în Deathknell.
- **Limită confirmată:** evaluatorul `evaluate_live_steering_trace.py` a
  respins ambele trace-uri exclusiv pentru `control_observation_gap`: maxim
  `2.418 s` outbound și `3.260 s` return. Pauzele apar la
  `SEMANTIC_CORRIDOR_PREPLAN_STARTED`, unde baseline-ul WMO era sincron; prin
  urmare sosirea nu este încă dovadă de mișcare humanlike.
- **Cleanup:** înregistrarea video a fost oprită, runtime arm dezarmat, clientul
  LAB a rămas deschis, iar single-player/Hermes nu au fost atinse.

## ME-101 — Baseline-ul WMO nu mai blochează control loop-ul

- **Schimbare offline:** query-ul baseline pentru fiecare WMO candidat este
  trimis în `ProcessPoolExecutor`; control loop-ul aplică numai un `Future`
  deja terminat și reconstruiește query-ul fără blocker. Preplanul semantic
  vechi este anulat fără a aștepta worker-ul, iar următorul cadru poate porni
  preplanul filtrat.
- **Regresie:** testul workerului asincron și modulul compilat trec; suita
  țintită Movement Engine este verde (`136/136`), iar suita completă este
  verde (`1247/1247`).
- **Limită:** fixul trebuie încă revalidat într-un trace live pentru a demonstra
  gap-uri sub pragul oficial; nu s-a pornit un al doilea live după v36.

## ME-102 — V37 expune reintroducerea repetitivă a WMO-ului traversabil

- **Dovadă live bounded:** după gate-ul local verde, v37 a pornit din spawnul
  Crypt și a ajuns la `59/74` obiective înainte de `RESET_REQUIRED` la
  `[2190.382,666.152]`; nu a existat combat handoff și cleanup-ul a dezarmat
  runtime arm-ul.
- **Cauză:** baseline-ul WMO trecea, dar merge-ul static îl adăuga din nou la
  fiecare preplan pentru același semantic handoff. Asta producea churn de
  worker/replan și o frontieră fals persistentă.
- **Corecție offline:** un WMO trecut este memorat numai pentru indicele
  următorului obiectiv; aceeași pereche nu mai este reînaintată, iar un obiectiv
  diferit declanșează o reevaluare nouă. Este evidence local, nu waypoint.
- **Regresie:** testul scoped de suprimare și suita Movement Engine trec
  (`137/137`); suita completă curentă este verde (`1248/1248`).

- **Limită:** v37 rămâne proba care a expus bug-ul; după ea evaluatorul și
  implementarea au primit corecții separate, documentate mai jos.

## ME-103 — V38 încheie bucla și separă gap-ul de captură de o oprire reală

- **Dovadă live bounded:** v38 a parcurs `settlement:brill` și apoi
  `landmark:deathknell-crypt`, ambele cicluri `ARRIVED`, cu
  `combat_handoffs_used=0`; Predator a rămas viu la checkpoint-ul final.
- **Trace:** outbound `7.000` cadre / `281,613 s`, return `6.797` cadre /
  `254,282 s`; nu au existat turnuri discrete. Au fost măsurate 4, respectiv
  1 gap-uri brute peste 300 ms, dar fiecare capăt a păstrat `MOVE_FORWARD`,
  heading compatibil și deplasare world măsurabilă.
- **Quality gate:** evaluatorul păstrează gap-urile brute, dar le marchează ca
  `motion_continuity_exempted_gaps`; gap-urile fără input și progres rămân
  failure. V38 trece cu `unexplained_observation_gaps_over_300ms=0` pe ambele
  sensuri; schimbarea este acoperită de două teste dedicate.
- **Regresie:** suita Movement/quality este verde (`142/142`), iar suita
  completă este verde (`1250/1250`).
- **Limită:** aceasta validează rutarea și continuitatea observabilă, nu
  awareness exact pentru entități ascunse și nu autorizează combatul; combatul
  rămâne separat și fail-closed până la o autorizație explicită compatibilă.

## ME-104 — Control Center vede toate map ID-urile din clientul TBC

- **Schimbare offline:** registry-ul poate importa inventarul `Map.dbc`-bound
  al clientului și adaugă intrări inventory-only pentru hărțile fără WorldPack
  runtime. Registry-ul curent expune 83 de hărți, inclusiv hărțile de test ale
  clientului, fără să inventeze coordonate sau semantic destinations.
- **UI:** selectorul Control Center poate identifica toate cele 83 de hărți;
  intrările fără runtime/semantic/structure artefacts rămân inspection-only și
  sunt refuzate fail-closed la AUTONOM.
- **Regresie:** registry loader și suitele movement aferente trec; numai
  Azeroth rămâne `autonomous_ready` deoarece este singura legătură completă
  verificată.

## ME-105 — Auditul actual al awareness-ului client-visible

- **Dovadă client-side:** SavedVariables-ul real al contului LAB (`schema 0.4`,
  capturat la `2026-08-31T07:52:48Z`) raportează `target_state`, `focus_unit`,
  `combat_log_event` și `map_coordinates`; nu raportează un API public de
  poziție pentru unități. În sursa addonului TBC 2.4.3 nu există `UnitPosition`
  sau unit tokens enumerabili pentru toate nameplate-urile.
- **Ce poate folosi Predator:** target/focus și GUID/name/HP/reacție, combat log,
  nameplate-uri vizibile și geometrie screen-space; range-ul rămâne doar o
  relație `0–5 yd`/`>5 yd` demonstrată prin martori de acțiune.
- **Ce nu poate afirma:** coordonata 3D exactă a unui mob/NPC ne-selectat sau
  aflat în afara viewport/visibility-set. Static WorldPack și server truth nu
  sunt substituite pentru această observație lipsă.
- **Consecință:** Control Center și contractul `dynamic_entity_awareness` rămân
  fail-closed și afișează explicit `screen-space`, incertitudine și `unknown`,
  în loc să transforme o proiecție într-o poziție exactă. Acesta este progresul
  maxim verificabil cu API-ul public existent; un API public ulterior poate fi
  adăugat numai prin capability negotiation și contract versioning.

## ME-106 — Martor public `mouseover` pentru unități ne-selectate

- **Schimbare offline:** addonul `PerfectAssassinObserver 0.5.7` capturează
  evenimentul public `UPDATE_MOUSEOVER_UNIT` și publică un `mouseover_snapshot`
  read-only cu GUID, nume, tip player/NPC, HP, reacție și starea decesului.
  Adapterul îl normalizează ca `client_observed` prin capability-ul
  `mouseover_state`.
- **Limită păstrată:** snapshot-ul nu conține poziție 3D sau distanță; cursorul
  indică cel mult un singur obiect observat local. Nameplate-urile rămân
  screen-space și fără identitate generică pentru obiectele ne-selectate.
- **Verificare:** schema/adapterul, fixture-ul sintetic și boundary tests trec;
  suita completă curentă este verde (`1251/1251`). Pachetul nu a fost instalat
  în clientul WoW deja pornit și nu a fost pornit un test live.

## ME-108 — Verificare API pentru poziția altor unități

- **Rezultat:** `GetPlayerMapPosition(unit)` din API-ul legacy nu este un feed
  generic pentru NPC-uri; clasele documentate sunt `player`, `partyN` și
  `raidN`. `target`/`focus`/`mouseover` pot furniza identitate și stare, dar nu
  coordonate map publice pentru mob-uri.
- **Decizie:** nu adăugăm o încercare de a trata `GetPlayerMapPosition("target")`
  drept coordonată exactă. Un astfel de fallback ar produce valori zero/unknown
  sau ar recicla coordonata jucătorului și ar corupe provenance. `mouseover` din
  ME-106 rămâne martor client-visible fără poziție 3D.

## ME-107 — Observer 0.5.7 instalat în clientul LAB cu rollback verificat

- **Deploy controlat:** installerul a clasificat addonul existent `0.5.6`, a
  creat backup-ul exact
  `data/runtime/addon-backups/PerfectAssassinObserver-20260831T111748782` și
  a instalat `0.5.7` în `E:\Games\WoW TBC 2.4.3\Interface\AddOns`.
- **Integritate:** hash-urile instalate sunt `D54C7D7B...D6B27` (Lua),
  `74399892...C07CA` (TOC) și `D7E83E4E...8176` (README); backup-ul păstrează
  hash-urile `0.5.6` așteptate. Procesul WoW nu a fost repornit.
- **Limită de validare:** instalarea nu este o probă live; addonul va produce
  `mouseover_snapshot` numai după următoarea încărcare normală a UI-ului.
  Niciun input, combat sau test de rută nu a fost pornit în această operație.

## ME-109 — Audit de continuitate după handoff

- **Verificare read-only:** procesul WoW LAB `39544` răspunde în continuare;
  nu a fost oprit, repornit sau reîncărcat UI-ul. Addonul instalat păstrează
  hash-urile versiunii `0.5.7`, iar backup-ul rollback pentru `0.5.6` rămâne
  disponibil.
- **Regresie offline:** suita completă curentă a rulat `1251/1251` teste în
  `94.240 s`. Mesajul subprocessului despre `--jobs must be between 1 and 4`
  este o eroare a fixture-ului de worker așteptată și nu a schimbat rezultatul
  suitei (`OK`).
- **Artefact live existent:** `holdout-crypt-brill-crypt-20260831-v38.json`
  trece schema de handoff și rămâne singura dovadă bounded pentru bucla
  Crypt→Brill→Crypt; `execution_authority=false` și `combat_handoffs_used=0`.
- **Limită:** auditul nu autorizează un nou test live și nu transformă
  `mouseover` sau nameplate screen-space în poziții 3D exacte. Combatul rămâne
  separat, fail-closed, până la o autorizație explicită compatibilă.

## ME-110 — Combat nu are runtime arm activ

- **Verificare read-only:** directoarele operator conțin două snapshot-uri de
  autorizare combat istorice, ambele cu `status=approved_bounded`, dar expirate
  la `2026-08-28`. Snapshot-ul de realm este de asemenea expirat; niciun fișier
  de `combat-runtime-arm` activ nu există.
- **Decizie:** artefactele expirate sunt păstrate pentru audit și rollback, nu
  sunt șterse automat. Loaderul runtime trebuie să le respingă după expirare,
  iar absența arm-ului ține `execution_authority=false`.
- **Limită:** nu se emite o autorizație nouă și nu se pornește combat până când
  operatorul nu cere explicit o sesiune bounded compatibilă cu LAB.

## ME-111 — Scoring exact al awareness-ului rămâne separat de Champion

- **Schimbare offline:** `perfect_assassin.lab.entity_awareness` și contractul
  `lab-entity-awareness-evaluation.schema.json` calculează recall/precision de
  identitate și eroare de poziție numai pentru un evaluator LAB. Martorii
  anonimi screen-space sunt numărați ca ne-localizați; nicio coordonată nu este
  inferată.
- **Boundary:** raportul declară explicit `server_ground_truth` ca origine a
  oracle-ului LAB, `client_observed` ca origine a martorilor și
  `execution_authority=false`. Modulul nu este importat de Brain sau Movement.
- **Verificare:** cele 3 teste dedicate trec (`3/3`), iar regresia completă
  este verde (`1254/1254`); contractul este validat pentru cazurile cu poziție
  lipsă și poziție disponibilă. Aceasta oferă o măsurătoare exactă a limitării
  fără a introduce server ESP în live.

## ME-112 — Revalidare offline completă după boundary-ul LAB

- **Dovadă offline:**
  `data/runtime/navigation-f3b/semantic-road-journey-validation-v40.json`
  raportează `status=PASS` pentru toate cele cinci cazuri selectate.
- **Rezultat:** `canonical_crypt_spawn_to_brill`, `deathknell_to_brill`,
  `brill_to_deathknell` și `brill_to_south_road_holdout` au
  `destination_reached=true`; cazul `hill_fixture_requires_reset` rămâne
  `reset_required=true`, `safe=false`, conform gate-ului de frontieră parțială.
  Nu există waypoints operator executabili în acest validator.
- **Limită:** v40 este replay/simulare offline și nu schimbă starea WoW-ului;
  nu justifică o a doua rulare live și nu autorizează combat.

## ME-113 — Reevaluare offline a calității trace-urilor v38

- **Dovadă:** evaluatorul `evaluate_live_steering_trace.py` a fost rulat din
  nou pe cele două trace-uri v38 și a scris
  `quality-v38-outbound-v3.json` și `quality-v38-return-v3.json`.
- **Rezultat:** ambele au `arrived=true`, `passed=true` și
  `unexplained_observation_gaps_over_300ms=0`. Outbound păstrează explicit 4
  gap-uri brute (toate cu continuitate de mișcare), iar returul păstrează 1;
  ratele de reversare și pivotare rămân în limitele gate-ului.
- **Limită:** aceasta este reevaluare offline a trace-ului live existent, nu o
  nouă intrare în joc și nu dovedește awareness 3D sau combat.

## ME-114 — Monte Carlo hairpin și tuning rămân stabile

- **Dovadă offline:**
  `steering-monte-carlo-20260831-v2.json` rulează 100 trial-uri pentru fiecare
  dintre cele șase scenarii, inclusiv `narrow_outdoor_hairpin`,
  `confined_stair_bend`, `open_ground_doodad_gateway` și `straight_bridge`.
- **Rezultat:** `600/600` trial-uri completate și trecute, zero coliziuni,
  zero sample quality failures; hairpin-ul are maximum cross-track `1.4817 yd`
  și pivot fraction `0.2831`, sub limitele scenariului.
- **Tuning:** căutarea offline cu 18 candidați
  (`steering-tuning-search-20260831-v1.json`) a găsit mai multe configurații
  cu `minimum_quality_pass_rate=1.0`. Nu se promovează o schimbare de
  producție numai din acest rezultat; profilul verificat rămâne neschimbat
  până la o regresie și dovadă live bounded nouă.
- **Limită:** toate rezultatele sunt simulări offline; nu autorizează input live.

## ME-115 — Grila de tuning include baseline-ul de producție

- **Corecție offline:** `search_steering_tuning.py` folosește acum întregul
  corpus de șase scenarii și compară ambele valori de `pivot_gain`, inclusiv
  baseline-ul verificat `3.4`; anterior căutarea ținea accidental această
  constantă fix la `2.4` și omitea hairpin-ul.
- **Rezultat:** grila extinsă (`36` candidați × `6` scenarii × `100` trial-uri)
  găsește baseline-ul actual cu `minimum_quality_pass_rate=1.0`, fără
  coliziuni sau quality failures. Nu s-au schimbat constantele de producție.
- **Regresie:** testul corpusului și suita completă trec (`1256/1256`); mesajul
  fixture-ului worker despre `--jobs` rămâne non-fatal.
- **Limită:** este o îmbunătățire a verificării offline; nu este o autorizație
  pentru o nouă intrare live.

## ME-116 — Contractul minim de trial-uri este verificat la CLI

- **Corecție offline:** `search_steering_tuning.py` respinge acum explicit
  `--runs < 100` înainte de a porni simularea; valoarea minimă documentată și
  testată este `100` trial-uri pentru fiecare candidat și scenariu.
- **Regresie:** testele dedicate tuningului trec `3/3`; `--runs 50` se
  termină cu eroare de argument și nu scrie artefact. Suita completă trece
  `1257/1257`; mesajul fixture-ului worker despre `--jobs` rămâne non-fatal.
- **Limită:** validarea CLI și grila extinsă rămân dovezi offline; nu modifică
  constantele de producție și nu autorizează input live.

## ME-117 — O pauză fizică nu mai este mascată de proiecția coridorului

- **Dovadă:** analiza trace-ului v38 a identificat la apropierea de Brill o
  observație de `1.25 s` cu numai `~0.55 yd` avans, deși `MOVE_FORWARD` era
  ținut. Acest semnal este compatibil cu pauza văzută în video și nu trebuie
  tratat ca progres doar pentru că proiecția pe navmesh a avansat. Replay-ul
  helperului găsește un singur long-gap flag pe outbound și niciunul pe retur;
  maximumul de cadre consecutive non-continuous este `2`/`3`.
- **Corecție offline:** `observed_motion_is_continuous()` cere deplasare
  fizică și, pentru intervale lungi, viteză medie minimă; runner-ul păstrează
  această dovadă în `physical_motion_continuous` și nu resetează ceasul de
  no-progress pentru o staționare observată.
- **Regresie:** testele țintite trec `83/83`, iar suita completă trece
  `1259/1259`; nu s-au schimbat harta, constantele de producție sau
  `execution_authority`.
- **Limită:** corecția este verificată offline; nu implică reload, input live
  sau combat.

## ME-118 — Proof pack-ul este refăcut cu catalog runtime bundlat

- **Dovadă:** manifestul offline `tbc243-8606-proof-worldpack-v2` are hash-ul
  `d2dac1272c7e19272810a4619cc27773ec7c99f2662c8dbb1385eb27258c0588` și
  declară hărțile `47:RazorfenKraulInstance` și `532:Karazahn`; queue-ul de
  bake le marchează `COMPLETE` cu navmesh, road semantics și asset-uri.
- **Verificare negativă:** v2 a fost respins deoarece nu conținea
  `identity/client-world-catalog.json`; nu a fost legat ca runtime profile.
- **Corecție offline:** din aceleași artefacte deterministe am generat catalogul
  candidat și am sigilat v3 separat. `seal_standalone_world_pack.py --verify-only`
  și `load_world_pack_runtime_profile` trec pentru ambele hărți; v3 are 826
  artefacte și hash `33bbbba1ef9f698cd1e843c7ca463a069e78dd27339a28f57715669a00b03363`.
- **Registry/UI:** v3 este acum legat pentru `47:RazorfenKraulInstance` și
  `532:Karazahn`, iar Control Center le poate selecta. Catalogul declară
  intenționat `partial`, fără structure-access graph; readiness rămâne
  `OBSERVE_ONLY`/fail-closed.
- **Regresie:** testele map/UI/catalog trec `28/28`, iar suita completă rămâne
  verde la `1259/1259`; v2 rămâne intact pentru rollback.
- **Limită:** runtime-loadable nu înseamnă autonom; promovarea cere semantic
  catalog și egress/structure evidence independente.

## ME-119 — Probe interioare sparse și prima curbă Razorfen

- **Dovadă:** smoke-ul offline pe `worldpack-runtime:tbc243:proof:v3`, cu
  `RazorfenKraulInstance:27_27`, a testat pattern-urile generate din limitele
  ADT. Pentru `p0`, worker-ul găsește înălțimea locală, dar nu găsește un
  poligon walkable la endpoint-ul de frontieră (`x≈2149`, ~3% din ADT), deci
  raportul păstrează `ENDPOINT_UNAVAILABLE` și nu inventează o rută.
  Scanarea aceleiași tile cu probe la 10–90% confirmă suprafețe valide, iar
  rularea reluabilă cu două candidate a găsit `p1` și un coridor complet.
- **Rezultat:** coridorul `p1` are 29 poligoane, 28 portaluri, zero coliziuni și
  100/100 sosiri. Controllerul geometric actual trece doar 44/100 trial-uri
  la limita de cross-track de 2 yd; `pa_mppi_v1` ridică rezultatul la 93/100,
  dar încă nu este un PASS de promovare.
- **Interpretare:** cauza nu este un `z=0` folosit ca podea (worker-ul
  rezolvă podeaua prin `find_heights`), ci faptul că probele uniforme pot cădea
  în goluri reale ale navmesh-ului interior. `corridors_per_tile` trebuie să
  permită candidate de rezervă, iar frontier probes rămân vizibile în raport.
- **Limită:** aceasta este dovadă offline pe coverage parțial; nu promovează
  Razorfen/Karazhan la autonomous-ready, nu schimbă constantele de producție
  și nu autorizează o nouă rulare live sau combat. Următoarea corecție este
  tuning/steering pe coridoare interioare reale, nu waypoint-uri hardcodate.

## ME-121 — Selectorul adaptiv nu vedea tranzițiile înguste cu viraj modest

- **Cauză:** selectorul MPPI verifica doar un viraj de cel puțin `1.35 rad`
  în primele 12 yd. Coridorul Razorfen p1 are portaluri înguste și dovezi de
  clearance/înclinare, dar virajul funnel este modest și apărea ca teren pentru
  followerul geometric, deși geometria locală cerea anticipare suplimentară.
- **Corecție:** `AdaptiveTrajectorySteeringController` selectează acum MPPI
  când portalul minim este `<=3.5 yd` și geometria clientului raportează un
  clearance inset sau o pantă de cel puțin `30°`. Regula este latching pe
  semnătura coridorului și nu conține hartă, coordonate sau waypoint-uri.
  Profilul adaptiv folosește `yaw_smoothness_weight=6.0`,
  `replan_interval_ticks=3`; Control Center pornește cu `256 x 56`.
- **Rezultat:** benchmark-ul adaptiv rămâne `600/600` pe cele șase scenarii;
  p1 adaptiv trece `100/100` în replay, iar holdout-ul real MPPI cu 1.000 de
  trial-uri trece `1000/1000`, zero coliziuni, abatere maximă `1.591 yd`.
- **Regresie:** suita completă trece `1260/1260`; nu s-a pornit live test,
  reload sau combat.
- **Limită:** rezultatul este validare offline pe un coridor interior și nu
  dovedește încă traseul Crypt→Brill→Crypt cu profilul nou. Live rămâne
  pending până la o autorizare bounded explicită și un rollback verificat.

## ME-122 — Inventarul de teren nu este încă un bake navmesh complet

- **Dovadă offline:** `build_client_world_bake_queue.py` a fost rulat în mod
  determinist pe catalogul clientului TBC `2.4.3.8606`, cu `35` hărți și
  `3,610` ADT-uri eligibile. Artefactul este
  `data/runtime/navigation-f3b/client-world-bake-queue-audit-20260831.json`.
- **Rezultat:** `complete_map_count=0`, `bvh_ready=false` și
  `bvh_artifact_count=0` pentru rădăcina canonică declarată
  `E:\\WoWserver\\PerfectAssassin-Runtime\\navigation\\tbc243-full-v1`.
  Rădăcinile care există deja (`full-v3-repair-work`, `shadowfang`,
  `tirisfal-silverpine` și variantele de drum) sunt work/proof snapshots cu
  acoperire parțială; nu au fost promovate automat ca bake pentru toate hărțile.
- **Interpretare:** avem sursă locală de teren pentru o parte importantă din
  client, dar încă nu avem navmesh/BVH + semantic/access sigilate și asociate
  map-by-map. Afișarea tuturor ID-urilor în Control Center nu poate fi tratată
  ca dovadă de rutare autonomă.
- **Limită:** această verificare doar generează coada și nu pornește
  `MoveMapGen`, nu modifică WoW/Hermes și nu acordă `execution_authority`.
  Următorul pas este un bake offline reluabil pe hărți selectate, cu manifest
  și rollback, nu un test live.

## ME-123 — Azeroth v4 este sigilat offline, fără promovare implicită

- **Corecție de pipeline:** bake-ul a folosit `MapBuilder` pinned v5 din
  `PerfectAssassin-Dependencies`; `MoveMapGen.exe` din TBC-LAB produce
  `.mmap/.mmtile` pentru oracle-ul LAB și nu este builderul `.nav/BVH` al
  Movement Engine. Rădăcina MPQ corectă pentru MapBuilder este
  `E:\\Games\\WoW TBC 2.4.3\\Data`.
- **Dovadă:** etapa semantică a generat `687/687` sidecar-uri `.road`, BVH-ul
  are `2,178` artefacte, iar MapBuilder a generat `687/687` tile-uri `.nav`.
  Queue-ul marchează Azeroth `COMPLETE`; celelalte hărți rămân în stările lor
  anterioare.
- **Validare:** quality report v4 are `nav_adt_count=687`, zero tile-uri
  eșuate și `COMPLETE_WITH_RECAST_DIAGNOSTICS`; auditul structural serial a
  trecut `687/687` cu `failure_count=0`. Diagnosticele Recast sunt păstrate
  explicit (`7,894` errors, `21,433` warnings) și cer validare geometrică,
  nu sunt suprimate. CLI-ul quality audit acceptă acum explicit `--catalog-id`,
  pentru a lega raportul de catalogul candidat fără a altera inventarul client.
- **WorldPack candidat:**
  `E:\\WoWserver\\PerfectAssassin-Runtime\\worldpacks\\tbc243-azeroth-full-v4-candidate`
  este sigilat și verificat cu `runtime_ready=true`, `3,558` artefacte și
  hash `99feeb1ca0969f0a0cbc1575f5fb4adb37eb2ee464fc53a54d04782f157f6dbf`.
  v3 rămâne intact pentru rollback; v4 nu este încă legat în registry.
- **Limită:** catalogul v4 acoperă complet doar `1/83` identități de hartă;
  nu dovedește rutare autonomă all-map, awareness generic 3D sau combat. Nu
  s-a pornit live input, reload WoW ori proces Hermes.

## ME-124 — Corpus steering v4 și corecția workerului de awareness

- **Cauză a primului eșec:** smoke-testul a primit accidental `MapBuilder.exe`
  ca worker pentru protocolul `--awareness-server`; serviciul persistent nu a
  putut face handshake. Nu a fost o modificare a navmesh-ului și nu a pornit
  input live.
- **Corecție:** corpusul folosește acum binarul compilat și compatibil
  `data/runtime/native-build/pa_nav_probe-v35/Debug/pa_nav_probe.exe`, cu
  timeout-ul contractual de `10` secunde. O scanare read-only a identificat
  coridoare valide și a păstrat separat capetele fără suprafață walkable.
- **Dovadă geometrică:** corpusul geometric pe patru ADT-uri a rezolvat `2/4`
  coridoare și a simulat `200/200` trial-uri cu quality-pass, zero coliziuni și
  zero quality failures; celelalte două au fost `PARTIAL_CORRIDOR`, fail-closed.
- **Dovadă MPPI de producție:**
  `data/runtime/navigation-f3b/azeroth-v4-steering-smoke-mppi-2tiles-20260831.json`
  a rezolvat `2/2` coridoare și a trecut `200/200` trial-uri, zero coliziuni,
  zero quality failures; MPPI a fost activ în aproximativ `96.7%–97.0%` din
  observațiile celor două coridoare.
- **Limită:** aceasta este validare offline pe patru ADT-uri și nu dovedește
  încă acoperirea completă Azeroth, traseul Crypt→Brill→Crypt sau comportament
  live/humanlike. Nu s-a pornit live input, reload WoW, combat sau Hermes.

## ME-125 — Kalimdor bake și WorldPack candidat separat

- **Bake offline:** runnerul reluabil a procesat Kalimdor din starea
  `READY_FOR_SEMANTICS` folosind MPQ-urile locale și MapBuilder pinned v5.
  Semantică de drum: `1018/1018`; navmesh: `1018/1018`; queue: `COMPLETE`;
  BVH global: `3261` artefacte. Rezultatul contractual este
  `data/runtime/navigation-f3b/kalimdor-bake-20260831.json` cu `status=PASS` și
  `execution_authority=false`.
- **Quality și structură:** auditul Recast este păstrat ca
  `COMPLETE_WITH_RECAST_DIAGNOSTICS` (zero tile-uri lipsă/eșuate; `12,237`
  errors, `30,081` warnings), iar auditul structural serial trece
  `1018/1018`, `failure_count=0`. Diagnosticele nu sunt convertite implicit în
  PASS.
- **WorldPack candidat:**
  `E:\WoWserver\PerfectAssassin-Runtime\worldpacks\tbc243-kalimdor-v1-candidate`
  este sigilat și verificat (`runtime_ready=true`, `5303` artefacte, hash
  `609a20256ec154c98bd630091753a6229f610488536ec61b7ef0a5ca19c3db5f`). Este
  separat de Stable și nu este legat automat în registry.
- **Limită:** aceasta ridică bake-ul offline complet la două hărți din cele
  `35` eligibile (`Azeroth` și `Kalimdor`), dar nu dovedește all-map autonomy,
  semantic/access promotion, awareness generic 3D sau live/combat. Nu s-a
  pornit live input, reload WoW, combat sau Hermes.

## ME-126 — Corpus MPPI Kalimdor pe geometrie reală

- **Dovadă:** `data/runtime/navigation-f3b/kalimdor-v1-steering-smoke-mppi-4tiles-20260831.json`
  a interogat și rezolvat `4/4` coridoare din catalogul Kalimdor (`1018`
  tile-uri), apoi a trecut `400/400` trial-uri MPPI cu profilul Control Center
  (`256 x 56`, replan `3`), zero coliziuni și zero quality failures.
- **Acoperire de risc:** corpusul include coridoare clasificate cu
  `STEEP_GEOMETRY`, `DOODAD_DETOUR`, `CLEARANCE_INSET`, precum și un caz cu
  `SHARP_TURN` și `NARROW_PORTAL`; aceste dovezi rămân derivate din navmesh și
  BVH, nu din waypoints executabile.
- **Limită:** este o probă offline pe patru ADT-uri, nu promovare în registry și
  nu dovedește all-map autonomy, awareness generic 3D, traseul
  Crypt→Brill→Crypt humanlike sau combat. Nu s-a pornit live input, reload WoW,
  combat sau Hermes.

## ME-127 — Anticipare MPPI și accelerație yaw pentru hairpin Shadowfang

- **Cauză:** preview-ul nominal de `0.90 s` și limita de accelerație yaw de
  `8 rad/s²` lăsau camera să intre prea târziu în apexul de 60–70° al
  corridorului `Shadowfang:28_30:p0`. Actorul ajungea la destinație, dar
  depășea sporadic poarta strictă de cross-track.
- **Corecție candidată:** preview temporal `1.80 s` și accelerație yaw
  `12 rad/s²` în `MppiConfiguration`. Ambele sunt constante de control pe
  geometria corridorului observat; nu introduc coordonate, route waypoints sau
  reguli pentru Shadowfang.
- **Dovadă:** raportul
  `data/runtime/navigation-f3b/shadowfang-v3-steering-replay-preview18-accel12-28-30-100-20260831.json`
  a avut `100/100` sosiri, `99/100` quality-pass, zero coliziuni, zero pivots,
  maximum cross-track `2.030789 yd`, p95 `1.930345 yd` și MPPI activ în
  `98.21%` din observații. Testele unitare MPPI trec `12/12`.
- **Limită:** un singur seed (`trial_index=86`) depășește pragul de `2.0 yd`
  cu `0.030789 yd`. Nu relaxăm poarta și nu tratăm candidatul ca PASS live.
  WorldPack-ul și registry-ul Stable rămân neschimbate; nu s-a pornit input
  live, reload WoW, combat sau Hermes.

## ME-128 — Coridorul Shadowfang adiacent după reglajul MPPI

- **Dovadă:** raportul
  `data/runtime/navigation-f3b/shadowfang-v3-steering-replay-preview18-accel12-28-31-100-20260831.json`
  a trecut `100/100` trial-uri cu profilul `256 x 56`, replan `3`, zero
  coliziuni, zero pivots, maximum cross-track `1.986825 yd` și maximum
  `4` schimbări de semn.
- **Interpretare:** accelerația suplimentară nu produce regresie pe tranziția
  Shadowfang 28_31; hairpin-ul 28_30 păstrează însă un outlier offline și
  rămâne sub pragul de promovare completă.
- **Regresie:** suita completă curentă trece `1262/1262` teste; stderr-ul
  fixture-ului pentru argumentul invalid `--jobs` este așteptat și nu schimbă
  verdictul. Nu s-a pornit input live, reload WoW, combat sau Hermes.

## ME-129 — Auditul outlierului de proiecție la apex

- **Observație:** în `trial_index=86` din `Shadowfang:28_30:p0`, la observația
  `182`, proiecția monotonică a raportat progres `124.208726 yd` și
  cross-track `2.030789 yd`. Punctul geometric local cel mai apropiat fără
  limita temporală este la aproximativ `1.9426 yd`, la progresul `124.801 yd`;
  limita de avans (`PROJECTION_ADVANCE_TIME_S=0.40`) ține proiecția cu circa
  `0.7 yd` în urmă peste apex.
- **Verificare:** ferestrele alternative `0.35`, `0.45`, `0.50` și `0.55 s`
  nu au îmbunătățit consistent shard-ul offline de `20` seeds (toate au
  rămas la `16/20`), deci nu am modificat proiecția sau evaluatorul și nu am
  ascuns outlierul printr-o poartă mai largă.
- **Stare:** `0.40 s` rămâne în producție, deoarece protejează împotriva
  salturilor între ramuri apropiate. Outlierul este păstrat ca defect de
  măsurare/edge-case de investigat; nu autorizează live input, reload WoW,
  combat sau Hermes.

## ME-130 — Extensie locală a proiecției pe tangenta de ieșire

- **Cauză:** la un colț geometric valid, o observație capturată imediat după
  apex putea rămâne limitată pe segmentul de intrare de fereastra temporală de
  `0.40 s`, deși actorul era deja orientat pe tangenta de ieșire. În trial-ul
  86, punctul local real era la `1.9426 yd`, dar proiecția măsura `2.030789 yd`.
- **Corecție:** când coridorul are geometrie/portal valid, colțul este în
  fereastra existentă, actorul este la cel mult `4 yd` de colț și heading-ul
  observat este la cel mult `0.85 rad` de tangenta outbound, proiecția poate
  folosi restul limitei maxime deja existente de `4 yd`. Se păstrează
  proiecția pe cel mai apropiat segment; nu se adaugă waypoint sau shortcut.
  Ghidajul este cache-uit per coridor pentru a păstra control-loop-ul
  bounded; detecția colțului își păstrează discretizarea existentă.
- **Dovadă:** replay-ul oficial `256 x 56`, replan `3`, pe
  `Shadowfang:28_30:p0` a trecut `100/100` quality, zero coliziuni/pivots,
  maxim cross-track `1.988531 yd`, fără quality failures. Artefactul este
  `data/runtime/navigation-f3b/shadowfang-v3-steering-replay-projection-corner-final-28-30-100-20260831.json`.
  Coridorul adiacent `28_31:p0` a rămas `100/100`, zero coliziuni/pivots,
  maxim `1.986825 yd`.
  Raportul `data/runtime/navigation-f3b/steering-monte-carlo-20260831-v5-projection-corner-open-ground.json`
  trece `600/600` pe cele șase scenarii,
  inclusiv `narrow_outdoor_hairpin`, fără coliziuni sau quality failures.
  Regresia completă trece `1263/1263`; testele dedicate de navigație/MPPI
  trec `96/96`.
- **Limită:** aceasta este dovadă offline/replay, nu autorizare live. Nu am
  pornit reload WoW, input live, combat sau Hermes; runtime arm-ul rămâne
  dezarmat.

## ME-131 — Se elimină blocarea map-id din selectorul Control Center

- **Observație:** selectorul expunea toate identitățile din inventar, dar
  readiness-ul respingea orice profil cu `map_id != 0` înainte să verifice
  artefactele sale reale. Această regulă făcea imposibilă promovarea generică
  a unei hărți noi și era o formă de hardcode de hartă.
- **Corecție:** selecția și readiness-ul verifică acum doar existența runtime
  WorldPack, catalogului semantic, structure index-ului, access graph-ului și
  gate-ului legat de profilul selectat. Profilurile incomplete rămân
  `OBSERVE_ONLY`, iar fallback-ul Azeroth există numai pentru instanța
  diagnostică fără selecție explicită.
- **Regresie:** `tests.test_movement_engine` trece `139/139`, inclusiv un
  profil sintetic `map_id=33` care ajunge la `AWARENESS SE VERIFICĂ`, nu la o
  respingere specială pentru ID. Nu s-a pornit input live, reload WoW, combat
  sau Hermes. Testul separat confirmă și legarea semantic gate-ului de
  WorldPack-ul profilului selectat. Suta completă `python -m unittest discover -s tests` trece
  `1270/1270`; stderr-ul fixture-ului pentru `--jobs=5` este așteptat și
  non-fatal.

## ME-134 — Catalog semantic legat de profil în Control Center

- **Schimbare:** destinațiile UI sunt încărcate din catalogul profilului
  WorldPack selectat și sunt verificate după identitatea hărții, zona,
  coordonatele clientului și atlasul declarat. La selectarea unei hărți fără
  catalog valid, destinațiile și secvența sunt resetate; nu rămân coordonate
  Azeroth prezentate pe altă hartă.
- **Planificare:** plannerul semantic rezolvă acum runtime WorldPack din
  profilul activ, nu din fallback-ul global Azeroth.
- **Regresie:** trei teste noi acoperă catalog non-default, catalog cross-map
  și plannerul legat de runtime; suita completă trece `1276/1276`. Nu s-a
  pornit input live, reload WoW,
combat sau Hermes.

## ME-135 — Knowledge Broker static, cu proveniență

- **Schimbare:** catalogul versionat read-only acoperă traineri de clasă/
  profesie, class/profession quest-uri, pași de leveling și route-teacher.
  Fiecare fapt este legat de build/map, provider, origin, versiune, timestamp,
  confidence și evidence refs.
- **Limită:** locațiile externe sunt marcate `STATIC_SOURCE_CANDIDATE` și cer
  confirmare client + binding WorldPack; nu sunt feed generic de entități și nu
  pot acorda execuție. Originile server/LAB și semantica `LIVE_EXACT` sunt
  respinse. Un Zygor cumpărat poate fi importat doar din exportul user-owned,
  fără copierea pachetului licențiat în repo.
- **Regresie:** Knowledge Broker `6/6`; suita completă curentă `1276/1276`.

## ME-136 — Validator semantic profile-aware v41

- **Dovadă offline:**
  `data/runtime/navigation-f3b/semantic-road-journey-validation-v41-profile-aware.json`
  este `PASS` pentru `5/5` scenarii.
- **Rezultat:** Crypt spawn→Brill, Deathknell↔Brill și holdout-ul sudic ating
  destinația semantică; fixture-ul incomplet de deal rămâne
  `RESET_REQUIRED`/`safe=false`, fără a fi promovat artificial.
- **Limită:** rezultatul este replay/validare offline și nu autorizează input,
  reload WoW sau combat.

## ME-137 — Audit Zygor Anniversary și import RouteTeacher

- **Constatare:** RAR-ul `D:\Downloads\Zygor Release 8.1.37070.rar` declară
  `Interface: 20506`, `Version: 8.1` și conține module TBC pentru leveling,
  professions, dungeons, NPC și quest data. Este compatibil ca sursă de ghid
  Anniversary, nu ca instalare directă pentru clientul legacy `2.4.3.8606`
  (`Interface: 20400`).
- **Dovadă offline:** importatorul Lua bounded a parcurs cele trei fișiere
  non-Trial de leveling: `11205` pași, `10007` locații 2D candidate, `730`
  traineri de clasă și `2373` pași de combat. Cele trei fișiere non-Trial de
  profesii adaugă `3543` pași, `1680` locații, `524` traineri de profesie și
  `16` quest-uri de profesie; fiecare zonă a cerut binding WorldPack explicit.
- **Limită:** Zygor rămâne RouteTeacher advisory; coordonatele sunt 2D statice,
  iar `kill`/`trainer` nu înseamnă că addonul execută combat. Un benchmark live
  lvl 1–70 se poate planifica doar în sesiuni bounded, cu verificare client și
  autorizare proaspătă; nu s-a pornit acum.

## ME-133 — Coverage audit pentru WorldMapArea.dbc

- **Sursă:** assetul static de client
  `E:\\WoWserver\\TBC-LAB\\client-data\\dbc\\WorldMapArea.dbc`, citit cu
  `WorldMapAreaTable` și scope `lab_evaluation_only`; nu se citește server
  ground truth și nu se promovează date în Champion.
- **Dovadă:** `data/runtime/navigation-f3b/client-world-map-area-audit-20260831.json`
  are `68` rânduri, `7` map contexts și map IDs
  `0,1,30,489,529,530,566`, cu hash-ul exact al buildului.
- **Limită:** WorldMapArea oferă bounds 2D pentru zonele pe care le declară;
  nu este un feed de poziții live și nu acoperă automat toate dungeon map IDs.
  Testul schema/parser trece `1/1`, iar `--check` este verde.

## ME-132 — Registry audit determinist pentru Control Center

- **Schimbare:** `scripts/audit_world_map_registry.py` validează registry-ul
  TBC 2.4.3, inventarul clientului și bake queue-ul și produce raportul
  `data/runtime/navigation-f3b/world-map-registry-audit-20260831.json`.
- **Dovadă:** raportul are `83` identități, `35` mapări în queue, `3` stări
  `COMPLETE` și `1` profil `autonomous_ready`. Câmpurile per hartă separă
  `declared`, `ready`, `queue_known` și `queue_state`; nu există promovare
  implicită a unei hărți fără semantic/access.
- **Regresie:** testele registry/audit trec `3/3`, iar `--check` confirmă
  egalitatea exactă a raportului generat. Niciun input live, reload WoW,
combat sau Hermes nu a fost pornit.

## ME-138 — Import static NPCData cu map scope fail-closed

- **Schimbare:** `knowledge_broker_catalog` acceptă kind-ul `npc_static` și
  scope-ul de coordonate `worldpack`/`zone_area`. Importatorul bounded
  `src/perfect_assassin/knowledge/npc_data.py` păstrează ID-urile `m####` din
  Zygor ca `zone_area` și cere binding explicit pentru fiecare map-area ID;
  nu convertește implicit către continentele WorldPack.
- **Dovadă:** fișierul real Anniversary are 35 secțiuni și 3.255 rânduri
  parse-abile în memorie: `286` class trainers, `287` profession trainers și
  `2.682` NPC static. Testele Knowledge Broker sunt `8/8`; regresia completă
  offline este `1278/1278`.
- **Limită:** coordonatele sunt 2D statice, marcate
  `STATIC_SOURCE_CANDIDATE`; nu sunt unit positions live, nu acordă execuție
  și nu au fost folosite pentru input, reload WoW, combat sau Hermes.

## ME-139 — Audit NPCData fără a persista conținut licențiat

- **Schimbare:** `scripts/audit_zygor_npcdata.py` rulează importatorul bounded
  pe un export local și emite un raport strict minimal: hash/size, secțiuni,
  rânduri, tipuri, facțiuni și distribuție pe map-area. Nu persistă rânduri,
  nume sau coordonate din addon.
- **Siguranță:** fișierul de binding este obligatoriu și fiecare `m####`
  întâlnit trebuie declarat explicit; lipsa lui oprește importul. ID-ul rămâne
  `zone_area`, fără conversie implicită la WorldPack.
- **Regresie:** testul scriptului trece `1/1`; suita offline curentă trece
  `1279/1279`. Nu s-a instalat RAR-ul, nu s-a reîncărcat WoW și nu s-a pornit
  input live.

## ME-140 — Descoperire map-area IDs fără copierea conținutului Zygor

- **Schimbare:** `scripts/discover_zygor_npcdata_maps.py` face o primă trecere
  bounded peste `NPCData.lua` și persistă doar hash/size și distribuția
  numerică a ID-urilor `m####`; nu cere încă binding-uri și nu păstrează
  conținut licențiat.
- **Dovadă:** exportul Anniversary are `66` map-area IDs și `3.255` rânduri;
  raportul este `data/runtime/navigation-f3b/zygor-npcdata-map-discovery-20260831.json`.
  Verificarea `--check` este verde, iar testele dedicate sunt `2/2`.
- **Limită:** ID-urile rămân `zone_area`; nu sunt map IDs WorldPack și nu pot
  produce destinații sau input. Orice reconciliere cere binding explicit și
  confirmare din client. Nu s-a pornit test live.

## ME-141 — Kalimdor: index structural și probe bounded fără promovare

- **Dovadă:** indexul local `kalimdor-candidate-world-structure-index-v1.json`
  este `VERIFIED` pentru pachetul cu `1.018` tile-uri, `1.426` WMO și
  `103.898` doodads. Planul de access scan acoperă toate WMO și `40.794`
  seed-uri generate din AABB/intersecția cu tile-urile navmesh.
- **Lot controlat:** primele `100` probe au avut `0` `PROBE_ERROR`, `74`
  răspunsuri prin worker persistent și `26` fallback one-shot; `0` WMO
  confirmate, `26` awareness-uri incomplete. Raportul de progres rămâne
  `PAUSED_AT_PROBE_BUDGET` cu `40.694` seed-uri neprocesate.
- **Limită:** rezultatul nu justifică încă access graph sau autonomie pe
  Kalimdor; nu se schimbă registry-ul și nu se pornește input/reload/live.

## ME-142 — Prim WMO Kalimdor cu graph parțial, fără promovare map-wide

- **Dovadă:** structura țintită a avut `39` seed-uri; `2` au fost confirmate
  conținute, iar agregarea a produs `14` access openings și `9` boundary
  chains. Artefactul este
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-ratchet-359589-v1.json`.
- **Verdict:** graph-ul este `PARTIAL_OBSERVED_COMPONENTS`; `34` seed-uri au
  fost respinse ca exterioare, `3` nu au avut poligon navmesh și `0` probe au
  avut eroare de worker. Nu este legat în registry și nu poate ghida autonomie
  pe restul hărții.
- **Limită:** este calibrare structurală locală, nu dovadă de autonomie live,
  NPC awareness sau input. WoW și testul live au rămas oprite.

## ME-143 — Kalimdor: extindere bounded și graph candidat parțial

- **Dovadă:** lotul suplimentar de `1.000` probe a ridicat progresul la
  `1.139/40.794`, cu `36` WMO confirmate și `0` erori de worker. Au fost
  observate `136` awareness-uri incomplete și `149` cazuri fără poligon;
  `39.655` seed-uri rămân neprocesate.
- **Agregare:** task-urile completate cu observații au generat un graph
  candidat pentru `16` structuri, cu `36` observații, `135` openings și
  `293` boundary chains. Starea este `PARTIAL_OBSERVED_COMPONENTS`.
- **Limită:** graph-ul nu este map-wide, nu este legat în registry și nu
  acordă input. Testul live și WoW rămân oprite.

## ME-144 — Binding static complet pentru map-area IDs Zygor

- **Schimbare:** parserul bounded din
  `src/perfect_assassin/knowledge/zygor_map_bindings.py` citește numai tabela
  `data.MapIDsByName` din `LibRover/data.lua`; nu execută Lua și nu alege
  implicit aliasuri ambigue. `scripts/audit_zygor_npcdata_map_bindings.py`
  compară ID-urile din `NPCData.lua` cu această tabelă și emite un audit
  content-minimal.
- **Dovadă:** sursa Anniversary rezolvă `66/66` IDs, cu `0` ambigue și `0`
  nerezolvate. Importul în memorie validează `3.255` intrări și distribuția
  `286` class trainers / `287` profession trainers / `2.682` NPC static; toate
  rămân `zone_area`, `STATIC_SOURCE_CANDIDATE`, fără autoritate de execuție.
  Auditul este `data/runtime/navigation-f3b/zygor-npcdata-map-binding-audit-20260831.json`;
  `--check` trece.
- **Limită:** binding-ul nu convertește IDs în poziții live și nu promovează
  NPCData în awareness 3D; observer-ul rămâne limitat la target/focus/mouseover
  și nameplate screen-space. Nu s-a instalat addonul, nu s-a reîncărcat WoW și
  nu s-a pornit test live.

## ME-145 — Expansion01: bake complet și audit geometric fără promovare

- **Baked offline:** `Expansion01` (map `530`) a pornit din
  `READY_FOR_SEMANTICS` și a terminat cu `800/800` road sidecars și `800/800`
  nav tiles. Rezultatul este
  `data/runtime/navigation-f3b/expansion01-bake-20260831.json`, `PASS`, cu
  sursă exclusiv din client și `execution_authority=false`.
- **Catalog candidat:**
  `client-world-catalog-world-continents-v2-candidate.json` include exact
  `Azeroth`, `Kalimdor`, `Expansion01` și `3/3` coverage complete în catalogul
  candidat; cele `83` identități de client rămân vizibile, dar registry-ul nu
  este modificat și semantic/access autonomy nu este acordată.
- **Audit structural:**
  `expansion01-navmesh-geometry-20260831.json` trece `800/800` tile-uri,
  `204.800` sub-tile-uri și `0` failures. Auditul de calitate este
  `COMPLETE_WITH_RECAST_DIAGNOSTICS`, cu `0` tile-uri lipsă/eșuate și
  diagnostice Recast păstrate (nu ascunse).
- **Corecție validator:** worker-ul Windows pe payload Namigator mare expunea
  un `NameError`/crash intern Python 3.14. Header-ul `'<6I'` este acum local
  funcției, iar testul parallel cu ADT comprimat și link-uri 64-bit trece.
  Un pool mare continuă să lovească bug-ul intern `Executing a cache`; pentru
  dovada hărții complete s-a folosit audit serial, fără a relaxa gate-ul.
- **Limită:** nu este dovadă de semantic destinations, structure/access graph,
  awareness 3D generic sau rutare live. Nu s-a instalat Zygor, nu s-a
  reîncărcat WoW și nu s-a pornit input/combat/Hermes.

## ME-146 — Zygor Anniversary verificat și map-area reconciliation parțial

RAR-ul local `Zygor Release 8.1.37070.rar` este valid (RAR5, 18.260.702
bytes, SHA-256 `d8d416ad95f9071fd8578df218a70235c377ea8b350f81ca2ea6f5417a65d2d3`)
și conține ediția TBC Anniversary (`Interface: 20506`, `Version: 8.1`,
`Guides-TBC`, `Data-TBC`, `Code-TBC`). `Zygor.zip` nu este aceeași ediție:
este exportul vechi din 2008.

Auditul offline a reconfirmat datele de ghidare fără a evalua Lua: `11.205`
pași leveling, `10.007` poziții candidate, `730` traineri de clasă și `2.373`
pași combat; profesiile: `3.543` pași, `1.680` poziții, `524` traineri și `16`
quest-uri.

`scripts/audit_zygor_world_map_reconciliation.py` compară numeric și
content-minimal `m####` cu `WorldMapArea.dbc`: `45/66` rezolvate (`22` exact,
`23` normalizat), `0` ambigue, `21` nerezolvate. Rezultatul este
`data/runtime/navigation-f3b/zygor-world-map-reconciliation-20260831.json`,
cu `execution_authority=false`; ID-urile nerezolvate nu devin destinații,
nu acordă autonomie și nu justifică test live.
Regresia completă după această adăugare este `1287/1287`.

## ME-147 — Secvență multi-destinație cu retur explicit

Contractul `semantic_destination_sequence` acceptă acum opțional
`close_loop`. Pentru `A → B → C`, un loop închis produce
`A → B → C → A`; bucla nu conține coordonate sau input executabil, iar
fișierele existente fără câmp rămân valide. Control Center expune opțiunea
și supervisor-ul o consumă după validarea catalogului și a map ID-ului.

Verificarea țintită este `31/31` teste verzi. Aceasta nu promovează hărți fără
semantic/access graph și nu pornește live.

## ME-148 — Regresie post-loop și acoperire registry/UI

- `1289/1289` teste offline trec după `close_loop`; `compileall` și
  `git diff --check` sunt verzi. Mesajul fixture-ului negativ pentru
  `--jobs=5` este așteptat.
- Verificările `--check` pentru cele trei audituri Zygor trec pe fișierele
  extrase temporar din RAR; nu s-a copiat addonul în repo și nu s-a evaluat
  Lua.
- Registry/UI expune `83` profiluri, dintre care `35` sunt în bake queue și
  `4` au bake complet; doar `1` este `autonomous_ready`. Restul rămân
  `OBSERVE_ONLY`/fail-closed până la catalog semantic și structure/access
  graph proprii.
- Nu s-a instalat addonul, nu s-a reîncărcat WoW și nu s-a pornit input live.

## ME-149 — Audit content-minimal pentru ghidurile Zygor și indicator UI

- Auditul `scripts/audit_zygor_guide_coverage.py` procesează cele șase fișiere
  non-Trial selectate și păstrează doar hash-uri, dimensiuni și count-uri.
  Artefactul `data/runtime/navigation-f3b/zygor-guide-coverage-20260901.json`
  raportează `14.748` pași, `11.687` coordonate candidate, `730` traineri de
  clasă, `663` traineri de profesie și `855` quest-uri clasificate.
- Control Center afișează acoperirea ca RouteTeacher read-only. Auditul este
  respins dacă este malformat sau are `execution_authority=true`; nu creează
  waypoints și nu schimbă gate-ul WorldPack. Testele dedicate trec `21/21`.
- Nu s-a copiat addonul în repo, nu s-a evaluat Lua, nu s-a reîncărcat WoW și
  nu s-a pornit input live.
  Regresia completă după integrarea indicatorului trece `1293/1293`; auditul
  `--check`, `compileall` și `git diff --check` sunt verzi.

## ME-150 — Replay Shadowfang: mismatch de profil MPPI

- **Constatare:** replay-ul Shadowfang rulat cu vechile implicite
  `128/56/4` a avut `79/100` treceri de calitate, deși toate trial-urile au
  ajuns și nu au avut coliziuni. Cauza urmărită a fost mismatch-ul față de
  profilul MPPI validat în benchmark.
- **Corecție/dovadă:** cu `batch_size=256`, `time_steps=56` și
  `replan_interval_ticks=3`, replay-ul are `100/100` calitate, `0` coliziuni,
  cross-track maxim `1.9885` și activare MPPI `98.2%`; artefactul este
  `data/runtime/navigation-f3b/shadowfang-v3-steering-replay-adaptive-20260901-v2.json`.
  Implicitele replayer-ului sunt acum aliniate, iar regresia steering dedicată
  trece `14/14`.
- **Limită:** acesta este replay offline pe coridorul reținut. Validarea nu
  acordă autoritate de execuție, nu modifică serverul și nu autorizează input
  live sau combat. Regresia offline completă după corecție trece `1295/1295`;
  `compileall` și `git diff --check` sunt verzi.

## ME-152 — Scan Kalimdor reluat cu worker pin-uit și graph candidat v2

- **Dovadă:** lotul bounded de `1.000` probe a crescut progresul la
  `2.139/40.794`, `57` WMO confirmate, `74` structuri complete și `0` erori.
  Worker-ul `v35` are hash-ul cerut de plan; fallback-ul persistent a clasificat
  `129` probe, iar `871` au folosit awareness persistent.
- **Agregare:** graph-ul
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v2.json`
  include `57` observații, `254` openings și `488` boundary chains, cu starea
  `PARTIAL_OBSERVED_COMPONENTS`.
- **Limită:** graph-ul nu este map-wide și nu este atașat registry-ului sau
  autonomiei Kalimdor. Prima comandă cu `v34` a fost refuzată fail-closed
  pentru mismatch de hash; nicio probă nu a ajuns în joc și live-ul rămâne oprit.

## ME-151 — RouteTeacher map coverage și context zonal

- **Schimbare:** binding-ul explicit din
  `config/knowledge/zygor-zone-map-bindings-tbc243.json` acoperă cele `66`
  de zone întâlnite în fișierele Anniversary selectate. Noul audit
  `scripts/audit_zygor_route_coverage.py` parsează pașii fără evaluare Lua și
  persistă doar hash-uri, identități de hartă și count-uri.
- **Dovadă:** artefactul
  `data/runtime/navigation-f3b/zygor-route-coverage-20260901.json` raportează
  `4.625` pași Azeroth, `5.148` Kalimdor, `4.974` Expansion01 și `1`
  BlackTemple; totalul este `14.748` pași și `11.687` coordonate candidate.
  Parserul modern păstrează ultima zonă explicită pentru pașii fără `goto` din
  aceeași guide, evitând atribuirea implicită greșită la Azeroth.
- **Limită:** acestea sunt fapte RouteTeacher advisory, nu poziții live exacte
  și nu waypoints executabile. Binding-urile și UI-ul au
  `execution_authority=false`; testele dedicate trec `13/13`, iar live-ul
  rămâne oprit. Regresia offline completă după schimbare trece `1300/1300`;
  auditul `--check`, `compileall` și `git diff --check` sunt verzi.

## ME-153 — Scan Kalimdor continuat cu profilul v35

- **Dovadă:** al doilea lot bounded de `1.000` probe a dus progresul la
  `3.139/40.794`, cu `73` observații WMO, `106` structuri complete și `0` erori
  de worker. Rămân `37.655` seed-uri neatinse în raportul
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v1.json`.
- **Agregare:**
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v3.json`
  include `73` observații, `350` openings și `692` boundary chains.
- **Limită:** starea rămâne `PARTIAL_OBSERVED_COMPONENTS`; graph-ul nu este
  map-wide, nu este legat în registry și nu acordă autonomie. Totul a fost
  offline; niciun reload WoW și niciun input live nu au fost pornite.

## ME-154 — Primul access scan bounded pentru Expansion01

- **Index/plan:** bake-ul Expansion01 este `800/800` tile-uri; indexul local
  are `1.659` WMO și `94.506` doodads, iar planul are `47.170` seed-uri
  eligibile și `0` deferred.
- **Dovadă:** primul lot offline de `1.000` probe cu v35 a confirmat `17` WMO,
  `35` structuri complete și `0` erori; rămân `46.170` seed-uri. Artefactele
  sunt `expansion01-candidate-structure-access-scan-progress-v1.json` și
  `expansion01-candidate-structure-access-partial-v1.json` în
  `data/runtime/navigation-f3b/`.
- **Limită:** graph-ul candidat are `17` observații, `29` openings și `88`
  boundary chains, rămâne `PARTIAL_OBSERVED_COMPONENTS` și nu este legat în
  registry. Scanarea a fost exclusiv offline, fără reload WoW sau input live.

## ME-155 — NPCData static content-minimal în Control Center

- **Dovadă:** binding-ul LibRover pentru toate cele `66` map-area IDs este
  complet și neambiguu. Auditul
  `data/runtime/navigation-f3b/zygor-npcdata-audit-20260901.json` are `3.255`
  rânduri: `286` class trainers, `287` profession trainers și `2.682` NPC statici.
- **Integrare:** Control Center afișează doar count-uri/hash-uri read-only;
  nu transformă coordonatele sursei în poziții live și nu acordă execuție.
- **Limită:** este knowledge static advisory, nu awareness 3D exact sau server
  truth. Testele UI verifică și respingerea `execution_authority=true`; nu s-a
  evaluat Lua, nu s-a reîncărcat WoW și nu s-a pornit input live.

## ME-156 — Holdout offline Crypt→Brill→Crypt și starea Anniversary

- **Dovadă:** comparația read-only a holdout-urilor `v17`–`v38` găsește `5`
  `ARRIVED`, `10` `STOPPED_FAIL_CLOSED`, `3` `STOPPED_CHILD_ERROR`, `2`
  `STOPPED_NAVIGATION_BUDGET` și `1` `STOPPED_COMBAT_BUDGET`. Ultimul (`v38`)
  este `ARRIVED`, însă seria nu dovedește încă determinism.
- **Bază offline:** artefactul profile-aware v41 trece `5/5` cazuri, inclusiv
  ambele sensuri Crypt/Brill; fixture-ul de deal este fail-closed și acceptat
  ca frontieră locală parțială.
- **Limită:** toate artefactele au `execution_authority=false`; diferența
  rămasă este în runner/frontieră și trebuie investigată offline. Nu s-a
  reîncărcat WoW și nu s-a pornit input live.

## ME-157 — Scan Kalimdor continuat cu binding-ul corect

- **Preflight:** combinația inițială cu profilul agregat `world-continents` a
  fost respinsă înainte de probe pentru mismatch de `pack_id`; indexul este
  legat corect de profilul candidat Kalimdor.
- **Dovadă:** lotul bounded de `1.000` seed-uri a dus progresul la
  `4.139/40.794`, cu `121` observații WMO, `140` structuri complete și `0`
  erori; rămân `36.655` seed-uri.
- **Agregare/limită:** `partial-v4` are `121` observații, `608` openings și
  `1.126` boundary chains, starea `PARTIAL_OBSERVED_COMPONENTS`; nu este
  legat în registry și nu acordă autonomie. Nicio modificare live.

## ME-158 — Filtrare strictă a ancorelor semantice Tirisfal

- **Schimbare:** catalogul Azeroth include acum doar
  `landmark:deathknell-south-gate`, o ancoră semantică derivată din ruta
  revizuită și validată local cu query 3D complet.
- **Fail-closed:** ancorele candidate pentru coborâri/midpoint/apropiere au
  fost verificate offline; cele care au produs frontieră parțială, eroare de
  height sau timeout nu au fost păstrate în picker.
- **Limită:** destinația este semantică, nu waypoint executabil; nu se acordă
  autonomie suplimentară și nu s-a pornit live.

## ME-159 — Primul lot Expansion01 după indexarea WMO

- **Dovadă:** lotul bounded de `1.000` seed-uri a dus Expansion01 la
  `2.000/47.170`, cu `37` observații WMO, `70` structuri complete și `0` erori;
  rămân `45.170` seed-uri.
- **Agregare:** `expansion01-candidate-structure-access-partial-v2.json`
  conține `37` observații, `98` openings și `254` boundary chains.
- **Limită:** starea este `PARTIAL_OBSERVED_COMPONENTS`, graph-ul nu este
  legat în registry și nu acordă autonomie; scanarea a fost offline.

## ME-160 — Scan Kalimdor bounded după lotul v4

- **Dovadă:** un lot offline de `1.000` probe cu perechea exactă profil/index
  Kalimdor și worker v35 a dus progresul la `5.139/40.794`, cu `146`
  observații WMO, `175` structuri complete și `0` erori; rămân `35.655`
  seed-uri.
- **Agregare:** `kalimdor-candidate-structure-access-partial-v5.json` are
  `146` observații, `753` openings și `1.439` boundary chains; raportul de
  progres este `kalimdor-candidate-structure-access-scan-progress-v1.json`.
- **Limită:** starea rămâne `PARTIAL_OBSERVED_COMPONENTS`, graful nu este
  legat în registry și nu acordă autonomie; totul a fost offline.

## ME-161 — Scan Expansion01 bounded continuat

- **Dovadă:** lotul offline de `1.000` probe cu profilul agregat corect a dus
  progresul la `3.000/47.170`, cu `83` observații WMO, `105` structuri complete
  și `0` erori; rămân `44.170` seed-uri.
- **Agregare:** `expansion01-candidate-structure-access-partial-v3.json`
  are `83` observații, `186` openings și `586` boundary chains; progresul este
  în `expansion01-candidate-structure-access-scan-progress-v1.json`.
- **Limită:** starea rămâne `PARTIAL_OBSERVED_COMPONENTS`, graful nu este
  legat în registry și nu acordă autonomie; scanarea a fost exclusiv offline.

## ME-162 — Reevaluare offline a calității trace-urilor v38

- **Dovadă:** evaluatorul oficial a fost rerulat pe cele două rezultate v38
  existente. Ambele au `arrived=true`, `passed=true` și `0` gap-uri neexplicate
  peste 300 ms.
- **Transparență:** outbound păstrează `4` gap-uri brute, returul `1`; toate
  sunt `motion_continuity_exempted_gaps` cu deplasare măsurată și input înainte
  compatibil. Pragul nu a fost relaxat și nu s-a pornit live.

## ME-163 — Catalog read-only pentru transformările WorldMapArea

- **Schimbare:** catalogul
  `config/pose/world-map-zone-transforms-tbc243-8606.json` acoperă `68`
  transformări unice `(map_id, area_id)` din auditul clientului TBC 2.4.3 și
  păstrează hash/fingerprint, sursa și momentul recuperării.
- **Siguranță:** loaderul validează bounds și respinge duplicatele sau
  `execution_authority=true`; Control Center afișează doar acoperirea, fără
  rută executabilă ori înălțime live.
- **Regresie:** testele țintite trec `29/29`, iar suita completă offline trece
  `1309/1309`; WoW și inputul live au rămas oprite.

## ME-164 — Acoperire RouteTeacher prin transformări 2D

- **Schimbare:** auditul bounded al celor șase fișiere Zygor non-Trial compară
  fiecare coordonată cu transformările client WorldMapArea. Aliasurile sunt
  compatibilitate de nume, nu waypoints sau instrucțiuni de input.
- **Dovadă:** `11.686/11.687` coordonate candidate transformate; Azeroth
  `3.434/3.434`, Kalimdor `3.918/3.918`, Expansion01 `4.334/4.334`. Singurul
  caz nerezolvat este Black Temple (`map_id=564`), absent din catalogul auditat.
- **Limită:** artefactul păstrează doar hash-uri/count-uri și rămâne
  `PARTIAL_CLIENT_2D_TRANSFORM`, `execution_authority=false`; nu acordă
  autonomie semantică/access și nu s-a pornit test live.

## ME-165 — Scanuri bounded continuate pe continente

- **Kalimdor:** progres `6.139/40.794`, `177` observații WMO acceptate, `209`
  structuri complete, `0` erori; `partial-v6` are `812` openings și `1.622`
  boundary chains.
- **Expansion01:** progres `4.000/47.170`, `114` observații acceptate, `141`
  structuri complete, `0` erori; `partial-v4` are `226` openings și `776`
  boundary chains.
- **Limită:** ambele rămân `PARTIAL_OBSERVED_COMPONENTS`, nelegate în registry,
  fără `execution_authority`; nu s-a pornit test live.

## ME-166 — Scan Kalimdor bounded continuat

- **Kalimdor:** lot offline de `1.000` probe; progres `7.139/40.794`, `188`
  seed-uri acceptate, `246` structuri complete, `33.655` seed-uri rămase și
  `0` erori de worker.
- **Graph:** `partial-v7` are `186` observații din task-urile complete, `837`
  openings și `1.682` boundary chains; starea rămâne
  `PARTIAL_OBSERVED_COMPONENTS`.
- **Limită:** artefactul nu este legat în registry și are
`execution_authority=false`; nu s-a pornit WoW sau input live.

## ME-170 — Monte Carlo offline extins pentru hairpin și curbe înguste

- **Simulare:** `200` curse pentru fiecare dintre cele șase scenarii, `5` joburi;
  `1.200/1.200` curse completate, `0` coliziuni și `0` eșecuri quality gate.
- **Hairpin:** `narrow_outdoor_hairpin` are maximum `2` schimbări de semn și
  maximum `0.2830` pivot fraction.
- **Limită:** raportul este evidence offline cu `execution_authority=false`;
  nu este test live.

## ME-169 — Recheck offline al trace-urilor Crypt↔Brill

- **Outbound:** `7.000` cadre, `arrived=true`, `passed=true`, patru gap-uri
  peste 300 ms clasificate ca motion-continuity exemptions, zero gap-uri
  neexplicate.
- **Retur:** `6.797` cadre, `arrived=true`, `passed=true`, o exemption și zero
  gap-uri neexplicate.
- **Limită:** evaluatorul a folosit trace-uri brute existente; nu este un test
  live nou și nu schimbă `execution_authority=false`.

## ME-168 — Regresie offline după scanurile continentale

- **Validare:** testele țintite pentru structure-access, transformări RouteTeacher
  și Control Center trec `56/56`; suita offline completă trece `1313/1313` în
  `111,05 s`.
- **Mediu:** `.venv` folosește `pytest==8.4.2` pentru această regresie; nu s-a
  schimbat codul de runtime.
- **Limită:** rezultatul validează doar contractele și replay-urile offline;
  WoW, inputul live și procesele Hermes au rămas oprite.

## ME-167 — Scan Expansion01 bounded continuat

- **Expansion01:** lot offline de `1.000` probe; progres `5.000/47.170`, `123`
  seed-uri acceptate, `177` structuri complete, `42.170` seed-uri rămase și
  `0` erori de worker.
- **Graph:** `partial-v5` are `123` observații, `303` openings și `848`
  boundary chains; starea rămâne `PARTIAL_OBSERVED_COMPONENTS`.
- **Limită:** artefactul nu este legat în registry și are
  `execution_authority=false`; nu s-a pornit WoW sau input live.

## ME-175 — Semantic gate offline proaspăt, inert

- **Gate:** `data/runtime/operator/movement-engine-semantic-gate.json` are
  `status=PASS`, hash binding către v43/WorldPack Azeroth v3/worker v34 și
  `live_authority_enabled=false`.
- **Preflight:** autorizația temporală LAB și runtime arm-ul lipsesc; gate-ul
  nu poate autoriza input.
- **Limită:** nu s-a pornit WoW și nu s-a schimbat niciun proces paralel.

## ME-174 — Regresie awareness client-visible și scoring LAB

- **Validare:** testele pentru `dynamic_entity_awareness`, tracker nameplate,
  dynamic avoidance, experiență append-only, detector vizibil și combat HUD
  trec `38/38`.
- **Limită:** evidence-ul acoperă numai viewport/nameplate și scoring LAB; nu
  dovedește poziții 3D exacte pentru entități ascunse și nu acordă combat/input.
- **Gate:** nu există autorizație temporală LAB, semantic gate activ sau runtime
  arm; operațiunile live au rămas oprite.

## ME-171 — Scan Kalimdor bounded continuat

- **Kalimdor:** lot offline de `1.000` probe; progres `8.139/40.794`, `194`
  seed-uri acceptate, `280` structuri complete, `32.655` rămase și `0` erori.
- **Graph:** `partial-v8` are `194` observații, `888` openings și `1.735`
  boundary chains; rămâne `PARTIAL_OBSERVED_COMPONENTS`, nelegat în registry,
  cu `execution_authority=false`.

## ME-172 — Scan Expansion01 bounded continuat

- **Expansion01:** lot offline de `1.000` probe; progres `6.000/47.170`, `129`
  seed-uri acceptate, `214` structuri complete, `41.170` rămase și `0` erori.
- **Graph:** `partial-v6` are `129` observații, `320` openings și `910`
  boundary chains; rămâne `PARTIAL_OBSERVED_COMPONENTS`, nelegat în registry,
  cu `execution_authority=false`.
- **Limită:** nu s-a pornit WoW, input live sau procese Hermes.

## ME-173 — Validator semantic offline reexecutat pe Crypt/Brill

- **Rezultat:** toate cele cinci cazuri au verdictul așteptat în
  `semantic-road-journey-validation-20260901-v42.json`: cele patru coridoare
  ajung la destinație, iar fixture-ul de deal rămâne `RESET_REQUIRED` cu
  `partial_local_navmesh_corridor`.
- **Limită:** rularea folosește WorldPack/worker offline, are
  `execution_authority=false` și nu scrie live gate; WoW și inputul live au
  rămas oprite.

## ME-176 — Transform runtime legat de mapă și zonă

- **Schimbare:** runner-ul navmesh rezolvă transformarea 2D din catalogul
  client read-only `WorldMapArea.dbc` după `map_id` și `zone_index`; aliasurile
  Tirisfal/Undercity sunt folosite doar când ID-ul HUD diferă de `area_id`.
- **Control Center:** transmite zona explicită din catalogul semantic și calea
  catalogului de transformări, în loc să fixeze `zone_index=25`.
- **Dovadă:** cazul offline `Kalimdor/Durotar` și regresia țintită trec
  `184/184`; nicio hartă nouă nu este promovată, iar gate-ul rămâne inert.
- **Limită:** hărțile fără catalog semantic și structure/access graph complet
  rămân `OBSERVE_ONLY`; nu s-a pornit WoW și nu s-a trimis input live.

## ME-177 — Regresie semantică după transformarea multi-map

- **Dovadă:** validatorul offline v44 trece toate cele cinci cazuri; cele patru
  coridoare ajung la destinație, iar fixture-ul deal/frontieră rămâne
  `RESET_REQUIRED` cu `partial_local_navmesh_corridor`.
- **Regresie:** suita completă trece `1316/1316` după schimbarea de rezolvare a
  transformărilor map/zonă.
- **Limită:** rezultatul este offline/replay evidence; gate-ul live este inert,
  fără autorizație temporală LAB/runtime arm și fără input live.

## ME-178 — Gate offline rebondat la v45

- **Dovadă:** validatorul complet rulat cu `--write-offline-gate` a trecut toate
  cele cinci cazuri și a scris rezultatul v45.
- **Gate:** `movement-engine-semantic-gate.json` pointează la v45 cu hash valid,
  dar `live_authority_enabled=false`.
- **Limită:** nu există autorizație temporală LAB sau runtime arm; WoW și inputul
  live au rămas oprite.

## ME-179 — Toate refresh-urile de poziție folosesc transformarea selectată

- **Schimbare:** apelurile `_position()` din refresh, replan, combat handoff și
  handler-ele de eroare primesc transformarea deja rezolvată după
  `map_id + zone_index`; nu mai revin la fallback implicit Tirisfal.
- **Validare:** regresia țintită `184/184`, suita completă `1316/1316` în
  `112,31 s`, `compileall` și `git diff --check` verzi.
- **Limită:** gate-ul semantic rămâne inert (`live_authority_enabled=false`),
  fără autorizație LAB/runtime arm și fără WoW sau input live.

## ME-180 — Revalidare locală a arhivei TBC Anniversary

- **Dovadă:** 7-Zip raportează `Everything is Ok` pentru RAR5, cu `83` directoare,
  `868` fișiere și `85.807.771` bytes necomprimați; SHA-256 este
  `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`.
- **Identitate:** TOC-ul TBC declară `Interface: 20506`, `Version: 8.1` și
  `ZygorGuidesViewerClassicTBCAnniv`.
- **Limită:** verificarea a fost read-only; arhiva nu a fost copiată în repo,
  Lua nu a fost evaluat și nu s-a pornit WoW/input live.

## ME-181 — Viewer și continuitate map-bound

- **Schimbare:** pose-ul read-only, bridge-ul MapViewer și corpse-recovery
  propagă `map_id + zone_index + zone-transform-catalog`; nu mai convertesc
  implicit un profil nenul prin Tirisfal.
- **Validare:** testul Durotar (`map_id=1`, `zone_index=14`), viewer/continuity
  și regresia completă `1319/1319` sunt verzi; `compileall` și `git diff --check`
  trec.
- **Limită:** hărțile fără semantic/access graph rămân fail-closed/observe-only;
  gate-ul este inert și nu s-a pornit WoW sau input live.

## ME-182 — Diagnostic offline al frontierei de deal

- **Dovadă:** worker-ul se oprește la `(2055.357422, 1240.476562, 64.966675)`,
  cu `101.64` yards până la anchor, `7` tranziții steep și `5617` poligoane
  penalizate; rafinarea adaptivă nu produce progres înainte.
- **Verdict:** fixture-ul rămâne corect `RESET_REQUIRED`/
  `partial_local_navmesh_corridor`; nu este marcat artificial sigur și nu se
  adaugă shortcut geometric.
- **Limită:** Crypt↔Brill rămâne valid offline, iar gate-ul semantic este inert;
  nu s-a pornit WoW sau input live.

## ME-183 — Layer/variant probe offline pentru aceeași frontieră

- **Strat vertical:** nouă probe bounded (`0`, `±32`, `±64`, `±128`, `±256`)
  au rezolvat aceeași suprafață (`height_candidates=1`) și același stop
  `(2055.357422, 1240.476562)`; selectorul nu are un etaj alternativ legitim.
- **Planner variants:** `road_backbone`, `balanced` și `shortcut` păstrează
  aceeași intrare `(2132.100586, 1307.117310)`. Toate requery-urile se opresc la
  frontieră, cu gap `101.64` yards; ancorele ulterioare rămân parțiale.
- **Verdict:** `RESET_REQUIRED`/`partial_local_navmesh_corridor` rămâne corect;
  fără relaxare steep, waypoint inventat, shortcut geometric sau test live.

## ME-184 — Neighborhood frontier probe fără teleport sau waypoint

- **Dovadă:** seed-ul dealului snap-uiește la `(2031.547241, 1226.785400)` cu
  radial egress nereușit și același stop `(2055.357422, 1240.476562)`; probele
  la circa `+100` yards sud ajung la anchor, dar requery-ul invers spre seed se
  oprește la `(2019.0, 1291.7)`, gap `~67.2` yards.
- **Interpretare:** sunt componente navmesh distincte; apropierea geometrică
  nu dovedește traversabilitate. Endpoint-ul fără poligon a fost fail-closed.
- **Verdict:** rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`; nu se
  adaugă teleport, bridge geometric, waypoint hardcodat sau relaxare steep și
  nu se pornește live.

## ME-185 — Reconciliere explicită a aliasurilor Zygor–WorldMapArea

- **Schimbare:** aliasurile de nume dintre LibRover și `WorldMapArea` sunt
  centralizate într-un compat layer read-only și folosite de auditurile de
  route/NPCData; nu conțin rute executabile.
- **Dovadă:** arhiva reală raportează acum `62/66` map-area-uri rezolvate
  (`22` exact, `40` normalizate/alias), `0` ambigue și `4` fără rând client
  (`Black Temple` plus trei instanțe sintetice).
- **Limită:** coordonatele rămân static source candidates; nu se inferă
  poziții live, iar hărțile fără `WorldMapArea` rămân fail-closed.

## ME-186 — Revalidare semantică după compat layer

- **Dovadă:** `semantic-road-journey-validation-20260901-v46.json` este
  `PASS`; cele patru direcții așteptate sunt `ARRIVE`, iar fixture-ul dealului
  rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`.
- **Limită:** v46 este verificare offline cu WorldPack/navmesh; gate-ul are
  `live_authority_enabled=false`, fără autorizație LAB/runtime arm și fără
  input live.

## ME-187 — Query advisory pentru candidați statici NPC/trainer

- **Schimbare:** Knowledge Broker poate interoga candidați statici în jurul
  unei poziții 2D normalizate, cu identitate exactă de map-area, scope și
  tipuri filtrate; sortarea este deterministă.
- **Siguranță:** rezultatul rămâne `STATIC_SOURCE_CANDIDATE`, fără poziție
  live, destinație executabilă sau autoritate. Dynamic nameplate awareness nu
  este înlocuită cu NPCData static.
- **Validare:** testul dedicat trece; invalid map/coordinate este respins
  fail-closed; indicatorul Control Center respinge autoritatea falsificată;
  suita completă după schimbare este `1323 passed`.

## ME-188 — Revalidare a frontierei cu worker și pack-uri alternative

- **Dovadă:** v34 și v35, pe pack-urile v3, v4 candidate și repair-source,
  returnează același stop `(2055.357422, 1240.476562)`, cu
  `complete=false`, `steep=5617` și `doodad=1356`.
- **Interpretare:** tile-ul reparat `29_28` este încărcat, însă componenta
  dealului rămâne separată de continuarea de drum; nu este o variație de
  worker/pack care să justifice relaxarea gate-ului.
- **Siguranță:** fără shortcut, teleport, waypoint hardcodat sau input live;
  `RESET_REQUIRED`/`partial_local_navmesh_corridor` rămâne fail-closed.

## ME-189 — Holdout live bounded și preplanare asincronă a pauzelor

- **Dovadă live:** cu autorizație LAB proaspătă, runtime arm temporar și
  `combat_handoffs_used=0`, secvența identifier-only
  `settlement:brill -> landmark:deathknell-crypt` a raportat `ARRIVED` pe
  ambele picioare în
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live.json`.
  Ambele rezultate navmesh sunt `execution_authority=false`; Predator a fost
  observat viu la Crypt la checkpoint, iar WoW a rămas deschis și disarmat.
- **Calitate temporală:** evaluatorul oficial trece returul
  (`data/runtime/navigation-f3b/results/navmesh-roaming-442c898c-8517-481e-950c-fafe930e6640-quality.json`, fără goluri inexplicate), dar outbound-ul
  (`data/runtime/navigation-f3b/results/navmesh-roaming-7442991d-70fa-439f-b189-133e69575b1b-quality.json`) rămâne `passed=false`: un gol inexplicat de
  `2.1296 s` la frontieră/static pivot și unul de `1.2960 s` la
  `CORRIDOR_RECENTER_REPLAN`. Nu sunt ascunse prin relaxarea pragului.
- **Schimbare offline:** runner-ul pregătește în process-pool bypass-ul din
  celulele ordonate ale rutei semantice și replanarea de recenter înainte de
  pragul strict; aplică rezultatul numai dacă query-ul, ținta și poziția de
  start rămân valide. În caz contrar, fallback-ul sincron fail-closed rămâne
  activ. Validatorul semantic v47 trece `5/5` cazuri așteptate
  (`4×ARRIVE`, deal `RESET_REQUIRED`). Testele focalizate sunt `145/145`,
  runtime/supervisor `98/98`, iar regresia completă este `1325/1325`.
- **Limită:** acesta este un holdout diagnostic, nu o certificare humanlike;
  nu se pornește încă un test live până când outbound-ul nu trece poarta
  temporală după validare offline suplimentară.

## ME-190 — Holdout live v2 și prioritate offline pentru frontieră

- **Dovadă live:** versiunea cu preplanare a ajuns din nou la Brill și apoi la
  Crypt (`ARRIVED`) în
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v2.json`,
  cu run-uri `8cbb021e-5880-4895-aa0b-005b6cfe0cee` și
  `6fa3f7e0-0d39-4281-94f2-4b8808b39103`, zero handoff combat și
  `execution_authority=false`. Sesiunea a fost disarmată imediat după verdict.
- **Calitate:** returul trece (`6699` frames, `0` goluri inexplicate). Outbound
  s-a îmbunătățit la un singur gol inexplicat de `2.10225 s` la
  `SEMANTIC_STATIC_FRONTIER_BYPASS`; recenter-ul nu mai este gol inexplicat
  (`1.3329 s` cu mișcare continuă măsurată). Artefactul quality este
  `data/runtime/navigation-f3b/results/navmesh-roaming-8cbb021e-5880-4895-aa0b-005b6cfe0cee-quality.json`.
- **Schimbare offline ulterioară:** când coridorul curent este parțial,
  runner-ul nu mai pornește preplanarea următorului obiectiv înaintea
  bypass-ului frontieră; eliberează worker-ul pentru candidaturile ordonate
  ale rutei. Testele focalizate sunt `244/244`, iar suita completă este
  `1326/1326`.
- **Limită:** această ultimă prioritate nu a fost încă revalidată live; nu se
  declară încă mișcare humanlike certificată și nu se pornește alt test live în
  acest ciclu.

## ME-191 — Pool dedicat pentru bypass-ul de frontieră

- **Schimbare offline:** query-ul bounded pentru bypass-ul atlas-forward rulează
  într-un `ProcessPoolExecutor` separat (`max_workers=1`), astfel încât
  baseline-urile WMO și preplanurile ordinare nu îl pot pune în coadă. Pool-ul
  este închis explicit la teardown.
- **Siguranță:** worker-ul rămâne fără actuator; candidații provin exclusiv din
  ruta semantică, iar aplicarea verifică în continuare query-ul, ținta și
  apropierea de frontieră. Nu se introduc coordonate inventate, teleport sau
  shortcut.
- **Validare:** compileall și testele focalizate Movement Engine/runtime/
  supervisor trec `245/245`; nu s-a pornit test live după amendament.

## ME-192 — Fan-out bounded pentru candidaturile de frontieră

- **Schimbare offline:** pool-ul dedicat validează concurent cel mult patru
  query-uri native read-only din orizontul de cel mult opt candidaturi. Alegerea
  rămâne în ordinea rutei semantice, nu în ordinea în care se termină query-urile.
- **Siguranță:** fiecare rezultat este verificat ca și coridor client-navmesh
  complet către raza locală; nu există coordonate laterale inventate, shortcut
  sau autoritate de execuție.
- **Validare:** compileall și testele Movement Engine trec `147/147`; suita
  completă va fi rerulată înainte de următorul gate live. Nu s-a pornit test live.

## ME-193 — Scanări continentale bounded continuate

- **Dovadă offline:** Kalimdor a ajuns la `9.139/40.794` seeds, cu `211`
  observații WMO acceptate, `314` structuri finalizate și `0` erori; agregarea
  strictă `partial-v9` are `967` openings și `1.842` boundary chains.
- **Dovadă offline:** Expansion01 a ajuns la `7.000/47.170` seeds, cu `149`
  observații, `249` structuri finalizate și `0` erori; `partial-v7` are `429`
  openings și `1.070` boundary chains.
- **Limită:** ambele grafuri sunt încă `PARTIAL_OBSERVED_COMPONENTS` și nu sunt
  legate la autonomia Control Center; nu s-a pornit input live.

## ME-194 — Holdout live după pool dedicat și fan-out bounded

- **Audit addon local:** `D:\Downloads\Zygor Release 8.1.37070.rar` este
  `ZygorGuidesViewerClassicTBCAnniv`, Interface `20506`, Version `8.1`, cu
  SHA-256 `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`,
  868 fișiere și 83 directoare; arhiva a rămas neextrasă și în afara repo-ului.
- **Preflight:** `live-v3` a fost refuzat la `CHARACTER_SELECT`, fără input de
  mișcare. După `EnterWorld` controlat, singurul holdout efectiv
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v4.json`
  a ajuns la Brill și Crypt, cu zero handoff combat și
  `execution_authority=false`.
- **Calitate outbound:**
  `data/runtime/navigation-f3b/results/navmesh-roaming-0e23b788-fde8-4759-9494-85ae42f26515-quality.json`
  are 6 goluri brute, 3 compensate și 3 inexplicabile; maximul este `2.554495 s`.
- **Calitate retur:**
  `data/runtime/navigation-f3b/results/navmesh-roaming-2b46aa01-b0c8-4ead-96bc-aae8c2f1907d-quality.json`
  are 2 goluri brute, 1 compensat și 1 inexplicat; maximul este `0.366721 s`.
  Ambele leg-uri sunt `ARRIVED`, dar `passed=false` pentru
  `control_observation_gap`; nu se declară mișcare humanlike certificată și nu
  se pornește o a doua rulare live.

## ME-195 — Alinierea limitei worker-ului cu fereastra inclusivă de frontieră

- **Cauză confirmată offline:** trace-ul v4 a înregistrat 9 candidaturi la
  frontiera `1883.035767, 1583.333374`; helper-ul produce această fereastră
  inclusivă din extensia de 8 celule și următorul obiectiv coalescat, dar
  worker-ul respingea lotul peste 8. Future-ul eșua, iar caller-ul executa un
  query sincron în bucla de control.
- **Schimbare offline:** limita worker-ului este acum `32`, separată de
  extensia semantică; fan-out-ul rămâne la cel mult `10` query-uri native
  concurente, cu rezultat ales în ordinea rutei. Loturile peste limită sunt
  respinse explicit, iar autoritatea de execuție rămâne `false`.
- **Validare:** testele Movement Engine trec `149/149`; regresia completă
  anterioară corecției era `1328/1328`, iar după corecție este `1329/1329`.
  Nu se pornește acum o nouă rulare live.

## ME-196 — Fan-out frontieră calibrat offline pe batch-ul real

- **Dovadă offline:** worker-ul real a validat aceeași frontieră Crypt→Brill,
  cu 10 candidaturi reconstruite din ruta semantică, și a returnat coridorul
  complet `route_index=18`. Timpul a fost aproximativ `3.3 s` cu fan-out 4 și
  `1.5 s` cu fan-out 10, fără input sau acces la procesul WoW.
- **Schimbare:** fan-out-ul bounded este setat la `10`; limita lotului rămâne
  `32`, iar selecția este deterministă în ordinea rutei. Nu se introduc
  coordonate, teleport sau autoritate live.
- **Validare:** Movement Engine `150/150`, full regression `1330/1330`.
  Benchmark-ul nu substituie poarta temporală live; nu se pornește o nouă
  rulare în acest ciclu.

## ME-197 — Holdout live v5 după corecția ferestrei inclusive

- **Dovadă live:** după `EnterWorld` și checkpoint vizual `InWorld`, secvența
  bounded `Crypt -> Brill -> Crypt` a raportat `ARRIVED` pe ambele leg-uri în
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-live-v5.json`.
  Run-urile sunt `bdb4916c-b97d-4779-a91d-8cbcc3a2b62f` și
  `4f0eb7b0-e029-488d-a3ba-c2de7e67997f`, cu `5987`/`6110` frame-uri, zero
  handoff-uri de combat și `execution_authority=false`.
- **Calitate temporală:** outbound are `15` goluri brute, `13` compensate și
  `2` inexplicate (maxim `2.104445 s`); returul are `12` brute, `11`
  compensate și `1` inexplicat (maxim `0.384832 s`). Ambele artifacts sunt
  `passed=false` pentru `control_observation_gap`, deși destinațiile sunt
  atinse.
- **Siguranță:** ShadowPlay a fost toggled numai pentru holdout și runtime-ul
  a fost disarmat imediat după checkpoint-ul final. Nu se declară mișcare
  humanlike certificată și nu se pornește alt live holdout; următorul pas este
  analiza offline a ferestrelor frontieră/pivot și a fallback-ului de retur.

## ME-198 — Păstrarea future-ului la replanul parțial (offline)

- **Cauză confirmată:** în trace-ul v5, ramura de replan parțial anula future-ul
  de bypass al aceleiași frontiere înainte de blocul de handoff care trebuia să
  îl reutilizeze. Runner-ul cădea astfel pe `SEMANTIC_STATIC_FRONTIER_BYPASS`
  sincron, chiar după calibrarea worker-ului.
- **Schimbare:** future-ul este păstrat până la verificarea de handoff pentru
  aceeași frontieră și același query; rezultatele stale/incomplete rămân
  respinse fail-closed, iar fallback-ul sincron rămâne ultima opțiune validată.
- **Validare:** Movement Engine `151/151`, full regression `1331/1331`,
  `py_compile` și `git diff --check` trec. Nu s-a pornit live după amendament.

## ME-199 — Invalidează future-ul când replanul schimbă frontiera (offline)

- **Schimbare:** replanul care mută stopul la o frontieră diferită anulează
  future-ul pregătit pentru contextul vechi; pentru aceeași frontieră, future-ul
  rămâne disponibil pentru verificarea de handoff. Astfel nu există reutilizare
  accidentală între contexte topologice diferite.
- **Validare:** Movement Engine `151/151`, full regression `1331/1331` și
  `py_compile` trec. Nu s-a pornit live după această ajustare.

## ME-200 — Benchmark offline hairpin după corecțiile frontieră

- **Dovadă offline:** `adaptive-steering-benchmark-20260901-me199-1000.json`
  a completat `6.000/6.000` curse (1.000 pentru fiecare din șase scenarii),
  fără coliziuni sau curse incomplete. Scenariul `narrow_outdoor_hairpin`
  raportează `quality_pass_rate=1.0`, MPPI activ în `0.484` din observații,
  cross-track maxim `1.448` yards și pivot maxim `0.278`.
- **Limită:** benchmark-ul rămâne offline și nu certifică gap-urile temporale
  ale holdout-ului live v5.

## ME-201 — Confirmare read-only a arhivei TBC Anniversary furnizate

- **Audit arhivă:** `D:\Downloads\Zygor Release 8.1.37070.rar` reproduce exact
  varianta `ZygorGuidesViewerClassicTBCAnniv`, Interface `20506`, Version `8.1`,
  cu SHA-256
  `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`,
  `868` fișiere și `83` directoare. Verificarea a folosit doar un director
  temporar; arhiva nu a fost instalată sau copiată în repo.
- **Acoperire:** cele șase fișiere non-Trial au `14.748` pași și `11.687`
  candidaturi de coordonate; `NPCData.lua` are `35` secțiuni și `3.255` rânduri,
  inclusiv `286` class trainers și `287` profession trainers.
- **Transformare:** catalogul 2D client transformă `11.686/11.687` coordonate;
  singurul nerezolvat este map ID `564` (`BlackTemple`), fără row compatibil.
  Toate cele trei artefacte existente trec `--check`; `execution_authority`
  rămâne `false` și nu se pornește live nou.

## ME-202 — Regresie offline pentru invalidarea future-ului stale

- **Regresie:** testul verifică explicit că un replan cu frontieră diferită
  anulează future-ul pregătit din topologia veche; rezultatul nu poate ajunge
  în fallback sau în handoff.
- **Validare:** Movement Engine `152/152`, full regression `1332/1332`,
  `py_compile` și `git diff --check` verzi. Trace-ul v5 rămâne neschimbat și
  nu s-a pornit live nou.

## ME-203 — Readiness de profil legat de identitatea hărții (offline)

- **Observat:** registry-ul putea considera un artefact „ready” doar pentru că
  fișierul exista; asta lăsa posibilitatea ca un fișier valid al altei hărți să
  fie afișat ca dovadă pentru profilul selectat.
- **Schimbare:** `inspect_world_map_profile` verifică acum record type/schema,
  `execution_authority=false` și perechea exactă `map_id`/`internal_name` în
  runtime profile, semantic catalog, structure index și access graph. Profilul
  partajat este permis numai când lista lui declară explicit harta cerută.
- **Validare:** testele registry + audit + Movement Engine trec `156/156`;
  auditul celor `83` identități trece `--check`, cu `1` profil autonom-ready.
  Nu s-a pornit live.

## ME-204 — Extindere advisory a scanării structurale Expansion01 (offline)

- **Scanare:** workerul local verificat `pa_nav_probe-v35` a procesat încă `500`
  probe; raportul recalculat are `8.000/47.170` seed-uri completate, `160`
  acceptate, `7.040` structură neconfirmată, `647` fără nav polygon, `153`
  awareness static incompletă, `0` probe errors și `39.170` rămase.
- **Agregare:** graful partial-v8 conține `92` structuri distincte observate,
  `160` observații, `1.267` boundary chains și `501` access openings; starea
  este `PARTIAL_OBSERVED_COMPONENTS`.
- **Limită:** `dynamic_entity_knowledge=NONE` și `execution_authority=false`;
  rezultatul rămâne advisory, nu intră în registry/readiness și nu s-a pornit
  niciun test live.

## ME-205 — Prioritate redusă pentru worker-ele native read-only (offline)

- **Schimbare:** `ClientAssetNavmeshQuery` și serviciul persistent de awareness
  pornesc worker-ele native cu `CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS`
  pe Windows. Flag-ul este capability-detected și devine `0` pe host-uri unde
  nu există; nu schimbă protocolul, izolarea sau autoritatea de execuție.
- **Motivație:** preplanul de frontieră poate face simultan cold tile loads;
  prioritatea normală putea concura cu capture/control și produce ferestre
  temporale inexplicate. Worker-ele rămân read-only și fără actuator.
- **Validare:** testele Movement Engine + runtime `239/239`, suita completă
  `1336/1336`; validarea semantică offline v49 este `PASS` (`4×ARRIVE`, deal
  `RESET_REQUIRED`). Nu s-a relaxat evaluatorul temporal și nu s-a pornit live.

## ME-206 — Preflight live păstrat fail-closed după corecția offline

- **Observat:** gate-ul semantic v49 este `PASS`, dar
  `live_authority_enabled=false`; clientul WoW LAB PID `53092` și listener-ele
  loopback există, însă autorizația/receipt-ul de sesiune sunt expirate și
  `runtime_arm_present=false`.
- **Decizie:** nu s-a regenerat autorizația, nu s-a armat runtime-ul și nu s-a
  trimis input. Un client deschis nu este tratat ca sesiune live autorizată.

## ME-207 — Reînnoire controlată, blocare vizuală și dezarmare (live gate)

- **Preflight:** autorizația LAB fix-UI, receipt-ul de identitate și
  runtime-arm-ul au fost reînnoite controlat pentru clientul existent PID
  `53092`, fără activarea combatului și fără schimbarea `execution_authority`
  pentru traseu.
- **Blocaj:** pose-ul read-only a respins sesiunea cu
  `ClientVisibleStateError: DISCONNECTED_DIALOG` la confidence `0.532`;
  starea `InWorld`/Crypt nu a fost demonstrată.
- **Decizie:** nu s-a trimis input și nu s-a executat holdout-ul. Runtime-arm-ul
  a fost dezarmat imediat (`runtime_arm_present=false`); WoW și Hermes au rămas
  pornite și neatinse.

## ME-208 — Fast-path pentru primul bypass de frontieră (offline)

- **Observat:** în trace-ul v5, prima celulă validă din ordinea semantică era
  găsită, dar contextul `ThreadPoolExecutor` aștepta și coada de probe
  speculative înainte de return; acest lucru putea produce un gol temporal la
  frontieră chiar dacă rezultatul era deja disponibil.
- **Schimbare:** prima candidatură este verificată singură și returnată imediat
  când trece query-ul navmesh. Fan-out-ul bounded și ordinea deterministă se
  păstrează pentru cazul de eșec al primei probe; worker-ele rămân read-only și
  teardown-ul este explicit.
- **Validare:** testele relevante `245/245`, full regression `1337/1337`,
  validarea semantică offline v50 `PASS` (`4×ARRIVE`, deal
  `RESET_REQUIRED`). Quality gate-ul nu a fost slăbit și nu s-a pornit live.

## ME-209 — Warmup bounded al workerelor înainte de pose clock (offline)

- **Observat:** trace-ul v6b a păstrat două gap-uri outbound inexplicate,
  aproximativ `1.159 s`, în jurul primelor preplanări. `ProcessPoolExecutor`
  pornea lazy la primul `submit`, concurând cu bucla de captură/control.
- **Schimbare:** runner-ul execută un no-op picklable înainte de
  `pose_source.open()` pentru toate cele cinci procese read-only (2 preplan,
  2 advisory, 1 frontier). Warmup-ul are timeout bounded și fail-closed;
  nu are acces la client sau actuator.
- **Validare:** Movement Engine + runtime `247/247`, full regression
  `1339/1339`, compileall verde, semantic v51 `PASS` (`4×ARRIVE`, deal
  `RESET_REQUIRED`). Nu s-a pornit live după această schimbare.

## ME-210 — Holdout live v6b: sosire funcțională, calitate temporală incompletă

- **Rezultat:** secvența identifier-only `Crypt -> Brill -> Crypt` a ajuns la
  ambele destinații în
  `data/runtime/navigation-f3b/journey-combat-supervisor-live-priority-v6b-20260901.json`,
  cu zero handoff-uri de combat și `execution_authority=false`.
- **Quality:** outbound `6591` frame-uri, `5` gap-uri brute, `3` compensate
  prin mișcare continuă și `2` inexplicate (maxim `1.551341 s`), deci
  `passed=false`; retur `6285` frame-uri, un gap compensat de `0.300153 s`,
  `passed=true`.
- **Decizie:** runtime arm-ul a fost dezarmat imediat. Sosirea este dovadă
  funcțională, nu certificare humanlike; combatul rămâne blocat până când
  outbound trece poarta temporală. Graful structural opțional nu a fost folosit
  deoarece era legat de worker v34, nu de v35.

## ME-211 — Holdout live v7: retur oprit la plecarea din Brill

- **Rezultat:** outbound-ul din secvența bounded `Crypt -> Brill -> Crypt` a
  ajuns la Brill, dar returul s-a oprit cu
  `CORRIDOR_RECENTER_REPLAN_BUDGET_EXHAUSTED`.
- **Cauză observată:** primele pose-uri de la handoff nu au avut facing vizibil;
  controllerul a emis stride-ul natural `CALIBRATE_HEADING`, iar deplasarea a
  pornit în direcția greșită. Quality outbound a rămas `passed=false` (un gap
  inexplicat, maxim `1.266432 s`); returul nu a atins destinația.
- **Limită:** nu s-a folosit combat, nu s-a repetat testul live, iar runtime-ul
  a fost dezarmat imediat (`runtime_arm_present=false`).

## ME-212 — Heading inițial: reacquisition read-only fail-closed (offline)

- **Schimbare:** înainte de primul input și după planificarea rutei, runner-ul
  cere până la patru observații fresh fără controale ținute, acceptând numai
  facing HUD exact sau fallback minimap cu provenance. Lipsa persistentă a
  heading-ului produce `refusing natural calibration stride` și zero input.
- **Validare:** teste focale `249/249`, suita completă `1341/1341`, compileall și
  `git diff --check` verzi. Corecția nu a fost încă rulată live.

## ME-213 — Materializarea frontier result înaintea handoff-ului (offline)

- **Observat:** gap-ul outbound v7 de `1079.78 ms` apărea când un rezultat
  frontieră deja finalizat era consumat în aceeași iterație cu handoff-ul.
- **Schimbare:** runner-ul materializează o singură dată `Future.result()` când
  future-ul este `done()` și coridorul curent încă rulează; handoff-ul folosește
  rezultatul deja materializat. Nu se schimbă ordinea semantică, candidații sau
  autoritatea workerului.
- **Validare:** teste focale `250/250`, suita completă `1342/1342`, semantic v52
  `PASS` (`4×ARRIVE`, deal `RESET_REQUIRED`). Nu s-a pornit live după schimbare.

## ME-214 — Reconfirmare read-only a pachetului Anniversary și a Control Center-ului

- **Confirmat:** `D:\Downloads\Zygor Release 8.1.37070.rar` este pachetul TBC
  Anniversary (`ZygorGuidesViewerClassicTBCAnniv`, `Interface: 20506`, versiunea
  `8.1`), cu SHA-256
  `D8D416AD95F9071FD8578DF218A70235C377EA8B350F81CA2EA6F5417A65D2D3`.
  Reauditurile `--check` păstrează doar hash-uri/count-uri și confirmă
  `14.748` pași, `11.687` coordonate candidate și transformare client-side
  `11.686/11.687`; cazul nerezolvat este `map_id=564` (BlackTemple).
- **Control Center:** secvențele identifier-only sunt bounded la `2–16` ID-uri,
  `1–32` repetări și pot închide bucla prin `close_loop`; supervisor-ul validează
  catalogul înaintea oricărui child, iar fiecare leg este replănuit din observația
  proaspătă. Registry-ul expune `83` hărți, însă doar Azeroth este
  `autonomous_ready`; restul se opresc fail-closed fără artefacte semantic/access.
  NPCData este knowledge static read-only (`3.255` rânduri), iar awareness
  dinamic rămâne viewport/nameplate screen-space, fără poziții 3D inventate.
- **Limită:** arhiva nu este instalată/copiată în repo, Lua nu este evaluat,
  WoW/Hermes nu sunt atinse și nu s-a pornit niciun test live; runtime-ul rămâne
  `OBSERVE_ONLY`.

## ME-215 — Aliniere worker–graph și regresie offline completă

- **Schimbare:** validatorul semantic Azeroth v3 a fost rerulat cu workerul
  `pa_nav_probe-v34`, identic cu workerul legat în access graph. Gate-ul scris
  este `v53-worker-v34`, cu `live_authority_enabled=false`.
- **Dovadă:** `4×ARRIVE` pentru Crypt/Deathknell/Brill, fixture deal
  `RESET_REQUIRED` (`partial_local_navmesh_corridor`), iar serviciul read-only
  structure awareness a raportat `READY` (`96.024` structuri, `4.754` openings).
  Regresia completă este `1342/1342`; compileall și diff checks sunt verzi.
- **Limită:** alinierea este exclusiv offline. Autorizația LAB este expirată,
  runtime arm-ul lipsește, iar niciun proces WoW/Hermes nu a fost reîncărcat și
  nu s-a trimis input live.

## ME-216 — Scanări continentale candidate continuate

- **Dovadă:** două loturi read-only de câte `1.000` probe au dus Kalimdor la
  `10.639/40.794` seed-uri (`229` acceptate) și Expansion01 la `9.000/47.170`
  (`176` acceptate), ambele cu `0` erori de worker. Progresul este sigilat în
  rapoartele v2/v3 corespunzătoare.
- **Agregare:** grafurile `kalimdor...partial-v11.json` și
  `expansion01...partial-v9.json` au starea `PARTIAL_OBSERVED_COMPONENTS` și
  sunt legate în registry doar ca dovezi read-only pentru structure awareness;
  nu sunt candidate executabile.
- **Limită:** nu există încă coverage completă semantic/access pentru aceste
  hărți; nu au devenit `autonomous_ready`, nu s-a schimbat gate-ul și nu s-a
  pornit live.

## ME-217 — Legare registry pentru awareness continental read-only

- **Schimbare:** registry-ul map-by-map referă indexul și graful partial pentru
  Kalimdor și Expansion01. Control Center le poate încărca pentru nearby WMO/
  BVH awareness, fără a transforma probele în rută executabilă.
- **Gate:** ambele profile au acum `structure_index_ready=true` și
  `structure_access_graph_ready=true`, dar `semantic_catalog_ready=false`,
  deci rămân `OBSERVE_ONLY`; auditul confirmă `1/83` hărți
  `autonomous_ready`.
- **Regresie:** testele registry/UI/scan trec `46/46`; ADR-0074 descrie
  consecințele și rollback-ul. Niciun live input nu a fost pornit.

## ME-218 — Worker identity pentru structure-awareness

- **Cauză:** grafurile continentale candidate sunt legate de worker v35, în
  timp ce graful Azeroth folosește v34; workerul global al UI-ului nu putea
  încărca ambele identități corect.
- **Corecție:** UI-ul selectează numai v34/v35 din allowlist, comparând hash-ul
  grafului. Hash lipsă, necunoscut sau fișier absent oprește serviciul fără
  input și fără fallback arbitrar.
- **Validare:** regresie completă `1343/1343`, compileall verde; semantic gate,
  runtime arm și live rămân neschimbate (`false`/absent).

## ME-219 — Lot Kalimdor v12 și stare curentă a acoperirii candidate

- **Dovadă:** al doilea lot bounded read-only (`1.000` probe, `jobs=4`, worker
  v35) a dus Kalimdor la `11.639/40.794` seed-uri completate, `250` observații
  acceptate, `401` structuri complete, `29.155` seed-uri rămase și `0` erori.
  Raportul este `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v3.json`.
- **Agregare:** graful
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v12.json`
  are `250` observații, `1.204` openings și `2.269` boundary chains, cu
  `PARTIAL_OBSERVED_COMPONENTS`; registry-ul a fost mutat la acest hash doar
  pentru awareness structural read-only.
- **Limită:** semantic catalogul Kalimdor lipsește, auditul rămâne la `1/83`
  hărți `autonomous_ready`, iar runtime arm și input authority sunt absente.
  Nu s-a pornit test live și nu s-a atins clientul WoW/Hermes.

## ME-227 — Extindere candidate Kalimdor/Expansion01 și graph-uri read-only (offline)

- **Dovadă:** loturi bounded de câte `1.000` probe cu worker v35 au dus
  Kalimdor la `13.639/40.794` seed-uri (`313` acceptate, `0` erori) și
  Expansion01 la `12.000/47.170` (`247` acceptate, `0` erori).
- **Agregare:** `kalimdor-candidate-structure-access-partial-v14.json` are
  `1.373` openings și `2.632` boundary chains; `expansion01-candidate-structure-access-partial-v12.json`
  are `994` openings și `2.289` boundary chains. Ambele sunt
  `PARTIAL_OBSERVED_COMPONENTS` și rămân evidence read-only.
- **Limită:** fără catalog semantic, cele două continente rămân
  `OBSERVE_ONLY`; auditul rămâne `1/83 autonomous_ready`. Nu s-a reînnoit
  autorizația, nu există runtime arm și nu s-a pornit live sau nu s-a atins
  WoW/Hermes.

## ME-222 — Lot Expansion01 v11 și reconfirmare RAR Anniversary (offline)

- **Dovadă:** lot bounded read-only (`1.000` probe, `jobs=4`, worker v35) a
  dus Expansion01 la `11.000/47.170` seed-uri, `217` observații acceptate,
  `298` awareness incomplete și `0` erori; rămân `36.170` seed-uri.
- **Agregare:** graful
  `data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v11.json`
  are `217` observații, `843` openings și `1.958` boundary chains,
  `PARTIAL_OBSERVED_COMPONENTS`, hash
  `b32eb73314950bf597a1018140d5adb3af7bc22e94a7fcd654719f46f99973dd`.
  Registry-ul îl folosește numai pentru awareness structural read-only.
- **Limită:** Expansion01 rămâne `OBSERVE_ONLY` fără catalog semantic; nu s-a
  pornit live și nu s-a atins clientul WoW/Hermes. RAR-ul local a trecut testul
  7-Zip read-only (RAR5, `868` fișiere, `83` directoare, hash identic).

## ME-223 — Indexuri structurale pentru Razorfen/Karazhan și validare v54

- **Dovadă:** proof WorldPack v3 a fost indexat read-only pentru
  `RazorfenKraulInstance` (`395` structuri, `6` tile-uri) și `Karazahn`
  (`5.449` structuri, `9` tile-uri); indexurile sunt identity-bound și au fost
  adăugate în registry doar ca awareness static.
- **Validare:** semantic journey v54 cu worker v34 este `PASS` pentru cele patru
  cazuri Azeroth (inclusiv Crypt→Brill și retur); fixture-ul de deal rămâne
  `RESET_REQUIRED` fail-closed. Testele registry/UI dedicate trec `35/35`.
- **Limită:** ambele hărți noi nu au încă access graph sau catalog semantic, deci
  rămân `OBSERVE_ONLY`; nu s-a pornit live, nu s-a modificat WoW/Hermes.

## ME-224 — Regresie completă după indexurile multi-map

- **Validare:** suita offline completă a trecut `1343/1343` în `119.63s`, cu
  `compileall` și `git diff --check` verzi.
- **Concluzie:** indexurile Razorfen/Karazhan și schimbarea de registry nu au
  modificat semantic gate-ul sau input authority; live-ul nu a fost pornit.

## ME-225 — Scan interior Karazhan și frontieră Razorfen

- **Karazhan:** scanare completă `1.662/1.662`, `65` observații acceptate,
  `0` erori, `124` seed-uri fără poligon; graful v2 are `116` openings și
  `315` boundary chains și rămâne `PARTIAL_OBSERVED_COMPONENTS`.
- **Razorfen:** scanare completă `147/147`, `0` erori, dar `0` WMO confirmate
  (`18` seed-uri fără poligon). Nu s-a creat graph, ca frontieră neacoperită să
  rămână fail-closed.
- **Limită:** lipsesc cataloagele semantice, deci ambele hărți rămân
  `OBSERVE_ONLY`; fără live input sau modificări WoW/Hermes.

## ME-226 — Regresie completă după graph-ul Karazhan v2

- **Validare:** suita offline completă a trecut `1343/1343` în `118.94s`, cu
  `compileall` și `git diff --check` curate.
- **Concluzie:** legarea graph-ului Karazhan nu a deschis autonomia sau input
  authority; live-ul nu a fost pornit.

## ME-220 — Lot Expansion01 v10 și stare curentă a acoperirii candidate

- **Dovadă:** lotul bounded read-only (`1.000` probe, `jobs=4`, worker v35)
  a dus Expansion01 la `10.000/47.170` seed-uri completate, `196` observații
  acceptate, `352` structuri complete, `37.170` seed-uri rămase și `0` erori.
  Raportul este `data/runtime/navigation-f3b/expansion01-candidate-structure-access-scan-progress-v4.json`.
- **Agregare:** graful
  `data/runtime/navigation-f3b/expansion01-candidate-structure-access-partial-v10.json`
  are `196` observații, `728` openings și `1.764` boundary chains, cu
  `PARTIAL_OBSERVED_COMPONENTS`; registry-ul a fost mutat la v10 numai pentru
  awareness structural read-only.
- **Limită:** semantic catalogul Expansion01 lipsește, auditul rămâne la
  `1/83` hărți `autonomous_ready`, iar runtime arm și input authority sunt
  absente. Nu s-a pornit test live și nu s-a atins clientul WoW/Hermes.

## ME-221 — Lot Kalimdor v13 și stare curentă a acoperirii candidate

- **Dovadă:** lotul bounded read-only (`1.000` probe, `jobs=4`, worker v35)
  a dus Kalimdor la `12.639/40.794` seed-uri completate, `290` observații
  acceptate, `437` structuri complete, `28.155` seed-uri rămase și `0` erori.
  Raportul este `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-scan-progress-v4.json`.
- **Agregare:** graful
  `data/runtime/navigation-f3b/kalimdor-candidate-structure-access-partial-v13.json`
  are `290` observații, `1.285` openings și `2.466` boundary chains, cu
  `PARTIAL_OBSERVED_COMPONENTS`; registry-ul a fost mutat la v13 numai pentru
  awareness structural read-only.
- **Limită:** semantic catalogul Kalimdor lipsește, auditul rămâne la `1/83`
  hărți `autonomous_ready`, iar runtime arm și input authority sunt absente.
  Nu s-a pornit test live și nu s-a atins clientul WoW/Hermes.

## ME-228 — Gate semantic v55 după extinderea multi-map (offline)

- **Validare:** validatorul semantic cu worker v34 și WorldPack Azeroth pinned
  a raportat `PASS`: patru cazuri (`Crypt→Brill`, `Deathknell→Brill`,
  `Brill→Deathknell`, `Brill→South Road Bend`) sunt `ARRIVE`; fixture-ul de
  deal rămâne `RESET_REQUIRED`/`partial_local_navmesh_corridor`.
- **Artefact:** `data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v55-worker-v34.json`.
- **Limită:** gate-ul live și autoritatea de input nu s-au schimbat; nu există
  runtime arm și nu s-a pornit live.

## ME-229 — Comparație offline pentru mers fără A/D

- **Dovadă:** varianta camera-only, cu `MOVE_FORWARD` și RMB dar fără
  `STRAFE_LEFT`/`STRAFE_RIGHT`, a fost comparată cu controllerul predictiv
  actual pe șase scenarii sintetice. Ambele au trecut `1.000/1.000` probe pe
  fiecare scenariu, cu zero coliziuni.
- **Observație:** controllerul actual a emis `1.695` cadre de strafe în cele
  `6.000` probe; varianta camera-only a emis `0`. Diferența nu a redus rata de
  trecere în acest model kinematic.
- **Limită:** nu este test WorldPack Crypt→Brill și nu este test live. Profilul
  de producție nu a fost schimbat; orice test live camera-only cere autorizație
  bounded nouă și runtime arm.

## ME-230 — Test live bounded camera-only oprit în siguranță

- **Dovadă:** un singur test local bounded, cu Predator în Brill, a pornit cu
  controllerul camera-only (`W` + RMB, fără A/D), autorizație reînnoită și
  runtime arm. Rezultatul este
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v39-camera-only.json`.
- **Rezultat:** `STOPPED_CHILD_ERROR` înainte de prima destinație; nu există
  sosire și nu există handoff de combat.
- **Cauză:** clientul a confirmat obstacolul
  `obstacle:60812e3b1d58cfc5`, dar nu exista ocol validat. Runnerul a oprit
  traseul; nu a forțat trecerea și nu a folosit server truth.
- **Video:** ShadowPlay a creat un clip local de `180` secunde, aproximativ
  `1,069,027,610` bytes, în Videos-ul operatorului; clipul nu este în repo.
- **Limită:** testul arată că fail-closed funcționează. Nu arată că ruta
  Crypt→Brill este rezolvată. Predator și procesele WoW/Hermes au rămas pornite;
  nu se pornește alt live fără un ocol verificat pentru obstacol.

## ME-231 — Ocolul mic nu mai este respins prea devreme

- **Cauză:** ocolul calculat din raza obstacolului avea o curbă client-navmesh
  validă, dar depășea cu puțin limita fixă veche de lungime.
- **Schimbare:** limita primește o margine mică, derivată din raza observată și
  plafonată. Se aplică doar verificărilor de clearance; nu se adaugă coordonate
  sau waypoints hardcodate.
- **Test:** test nou pentru arc limitat; suita completă a trecut `1344/1344`.

## ME-232 — Gate semantic v56 după repararea ocolului (offline)

- **Dovadă:** `data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v56-obstacle-prior.json`
  este `PASS` pentru cele patru drumuri reale și păstrează dealul ca
  `RESET_REQUIRED`.
- **Dovadă locală:** la poziția din Brill folosită în probe,
  `obstacle:60812e3b1d58cfc5` produce `CONFIRMED_CLEARANCE_PRIOR_APPLIED` și
  toate cele trei picioare ale ocolului sunt validate de navmesh.
- **Limită:** este doar verificare offline. Un nou test live cere autorizație
  bounded și runtime arm proaspete.

## ME-233 — Live v40 s-a oprit la primul obstacol local din Brill

- **Dovadă:** holdout-ul bounded camera-only
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v40-camera-only.json`
  a pornit din Brill cu `W` + RMB, fără A/D, și nu a ajuns la criptă.
- **Rezultat:** copilul navmesh este `STUCK_REPLAN_REQUIRED`, cu `463` cadre,
  `4` recuperări și `0` obiective semantice completate. Oprirea este
  `STOPPED_FAIL_CLOSED`; nu a existat handoff de combat și
  `execution_authority=false`.
- **Cauză observată:** coliziuni repetate în aceeași zonă de lângă lampă,
  grajd și fermă. Ocolurile validate local au fost încercate, dar traseul a
  revenit în aceeași concavitate. Structurile corespund geometriei clientului
  din WorldPack; nu s-a folosit server truth.
- **Camera:** filmarea locală arată camera ridicată după blocare. Trace-ul nu
  are input vertical (`mouse_delta_y=0`, `mouse_velocity_y=0`). Concluzia
  probabilă este Smart Pivot-ul clientului (`cameraPivot=1`) la contactul cu
  geometria; este o inferență, nu o citire internă a clientului. Camera a fost
  readusă separat la vederea salvată.
- **Stare:** problema de oprire și protecția camerei rămân deschise pentru
  lucru offline; nu se pornește alt live până la o nouă verificare locală.

## ME-234 — Camera de exterior nu mai folosește Smart Pivot

- **Schimbare:** profilul de cameră pentru exterior setează `cameraPivot=0`.
  Astfel, coliziunea cu o lampă, căruță sau clădire nu mai poate împinge
  vederea spre cer. Pentru un WMO verificat, profilul poate seta în continuare
  `cameraPivot=1`.
- **Regresie:** testele dedicate camerei sunt `36/36`, iar suita completă după
  schimbare este `1345/1345`.
- **Limită:** cauza geometrică a opririi v40 nu este încă rezolvată. Camera a
  fost protejată offline; nu s-a pornit un nou live.

## ME-235 — Coridorul de început este reîmprospătat după alegerea podelei

- **Cauză:** scanarea statică inițială folosea `z=100`, iar structura stabilă de
  lângă ieșirea din Brill era la podeaua clientului, aproximativ `z=34`.
- **Schimbare:** după alegerea podelei, runnerul reface orizontul static pentru
  primele obiective și reconstruiește query-ul cu structurile confirmate din
  WorldPack. Nu există coordonate sau waypoints hardcodate.
- **Dovadă:** în cazul exact Brill→Crypt s-a adăugat un singur blocator stabil;
  primul coridor are `41` puncte și `complete=true`. Gate-ul semantic v57 este
  `PASS` pentru cele patru drumuri reale; dealul rămâne `RESET_REQUIRED`.
- **Artefact:** `data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v57-layer-refresh.json`.
- **Test:** suita de până la acest patch a trecut `1346/1346`.

## ME-236 — Camera home nu mai reactivează Smart Pivot afară

- **Cauză:** recuperarea prin `SetView(3)` seta din nou `cameraPivot=1`, chiar
  după profilul exterior care îl oprise.
- **Schimbare:** recuperarea de exterior transmite `cameraPivot=0`; WMO poate
  cere explicit `cameraPivot=1`.
- **Dovadă:** după recuperare, captura
  `data/runtime/operator/20260901T120441210Z-manual-checkpoint.png` arată
  Predator viu și cu camera pe drum.
- **Test:** testele țintite au trecut `200/200`, iar suita completă a trecut
  `1348/1348`. Nu s-a pornit rută live nouă.

## ME-237 — Smart Pivot ridică și camera din Crypt

- **Dovadă:** filmarea locală a holdout-ului v42 este
  `C:\\Users\\LabUser\\Videos\\NVIDIA\\Wow.exe\\Wow.exe 2026.09.01 - 15.15.20.91.mp4`.
  Vederea pornește normal, apoi se înclină spre tavan când Predator atinge
  geometria interioară din Crypt.
- **Cauză probabilă confirmată vizual:** `cameraPivot=1` din client poate
  împinge camera în sus chiar și într-un WMO; trace-ul nu trimite input vertical.
- **Schimbare:** toate profilurile de navigare setează `cameraPivot=0`.
  Înclinarea și distanța rămân cele din vederea salvată a operatorului.
  Parametrul explicit pentru `cameraPivot=1` este păstrat doar pentru
  diagnostic și nu este folosit de runnerul autonom.
- **Test:** testele țintite sunt `200/200`. Nu s-a pornit un alt live pentru
  această schimbare.
- **Limită:** v42 rămâne blocat la ieșirea din podeaua interioară a Crypt-ului;
  protecția camerei nu este dovadă că traseul este rezolvat.

## ME-238 — Aliniere staționară la începutul spațiilor înguste (offline)

- **Dovadă:** în v42, `continuous_trajectory_v1` a intrat direct cu W pe
  coridorul interior. În rularea istorică reușită, controllerul a făcut mai
  întâi un pivot pe loc.
- **Schimbare:** pentru coridoare cu awareness WMO/închis sau cu ocol de
  doodad, prima aliniere ține doar RMB până când unghiul față de tangenta
  coridorului este mic. Este o regulă bazată pe geometria clientului, fără
  coordonate sau locații speciale.
- **Test:** scenariul sintetic verifică `PIVOT` fără W, apoi `FOLLOW` după
  aliniere; testele țintite sunt `169/169`, iar suita completă este
  `1349/1349`.
- **Limită:** este verificare offline. Ieșirea din Crypt nu este încă
  certificată live și nu s-a pornit alt test live.

## ME-239 — Live v43: regula de aliniere s-a reluat după primul pivot

- **Dovadă:** holdout-ul bounded `Crypt -> Brill -> Crypt` a ajuns la Crypt,
  apoi legătura Crypt→Brill s-a oprit `STUCK_REPLAN_REQUIRED` după `624`
  cadre, la `[1672.7381, 1691.1194]`. Fișierul sumar este
  `data/runtime/navigation-f3b/holdout-crypt-brill-crypt-20260901-v43-precision-start.json`.
- **Siguranță:** `combat_handoffs_used=0`, protecția de combat a fost OFF,
  Predator nu a murit, iar `execution_authority=false` a rămas în trace.
- **Cauză:** prima aliniere a folosit `PIVOT` fără W, dar zgomotul de heading
  și progresul mic au făcut controllerul să aplice din nou aceeași regulă;
  pivotul a rămas activ și recuperările locale s-au epuizat.
- **Schimbare offline:** controllerul marchează alinierea ca terminată după
  prima trecere în fereastra de reluare a unghiului. Un zgomot ulterior nu mai
  reia pivotul pe același coridor. Testul sintetic acoperă exact acest caz.
- **Test:** suita completă a trecut `1349/1349`; `compileall` trece.
- **Video:** fișierul ShadowPlay al acestei probe are `0` bytes; nu este
  folosit ca dovadă.
- **Limită:** schimbarea nu a fost încă validată live. Nu pornesc un al doilea
  live până când analiza offline a recenterului nu este închisă.

## ME-240 — Gate offline complet după fixul de aliniere

- **Monte Carlo:** raportul
  `data/runtime/navigation-f3b/steering-monte-carlo-20260901-v44-precision-gate.json`
  are `1.000/1.000` probe de calitate pentru fiecare din cele șase scenarii:
  curbe înguste, S-gate, hairpin, pod și ocol de doodad. Nu au fost coliziuni
  sau eșecuri.
- **WorldPack/navmesh:**
  `data/runtime/navigation-f3b/semantic-road-journey-validation-20260901-v58-precision-gate.json`
  este `PASS`; cele patru drumuri reale ajung la destinație în validator, iar
  fixture-ul de deal rămâne `RESET_REQUIRED`.
- **Limită:** acestea sunt probe offline. Patch-ul pentru aliniere nu este
  încă certificat în client; nu pornesc încă un al doilea live.

## ME-241 — Registrul mapelor este complet la nivel de identitate

- **Dovadă:** auditul
  `data/runtime/navigation-f3b/world-map-registry-audit-20260901-v44.json`
  vede `83/83` map IDs din buildul TBC 2.4.3.8606 și le oferă Control Center-
  ului ca opțiuni read-only.
- **Limită importantă:** numai Azeroth este `autonomous_ready` (`1/83`). Fără
  WorldPack/navmesh și semantic catalog validate, celelalte hărți nu primesc
  rutare autonomă inventată; rămân `OBSERVE_ONLY`.
- **Test:** verificările pentru Control Center, registry, awareness și datele
  dinamice au trecut `45/45`.

## ME-452 — Un obstacol învățat fals tăia coridorul valid al Crypt-ului

- **Simptom:** WorldPack-ul părea orb la ieșire, iar ruta locală avea numai un
  poligon și două puncte, deși geometria clientului conține întregul pasaj.
- **Cauză:** o excludere Detour memorată dintr-o coliziune veche, chiar lângă
  spawn, era injectată înainte ca traversarea manuală `COMPLETE` să poată
  contrazice anvelopa. Codul Luna contrazicea doar obstacole de clearance, nu și
  excluderile poligonale confirmate.
- **Soluție standalone:** excluderile poligonale învățate sunt aplicate după
  verificarea dovezii de traversabilitate. O traversare completă poate elimina
  doar obstacolul pe care îl traversează; punctele operatorului rămân
  neexecutabile și destinația autonomă nu se schimbă.
- **Regresii secundare reparate:** noile surse de heading
  `DISPLACEMENT_VISIBLE_*` sunt recunoscute de poarta de prospețime; cerința de
  siluetă este propagată identic în runner și în preflight, fiind implicit doar
  diagnostică.
- **Dovadă:** coridorul live are `50` poligoane/`69` puncte. Lanțul filmat a
  ieșit din Crypt, a continuat `153.86 yd` pe potecă fără recuperări și s-a
  încheiat `ARRIVED` în Deathknell. Rezultatele sunt
  `navmesh-roaming-109fb333-5a13-47cd-a804-0db50831db88.json`,
  `navmesh-roaming-7fb027c0-34c5-47b5-813b-cff6c0dcc784.json` și
  `navmesh-roaming-0a0f7d27-d3e9-484a-afbb-fb8514d3d98b.json`.
- **Test:** `1531 passed in 134.60s`.

## ME-453 — Control Center pierdea poziția când navigatorul stătea

- **Simptom:** harta 2D și săgeata Predatorului păreau înghețate sau dispăreau
  la aproximativ 1,5 secunde după oprirea unei călătorii. Ecranul principal era
  aglomerat cu combat, leveling, recorder, overlay și editor de trasee.
- **Cauză:** harta 2D citea numai snapshot-ul produs de navigator. Fluxul HUD
  persistent era pornit numai împreună cu viewerul 3D și murea când viewerul se
  închidea.
- **Soluție standalone:** un singur proces ascuns publică poziția și facingul
  vizibile la 5 Hz pe toată durata Control Center-ului. Harta 2D și viewerul 3D
  consumă același flux. La mers activ, fluxul reutilizează snapshot-ul
  navigatorului și nu deschide a doua captură. La repaus, publică numai poziția;
  geometria locală veche nu este mutată fals sub noua poziție.
- **UI:** tab-ul implicit este `MovementEngine`, harta ocupă spațiul principal,
  poate rămâne centrată pe Predator și desenează o săgeată albastră de facing.
  Combatul și uneltele operatorului sunt păstrate în `Mai târziu`; nu au fost
  șterse.
- **Siguranță:** modul implicit revine la destinație autonomă. Traseele
  operatorului rămân salvate, dar nu sunt desenate și nu devin input autonom.
- **Test:** parserul fluxului live, respingerea poziției vechi și snapshot-ul
  fără geometrie locală moștenită au teste dedicate.

## ME-454 — Control Center confunda validarea cu autorizarea

- **Simptom:** interfața afișa „regresia semantică a drumului nu a trecut”,
  deși artefactul semantic avea `status=PASS`.
- **Cauză:** aceeași valoare booleană reprezenta atât identitatea și rezultatul
  validatorului, cât și autorizarea live controlată de operator.
- **Soluție:** starea semantică distinge acum `OPEN`, `INVALID` și
  `VALIDATION_PASS_AUTHORITY_DISABLED`. Ultima stare păstrează inputul oprit,
  dar spune adevărul: regresia a trecut și operatorul nu a autorizat live-ul.
- **Dovadă vizuală:** Control Center-ul standalone relansat afișează
  `AUTORIZARE LIVE OPRITĂ` și explicația corectă.
- **Test:** regresia țintită a trecut `233/233`; după sigilarea baseline-ului,
  suita completă a trecut `1552/1552`.

## ME-455 — Ieșirea bună din Cryptă nu era protejată ca baseline

- **Risc:** cele trei trace-uri ME-452 și cele două clipuri aprobate puteau fi
  mutate, înlocuite sau șterse fără ca testele să observe.
- **Soluție:** `crypt-egress-live-baseline-v1.json` fixează rolul, dimensiunea,
  SHA-256 și rezultatele observate pentru toate cele cinci artefacte. Baseline-ul
  nu acordă autoritate de execuție.
- **Adevăr păstrat:** primul segment are o recuperare; aceasta nu este ascunsă
  ca zero. Al doilea segment are zero recuperări, iar al treilea este `ARRIVED`.
- **Promovare:** o versiune viitoare cere minimum zece ieșiri filmate, fără
  blocaj, fără regresie față de referință și cu review explicit al operatorului.
- **Verifier:** `scripts/verify_movement_live_baseline.py` a verificat cinci
  artefacte și `76.850.561` bytes, cu `passed=true` și zero eșecuri.

## ME-456 — Poziția staționară putea fi doar privită, nu certificată

- **Problemă:** harta live respingea mostrele vechi, dar nu exista un artefact
  separat care să dovedească pe mai multe cadre că Predatorul stă în același
  punct și că facingul corpului provine din canalul exact al HUD-ului.
- **Soluție:** parserul protocolului live este acum comun între Control Center
  și `validate_stationary_live_pose.py`. Validatorul cere minimum `15` secvențe
  distincte, minimum `2` secunde, goluri sub `0,60 s`, deplasare sub `0,10 yd`
  și jitter de facing sub `0,05 rad`. Orice facing lipsă sau neexact este
  respins; validatorul nu trimite input și nu acordă autoritate de execuție.
- **Probă fail-closed:** cu WoW la ecranul `Disconnected from server`, fișierul
  vechi din august a produs `0` mostre acceptate și `passed=false`; nu a fost
  afișată o poziție inventată.
- **Test:** testele țintite au trecut `237/237`; suita completă după schimbare
  a trecut `1556/1556`.

## ME-457 — Probele live din Cryptă nu aveau un registru strict de promovare

- **Risc:** clipurile, rezultatele navigatorului și validarea poziției puteau fi
  numărate separat sau de mai multe ori, fără să dovedească zece ieșiri complete
  și distincte.
- **Soluție:** `crypt-egress-live-trials.json` declară fiecare probă printr-un ID
  unic și fixează trei artefacte: rezultatul navigatorului, filmarea și raportul
  poziției staționare. Fiecare fișier este legat prin dimensiune și SHA-256.
- **Gate:** o probă este validă numai dacă ajunge la destinație, nu se blochează,
  nu regresează față de baseline, păstrează facingul corpului separat de cameră
  și primește review `PASS` de la operator. Promovarea cere minimum `10/10`.
- **UI:** Control Center afișează direct starea baseline-ului și progresul
  probelor; în starea curentă arată `intact`, `0/10` și `promovare oprită`.
- **Dovadă:** verifierul baseline-ului confirmă `5` artefacte și `76.850.561`
  bytes fără erori. Verifierul probelor raportează intenționat
  `minimum_filmed_trials_not_met`, cu `execution_authority=false`.
- **Test:** suita completă după integrarea registrului și a stării din UI a
  trecut `1559/1559` în `131,40 s`.

## ME-458 — Certificarea staționară nu era accesibilă din Control Center

- **Problemă:** validatorul exista numai ca script, deci operatorul nu putea
  porni și vedea proba de bază din aceeași interfață în care urmărește harta.
- **Soluție:** tab-ul principal MovementEngine are acum butonul
  `Verifică 4 secunde — fără input`. Colectarea rulează separat de UI, citește
  exclusiv fluxul comun de poziție/facing și scrie raportul versionat
  `stationary-pose-latest.json`; nu acordă și nu folosește autoritate de input.
- **Probă fail-closed vizuală:** cu WoW la `Disconnected from server`, UI-ul a
  raportat `EȘEC • telemetrie live insuficientă • 0 mostre`. Datele vechi nu au
  fost acceptate ca poziție curentă.
- **Test:** testele țintite au trecut `240/240`, iar suita completă a trecut
  `1561/1561` în `134,57 s`.

## ME-459 — Control Center nu numea separat sursele poziției și facingului

- **Problemă:** UI-ul afișa coordonata și vechimea fluxului, dar textul
  `facing exact` nu dovedea ce canal a furnizat poziția și ce canal a furnizat
  orientarea corpului.
- **Soluție:** panoul principal afișează acum separat `poziție
  COORDINATE_HUD`, `facing corp COORDINATE_HUD_EXACT` și vechimea în
  milisecunde. Dacă fluxul lipsește, toate câmpurile devin explicit
  indisponibile; o demonstrație operator nu este etichetată drept facing exact.
- **Dovadă vizuală:** cu clientul deconectat, Control Center arată
  `poziție indisponibilă • facing corp indisponibil • vechime —`.
- **Test:** testele țintite au trecut `241/241`, iar suita completă a trecut
  `1562/1562` în `134,17 s`.

## ME-460 — O poziție stabilă din afara Crypt-ului putea trece prima probă

- **Problemă:** validatorul staționar certifica stabilitatea și facingul exact,
  dar nu dovedea că proba fusese făcută în Cryptă, așa cum cere gate-ul live.
- **Soluție generală:** validatorul primește o regiune semantică versionată din
  catalog, nu coordonate introduse în codul MovementEngine. Pentru prima etapă,
  Control Center încarcă `landmark:deathknell-crypt`, centrul și raza din
  `semantic-destinations-tbc243.json`, apoi verifică fiecare mostră în acea
  regiune.
- **Gate:** registrul celor zece ieșiri acceptă raportul staționar numai cu
  locația `landmark:deathknell-crypt`, mapa `Azeroth`, sistemul de coordonate
  `tbc243_client_world_xy` și `within_expected_location=true`.
- **Probă fail-closed:** clientul deconectat produce `0` mostre,
  `within_expected_location=false` și nu poate fi promovat.
- **Test:** testele țintite au trecut `245/245`, iar suita completă a trecut
  `1564/1564` în `134,35 s`.

## ME-461 — Snapshot-ul UI putea confunda corpul cu estimarea camerei

- **Problemă:** `player_facing_rad` era un câmp vechi care putea conține
  headingul estimat al controllerului, în timp ce fluxul HUD publica facingul
  exact al corpului. Control Center nu putea afișa transparent diferența.
- **Soluție:** snapshot-ul MovementLab păstrează acum canale separate:
  `body_facing_rad` cu proveniența exactă, `camera_yaw_estimate_rad` cu sursa
  estimării și `body_camera_yaw_delta_rad`. Lipsa provenienței pentru oricare
  dintre unghiuri invalidează snapshot-ul.
- **UI:** Control Center afișează gradele corpului și ale camerei, plus delta.
  Când navigatorul este oprit, corpul poate rămâne exact, dar camera este
  declarată `indisponibilă`; nu este inventată din facingul corpului.
- **Compatibilitate:** câmpurile sunt opționale la citirea snapshot-urilor
  vechi, astfel încât baseline-ul rămâne lizibil și neschimbat.
- **Test:** testele țintite au trecut `255/255`; suita completă a trecut
  `1566/1566` în `131,48 s`.

## ME-462 — Harta 2D desena o singură orientare ambiguă

- **Problemă:** săgeata hărții folosea câmpul vechi `player_facing_rad`, deci
  nu arăta vizual dacă facingul corpului și direcția estimată a camerei s-au
  separat.
- **Soluție:** harta desenează corpul exact cu albastru și camera estimată cu
  portocaliu punctat. Fiecare săgeată apare numai dacă propriul canal este
  disponibil; lipsa camerei nu este înlocuită cu facingul corpului.
- **UI:** legenda este vizibilă în panoul MovementEngine, lângă valorile
  numerice ale celor două unghiuri și delta lor.
- **Test:** verificările țintite au trecut `248/248`, iar suita completă a
  trecut `1567/1567` în `133,53 s`.

## ME-463 — Harta 3D confunda direcția corpului cu direcția camerei

- **Problemă:** viewerul 3D putea orienta atât Predatorul, cât și camera după
  aceeași valoare. Astfel, o cameră întoarsă separat de corp nu era reprezentată
  corect.
- **Soluție:** fluxul live v5 trimite separat direcția exactă a corpului și
  estimarea camerei. Săgeata Predatorului rămâne albastră, iar direcția camerei
  este portocalie și punctată. Viewerul folosește estimarea camerei numai când
  există; altfel folosește direcția corpului fără să pretindă că sunt identice.
- **Compatibilitate:** fluxurile v2-v4 rămân acceptate; verificarea staționară
  ignoră canalul camerei și certifică numai corpul.
- **Dovadă:** `MapViewer.exe` a fost reconstruit cu succes, iar suita completă
  a trecut `1568/1568` în `131,61 s`.

## ME-464 — Control Center era prea tehnic, iar Codex avea prea puține taste

- **Problemă:** interfața afișa termeni precum `WorldPack`, `semantic`,
  `authority`, `MovementEngine`, `HUD` și `3D Mesh Map`. În același timp,
  controlul armat pentru Codex permitea doar câteva taste de mers, nu și
  Spellbook-ul sau barele de abilități.
- **Soluție UI:** textele vizibile folosesc acum cuvinte simple: `Mișcare`,
  `Hartă 3D`, `Destinație`, `Poate merge singur` și `Îl mișcă Codex`.
  Detaliile tehnice rămân în cod și jurnale, nu în fața utilizatorului.
- **Soluție control:** armarea Codex permite tastele normale folosite de WoW,
  mouse-ul, F1-F12 și tastele de navigare. Tastele Windows, Print Screen și
  Pause rămân excluse. Controlul este legat strict de fereastra, PID-ul și
  procesul Control Center curente, iar tastele sunt eliberate automat.
- **Clarificare:** `Poate merge singur` permite motorului să țină tastele de
  mers; `Îl mișcă Codex` permite controlul manual asistat de Codex. Sunt două
  permisiuni diferite.
- **Test:** suita completă a trecut `1568/1568` în `131,61 s`.

## ME-465 — Harta live arunca direcția vizibilă pe clientul 2.4.3

- **Problemă:** poziția X/Y era live, iar detectorul minimapei găsea săgeata
  Predatorului, dar bridge-ul 3D accepta numai `GetPlayerFacing()`. Clientul
  TBC 2.4.3 nu oferă în mod normal acest API, astfel că harta publica mereu
  `facing none` și Predatorul părea fără direcție.
- **Soluție generală:** bridge-ul publică acum cea mai bună direcție vizibilă
  împreună cu sursa și încrederea ei. `COORDINATE_HUD_EXACT` rămâne exact;
  `MINIMAP_VISION_FALLBACK` este afișat cinstit drept „direcție văzută pe
  minimapă”. Camera rămâne un canal separat și nu este inventată.
- **Compatibilitate:** metadatele sunt puse după markerul `end`, deci viewerul
  nativ v5 continuă să citească săgeata fără o reconstrucție. Cititorii Python
  păstrează sursa și nu mai etichetează automat orice unghi drept exact.
- **Probă live fără input:** la poziția `1837.349, 1586.382`, detectorul a
  publicat `facing 3.861026389`, sursa `MINIMAP_VISION_FALLBACK` și încredere
  `0.768919`. Nu s-a apăsat nicio tastă și nu s-a pornit navigația.
- **Test:** testele țintite trec `246/246`; `compileall` și `git diff --check`
  trec. Gate-ul strict staționar rămâne fail-closed: direcția vizibilă nu este
  redenumită „exactă”.

## ME-466 — Control Center încă folosea cuvinte prea grele

- **Problemă:** chiar după prima curățare, pagina principală încă spunea
  „autonom”, „validare”, „poziție”, „citire” și alte expresii care cereau
  explicații.
- **Soluție:** toate acțiunile principale folosesc acum întrebări și verbe
  scurte: `Unde merge?`, `Alege singur drumul`, `Îi dau voie să meargă
  singur`, `Verifică locul`, `Harta acum` și `Ține Predatorul în mijloc`.
  Erorile grele rămân în jurnal; fereastra spune doar ce poate face copilul
  mai departe.
- **Test:** Control Center are un test dedicat pentru cuvintele principale,
  iar întreaga suită `test_movement_engine.py` trece `242/242`.

## ME-467 — Permisiunea scurtă oprea un drum lung

- **Problemă:** dovada locală că Predatorul are voie să meargă expiră după
  30 de secunde. Control Center o crea o singură dată, înainte de pornire,
  iar încărcarea hărții putea consuma deja acel timp.
- **Soluție generală:** cât timp `Îi dau voie să meargă singur` este bifat și
  procesul exact al drumului trăiește, Control Center verifică din nou lumea
  LAB și reînnoiește dovada la fiecare 12 secunde. Permisiunea de mers este
  refăcută înainte să expire, iar legătura cu sesiunea este refăcută pentru
  drumuri mai lungi. Debifarea, `OPREȘTE`, închiderea ferestrei sau terminarea
  procesului opresc imediat reînnoirea.
- **Vizibilitate:** verificările rulează ascuns și nu mai deschid ferestre
  negre. Dacă o verificare eșuează, intrările expiră singure, UI-ul spune
  simplu că mersul se oprește, iar cauza completă intră în
  `movement-arm-renewal.log`.
- **Test:** testul de contract verifică numele unic al fișierului, reînnoirea,
  oprirea și rularea ascunsă; suita MovementEngine trece `242/242`.
### ME-468 — Control Center could not start a journey after the routine-aggro option was added

- **Seen:** the journey supervisor stopped before the first movement frame with `unrecognized arguments: --continue-through-routine-aggro`.
- **Cause:** Control Center sent the travel-policy option to the supervisor, but the supervisor parser did not declare it.
- **Fix:** the supervisor now accepts the option and forwards it explicitly to the navigation child only when selected.
- **Regression proof:** parser and command-building tests cover both enabled and disabled states.
### ME-469 — A renewed movement arm was ignored until the old copy expired

- **Seen:** one successful Crypt exit stopped for about 27 seconds, then resumed in a second navigation slice.
- **Cause:** Control Center renewed the exact arm file, but the active movement gateway kept only the first in-memory expiry.
- **Fix:** the active runner now validates newer exact arm files and extends the same held-control session without releasing W or RMB. A changed client, actor, authorization, control set, or clock is rejected.
- **Regression proof:** transport and gateway tests assert that renewal crosses the old expiry with one W-down and one RMB-down, with no intermediate release.
### ME-470 — Control Center still used words that were too technical

- **Seen:** the main page still said things such as `Control cu Codex`, `obstacole`, `topologie`, and long camera/pose explanations.
- **Fix:** the visible page now uses short child-readable phrases: `Îl mișc eu`, `Pot apăsa tastele și mouse-ul`, `Podeaua`, `Uși și ieșiri`, `lucruri de ocolit`, `Zoom`, and `Harta drumului`.
- **Boundary:** exact coordinates, degrees, and counts remain visible because they help verify movement; technical causes remain in logs, not in the main page.

### ME-471 — Harta din Center îngheța când operatorul aducea Center-ul în față

- **Observat:** procesul hărții live rula, dar fișierul de poziție rămânea
  neschimbat și diagnosticul spunea `target window is not the foreground
  window` imediat ce Control Center devenea fereastra activă.
- **Cauză:** cititorul folosit de harta strict read-only moștenea regula de
  siguranță a motorului care apasă taste: numai WoW în prim-plan.
- **Soluție generală:** sursa de poziție are acum două moduri distincte.
  Harta read-only folosește o captură Win32 legată de HWND-ul exact al WoW și
  poate observa jocul chiar când Center-ul îl acoperă; orice navigator sau
  control manual păstrează implicit și obligatoriu verificarea că WoW este în
  prim-plan înainte de input. Proba locală `PrintWindow` a redat corect tot
  clientul 2.4.3 la `2414x1358` fără să aducă jocul în față.
- **UI:** formularea ambiguă `Îl mișc eu` a fost înlocuită cu `Codex AI —
  control manual` și explică explicit dacă AI-ul poate sau nu poate folosi
  tastatura și mouse-ul.
- **Durată:** Center-ul reînnoiește în fundal doar autorizația read-only înainte
  să expire. Aceasta nu bifează și nu prelungește permisiunea de tastatură sau
  mouse.
- **Regresie:** testele verifică explicit că numai bridge-ul de hartă cere
  `require_foreground_capture=False`, că backendul nu are API de input și că
  manifestul declară mereu `execution_authority: false`; toate celelalte
  utilizări păstrează valoarea sigură implicită `True`. Setul țintit trece
  `277/277`.

### ME-472 — Pornirea într-un spațiu îngust depășea direcția coridorului

- **Observat:** la prima scară, Predatorul începea la aproximativ `0,56 rad`
  față de tangenta coridorului. În șase cadre staționare, comanda RMB ajungea
  până la `640 px/s`; observația vizuală întârziată îl lăsa să treacă dincolo
  de tangentă, după care corecta în sens opus.
- **Cauză:** pragul vechi cerea `0,22 rad` înainte să permită W. Pentru o
  direcție cuantizată pe minimapă, pragul era mai strâns decât distanța de
  frânare a rotirii deja pornite.
- **Soluție generală:** protecția inițială continuă să oprească W peste
  `0,50 rad`, dar începe mersul la `0,32 rad`. De acolo, pure pursuit termină
  alinierea cu W și RMB împreună, în interiorul marginii de siguranță de
  `0,35 yd`. Regula se aplică oricărui coridor îngust/WMO și nu conține
  coordonate sau nume de loc.
- **Simulare:** `1.000/1.000` variații deterministe de poziție, heading,
  viteză și interval de observație au ajuns la destinație; `0` coliziuni,
  maximum o schimbare a sensului și eroare transversală maximă `0,751 yd`.
- **Stare:** schimbarea este eligibilă pentru următoarea probă live, dar nu
  înlocuiește dovada filmată și nu este încă promovată peste baseline.

### ME-473 — Bifa Codex putea rămâne în fișier după închiderea vechiului Center

- **Observat:** noul Control Center arăta controlul Codex oprit, dar fișierul
  de autorizare încă declara `enabled: true` și PID-ul unui Center care nu mai
  exista. Driverul refuza corect inputul, însă cele două stări puteau induce
  operatorul în eroare.
- **Cauză:** închiderea normală dezarma inputul, dar oprirea forțată sau o
  cădere de curent putea sări peste rutina de închidere. La pornire, noul
  proces inițializa bifa pe `false`, fără să înlocuiască imediat fișierul vechi.
- **Soluție generală:** fiecare proces Control Center scrie la pornire o stare
  explicit dezarmată, cu propriul PID. Numai o bifă făcută după acea pornire
  poate adăuga HWND-ul și PID-ul WoW și poate activa inputul. Închiderea
  continuă să dezarmeze a doua oară.
- **Probă live fără input:** după restart, fișierul a trecut la
  `enabled: false`, `control_center_pid: 3592`; procesul respectiv era viu,
  harta continua să publice poziția Crypt `1676.370, 1677.467`, iar WoW și
  serverul nu au fost repornite.
- **Regresie:** testul dedicat verifică ordinea pornire-dezarmare înainte de
  legarea ferestrei, suitele UI țintite trec `39/39`, iar suita completă trece
  `1.582/1.582` în `131,75 s`.

### ME-474 — Windows putea refuza focusul WoW pentru controlul Codex autorizat

- **Observat:** aprobarea Codex era validă și legată de PID/HWND-ul WoW, dar
  prima apăsare `Enter` s-a oprit înainte de input deoarece Windows a refuzat
  apelul simplu `SetForegroundWindow` făcut din procesul aflat în fundal.
- **Cauză:** driverul manual folosea o predare de focus mai slabă decât
  transportul MovementEngine deja validat. Verificarea fail-closed a protejat
  jocul, însă o aprobare corectă nu putea fi folosită cât altă fereastră avea
  focusul.
- **Soluție generală:** după validarea exactă a PID-ului, HWND-ului, clasei și
  titlului WoW, driverul atașează temporar coada sa de input la threadurile
  ferestrei active și ale țintei, aduce numai HWND-ul autorizat în față, apoi
  detașează întotdeauna threadurile în `finally`. Nicio tastă nu este trimisă
  dacă această predare nu se confirmă.
- **Probă live:** prima încercare a produs zero input și eroarea de focus;
  după corecție, exact aceeași comandă a executat un singur `Enter` pe PID
  `1744`, a închis dialogul `Disconnected`, iar fluxul operator verificat a
  reconectat Predatorul fără a expune parola în comandă sau jurnal.
- **Regresie:** testele driverului și transportului Win32 trec `40/40`.

### ME-475 — Bifa de mers singur și poarta semantică puteau rămâne despărțite

- **Observat:** `Îi dau voie să meargă singur` era bifat, dar butonul principal
  continua să spună `BIFEAZĂ CĂSUȚA` după ce validarea lumii fusese refăcută.
- **Cauză:** UI-ul păstra alegerea operatorului, în timp ce poarta semantică
  verificată rămânea cu `live_authority_enabled: false`. Cele două fișiere nu
  erau reunite la pornire sau imediat înaintea lansării.
- **Soluție generală:** Control Center poate schimba numai bitul de autoritate
  al unei porți deja validate și numai dacă identitatea WorldPack-ului,
  workerului și hash-ul rezultatului de validare au rămas identice. Orice
  diferență debifează mersul și rămâne fail-closed. Aceeași verificare se face
  la pornire, la bifă și chiar înainte de lansare.
- **Regresie:** testele acoperă rearmarea validă, refuzul după modificarea
  dovezii și ordinea rearmare -> sesiune -> input.

### ME-476 — Clientul 2.4.3 nu poate furniza direct direcția corpului

- **Observat:** proba `run:f3b:1e6989ea-3179-443d-9411-9c77ab011552` avea
  direcție vizibilă în toate cele `568` cadre, dar canalul separat corp/cameră
  era gol în toate cadrele.
- **Cauză:** `GetPlayerFacing()` a fost adăugat după clientul 2.4.3. Addonul
  verifică funcția și nu inventează valoarea. Pe acest client, săgeata nord-up
  de pe minimapă este observația vizuală a direcției corpului; camera este
  modelul separat integrat din comenzile RMB.
- **Soluție generală:** telemetria păstrează două canale și sursele lor:
  `MINIMAP_VISION_FALLBACK` pentru corp și
  `RMB_MOUSE_INTEGRATED_FROM_VISIBLE_BODY` pentru cameră. Numai primul rămâne
  aproximativ; nu este redenumit „exact”. Delta este acceptată doar când ambele
  valori și ambele etichete sunt prezente și coerente.
- **Camera:** detectorul vechi de siluetă a găsit Predatorul în doar `9/38`
  cadre eșantionate deoarece zoom-ul natural s-a schimbat la ieșirea dintre
  pereți. Acesta rămâne diagnostic. Dovada de control folosește chitanța exactă
  a fiecărui cadru: RMB ținut, zero mișcare verticală și sursă de yaw declarată.
  Astfel nu confundăm schimbarea firească de scară cu pierderea camerei.

### ME-477 — Evaluatorul confunda o curbă reală cu balansul camerei

- **Observat:** aceeași probă sosită fără blocare avea `12` schimbări totale de
  sens și era respinsă ca balans, deși o parte aparținea pasajului în S.
- **Cauză:** clasificatorul folosea numai timpul dintre semne opuse. Nu verifica
  dacă Predatorul era deja departe de axa coridorului sau dacă drumul cerea o
  corecție mare. Două intervale de captură cu peste `2,5 yd` parcurși erau de
  asemenea numite pauze doar pentru că direcția s-a schimbat într-o curbă.
- **Soluție generală:** „balans” înseamnă acum numai corecții opuse mici,
  rapide și aproape de aceeași linie. Curbele reale rămân numărate în total,
  dar nu sunt penalizate ca oscilație. Un interval mai lung este continuitate
  dacă W este ținut la ambele capete și poziția dovedește deplasare; calitatea
  direcției este verificată separat.
- **Rezultat diagnostic:** proba veche se reclasifică de la `9` la `4`
  inversări rapide, `6,86/min`, `0` pauze neexplicate și trece criteriile de
  mișcare. Nu intră retroactiv în cele zece probe deoarece nu conține noile
  surse corp/cameră pe fiecare cadru.
- **Alternativă respinsă:** înlocuirea controlerului geometric cu urmăritorul
  continuu peste tot a păstrat `0` coliziuni, dar a ratat calitatea în
  `88/1000` porți în S și `9/1000` poduri. Schimbarea a fost retrasă înainte de
  orice input live.

### ME-478 — Prima dovadă completă a separat corpul, camera și continuitatea

- **Probă live:** `run:f3b:6d10813e-eeb3-456a-a7bf-4650f596db23` a ajuns din
  Crypt în Deathknell cu `524` cadre, `0` blocări, `0` recuperări și toate
  cadrele având surse separate pentru corp și cameră plus RMB ținut orizontal.
- **Respins:** proba a avut `10` inversări mici rapide în `33,56 s`
  (`17,88/min`), concentrate în primele scări. Sosirea nu a ascuns balansul;
  filmarea și raportul strict au rămas dovezi negative.
- **A doua probă respinsă:** `run:f3b:0078fafb-615c-446e-a197-83aa4587a95d`
  a redus inversările rapide la `8`, dar a rămas peste prag. Telemetria a arătat
  că acele cadre veneau din `ContinuousTrajectoryFollower`, nu din controlerul
  predictiv corectat inițial. Schimbarea pusă pe controlerul greșit a fost
  retrasă înainte de următoarea probă.

### ME-479 — Coridorul nou făcea camera să uite impulsul anterior

- **Cauză:** fiecare previzualizare nouă a coridorului reseta viteza mouse-ului,
  ultimul sens și confirmarea inversării în urmăritorul continuu. Harta se
  schimba corect, dar camera fizică încă executa impulsul precedent; următoarea
  bucată putea cere imediat `1–4 px` în sens opus.
- **Soluție generală:** o schimbare de coridor resetează progresul geometric și
  stările de curbă, dar păstrează memoria fizică a actuatorului. Inversările de
  cel mult `4 px` sunt confirmate numai în plicul mic de eroare; o curbă reală
  sau o ieșire din coridor rămâne imediat autoritară. Nu există coordonate,
  nume de zonă sau traseu hardcodat.
- **Simulare:** atât corpusul geometric, cât și selectorul adaptiv au trecut
  câte `6.000/6.000` cazuri, cu `0` coliziuni; distanța minimă față de obstacol
  a rămas la valoarea baseline `0,1339 yd`.
- **Probă live acceptată tehnic:**
  `run:f3b:83fd9c61-76cb-42c3-88e8-cbbb61a3cc64` a ajuns fără recuperare.
  Raportul strict are `524` cadre, `5` inversări rapide (`8,79/min`), `3` cadre
  de pivot (`0,57%`), nicio blocare, nicio pauză de observație neexplicată și
  toate cele trei porți de corp/cameră/integritate complete. Rezultat: `PASS`.
- **Promovare:** proba poate conta drept primul candidat din seria de zece numai
  după verificarea vizuală a operatorului; nu a fost promovată automat.

### ME-480 — Un singur cadru expirat oprea întreaga călătorie

- **Observat:** a doua repetare filmată s-a oprit aproape de Deathknell cu
  `WindowsInputSinkError: continuous motion frame is stale`. Protecția a făcut
  partea sigură corect: a eliberat W și RMB și nu a trimis comanda veche. Nu a
  fost produs un rezultat de sosire, deci proba este respinsă.
- **Context, nu cauză pretinsă:** în aceeași probă rula encoderul software
  `libx264` la `3620×2036`. Această concurență poate explica întârzierea rară,
  dar logul singur nu o dovedește; problema reală demonstrată este că o singură
  întârziere tranzitorie abandona toată misiunea.
- **Soluție generală:** cadrul expirat rămâne interzis și toate controalele
  rămân eliberate. Runnerul recitește poziția și facingul vizibile, actualizează
  traseul observat și recalculează următoarea comandă. Sunt permise maximum
  `3` recitiri consecutive; o suprasarcină persistentă tot oprește fail-closed,
  fără buclă infinită și fără input dintr-o observație veche.
- **Verificare:** `119` teste țintite și suita completă de `1591` teste au
  trecut. Recorderul următoarei probe a folosit Media Foundation pentru a nu
  încărca inutil bucla de control.

### ME-481 — A doua ieșire tehnic verde, cu recorder separat de control

- **Poziționare staționară:** `21` observații în `4,007 s`, abatere de poziție
  și jitter de facing `0`, în `landmark:deathknell-crypt`; rezultat `PASS`.
- **Probă live:** `run:f3b:dcf6f083-3a0d-4d1f-a079-c0655b5648b9` a ajuns în
  Deathknell în `527` cadre și `33,81 s`, fără recuperare și fără blocare.
- **Calitate strictă:** `3` inversări rapide (`5,32/min`), `4` cadre de pivot
  (`0,76%`), `0` cadre de stall și `0` pauze de observație neexplicate. Toate
  cele `527/527` cadre au sursa facingului, separarea corp/cameră și integritatea
  camerei complete; rezultat tehnic `PASS`.
- **Limită de dovadă:** ramura nouă de recitire după cadru expirat nu a fost
  necesară în ME-481 (`0` recitiri). Proba confirmă lipsa regresiei pe traseul
  normal, nu pretinde că a exercitat incidentul ME-480.
- **Promovare:** filmarea utilă este
  `data/runtime/operator/live-video/crypt-deathknell-me481-motion-proxy.mp4`.
  Proba rămâne candidat până la verdictul vizual al operatorului.

### ME-482 — Repetarea a expus rotirea târzie înainte de curbă

- **Probă respinsă:** `run:f3b:f5fb9187-3708-423e-9328-dbd9a728ffd1`
  a ajuns, dar a avut `9` inversări rapide (`15,61/min`) și un cadru de mers
  fără progres. Nu este promovată și nu este ascunsă de cele două rezultate
  tehnic verzi anterioare.
- **Cauză observată:** chiar înaintea cotului din geometria coridorului,
  urmăritorul a cerut rotire puternică în sens opus curbei pentru a centra
  punctul apropiat. Când punctul urmărit a trecut dincolo de cot, comanda s-a
  inversat brusc. Predator a depășit axa coridorului și a trebuit să revină.
  Coridorul, obstacolele învățate și destinația au fost aceleași; nu este o
  rută nouă și nu este o excepție pentru Cryptă.

### ME-483 — Frânare anticipată din forma coridorului

- **Soluție generală:** pentru un coridor cu geometrie completă se calculează
  și sensul curbei care urmează. Dacă punctul apropiat cere momentan rotire în
  sens opus, iar Predator este încă aproape de axă, comanda este frânată către
  zero înainte de curbă. W rămâne apăsat; controlerul nu așteaptă colțul ca să
  schimbe brutal sensul.
- **Filtru anti-balans:** o inversare mică trebuie să persiste `11` cadre de
  control, adică mai mult decât fereastra strictă de `0,50 s`. Curbele reale,
  erorile mari și ieșirea din coridor rămân corectate imediat.
- **Dovadă offline:** corpusul geometric și selectorul adaptiv/MPPI au trecut
  fiecare `6.000/6.000` situații, cu `0` coliziuni și `100%` rată de calitate.
  Sunt incluse scări, pasaj în S, poartă cu obstacol, pod drept și curbă
  strânsă. Următoarea probă live rămâne una singură, filmată și bounded.

### ME-484 — Arborele de procese nu era o pornire dublă

- **Corecție:** prima citire arăta câte două PID-uri pentru Control Center,
  supervisor și navigație. Verificarea `ParentProcessId` a demonstrat că
  fiecare pereche este un singur program: launcherul `.venv\\Scripts\\pythonw`
  și interpretul Python copil. Nu existau două fluxuri de mouse/W.
- **Dovadă:** procesul UI `14312` are copilul `7076`, iar numai copilul deține
  fereastra `Predator`. Aceeași relație părinte-copil a existat la supervisor
  și runner. Tentativa oprită preventiv nu este numărată, dar nici nu este
  etichetată fals drept eroare de concurență.
- **Întărire păstrată:** starea `STARTING` respinge totuși un al doilea apel UI
  înainte ca procesul copil să fie memorat, iar firul de pregătire verifică
  faptul că deține încă evenimentul activ. Este o gardă generică, nu o
  pretinsă rezolvare a unui incident care nu a existat.

### ME-485 — Frâna de curbă a trecut prima probă live

- **Poziționare staționară:** `21` observații în `4,011 s`, cu abatere de
  poziție și jitter de facing `0`; locația Crypt a fost confirmată `PASS`.
- **Probă live:** `run:f3b:1088ddf1-07d7-4bca-86ab-b7ffe8a1ce67` a ajuns în
  Deathknell în `537` cadre și `33,44 s`, fără recuperare și fără blocare.
- **Schimbarea a fost exercitată:** motivul
  `continuous_pure_pursuit_upcoming_bend_brake` apare în `6` cadre; nu este
  doar cod trecut printr-un test care nu i-a folosit ramura nouă.
- **Calitate strictă:** `1` inversare rapidă (`1,79/min`), `4` cadre de pivot
  (`0,74%`), `0` cadre de stall și `0` pauze neexplicate. Toate cele `537/537`
  cadre au sursa facingului, separarea corp/cameră și integritatea camerei;
  rezultat tehnic `PASS`.
- **Limită:** filmarea scurtă este
  `data/runtime/operator/live-video/crypt-deathknell-me485-motion-proxy.mp4`.
  Proba rămâne candidat până la verdictul vizual al operatorului și nu este
  promovată automat în seria oficială de zece.

### ME-486–ME-494 — Zece ieșiri consecutive tehnic verzi

- Fără alte schimbări de cod, ME-486 până la ME-494 au repetat aceeași probă
  Crypt→Deathknell. Împreună cu ME-485 sunt `10/10` sosiri consecutive,
  fiecare cu validare staționară separată și filmare proprie.
- Toate cele zece rapoarte stricte sunt `PASS`: `0` blocări, `0` cadre de
  mers fără progres și `0` pauze de observație neexplicate. Inversările rapide
  au fost, în ordine: `1, 3, 0, 4, 2, 2, 3, 0, 1, 3`; maximul a fost
  `7,12/min`, sub pragul neschimbat.
- Durata mișcării a rămas strânsă între `33,09 s` și `33,99 s`; fiecare cadru
  din fiecare probă are sursa facingului, separarea corp/cameră și integritatea
  camerei complete.
- Filmările scurte au fost concatenate, fără a înlocui fișierele individuale,
  în `data/runtime/operator/live-video/crypt-egress-me485-me494-review.mp4`
  (`381 s`, `103536393` bytes, SHA-256
  `2F28F2E0E0EA23AF1DF7D5869D0F6B12C254FFB499129E4D6606539FB4F2C0A5`).
- **Limită de acceptare:** aceasta completează poarta tehnică, nu verdictul
  vizual. `config/movement-lab/crypt-egress-live-trials.json` rămâne
  nepromovat până când operatorul privește seria și declară explicit că nu
  există regresie uman-vizuală față de baseline.

### ME-495 — Reluarea de la jumătatea drumului a respins greșit un obstacol îndepărtat

- Drumul continuu Crypt→Brill a ajuns. La întoarcere, autorizația temporară de
  mișcare a expirat la poziția observată `(2187,99, 1049,80)`, iar reluarea
  sigură s-a oprit înainte de primul input.
- Cauza nu era harta: traseul de bază Brill→Crypt trecea valid. Un obstacol
  confirmat aflat la aproximativ `533 yd` era verificat ca și cum Predator s-ar
  fi aflat deja lângă el. Arcul local de trei bucăți nu putea fi validat de la
  acea distanță și întreaga călătorie era respinsă.
- Remedierea generală cere navmesh-ului clientului un coridor complet numai
  pentru segmentul semantic afectat, cu obstacolul memorat inclus. Dacă nu
  există coridor valid, mișcarea continuă să se oprească fail-closed.

### ME-496 — Obstacolul a fost trecut, dar 37 de mini-destinații au produs pauze

- Proba filmată a reluat exact din locul ME-495 și a ajuns în Crypt:
  `run:f3b:54137d30-3110-447f-8c3e-4e16a527a908`, `2713` cadre, `0`
  recuperări și `0` cadre de mers fără progres.
- Predator a trecut fizic pe lângă obstacolul memorat, dar prima implementare
  a transformat cele `37` puncte interne ale coridorului Detour în `37`
  mini-destinații. În acea zonă au apărut predări repetate, pivotări și `8`
  pauze de observație neexplicate; maximul a fost `6,89 s`.
- Raportul strict este corect `FAIL` pentru `control_observation_gap`. Sosirea
  nu este declarată mișcare fluidă și evaluatorul nu a fost relaxat.

### ME-497 — Coridorul de evitare rămâne o singură mișcare

- Coridorul Detour validat cu obstacolul confirmat este acum păstrat ca un
  singur segment executabil. Punctele lui geometrice rămân în traseul intern,
  dar nu mai devin opriri sau destinații pentru Predator.
- Cache-ul de siguranță are prioritate față de preplanul obișnuit atât la
  pornire, cât și la predarea dintre segmente. Nu există coordonate de Crypt,
  Brill sau ale obstacolului în regulă.
- Verificare offline: `365` teste direct relevante și întreaga suită de
  `1594` teste au trecut. Schimbarea rămâne candidat până la următoarea probă
  live filmată; nu se pretinde încă dispariția vizuală a pauzelor.

### ME-497 live — Călătoria a sosit, dar returul nu trece încă poarta strictă

- Proba filmată Crypt→Brill→Crypt a ajuns la ambele destinații. Segmentul
  final a folosit `CONFIRMED_CLEARANCE_PRIOR_APPLIED_BY_GLOBAL_NAVMESH` pentru
  obstacolul `60812e3b1d58cfc5` și a inserat `0` mini-destinații; remedierea
  ME-497 a fost astfel exercitată live.
- Outbound este `PASS`: `5915` cadre, `0` pauze neexplicate. Returul a fost
  împărțit de expirarea autorizației: prima parte a avut o pauză de `11,45 s`,
  iar segmentul final a ajuns, dar a păstrat două pauze neexplicate, cu maxim
  `1,36 s`. Sosirea completă nu este declarată încă fluidă.
- Cauzele sunt distincte: reemiterea autorizației F4a schimba hash-ul și era
  tratată ca o legare străină, iar un replan de recentrare sincron a eliberat
  mișcarea cât timp navmesh-ul calcula noul coridor.

### ME-498 — Reînnoirea temporală F4a nu mai rupe mersul continuu

- O autorizație F4a reînnoită declară acum hash-ul exact al părintelui și
  `renewal_scope=temporal_only`. Loaderul verifică lanțul, identitatea fizică
  a clientului și toate limitele neschimbate înainte de adoptare.
- Gateway-ul acceptă schimbarea hash-ului numai dacă părintele este exact
  autorizația activă. Clientul, actorul, instanța, profilul, controalele,
  ceasul și lease-ul trebuie să rămână identice; o ramură străină rămâne
  respinsă fail-closed.
- Reînnoirea extinde sesiunea existentă fără `key_up` pentru W și fără
  eliberarea RMB. Verificare offline: `255` teste țintite și suita completă de
  `1596` teste au trecut. Este necesară o nouă probă live mai lungă de opt
  minute pentru dovada efectului în client.

### ME-499 — Recentrarea începe calculul înainte de oprirea fizică

- Trace-ul live a arătat că abaterea laterală depășea `1,25 yd` cu peste două
  secunde înainte de realiniere, dar preplanul vechi pornea abia la `2 yd`, cu
  aproximativ `0,6 s` înainte de nevoie. Query-ul navmesh măsurat dura circa
  `1,3 s`, deci ramura sincronă elibera W/RMB și producea pauza vizibilă.
- Preplanul începe acum la `1,25 yd`, cât coridorul curent este încă sigur de
  urmărit. Un rezultat terminat poate fi adoptat după maximum `15 yd` de
  avans, deoarece followerul face o proiecție globală pe noul coridor înainte
  de următorul input și respinge în continuare o poziție realmente divergentă.
- Regula folosește numai geometria, viteza și coridorul curent; nu conține
  coordonate, nume de zonă sau excepții pentru Cryptă. `366` teste relevante
  și suita completă de `1598` teste au trecut. Dovada live rămâne necesară.

### ME-500 — Control Center reconciliază starea cu procesul real

- În proba ME-497, Predator se deplasa și checkpointul de continuitate era
  `RUNNING`, dar textul UI rămăsese la „Pregătesc drumul…”. Callbackul unic
  trimis din firul de pregătire către Tk nu este o sursă suficientă de adevăr
  când harta live redesenează intens.
- La fiecare refresh, Control Center verifică acum handle-ul exact al
  procesului. Dacă UI este încă `STARTING`, dar procesul există și rulează,
  trece singur la „Merge singur”. Procesul rămâne autoritatea; niciun fișier
  de stare și nicio presupunere nu pot declara pornirea.

### ME-501 — O recentrare nu mai șterge dovada că Predatorul este blocat

- Proba live reluată din Deathknell s-a oprit înainte de deplasare cu
  `CORRIDOR_RECENTER_REPLAN_BUDGET_EXHAUSTED`. Trace-ul arată W și RMB ținute,
  `35` cadre și poziție complet nemișcată lângă geometria clădirii.
- Fiecare dintre cele trei recentrări recrea un coridor din aceeași poziție,
  apoi reseta la zero timpul de mers fără deplasare. Astfel, dovada fizică nu
  putea ajunge niciodată la pragul de recuperare, deși personajul apăsa în
  obstacol.
- O recentrare geometrică nu este progres fizic, deci păstrează acum timpul
  acumulat într-un ceas separat. Ceasul scurt al controllerului se reia după
  realiniere, ca să poată emite cadre noi, dar a treia perioadă fără deplasare
  trece pragul complet și intră în recuperarea limitată. Memoria permanentă
  rămâne interzisă până la această dovadă completă. Regula nu conține
  coordonate sau nume de zonă.

### ME-502 — Harta nu mai „întoarce” doar numărul direcției

- Proba ME-501 a trecut de bucla de recentrare și a deplasat Predatorul circa
  `2,5 yd`, apoi recuperarea s-a oprit `RESET_REQUIRED`. Filmarea și trace-ul
  arată o nepotrivire de aproximativ 180°: traseul local era spre interiorul
  liber, dar corpul continua să privească în zid și aluneca lateral.
- Cauza era regula pentru săgeata mică de pe minimap. Când axa părea inversă
  față de traseu, codul adăuga 180° direcției din memorie și presupunea că și
  corpul s-a întors. O hartă poate alege ținta, dar nu poate roti fizic
  personajul prin schimbarea unui număr.
- Ambiguitatea este acum păstrată explicit. Direcția observată a corpului nu
  este falsificată și sursa vizuală curentă rămâne validă pentru preflight;
  ambiguitatea este o stare separată. Controllerul poate astfel face pivotul
  fizic cu RMB înainte de W, iar primul chord de deplasare verifică orientarea.
  Regula este geometrică și se aplică în clădiri, pe drumuri și în orice altă
  hartă.

### ME-503 — O linie validă pentru Detour nu dovedește că încape corpul

- Trei probe filmate au repetat contactul static din interior la aproximativ
  `(1870,91, 1575,15)`. Memoria îl confirmase, dar planificatorul semantic
  grosier nu îl compara cu coridorul local pe care Predatorul urma să calce.
- Verificarea rulează acum și pe coridorul local real. Prima probă a exercitat
  noua legătură, dar a respins candidatul live: ocolirea de `1,0 yd` era
  traversabilă pentru punctul central Detour, în timp ce corpul vizibil a
  lovit aceeași margine și a ajuns sub scară. Rezultatul rămâne eșec,
  `PARTIAL_CORRIDOR_FRONTIER_STUCK`; filmarea nu este promovată ca progres.
- Valoarea laterală nu mai este confundată cu spațiul real rămas corpului.
  Fiecare punct trebuie să rămână în afara razei celulei observate plus
  `DEFAULT_ACTOR_CLEARANCE_WORLD=1,25 yd`, iar proiecțiile navmesh mai mari de
  `0,10 yd` sunt respinse. Se execută coordonatele rezolvate de navmesh, cu
  înălțimea suprafeței corecte. Regula este generală; nu se adaugă coordonate
  speciale pentru această clădire.
