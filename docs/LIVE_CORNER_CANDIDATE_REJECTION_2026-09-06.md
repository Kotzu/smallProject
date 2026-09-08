# Predator — candidat respins după proba LAB

## Verdict

Candidatul geometric `7015e3f`, conectat reversibil prin `922f160`, nu se
promovează. Testele offline au trecut, dar singura probă live este o regresie
față de diagnosticul anterior. ARRIVED nu înseamnă humanlike sau clearance bun.
Nu a fost făcută o a doua corecție sau o a doua rulare.

## Condiții și rezultate confirmate

Start CC: 2026-09-06T08:31:53.173Z. Destinație Deathknell, plecare canonică
Shadow Grave, godmode și stay-online reafirmate ON, fără combat/hunting,
fără input manual de cameră sau deplasare în timpul probei.
Navigator candidat SHA256 `ca2b19def8517afbdad9ded7facde66e7e86d74182744a426a527f03db7935f3`;
producătorul grafului rămâne v34, verificat separat; graful nu este relabelat.
Poziția și heading-ul primei decizii coincid între probe:
XY 1676.36957516998, 1677.46695761255; heading 2.55878816750034 rad.
Ambele au încărcat 8 obstacole. Primul lookahead diferă în Y cu circa 0,343 yd.

| Indicator | Diagnostic v34 anterior | Candidat |
| --- | ---: | ---: |
| Sosire | ARRIVED | ARRIVED |
| Durata jurnalului de control | 33,571 s | 84,461 s |
| Cadre de control | 626 | 1036 |
| Cadre fără progres cu mers înainte | 0 | 87 |
| Cadre de pivotare | 9 | 116 |
| Recuperări | 0 | 4 |
| Întreruperi observații >300 ms | 8 | 43 |
| Întreruperi nejustificate de continuitate | 0 | 25 |

Evaluatorul existent, fără praguri relaxate, raportează `passed=false`:
`excessive_stationary_pivot`, `forward_input_without_progress`,
`control_observation_gap`; gap maxim 6,469 s, lipsă progres maximă 1,899 s.
Proveniența facing, separarea corp/cameră și integritatea camerei sunt prezente
în toate cele 1036 cadre; aceasta este completitudine de jurnal, nu validare vizuală.

Primul `no_progress_s > 0.5` apare la cadrul 68, XY aproximativ 1655,55 / 1675,19,
abatere transversală circa 1,49 yd. Prima replanificare după coliziune este în
acea zonă. Mai târziu sunt recuperări la circa 1669,70 / 1661,13, pe stratul superior.
Acestea delimitează analiza următoare; nu demonstrează singure dacă obstacolul,
eroarea de tracking sau forma coridorului declanșează primul contact.
Nu atribuim toate pauzele candidatei native fără replay și profilare.

## Captură eșuată — corectarea afirmației inițiale

NVIDIA a afișat timerul `00:00:00` și „Stop and save”, însă jurnalul său arată:
11:31:20.384 `CaptureState: 1`; 11:31:20.785 `Received Protected Content running
notification`; 11:31:20.835 `CaptureState: 0`, sesiune distrusă.
Nu există clip nou în destinația configurată sau în temporarele verificate.
Prin urmare proba NU este o verificare filmată completă. Capturile intermediare
ale ferestrei și jurnalul nu înlocuiesc filmul. A fost greșit să se considere
timerul inițial suficient pentru a porni testul. Pe viitor, înaintea oricărei
probe autorizate, se verifică persistența capturii și un fișier valid.
Nu se dezactivează și nu se ocolește protecția pentru conținut protejat.
Permisiunile de securitate/confidențialitate rămân acțiuni ale operatorului.

## Dovezi locale și rollback

Arhivă ignorată de Git: `data/runtime/operator/live-evidence/20260906-corner-candidate/`.
Include rezultat, supervisor, log motor, raport evaluator, gate înainte/după,
obstacole înainte/după, memoria recuperărilor după test și log NVIDIA.
`trial-archive-manifest.json` conține hash-uri. Rezultatul
`navmesh-roaming-9d231880-b9fa-40f9-b738-c94c2342799c.json` are SHA256
`130c79c4142440d7392fdf116187b3551a3f50c361ecfa2eb94567b70d14b305`.
Evaluator: `live-trace-quality.json`. Baseline: run
`8544bb3c-f0f6-41f1-84d5-8e7952458f56`, raport `LIVE_CRYPT_DIAGNOSTIC_2026-09-06.md`.

CC candidat închis după oprirea navigatorului. Gate-ul original a fost restaurat
byte-exact folosind verificarea identității candidatului și a artefactelor.
Memoria obstacolelor a fost arhivată și restaurată byte-exact: 62 înregistrări
pre-probă față de 46 după expirare/actualizare; numai două înregistrări prezente
aveau conținut nou, ambele atribuite exact run-ului candidat. Nicio modificare
a altui run nu a fost suprascrisă. Cele două sunt recuperabile în arhivă.
Memoria strategiilor de recuperare după probă conține doar trei intrări istorice;
nu există snapshot pre-probă verificat, deci nu se pretinde restaurare byte-exact
a acesteia. Baza append-only de experiență dinamică nu a fost ștearsă/modificată
de rollback; observațiile probei rămân istoric, nu dovadă de promovare.
WorldPack, graful, executabilul v34 și shortcut-ul nu au fost suprascrise.
CC relansat normal, fără flag candidat; motor oprit, control manual Codex OFF.
La redeschidere selectorul implicit este Brill; nu a fost pornită deplasarea.

## Continuare delimitată

Stabilizarea rămâne neîncheiată. Următorul pas propus este replay offline al
primelor 80 de cadre și al primului coridor, comparat cu v34, păstrând camera și
controllerul constante. Abia după identificarea cauzei se decide o nouă corecție
și o probă autorizată cu captură verificată. Nu se hardcodează cripta și nu se
adaugă combat, hunting sau alte funcții ca substitut pentru stabilitate.
