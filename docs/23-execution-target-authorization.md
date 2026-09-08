# 23 — Execution target authorization

## Outcome

Executorul nu este limitat tehnic la `localhost`. El este limitat la targeturi înscrise explicit într-un allowlist versionat. Sunt eligibile:

- emulator local;
- emulator din LAN;
- emulator remote controlat;
- Blizzard PTR cu autorizare specifică arhivată.

Orice `public_live` oficial rămâne exclus din scope-ul curent, inclusiv
realm-uri Classic/legacy și retail. Eligibilitatea Blizzard se poate aplica
numai unui PTR separat, autorizat explicit și fixat prin propriul profil.

Allowlist-ul, exact target binding și runtime arm sunt controale de identitate,
calitate și reproducibilitate: ele aleg instanța corectă și nu exprimă
neîncredere în operator. Nu limitează topologia la local și nu limitează
produsul la o singură instanță. Arhitectura completă este în
[ADR 0017](adr/0017-standalone-multi-target-and-multi-instance-operation.md).

## Cele patru gates independente

```text
TargetFingerprint exact
        +
Client build/executable hash exact
        +
Expected realm profile + target-specific assurance
        +
Active bounded authorization + runtime arm
        |
        v
Execution Gateway may authorize one primitive
```

Niciun singur gate nu este suficient. Capability profile spune ce poate face adapterul; execution authorization spune unde și în ce scop poate fi folosit; runtime arm confirmă sesiunea curentă.

Gates se evaluează per instanță. Fiecare Champion/LAB clone are propriul
`instance_id`, actor identity, client/window binding, runtime arm și runtime
artifacts; armarea unei instanțe nu autorizează alta.

În `ExecutionTargetAuthorization` v2.0, `actor_binding` fixează rolul și
identitatea actorului autorizat. `decision_context` este derivat din acest
binding, nu furnizat liber de caller; schimbarea realm-ului nu poate transforma
o LAB clone în Champion și nici invers.

Binding-ul include `instance_id`, `actor_role`, `actor_id`, `decision_context`,
`memory_namespace`, `expected_character_name`, `credential_alias` și
`binding_assurance`. Numele personajului este explicit o așteptare configurată,
nu o observație despre cine este logat în client. Până la o dovadă separată,
client-visible, starea este `configured_expected_only`, iar outputul Champion
rămâne nepromovabil. Nu există override liber de account/character din partea
callerului.

`permitted_capabilities` și `permitted_modes` sunt gates independente. Prima
listă poate permite captură read-only, HUD read-only sau helperul finit
`LAB_OPERATOR_FIXED_UI`; a doua permite separat numai moduri Predator
`MOVEMENT_ONLY|COMBAT_ONLY|FULL_AI`. Profilul LAB curent are
`permitted_modes=[]`: fixed-UI calibration nu este movement authorization.

Autorizația per instanță nu schimbă limita Win32: un Executor Worker poate emite
input pentru un singur desktop interactiv. Concurența fluidă folosește workeri
pe desktopuri/sesiuni/VM-uri/hosturi izolate; orchestratorul coordonează acești
workeri fără a le partaja runtime arm-ul.

## Emulator

Operatorul poate aproba un emulator local/LAN/remote dacă sunt înregistrate:

- build signature și executable SHA-256;
- expected realm fingerprint și metoda de assurance disponibilă pentru acel
  target;
- capabilities și, unde schema le permite, execution modes distincte;
- limită de timp;
- restrictions și evidence refs;
- takeover și `release_all` verificate.

Adresa rețelei nu conferă încredere. Un endpoint local necunoscut este respins,
iar un emulator remote allowlisted poate fi acceptat. Pentru LAB-ul local,
operatorul verifică exact realmlist-ul și procesele/configurațiile listenerelor;
în plus, interoghează read-only înregistrarea sanitizată `realmlist` pe care
`realmd` o livrează clientului și cere egalitate exactă pentru realm ID,
adresă, port și build-uri. Rezultatul canonic este legat prin SHA-256 de
receipt și runtime arm. Această probă este exclusiv un gate de target; nu intră
în observațiile sau deciziile Predatorului;
pentru LAN/remote, profilul curent poate declara numai
`remote_assurance.state=configured_endpoint_only`. Aceste profile rămân
`OBSERVE_ONLY`/read-only cu `permitted_modes=[]`; nu pretind acces la procesele
hostului serverului. Orice input remote viitor cere un adapter de assurance mai
puternic, un contract/schema nouă și o autorizare separată, nu reutilizarea
acestui state configurat.

Migrarea v1.0 → v2.0 adaugă actor binding obligatoriu, separă
`expected_character_name` de identitatea observată și redenumește
`expected_realm_fingerprint` pentru a evita prezentarea configurației ca dovadă
măsurată a instanței de server.

## Blizzard PTR educațional

PTR are profil separat de public live și separat de emulator. Înainte de activare arhivăm local o copie redactată a autorizării primite, apoi fixăm:

- emitentul și data;
- scopul educațional/content;
- client/build/realm acoperite;
- acțiunile permise și interzise;
- expirarea sau condițiile de revocare;
- restricțiile privind gathering/economie și memory access.

Baseline-ul PTR pregătit acum interzice explicit herbing, mining, fishing și economy farming/auctioning. După ce vedem răspunsul redactat, păstrăm formularea exactă și orice condiție suplimentară.

Până când aceste date sunt înregistrate, statusul este `pending_evidence`,
iar `permitted_modes` și `permitted_capabilities` sunt ambele goale. Aceasta nu
blochează dezvoltarea pe emulator.

## Public live

`public_live` este deny-by-construction în schema v2.0 pentru toate realm-urile
oficiale live, Classic/legacy sau retail. Direcția curentă a proiectului este
emulator + Classic/TBC PTR educațional autorizat separat, nu deployment live.

## Artifacts

- schema: `contracts/execution-target-authorization.schema.json`;
- emulatorul curent: `config/execution-targets/tbc_243_lab.json`;
- PTR pending: `config/execution-targets/tbc_classic_ptr_education_pending.json`.

Nu se comit emailuri brute, nume personale, adrese sau identificatori de cont. Evidența se redactează; hash-ul fișierului redactat și un reference ID sunt suficiente pentru repo.
