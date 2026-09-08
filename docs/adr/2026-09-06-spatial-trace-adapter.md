# Adaptor spațial peste înregistrarea reală, fără completări fictive

Status: implementat și verificat în replay, fără integrare runtime/CC.
Continuă `2026-09-06-observed-spatial-context.md`. Navigația v34, addonul,
anti-AFK, camera și procesele live nu sunt modificate de acest pas.

## Decizie

`adapter/spatial_trace.py` citește formatul existent `navmesh_roaming_result`
0.1. Asociază observația deciziei, nu poziția de după comandă, cu ultima
actualizare geometrică deja prezentă în ordinea evenimentelor și aplicată
unei observații cel mult la fel de noi. Nu caută geometrii viitoare în restul
fișierului și nu reutilizează geometry finală pentru întregul parcurs.
Referințele includ hash-ul fișierului și indexul exact al evenimentului.

Asocierea rămâne evidență istorică parțială: XY observat, Z proiectat separat,
originea interogării, poziția rezolvată de navmesh, vechimea relativă la
observația poziției, deplasarea XY și trunchierea setului de limite.
Nu promovează valorile de confidence inventate în câmpuri suplimentare.
Formatul 0.1 nu transportă dovada completă de localizare necesară pentru
`SpatialPoseEvidence`; adaptorul nu apelează evaluatorul XYZ cu un Z fals.
Eticheta `client_visible_pose` din jurnal nu autentifică singură sursa;
acesta nu este un canal de ingestie de încredere pentru Champion.

## Subtilitate temporală confirmată

În runner, `applied_to_pose_observed_monotonic_s` este timestamp-ul poziției,
nu ora aplicării rezultatului geometric. Rezultatul asincron poate fi mai
nou decât poziția, deși este deja disponibil înaintea deciziei. Prima
versiune a adaptorului respingea eronat acest caz; replay-ul real l-a expus.
Acum păstrează diferența semnată ca `geometry_age_relative_to_pose_s`, cu
motivul `GEOMETRY_OBSERVED_AFTER_POSE`, nu drept prospețime garantată.
Ordinea evenimentelor este păstrată. Nu avem timestamp-ul exact al evaluării
deciziei și nu îl substituim cu timestamp-ul observației.

## Rezultate reale

Înregistrare `8544bb3c-f0f6-41f1-84d5-8e7952458f56`, SHA256
`e2e220e4879f00baffdb72a9546084719cf5d408c3b772bda20cf88877a0a511`:

- 626 decizii și 166 actualizări geometrice procesate.
- 620 decizii cu geometrie anterioară asociată; primele 6 fără asemenea
  actualizare locală. Nu înseamnă că navigatorul nu avea coridor inițial.
- 578 decizii au deplasare XY de peste 0,30 yd față de originea interogării.
  Pragul aparține diagnosticului existent; nu este un nou prag de oprire și
  nu dovedește că geometria sau deplasarea erau nesigure.
- 9 decizii au rezultat geometric mai nou decât observația poziției.
- 626/626 nu oferă în acest format Z observat, etaj confirmat, confidence
  al poziției și eroare metrică. Nu se deduce că întregul proiect nu dispune
  de alte estimări; lipsesc din această dovadă exactă.
- Zero poziții spațiale complete certificate. Nicio distanță la un zid
  fizic nu este inventată; `execution_authority=false`, spațiu necertificat.

Raport local ignorat de Git:
`data/runtime/operator/live-evidence/20260906-spatial-context/replay-8544bb3c-verified.json`.
WorldPack-ul este identificat prin hash-ul înregistrat, nu rehash-uit complet.
Nu s-a executat worker de navigație sau interacțiune cu jocul/serverul.

## Teste și reproducere

97 teste relevante PASS în 2,23 s: adaptor, CLI, context spațial, dovezi de
decizie, fuziune, awareness, limite arhitecturale, replay geometric, audit
clearance și anti-AFK. Verificările statice și diff-check trec.
CLI limitează fișierul la 64 MiB și refuză suprascrierea rapoartelor.
Un test separat acoperă consola Windows cp1252 și păstrarea raportului UTF-8.

```powershell
.venv/Scripts/python.exe scripts/replay_spatial_context.py data/runtime/navigation-f3b/results/navmesh-roaming-8544bb3c-f0f6-41f1-84d5-8e7952458f56.json --output data/runtime/operator/live-evidence/20260906-spatial-context/replay-new.json
```

## Următorul pas

Înaintea unui panou CC cu distanțe, legați contractele de fuziune existente
de dovada de etaj/Z și eroare metrică, păstrând separat estimările și
observațiile. Nu transformați o incertitudine statistică într-o garanție.
CC trebuie să afișeze inclusiv starea parțială/necunoscută și vârsta datelor,
asincron; nu este încă implementată această afișare. Apoi evaluatorul XYZ
poate fi conectat când premisele lui sunt efectiv satisfăcute.

Rollback: retragerea exclusivă a adaptorului, CLI-ului și testelor noi;
niciun consumator live nu le importă. Nu schimbăm praguri în motor pentru
a forța rezultatul verde și nu confundăm această etapă cu repararea virajelor.
