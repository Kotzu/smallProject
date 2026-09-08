# Predator — plan delimitat pentru context spațial și Control Center

> Prioritățile consolidate și statusurile curente sunt în `PREDATOR_BACKLOG.md`.
> Cripta este primul reper de acceptare; planul de mai jos păstrează detaliile
> și istoricul cercetării, fără a autoriza extinderea prematură la alte medii.

Actualizat: 2026-09-06, la cererea operatorului de a păstra ultimele decizii
ca taskuri și referință. Acesta este planul de continuare; nu conferă input
live și nu înlocuiește autorizațiile runtime. Operatorul a activat goal-ul
complet pentru sonar geometric, localizare și integrare CC. Goal-ul vechi
de clearance nu a fost declarat realizat; problema lui rămâne în acest plan.

## Obiectiv

Predator să distingă unde se află, ce știe despre spațiul din jur și cât de
actuale/precise sunt informațiile, fără memory reading, fără soluție specifică
criptei și fără coordonate sau etaje inventate. Control Center trebuie să
afișeze aceste diferențe fără a bloca harta ori bucla de control.

Sonarul geometric include suprafețe și niveluri alternative, distanțe și
direcții către obstacole, treceri/dimensiuni/conexiuni și entități mobile
observabile. Razele sparse nu certifică spațiul dintre ele, iar o deschidere
nu primește un tip sau o destinație inventată. Aceste cerințe fac parte din
goal, chiar dacă lista de implementare de mai jos începe cu localizarea.

## Regula de surse confirmată de operator

- API-ul clientului este prima alegere când oferă informația necesară.
- OCR rămâne disponibil ca verificare suplimentară utilă sau fallback când
  informația nu poate fi obținută din API. Nu este eliminat din principiu.
- Banda vizibilă poate transporta valori obținute prin API: aceasta este
  decodare de date, nu recunoașterea textului din minimapă. Păstrăm ce ajută
  precizia și continuitatea client–CC, verificând latența și integritatea.
- API-ul propriu este o interfață de observație normalizată peste sursele
  permise. Nu creează informații inexistente și nu justifică memory reading,
  injecție ori acces server-side pentru percepția Predatorului.
- Fiecare valoare păstrează sursa, sesiunea, momentul observației, vechimea
  și calitatea. O estimare/OCR nu este redenumită observație directă API.
- API vechi nu bate OCR actual doar prin tipul sursei. Datele expirate ori
  din altă sesiune se exclud înaintea prioritizării. Conflictele se afișează,
  nu se ascund și nu produc automat o creștere a încrederii.
- Pentru cazul actual: Tirisfal Glades este regiunea, Deathknell localitatea.
  Câmpurile API rămân `zone`/`subzone`: alte subzone pot fi peșteri sau alte
  locuri, nu toate sunt orașe. Niciunul dintre aceste nume nu dovedește etajul.

## Taskuri, în ordine

1. [x] Nucleu spațial pur cu sesiune/hartă/etaj, vârstă și eroare metrică.
   `adr/2026-09-06-observed-spatial-context.md`.
2. [x] Replay al datelor reale: 626 decizii, 166 actualizări geometrice;
   XY observat separat de Z proiectat. Nu este localizare XYZ completă.
   `adr/2026-09-06-spatial-trace-adapter.md`.
3. [x] Confirmarea numelor zonei/subzonei din API-urile deja folosite de addon,
   nu OCR. Import și model de prezentare read-only, cu sesiune, timestamp,
   subzonă goală/indisponibilă și arhivă distinctă de un flux live.
   `adr/2026-09-06-api-location-labels.md`.
4. [x] Transport live pentru numele API către CC. Verificat staționar în LAB:
   Tirisfal Glades / Deathknell, addon 0.5.9, CC cu citire asincronă. Tranzițiile
   și invalidările sunt testate offline, nu încă prin deplasare live.
   Detalii și rollback: `adr/2026-09-06-live-api-location-transport.md`.
   Regula de surse este acum
   clarificată mai sus. Reutilizăm bridge-ul de observație existent, cu un
   payload separat/versionat pentru nume și identitate/prospețime. Mai întâi
   codec și teste de integritate, tranziție de regiune/subzonă, lipsuri,
   sesiune și înghețarea fluxului; apoi integrare și verificare live read-only.
   Nu duplicăm capture loop-ul, nu schimbăm protocoalele coordonate/combat/AFK
   pentru această extensie și nu forțăm reload/logout repetat pentru arhivă.
   Formatul și frecvența trebuie validate înaintea instalării; sursa API nu
   garantează singură precizia transportului sau a localizării.
5. [ ] Legarea Z/etajului la dovezile de localizare existente. Numele zonei
   restrânge contextul semantic, nu dovedește nivelul vertical ori camera
   fizică. Păstrarea separată a observației și estimării din asset-uri.
   Calibrarea camerei a fost separată de contactul actorului; prima ipoteză
   manuală 8+4 repere pe cadrul 98 este respinsă (verificare 345.914 px).
   Fără promovare la etaj; următorul fit cere asocieri mai sigure/distribuite.
   `adr/2026-09-06-camera-only-landmark-check.md`.
   Probă minimapă: 4 texturi WMO originale comparate cu 3 cadre reale și o
   referință negativă. Grupurile sunt vizibile simultan; scorul nu identifică
   grupul ocupat. Z/etaj rămân necunoscute. Compoziția geometrică este acum
   comparată cu XY din banda addonului: rezidual de deplasare 0.165/0.707 px
   în segmentul arhivat; nu este precizie metrică sau etaj confirmat.
   Tranziția a fost inspectată: minimapa se schimbă înaintea numelui subzonei,
   iar la ieșire persistă suprafețe WMO suprapuse. Urmează continuitatea dintre
   candidați pe traseul arhivat, nu alegerea scorului sau a seed-ului maxim.
   `adr/2026-09-06-minimap-stair-transition-evidence.md`.
   Opt interogări de continuitate v34 au separat rute complete scurte pe
   platformă de rute subterane lungi și rute de acoperiș incomplete. Nu confirmă
   încă etajul și evidențiază deplasarea produsă de proiecția pe navmesh.
   `adr/2026-09-06-vertical-corridor-continuity-audit.md`.
   Serviciul persistent separat a verificat offline aceleași 8 perechi:
   prima cerere 245 ms, cele următoare 0.2–0.3 ms. Loturile asincrone sunt acum
   integrate opt-in în CC, cu sesiune/prospețime și toate alternativele.
   Replay-ul nativ 98–100s produce 16/4 rânduri de comparații în modelul CC;
   94 teste PASS. Verificare vizuală live read-only făcută ulterior, staționar:
   după optimizarea publicării, 30/30 mostre valide fără creșterea ritmului
   geometric. Opțiunea este activă în CC; etajul rămâne neconfirmat.
   `adr/2026-09-06-live-continuity-publication.md`.
   `adr/2026-09-06-vertical-continuity-control-center.md`.
   `adr/2026-09-06-persistent-vertical-continuity.md`.
   `adr/2026-09-06-minimap-geometric-composition.md`.
   `adr/2026-09-06-minimap-original-texture-probe.md`.
   Observație independentă nouă: API interior/exterior transportat live în
   addon 0.5.10 și afișat în CC; exteriorul actual returnează nil/1. Verificat
   staționar, 477 teste relevante PASS. UnitPosition/GetPlayerFacing absente
   ca funcții Lua în sesiunea testată. Nu închide etajul, nu înseamnă plafon
   infinit. Urmează asocierea cu semantica geometriei, dacă este disponibilă,
   fără a elimina alternativele pe baza unui plafon nedetectat.
   `adr/2026-09-06-client-environment-api.md`.
   Auditul metadatelor originale demonstrează că AABB + flag interior nu
   diferențiază cele două Z ale criptei; Goldshire are bounds interior/exterior
   suprapuse. Parser offline disponibil, fără integrare runtime. Continuarea
   trebuie să asocieze suprafețe/grupuri, păstrând proveniența asseturilor:
   `adr/2026-09-06-wmo-group-semantic-audit.md`.
   Pas următor realizat offline: triunghiuri per grup, comparare exactă cu
   geometria BVH existentă (1947/1947), hit-uri legate la identitatea grupului.
   Urmează potrivirea candidaților nativi și sigilarea metadatelor înainte de
   CC; un candidat fără hit WMO nu este invalidat (terenul nu este inclus).
   `adr/2026-09-06-wmo-triangle-group-association.md`.
   Asocierea candidatelor native cu suprafețele WMO este acum verificată
   offline cu pack/index/worker controlate; lipsa unui hit nu elimină candidatul.
   Urmează bundle de metadate sigilat, cu acoperire explicită, înainte de CC.
   `adr/2026-09-06-native-wmo-surface-association.md`.
   Bundle sigilat realizat și verificat offline prin observerul de fundal:
   hash extern, legătură exactă la pack/index/BVH, acoperire parțială explicită.
   Opțiunea nu este încă activată în CC; urmează configurație, prezentarea
   dovezilor/limitelor și verificare staționară. 168 teste relevante PASS.
   `adr/2026-09-06-pinned-wmo-observer-bundle.md`.
   Integrarea/afișarea CC este acum activată opt-in și verificată staționar
   (12 mostre, fără erori), cu acoperire lipsă explicită și expirare păstrată.
   176 teste relevante PASS. Nu închide identificarea nivelului actorului.
   `adr/2026-09-06-wmo-evidence-control-center.md`.
   Audit de exhaustivitate: defect condițional al enumerării reprodus în
   fixture C++, dar fără omisiuni găsite în 49 coloane reale de referință.
   Nu schimbă workerul și nu explică singur ambiguitatea nivelului actorului.
   `adr/2026-09-06-height-enumeration-conditional-audit.md`.
   Experiment vizual offline implementat: proiecție din repere 3D–pixeli,
   verificare pe repere separate, ambiguitate păstrată la privire verticală.
   68 teste relevante PASS; două cadre reale inspectate, dar contactul/reperele
   nu sunt încă validate. Urmează adnotări vertex/pixel, nu promovare de Z.
   `adr/2026-09-06-visual-vertical-projection-probe.md`.
   Repere 3D rezolvate acum din vertexuri și transformări verificate; export
   real 164 puncte/269 muchii și 78 teste PASS. Nu sunt încă asocieri pixel/vertex
   confirmate; etapa de calibrare reală rămâne deschisă.
   `adr/2026-09-06-verified-visual-landmark-vertices.md`.
   Progres: proveniență urmărită până la hint/proiecția navmesh; replay-ul
   păstrează două alternative verticale reale, fără a confirma etajul.
   `adr/2026-09-06-vertical-evidence-lineage.md`. Etapa nu este închisă;
   asocierea runtime/CC și dovezile care diferențiază nivelurile urmează.
   Extensie nouă de observație: alternativele sunt acum returnate de worker
   și păstrate în adaptor; build separat verificat pe asset-uri reale, fără
   promovare în v34 sau CC. `adr/2026-09-06-sonar-vertical-candidates.md`.
6. [ ] Incertitudine: examinarea provenienței covarianței/erorii existente și
   calibrare în replay. `position_radius_95` nu devine limită absolută.
   Nu inventăm valori mici doar ca evaluatorul să accepte poziția.
7. [ ] Control Center: afișare asincronă pentru nume API, XY, Z/etaj confirmat
   ori estimat/necunoscut, vârstă și incertitudine; estomparea informației
   expirate. Nu desenăm spațiu liber certificat între sonde radiale sparse.
   Progres în surse: observer sonar asincron, sesiune/hartă/timpi separați,
   altitudine estimată și etaj neconfirmat. Integrare offline cu pack real;
   CC repornit și verificat vizual staționar în LAB, cu date proaspete în
   12 mostre și fără erori sonar. Nu dovedește etajul ori funcționarea în mers.
   Fără plafon detectat nu înseamnă
   infinit și altitudinea nu este număr de etaj.
   `adr/2026-09-06-sonar-session-binding.md`.
   Tab separat Sonar: limite, deschideri și sonde cu direcții world/distanțe
   condiționale. Expirarea golește tabelul; 373 teste relevante PASS și
   verificare vizuală staționară. `adr/2026-09-06-sonar-details-panel.md`.
   Nu închide identificarea etajului, eroarea metrică sau percepția volumetrică.
   Extensie: 64 raze la 0,25 /0,60 /1,20 /1,80 yd față de Z estimat, intervale
   de blocaj și afișare CC verificate offline și live staționar. Păstrează
   golurile dintre raze/înălțimi drept necunoscute. Test nativ și 400 Python
   PASS. `adr/2026-09-06-sonar-height-scan.md`. Urmează dovezi independente
   pentru alegerea nivelului, înainte de folosirea geometriei în decizii.
8. [ ] Validarea offline a traseului netezit și a volumului parcurs în viraj,
   inclusiv timpul până la următoarea reacție. Separarea planner/follower.
9. [ ] O corecție generală, numai după demonstrarea cauzei; teste de regresie,
   apoi o probă LAB delimitată cu film salvat, criterii și rollback. Nu
   declarăm humanlike pe baza ARRIVED și nu extindem etapa la hunting/combat.

## Ce păstrăm stabil

- Navigatorul activ v34; candidatul de clearance respins nu este reactivat.
- Control Center și harta responsivă; nicio operație lentă pe firul UI.
- Anti-AFK: un Space per episod confirmat, fără mișcare periodică. Opt-in
  salvat; guard-ul rămâne limitat la sesiunea lui și necesită dovezi valide.
- Godmode pentru probele LAB, când este autorizată intrarea/testarea.
- Codul și documentația în Git; fără credențiale ori telemetrie brută în Git.

## Regula de acceptare

O etapă se închide pe dovada ei: test de contract, replay, integrare cu
fișier real sau test live sunt lucruri diferite. Fiecare rezultat trebuie
să spună ce rămâne necunoscut și să lase un punct de revenire verificabil.
