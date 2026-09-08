# Candidat delimitat: rezerva de rotire în coridor geometric

## Verdict: nepromovat, controller restaurat

Proba live 59fe4963-f03e-4aba-82b0-59054981fa52 pe candidatul 8aa5af8:
OPERATOR_STOPPED, 296 cadre totale, 158 înaintea handoff-ului de ieșire,
zero recuperări și patru cadre PIVOT, ca în baseline.
Film valid: crypt-geometric-turn-budget/crypt-c09-20260907-170331.mp4,
105.833333 s, 2999 cadre, 2560×1440; prima decizie la ~84.295 s în film.

| Metrică înaintea handoff-ului | Baseline ebd340cd | Candidat 59fe4963 |
|---|---:|---:|
| Abatere maximă | 2.161 yd | 1.981 yd |
| Schimbări semn comandă FOLLOW | 7 | 9 |
| Timp până la ultima observație pre-handoff | 9.998 s | 10.085 s |
| Cadre PIVOT | 4 | 4 |
| Recuperări | 0 | 0 |

Acesta nu este timpul ieșirii complete a corpului. Numărul de schimbări de
semn este al comenzii, nu numărul de oscilații vizibile ale camerei.
Reducerea modestă a abaterii nu dovedește un câștig de clearance fizic;
camera își schimbă în continuare distanța în spațiile înguste. Nu există
câștig clar global de naturalețe/timp, deci candidatul NU este promovat.
Nu se pretinde o regresie fizică de contact care nu a fost măsurată.

Controllerul revine byte-exact la 7b0dfe0; testul specific rezervei extinse
este eliminat din suita activă, recuperabil în 8aa5af8. Indexul memoriei,
tratarea Stop, Anti-AFK și v34 rămân. Filmul/rezultatele sunt arhivate în
runtime ignorat. Urmează evaluarea volumului și a distanțelor în viraj,
nu creșterea repetată a plafonului de rotire sau modificarea camerei ca mască.

## Dovezi înainte de intervenție

Baza 7b0dfe0, film/run ebd340cd. Replay geometric 140/140 exact pe v34.
Abaterea maximă de 2.995 yd a întregii probe apare la cadrul 160, după
schimbarea coridorului spre ieșire; nu este același defect cu primul palier.
În interior, cadrul 82 la ~5.497 s: 2.161 yd. Cadrele 73–83 cer constant
-720 px/s; heading-ul și observațiile rămân surse client, nu adevăr server.

Selecția pe trepte a anticipării produce salturi: între cadrele 64/65
unghiul curbei trece 0.304→0.513 rad, distanța aleasă scade 5.965→2.75 yd;
la 79/80 distanța scade 5.149→2.75 yd. Interpolarea între praguri a fost
încercată numai offline, fără câștig: 98/100 quality, aceeași abatere maximă
2.715 yd. Nu este aplicată în producție.

La conversia actuală 0.0026 rad/pixel, 720 px/s înseamnă 1.872 rad/s.
La 8 yd/s, raza cinematică minimă este ~4.27 yd, fără întârziere. Aceasta
este predicție din calibrarea existentă, nu măsurare nouă de yaw/capsulă.
Bugetul contractului/gateway-ului existent este deja 960 px/s.

Simulare cinematică pe întreg coridorul real, 100 aceleași seed-uri,
variații inițiale și viteză 6.5–8.5 yd/s: candidat max 12 versus 9:
max cross-track 2.715→2.239 yd, p95 2.323→1.918, quality 98→100/100,
zero pivotări, maxim trei schimbări de semn în ambele cazuri. Simularea nu
conține zidurile fizice: collision_runs=0 nu certifică evitarea lor.

## Schimbarea pusă în probă

ContinuousTrajectoryFollower permite până la 12 unități ×80 px/s numai
pentru FOLLOW cu geometrie. Deschis fără geometrie și PIVOT păstrează 9.
Slew rămâne 4 unități/cadru; nu se schimbă lookahead, yaw calibration,
praguri de acceptare, v34, camera, planner, securitate sau viteza personajului.
Nu există coordonate/nume de locație în regulă. Limita domain nu este mărită.

302 teste relevante PASS: follower/smoothing, engine, adaptive, cache XYZ,
mișcare/gateway și operator Stop. Cinci teste noi verifică 4→8→12, plafonul
existent, slew, pivot și traseu fără geometrie neschimbate, mers drept.

## Probă și acceptare

Probă CC din același start canonic, v34, godmode LAB, film și watchdog18s.
Urmează comparația segmentului interior, inclusiv primul palier, nu maximul
global după handoff. Cerințe: fără recuperări/blocaje noi, fără pivotări noi,
abatere interioară redusă și film fără regresie vizibilă. Nici acest candidat
nu certifică întregul volum sau humanlike repetabil. Dacă regresează, revenim
la 7b0dfe0 numai pentru schimbarea controllerului; optimizarea memoriei rămâne.

După revenire: 292 teste relevante PASS; diff-ul controllerului față de
7b0dfe0 este gol. Testele candidatei eliminate sunt recuperabile în 8aa5af8.
Readucere canonică și godmode LAB confirmate după închiderea proceselor.
