# Audit proiect — 2026-08-29

## Verdict final pentru această etapă

Proiectul are un baseline funcțional solid: 1.130 teste au trecut înaintea
curățării, iar 1.132/1.132 trec după remedieri. Noul WorldPack standalone pentru
Azeroth, Kalimdor și Outland este sigilat și verificat independent. Auditul nu a
găsit un motiv tehnic pentru ștergere în masă de source code; volumul mare vine
în principal din date runtime și dovezi, nu din cod duplicat.

## Inventar

- workspace fără `.git` și `.venv`: 96.584 fișiere, aproximativ 12.498 MB;
- `data/`: 95.225 fișiere și 12.478 MB; majoritatea sunt runtime evidence,
  rapoarte, screenshots/video și rezultate de simulare, deci sunt păstrate;
- cod Python: 293 fișiere sursă;
- documentație: 160 fișiere Markdown;
- contracte/config/runtime records: 91.109 fișiere JSON, aproape toate sub
  `data/runtime` și ignorate de Git;
- patru arbori navigation supersedați și nereferențiați ocupă 34.156.598.662
  bytes; sunt enumerați exact în `cleanup-manifest.json`.

## Probleme confirmate și remedieri

1. Control Center putea pierde excepția reală înaintea callback-ului Tk și
   afișa o eroare secundară `undefined name`. Mesajul este acum capturat înainte
   ca block-ul `except` să se închidă.
2. `movement` importa `ContinuousMotionFrame` din `execution`, încălcând
   direcția declarată în `AGENTS.md`. Contractul non-autoritativ a fost mutat în
   `domain.motion`; executorul îl re-exportă pentru compatibilitate.
3. A fost adăugat un test arhitectural AST care respinge importuri outward din
   `brain` și orice import `execution` din `domain`/`movement`.
4. Verificarea statică focalizată pentru undefined/unused/syntax trece fără
   observații. Scanarea extinsă rămasă are 561 observații: 150 import ordering,
   79 broad catches la boundary-uri, 70 recomandări de tip al excepției, 66
   modernizări de import și restul predominant modernizări de stil. Nu aplicăm
   automat sute de rescrieri fără valoare funcțională înainte de Gitea.
5. Existau două ADR-uri cu numărul 0029. Manifestul păstrează conținutul și
   mută al doilea document la următorul identificator liber, 0049.
6. Auditorul navmesh a fost paralelizat, workerii sunt reciclați pe Windows și
   blocurile heightfield ignorate sunt sărite fără copii temporare. Raportul
   paralel rămâne identic cu cel serial.
7. O rescriere automată eliminase accidental facade-ul
   `build_semantic_live_gate_record` din Control Center. Suita completă a prins
   regresia; facade-ul stabil a fost restaurat și verificat.
8. Colecțiile de policy partajate sunt acum declarate explicit și imuabile,
   iar erorile de reparare navmesh păstrează cauza inițială în traceback.
9. `.gitattributes` fixează line endings pentru cod/documentație și marchează
   artefactele binare, pregătind un istoric Gitea mai curat fără renormalizare
   în masă în această etapă.

## Curățare executată

- au fost șterse patru copii navigation supersedate sau invalide:
  34.156.598.662 bytes, aproximativ 31,8 GiB;
- au fost eliminate cache-urile Python, `.pytest_cache`, metadata `egg-info` și
  logul NVIDIA accidental din rădăcina proiectului; toate sunt regenerabile;
- al doilea ADR 0029 a fost păstrat integral și renumerotat 0049;
- WorldPack-ul canonic a rămas neschimbat, cu SHA-256
  `d8a1b65e71602e6513b0d8e711001a23cdfc98ceb2109834ba8a86fa5ef689ac`.

## Ce nu se șterge

Nu se șterg telemetry, replay-uri, clipuri, screenshots, rapoarte de regresie,
zero-byte stderr logs care dovedesc succesul, WorldPack-uri sigilate, repair
source evidence, client assets, server/emulator sau schimbări necomise. Profilele
vechi vor fi migrate înainte de o a doua etapă de consolidare a WorldPack-urilor.

## Verificări finale

- 66 teste focalizate: PASS;
- 1.132 teste complete: PASS în 87,61 secunde;
- verificare statică critică: PASS;
- dependențe instalate: fără conflicte;
- `git diff --check`: fără erori ori avertismente de whitespace/line endings;
- `.gitignore` exclude runtime data, telemetry, replay, clips, secrets, logs,
  mediul virtual și metadata regenerabilă.

Pentru etapa Gitea rămâne intenționat neexecutată doar împărțirea schimbărilor
în commit-uri logice; nu am creat commit-uri și nu am alterat istoricul Git.

## Addendum după reluarea Movement Engine

După închiderea auditului, proiectul a primit controllerul PA-MPPI vectorizat,
corpusul reluabil per ADT și replay-ul exact al coridoarelor reale. Integrarea
live este explicită și asincronă, cu fallback geometric și telemetrie per frame;
nu este încă declarată confirmată în client înaintea holdout-ului filmat.

- smoke real pe Azeroth/Kalimdor/Expansion01: 300/300 variații trecute, zero
  coliziuni;
- coridorul Kalimdor EXTREME: 100/100, maximum 1,775 yd cross-track și maximum
  șase schimbări de sens;
- testele complete au crescut la 1.141/1.141 și trec în 94,36 secunde;
- `pip check`, verificarea statică critică și `git diff --check` rămân PASS;
- nu au fost create commit-uri și nu au fost șterse alte date ale proiectului.

## Addendum holdout live și semantică de drum

Holdout-ul PA-MPPI a găsit două defecte generale care nu apăreau în simulările
locale: facade-ul asincron nu trata frontierele Detour parțiale, iar atlasul de
drum promova o celulă grosieră dacă un singur pixel îi atingea marginea.

- fallback-ul pentru coridoare parțiale este testat și confirmat într-un retry
  live Brill → Deathknell;
- reducerea atlasului este vectorizată, folosește contribuția medie și ancorează
  waypoint-ul în centrul de masă al texturii reale;
- ocolul observat de 59,24 yd pentru o țintă la 13,60 yd dispare; segmentele
  înlocuitoare au raport traseu/direct 1,00;
- validarea 3D integrală crypt/Deathknell/Brill și retur trece, iar fixture-ul
  negativ continuă să ceară reset;
- WorldPack-ul canonic nu a fost modificat în loc și își păstrează identitatea
  sigilată. Corecțiile sunt în interpretarea standalone și în generatorul
  sidecar-urilor viitoare.

## Addendum confirmare live în ambele sensuri

Corecția semantică a fost promovată din dovadă offline în holdout live filmat:

- Brill → Deathknell: `ARRIVED`, 116/116 waypoint-uri, 2.613 cadre de control,
  zero replanificări parțiale și zero recovery;
- Deathknell → Brill: `ARRIVED`, 117/117 waypoint-uri, 2.698 cadre de control,
  zero replanificări parțiale și zero recovery;
- eșantionarea integrală a celor două clipuri și fereastra de 30 de secunde din
  zona fostei abateri confirmă că actorul rămâne pe potecă în ambele sensuri;
- clipurile sunt capturate de NVIDIA ca `Wow.exe`, 2560×1440, nu desktop;
- suita completă curentă are 1.147/1.147 teste trecute; `pip check`, Ruff critic
  și `git diff --check` rămân curate.

Auditul nu declară încă steeringul flawless. ME-043 păstrează deschisă reducerea
fallback-urilor MPPI și a micro-inversărilor observate în telemetrie; sosirea la
destinație nu este folosită ca substitut pentru fluiditate humanlike.

## Addendum research și separarea nucleului autonom

Research-ul comparativ cu mod-llm-playerbots, DaemonCraft/Gemma,
WowClassicGrindBot, Recast/Detour, Nav2 MPPI/RPP, Voyager și DAgger confirmă o
arhitectură hibridă: geometria și controlul rămân deterministe, iar un model AI
este opțional și asincron pentru obiective, curriculum și analiza eșecurilor.

- `MovementObservationPort` separă pentru prima dată motorul de adaptorul DXGI;
- fabrica de observații poate primi ulterior replay sau telemetrie autorizată
  fără a modifica motorul;
- toate căile Python fixe către `E:\WoWserver` au fost înlocuite cu rădăcini
  relocabile și override-uri de environment;
- vechiul UI `run_predator_control.py`, neexecutat de entrypoint, a fost redus
  de la 199 la 15 linii și păstrează shortcut-urile existente;
- bugul `__all__` suprascris și diagnosticul Ruff F841 au fost reparate;
- au fost eliminate numai cache-uri regenerabile, două atomic-write tmp vechi
  și un PID mort; evidence/runtime/WorldPack/native builds au fost păstrate;
- 1.171/1.171 teste complete trec în 92,57 secunde; Ruff critic, `pip check` și
  `git diff --check` trec.

Clarificarea operatorului permite captura read-only și HUD-ul optic ca adaptor,
dar nu logică de tip pixel-click. Core-ul rămâne standalone; fără adaptor optic
sau altă sursă autorizată nu există feedback live suficient pentru closed-loop
pose/facing, iar lipsa lui este tratată fail-closed.
