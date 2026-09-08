# ADR-0007 — External LAB client operator

- Status: accepted
- Date: 2026-08-22

## Context

Operatorul uman poate lipsi de la calculator în timpul unei probe controlate. Avem nevoie să putem porni clientul, autentifica contul LAB, intra/ieși din lume, face checkpoint-uri și importa SavedVariables fără să confundăm această operare cu Predator Brain sau cu un capability de movement/combat.

Clientul legacy are proveniență necanonică și `Wow.exe` raportează `Authenticode: HashMismatch`. UI-ul este dinamic; coordonatele singure nu sunt dovadă că ecranul a ajuns în starea așteptată.

## Decision

Introducem `scripts/Invoke-LabClientOperator.ps1` ca harness extern, separat de `src/perfect_assassin` și de execution gateway.

Harness-ul expune numai faze finite și acțiuni de calibrare cu input fix:

```text
Status → Launch → ArmSession → Login → InspectAddons → EnterWorld → Capture
       → OpenWorldMap / CloseWorldMap
       → ReloadUi
       → SetUiScale80 / SetUiScale100 / RestoreUiScaleDefault
       → ResizeWindowCompact / ResizeWindowBaseline
       → Logout → Close → Import
       → DisarmSession (oprire explicită a autorității cât clientul rămâne deschis)
```

Reguli:

- `Launch` cere explicit `-AcknowledgeClientRisk`;
- authorization JSON este validat brut prin schema v2.0 înainte de
  `ConvertFrom-Json`; approval-ul trebuie să fie deja înregistrat, neexpirat dacă
  are `expires_at`, `permitted_modes` trebuie să fie gol, iar capabilitatea
  auxiliară `LAB_OPERATOR_FIXED_UI` trebuie să fie explicit permisă; aceasta nu
  autorizează movement, combat sau `FULL_AI`;
- `actor_binding` leagă exact instanța, LAB clone-ul, namespace-ul de memorie,
  caracterul așteptat și aliasul credentialului; `decision_context` este derivat,
  nu ales de caller, iar caracterul rămâne `configured_expected_only` până la
  confirmarea client-visible;
- listener-ele LAB trebuie să existe exclusiv pe loopback; fiecare port este
  legat de process name, cale canonică, SHA-256, argumentele structurate de
  pornire și path/hash-ul configurației autorizate pentru MariaDB, `realmd` sau
  `mangosd`; conținutul configurației și eventualele secrete nu sunt logate;
- clientul folosește numai `realmlist.wtf` din rădăcina exactă a buildului, cu
  conținutul byte-exact unic `set realmlist 127.0.0.1` și SHA-256 pinned;
- după verificarea listenerului MariaDB, harness-ul folosește un client DB
  path/hash-pinned și un query read-only fix pentru a compara întreaga listă
  sanitizată de realm-uri cu profilul autorizat: realm ID, nume, adresă, port,
  icon/flags/timezone/security și build-uri. Secretul DB rămâne local, nu apare
  în argumente, audit sau output; hash-ul rezultatului canonic intră în receipt
  și runtime arm. Datele sunt numai evidence de target, nu knowledge pentru
  Predator Brain;
- înaintea pornirii și a fiecărei acțiuni, harness-ul leagă ținta de profilul autorizat prin calea canonică și SHA-256-ul exact al executabilului; PID-ul selectat trebuie să ruleze acel executabil;
- dacă legacy Windows refuză atât process-image query cât și CIM, fallback-ul
  există numai pentru `lab_clone` + `emulator_local`: `Launch` scrie atomic un
  receipt expiring, legat de PID/HWND/title/class, executable, build,
  authorization hash, actorul configurat și `expected_realm_fingerprint`.
  Assurance-ul realm din receipt este istoric, măsurat la launch; receipt-ul are
  `execution_authority=false` și nu este disponibil pentru Champion;
- `ArmSession -AcknowledgeRuntimeArm` creează separat autoritatea temporară de
  fixed-UI input, cu nonce, set finit de acțiuni și expiry cel mult egal cu
  `approval.max_session_minutes`, expiry-ul receipt-ului și plafonul absolut de
  `60` minute; profilul curent poate impune o limită mai mică;
- înaintea fiecărei acțiuni cu keyboard, mouse, console text sau resize se
  reverifică arm-ul, receipt-ul, realmlist-ul, listener owner images și
  configurații, routing record-ul realmului, PID/HWND/build/hash și foreground
  window; assurance-ul curent vine din această măsurare, nu din timestamp-ul
  istoric al receipt-ului;
- imediat înaintea fiecărui keyboard/mouse submit, `GetForegroundWindow` trebuie să indice exact HWND-ul verificat; dacă focusul este furat, inputul este refuzat;
- inputul text are limite explicite; fiecare caracter reverifică arm nonce,
  hash-ul fișierului de arm, expiry-ul UTC și un deadline monotonic de 30 s;
  resize-ul face aceleași verificări imediat în jurul `MoveWindow`;
- contul `PA_OBSERVER` este pin-uit în helper; credentialul este citit din secretul local, ambele câmpuri sunt golite înainte de scriere, control characters sunt respinse, iar secretul nu este afișat, logat sau comis;
- caracterul așteptat `Predator` este înregistrat în audit și trebuie confirmat vizual în checkpoint-ul de character select; helperul nu pretinde că îi citește automat identitatea;
- fiecare tranziție UI importantă produce checkpoint în `data/runtime/operator/`;
  un checkpoint este salvat numai dacă exact PID/HWND-ul clientului rămâne
  foreground și dreptunghiul ferestrei rămâne stabil înainte și după captură;
- `Login`, `EnterWorld`, acțiunile de calibrare și `Logout` cer starea vizuală prevăzută; comenzile care deschid chat-ul cer explicit `InWorldChatClosed`, iar acțiunile care schimbă ecranul se termină în `requires_visual_verification`;
- map toggle, UI reload, UI scale și resize au payload-uri fixe și limite versionate; nu acceptă text sau coordonate arbitrare de la apelant;
- `ReloadUi` este permis numai din `InWorldChatClosed`, tastează exclusiv
  comanda canonică TBC 2.4.3 `/console reloadui` și nu se bazează pe aliasul
  retail `/reload`; așteaptă cel mult cinci secunde în interiorul lease-ului de input,
  păstrează personajul în world și produce checkpoint stabil înainte/după;
  rezultatul rămâne `requires_visual_verification`;
- nu există acțiune generică pentru slash commands, movement, targeting, combat sau quest acceptance;
- nu există forced termination; logout și close trebuie să fie normale;
- `DisarmSession` elimină imediat autoritatea de input; `Close` normal elimină
  atât arm-ul, cât și receipt-ul;
- auditul etichetează actorul `external_lab_operator_harness` și menține Predator în `OBSERVE_ONLY`.

## Consequences

Putem reproduce în siguranță partea operațională când utilizatorul este plecat, dar o imagine trebuie inspectată înainte de continuarea unei tranziții sensibile. Harness-ul nu este și nu poate fi citat ca dovadă că Predator știe să joace.

Movement/combat necesită un sistem separat cu percepție vizuală, state estimation, execution gateway și fail-closed checks. Până atunci, încercările externe de control sunt probe LAB și nu se promovează drept skill.
