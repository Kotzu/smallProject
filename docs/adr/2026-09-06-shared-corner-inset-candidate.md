# Candidat offline: păstrarea razei la un colț comun

## Decizie ulterioară: respins după proba live

La 2026-09-06, candidatul a fost instalat temporar prin CC și testat o dată.
ARRIVED în 84,461 s, dar evaluatorul nemodificat FAIL; nu se promovează.
CC și gate au revenit la v34. Dovezi și limite de captură:
`../LIVE_CORNER_CANDIDATE_REJECTION_2026-09-06.md`.
Textul următor descrie stadiul istoric offline, nu starea runtime curentă.

Status: implementat și testat offline; NU instalat în Control Center, NU Stable.
Proba live necesită reintrarea operatorului în world: clientul observat prin
computer-use afișează `Disconnected from server`, la ecranul de autentificare.
Nu s-a automatizat autentificarea și nu s-a trimis input de mișcare.

## De ce revenim la un candidat restrâns

Încercarea din `2026-09-06-capsule-inset-reproduction.md` a fost respinsă ca
rezolvare a întregii probleme de pe scară: mostra 108 nu se îmbunătățea.
Acea constatare rămâne valabilă. Candidatul de aici corectează numai pierderea
razei prin media inset-urilor la colțuri comune, nu toate sondele scurte și
nici abaterea controlerului. Nu declarăm retrospectiv încercarea inițială PASS.

După experimentul Recast și extinderea testelor de invariabilitate, reținem
această corecție mică pentru o viitoare probă delimitată, fără rebake global.
Nu este suficientă dovadă pentru schimbarea versiunii active.

## Proveniență verificată, cu limite

- `Nav/Azeroth/28_28.nav` din pack-ul activ corespunde exact dovezii de repair:
  SHA256 `f4231e077a47421e838940cab3ead6244edcc155a3b5ccd6ce2d5c0922de7ebd`.
- Validarea structurală a acelui ADT: 255 tile-uri Detour și un tile gol.
  Toate cele 255 headere au height/radius/climb = `1.8 / 0.9 / 0.6`.
- Dovada bundled leagă tile-ul de pack-ul `azeroth-full-v3-repair-source`;
  nu include sursa completă/configurația compilatorului care a produs bake-ul.
- Sursa locală actuală `SerializeMeshTile` nu apelează `rcErodeWalkableArea`.
  Este dirty și nu a fost modificată. Header-ul radius 0.9 nu dovedește
  erodarea; nu afirmăm că am reconstruit proveniența completă a tuturor ADT-urilor.

## Experiment Recast independent de asset-uri

`recast_erosion_test.cpp` folosește biblioteca locală și dimensiunile din
`Common.hpp`, cu pardoseli voxel sintetice. Nu apelează întregul MapBuilder,
nu reprezintă geometria reală din criptă și nu reconstruiește WorldPack-ul.
Sunt verificate și conexiunile dintre trepte de 0.25 yd, nu numai numărul
celulelor. Conectarea compactă reproduce limita de climb nelimitată folosită
în prezent de `SerializeMeshTile`; nu certifică filtrele fizice ale bake-ului.

| Lățime inițială | După erodare cu 3 celule | Conexiune centrală |
|---|---:|---|
| 1.78571 yd / 6 celule | 0 celule | eliminată |
| 2.38095 yd / 8 celule | 2 celule | păstrată |
| 3.57143 yd / 12 celule | 6 celule | păstrată |

Aceleași rezultate pe plat și pe scări: șase cazuri PASS. Cazul îngust este
mai lat decât corpul + marja de tracking din worker (diametru 1.378 yd), dar
mai îngust decât diametrul conservator 1.8 yd. De aceea nu aplicăm erodarea
globală ca reparație simplă și nu micșorăm raza ca să forțăm un PASS.

## Schimbarea de producție, încă nedeployată

În `inset_funnel_corners`, numai când mai multe portaluri orizontale coincid
cu același colț XYZ (toleranță 0.0001), media XY este normalizată la raza
existentă 0.90 yd dacă aceasta s-a contractat. Z păstrează media portalurilor.
Portalurile înclinate sunt excluse: extinderea numai în XY ar lăsa Z în afara
planului lor. Nu înlocuim această verificare cu o presupunere despre scări.
Direcțiile care se anulează rămân neschimbate; nu se inventează o direcție.

Nu schimbăm pragul de lățime, capsulele, filtrele, navmesh-ul, camera,
controlerul, evaluatorul sau permisiunile. Verificările existente ale
traseului rămân active. Schimbarea NU oferă o garanție nouă că fiecare
segment este sigur față de orice geometrie fizică.

Testul generic anterior roșu trece acum în cele trei rotații. Alte nouă cazuri
verifică: lipsa portalurilor, un singur portal, pasaje înguste, direcții opuse,
colțuri apropiate dar distincte, alt Z, plan înclinat, direcții duplicate și
translație. Cazul planului înclinat protejează împotriva deplasării XY cu Z
neschimbat; nu certifică marja capsulei pe panta păstrată.

Interogarea independentă pe asset-uri produce 61 puncte în loc de 63, tot
3 inset-uri și zero segmente doodad nerezolvate. Lângă poziția istorică 103,
sonda minimă a punctului de traseu proiectat crește de la 1.40625 la 2.15625 yd.
La 108 rămâne 0.5625 yd, iar la 133 rămâne 1.125 yd. Sunt comparații de traseu
proiectat, NU predicții ale poziției executate și NU distanțe fizice certificate.

## Verificări și rollback

- Două teste CTest, 18 cazuri C++ distincte, PASS.
- 417 teste Python relevante, PASS: movement engine 255; client navigation
  runtime 100; clearance segment 7; semantic live gate 4; geometry replay 5;
  semantic navigation 5; trace evidence 9; live trace quality 20; smoothing 12.
- Prima variantă a trecut toate cele șase trasee semantice (529 etape).
  După introducerea protecției pentru pante, interogarea locală păstrează
  aceeași îmbunătățire la mostra 103. Rerularea pe executabilul final s-a
  încheiat cu exit 0: toate cele șase cazuri PASS, 529 etape. Sunt cinci
  sosiri semantice offline și refuzul corect `partial_local_navmesh_corridor`
  în cazul care cere reset; nu sunt șase deplasări executate în joc.
- Dovezi ignorate de Git: `data/runtime/operator/live-evidence/20260906-corner-candidate/`;
  rezultat final `semantic-validation-with-slope-guard.json`, SHA256
  `F02F8D47B17808E7B208391C22DB43806CDA2A523C872F64CBCCE5709DFCC8C9`.
  Hash-ul executabilului candidat a fost verificat înainte și după rulare.
- Worker candidat izolat:
  `data/runtime/native-build/pa-nav-clearance-test/Debug/pa_nav_probe.exe`,
  SHA256 `CA2B19DEF8517AFBDAD9DED7FACDE66E7E86D74182744A426A527F03DB7935F3`.
- Worker activ v34 nemodificat:
  `CB3555065C56A40C45C73D929A89BDA6F8237FE5FFA2E018FCE50FAC84821D3D`.
  CC, graph-worker binding, gate-ul semantic, WorldPack-ul și memoria
  obstacolelor nu au fost schimbate. Nu este necesar rollback de runtime.
- Baza de cod dinaintea candidatului: `55c71b3`. Revenirea se face prin
  revert-ul commitului candidat `7015e3f`, nu resetarea worktree-ului utilizatorului.

Verificarea finală a mediului: clientul WoW PID 10756 există, dar are zero
conexiuni TCP stabilite; se confirmă astfel impedimentul observat vizual la
autentificare. Gate-ul semantic activ păstrează hash-ul worker-ului v34.
Nu s-a pornit o nouă probă, nu s-a relansat clientul și nu s-a modificat CC.

## Înaintea oricărei probe viitoare

1. Operatorul reintră în world; se confirmă clientul LAB, godmode + stay-online.
2. Se decide explicit instalarea candidatului pentru o singură probă, cu
   checkpoint și worker activ păstrat. Worker-ul de structure awareness trebuie
   să rămână cel al hash-ului grafului; nu se rescrie acel hash pentru a trece.
3. Gate semantic validat pentru executabilul efectiv instalat, apoi armare
   limitată și probă filmată prin CC, la același început și aceeași destinație.
4. Comparație separată: traseu, abatere, colțul modificat, celelalte colțuri,
   sosire și aspect vizual. ARRIVED singur nu justifică promovarea Stable.
