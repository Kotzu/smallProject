# PA-024B3 — Visible self-coordinate HUD v0.1

## Outcome

`PASS PA-024B3b — exact-version 0.3.5 controlled-live complete; PA-024B3c zone transition pending`

Sursa primară de localizare 2D pentru TBC 2.4.3 este implementată read-only:
API-ul public al addonului pentru poziția propriului caracter, transportat prin
HUD vizibil și decodat cu CRC. Minimap vision rămâne cross-check/fallback.
Acest rezultat închide smoke-ul exact-version PA-024B3b, nu promovează încă
profilul către pose fusion sau actuator.

## Livrat

- export schema `0.3` cu `map_position_snapshot` strict și capability
  `map_coordinates`;
- semantic capability `self_map_position`; global/server positions rămân
  indisponibile;
- addon Observer exact `0.3.5`, cu text lizibil, fiducials, grid de 96 biți și
  CRC-16;
- codec Python deterministic și golden vector comun;
- detector BGRA8 tolerant la translație și scale, verificat sintetic și pe
  raster real;
- probe one-shot și multi-frame exact PID/HWND/build/hash, RAM-only;
- freshness gate modulo-256 cu limită de stagnare `600 ms`;
- actor binding configurat așteptat și `authorization_sha256` propagate din
  captura autorizată; numele personajului nu este prezentat ca identitate
  observată;
- contract de observație care impune `execution_authority=false`;
- cazuri negative pentru CRC corupt, HUD absent, build mismatch și poziție
  indisponibilă;
- SavedVariables rămâne audit/replay și include numai snapshoturi
  client-observed.

## Identitatea deploymentului 0.3.5

Clientul LAB a rulat exact cele trei artifacts hash-pinned:

- `PerfectAssassinObserver.lua`:
  `F091298093DE17549FF14E184FCD317EA98D40633B8916E81223345297F3D7D6`;
- `PerfectAssassinObserver.toc`:
  `160BABA2DDC417E0B9C12396C057721AC8D74B753DAEAF0DC78E5A896F613EF8`;
- `README.md`:
  `426519B0404F3A54CDA112E8925B47F5424ED23CAD3278CD90EFC5B164345759`.

Identitatea byte-exactă dovedește ce addon a rulat; nu autorizează movement și
nu transformă actorul configurat într-un personaj observat automat.

## Controlled-live run 1 — matricea exact 0.3.5

Pe același client LAB `2.4.3.8606`, cu pixelii păstrați numai în RAM:

| Caz | Rezultat |
|---|---|
| baseline `2048×1536`, UI scale `1.0` | `10/10` VALID |
| world map deschis | fail-closed `observation_not_valid`, fără poziție |
| world map închis | recovery, apoi `10/10` VALID |
| baseline, UI scale `0.8` | `10/10` VALID |
| compact `1628×1219`, UI scale `0.8` | `10/10` VALID |
| compact, UI scale `1.0`, prima încercare | `NoFreshCaptureFrameError`, fail-closed |
| compact, UI scale `1.0`, retry după checkpoint | `10/10` VALID |
| baseline restaurat, UI scale `1.0` | `10/10` VALID |

Prima încercare compact/1.0 nu este mascată drept pass: providerul nu a primit
un frame nou și a refuzat corect observația. După un checkpoint explicit,
retry-ul independent a trecut `10/10`. La final UI-ul a fost restaurat, apoi s-au
executat logout și close normale.

## Controlled-live run 2 — relaunch/relog independent

Un al doilea launch/login/enter-world a creat o sesiune nouă:
`session:pa024b3b:035-relaunch`.

- rezultat HUD: `10/10` VALID;
- sequence advances: `5`;
- sequence duplicates: `4`;
- maximum frame age: `8.373 ms`;
- pixel persistence: none;
- logout și close: normale;
- import SavedVariables final: `12` observations, `12` decisions și `18` raw
  combat events.

Importul este evidence offline observe-only. Raw combat events nu capătă
semantică suplimentară și nu devin server truth.

## Controlled-live run 3 — current-source hardening resmoke

După hardening-ul source binding/timestamp/least-privilege, traseul final a fost
reluat pe sursa curentă, nu dedus din testele anterioare:

- authorization ID: `execution:tbc243-lab:bounded-fixed-ui`;
- authorization SHA-256:
  `DBA02BD441956333FF6F1A37953A334834CD926C6B49937FC7765D5C10BA6F50`;
- `permitted_modes=[]`; fixed-UI a fost permis numai prin capabilitatea separată
  `LAB_OPERATOR_FIXED_UI`;
- sesiune: `session:pa024b3b:035-final-source`;
- source binding: PID `52524`, HWND `0x641526`;
- rezultat HUD: `10/10` VALID;
- sequence advances: `4`;
- sequence duplicates: `5`;
- maximum frame age: `7.883 ms`;
- age la validarea summary-ului final: `33.422 ms`;
- logout și close: normale;
- import SavedVariables: `12` observations, `12` decisions și `20` raw combat
  events.

Acest al treilea run a exercitat împreună capabilitatea fixed-UI cu zero
Predator modes, authorization hash-ul curent și traseul de captură harden-uit.

## Controlled-live run 4 — atomic runtime-arm final

După ultima corecție fail-closed care leagă parsarea și hash-ul runtime arm de
același snapshot de bytes, traseul exact curent a fost reluat integral:

- sesiune: `session:pa024b3b:035-atomic-arm-final`;
- source binding: PID `64056`, HWND `0x4A025E`;
- authorization ID/hash identice cu run 3 și `permitted_modes=[]`;
- rezultat HUD: `10/10` VALID;
- sequence advances: `5`;
- sequence duplicates: `4`;
- maximum forward delta: `1`;
- maximum unchanged interval: `100.345 ms`;
- maximum frame age: `7.663 ms`;
- age la validarea summary-ului final: `34.499 ms`;
- pixel persistence: none;
- `execution_authority=false`;
- logout și close: normale, receipt-ul și runtime arm-ul eliminate;
- import SavedVariables: `12` observations, `12` decisions și `16` raw combat
  events, dintre care `0` interpretate.

Run 4 închide caveatul exact-current-source: inclusiv runtime-arm snapshot-ul
atomic a fost exercitat live, iar rezultatul tehnic a rămas strict observe-only.

## Parity și corecții descoperite

Checkpoint-ul numeric de parity anterior a comparat observația HUD
`(0.2946059358, 0.6465247578)` cu snapshotul Tirisfal SavedVariables
`(0.2946131527, 0.6465227604)`. Erorile `7.217e-6` și `1.997e-6` sunt sub
jumătate de LSB `7.630e-6` al payloadului `uint16`. Matricea, relaunch-ul și
current-source resmoke-ul de mai sus adaugă dovada exact-version 0.3.5; nu
rescriu retroactiv originea checkpointului numeric.

Primele rulări reale au expus două incompatibilități corectate: clientul legacy
nu oferă `math.mod`, iar candidații UI colorați puteau preceda fiducials în scan
order. Encoderul folosește modulo aritmetic compatibil, iar detectorul
prioritizează componentele solide mari. `0.3.5` re-ancorează suplimentar
contextul hărții la fiecare măsurare pentru a nu moșteni contextul altui addon.

## Verification boundary

- la checkpoint-ul rollback/exact-smoke, suita repository a trecut `221/221`;
- după hardening și înaintea freeze-ului documentației, suita completă a
  trecut `234/234`;
- rollback-ul izolat `0.3.5 → 0.3.4 → 0.3.5` a trecut cu hash-urile celor trei
  artifacts reverificate;
- CRC standard check vector `123456789 -> 0x29B1`: pass;
- translated + `1.5×` scaled synthetic HUD: pass;
- corrupted CRC, missing fiducials, unavailable coordinates și build mismatch:
  fail-closed.

`221/221` rămâne numărul exact al checkpoint-ului rollback, nu totalul final.
Hardening-urile ulterioare au atât `234/234` test evidence, cât și exact-current
controlled-live evidence din run 4. Documentația nu schimbă runtime behavior;
suita finală se rerulează totuși după freeze-ul tuturor editărilor dacă working
tree-ul mai primește modificări.

## Limite și gate următor

- profilul rămâne prudent `synthetic_verified` până la cardul separat de zone
  transition;
- map coordinate este normalizată în harta zonei curente; transformarea 2D este
  PA-024B4, iar proiecția pe navmesh/height este încă pending;
- camera/body yaw provider rămâne separat;
- checkpoint-urile operatorului sunt audit vizual; gate-ul tehnic folosește
  client-region DXGI exact și DPI-aware;
- PA-024B3c rămâne pending: un LAB clone separat de Champion Journey trebuie să
  treacă o tranziție reală de zonă, să refuze primul context stale și să se
  recupereze numai după map refresh;
- numai după PA-024B3c profilul poate fi promovat și measurement-ul legat de
  pose fusion. Până atunci nu alimentează actuatorul.
