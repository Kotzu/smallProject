# ADR 0013 — Client integrity și input execution boundary

- Status: accepted
- Date: 2026-08-22
- Amends: ADR 0011 și ADR 0012

## Context

Perfect Assassin are nevoie în LAB de control fluid al unui client WoW închis. Au fost considerate trei familii de soluții:

1. citirea memoriei procesului pentru pose/state;
2. un virtual keyboard/mouse sau driver HID în kernel;
3. input sintetic user-mode prin API-ul documentat Windows.

Primele două ar putea reduce unele dificultăți tehnice, dar cresc puternic riscul de securitate, mentenanță, incompatibilitate și interpretare ca mecanism de evitare a platform policy. Ele nu fac controllerul mai inteligent sau mai natural.

## Decizie

### Clientul rămâne intact

Nu folosim:

- process memory read/write ori handle-uri cu drepturi VM/read/write/operation
  către procesul jocului;
- DLL/code injection, hooks în proces sau packet interception/injection;
- kernel driver, filter driver, Virtual HID Framework sau device spoofing;
- hardware proxy construit pentru a face inputul automat să pară fizic;
- tehnici de ascundere, anti-detection sau ocolire anti-cheat.

Aceste interdicții se aplică întregului produs, inclusiv LAB. Astfel păstrăm același nucleu de percepție legitimă și evităm dezvoltarea unei ramuri private-server-only bazate pe omnisciență.

Un handle metadata-only cu `PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE`
este permis exclusiv în adapterul Windows pentru a verifica path-ul imaginii,
creation time și liveness-ul procesului exact. Clientul legacy TBC 2.4.3 poate
refuza acel access mask modern cu `ERROR_ACCESS_DENIED`; numai în acel caz
adapterul poate relua verificarea cu
`PROCESS_QUERY_INFORMATION | SYNCHRONIZE`. Niciunul dintre cele două mask-uri
nu include `PROCESS_VM_OPERATION`, `PROCESS_VM_READ` sau `PROCESS_VM_WRITE`.
Handle-ul nu este transmis către Brain și este închis odată cu receipt-ul de
identitate. Orice altă eroare la prima deschidere este fail-closed și nu
activează fallback-ul.

### Executorul este user-mode și explicit

Primul actuator va fi `Win32SendInputAdapter`, în spatele Execution Gateway. `SendInput` este API-ul Windows documentat care introduce serial evenimente keyboard/mouse în input stream. WASD folosește scan-code events, iar camera relative mouse motion. Acestea rămân evenimente sintetice; nu pretindem că inputul este fizic sau nedetectabil.

Adapterul nu primește obiective sau tactică. El execută numai `MovementPrimitive` expirabile și auditate, aprobate de gateway:

```text
PA-MPPI proposal
      |
MovementPrimitiveCompiler
      |
Execution Gateway
  - target policy
  - exact HWND/PID/path/hash identity
  - allowlisted realm fingerprint
  - foreground/focus
  - pose != LOST
  - deadline/freshness
  - MANUAL override
      |
Win32SendInputAdapter (authorized target only)
```

Reguli obligatorii:

- inputul este permis numai pe un target profile cu `user_mode_synthetic_input=restricted`, o autorizare bounded activă, executable hash allowlisted și realm fingerprint exact;
- adapterul rulează la același integrity level ca ținta; nu escaladează privilegii;
- fiecare key-down are ownership și key-up garantat;
- `release_all` rulează la takeover, focus loss, stale proposal, pose `LOST`, exception, process exit și watchdog timeout;
- inputul fizic al operatorului are prioritate și comută imediat în `MANUAL`;
- nu folosim `PostMessage` drept movement transport; mesajele de fereastră nu reprezintă input stream-ul normal și dau semantics fragile;
- timing-ul vine din modelul de mișcare și feedback, nu din delay-uri macro sau randomizare pentru camuflaj;
- adapterul păstrează auditul `proposed -> authorized -> submitted -> observed_effect`.

### Emulator, Blizzard PTR și public live

Executorul poate funcționa pe emulator local, LAN sau remote dacă targetul este allowlisted explicit. `localhost` nu este o condiție de produs și nici o dovadă suficientă de încredere.

Blizzard PTR primește un profil separat. Synthetic/autonomous input poate deveni `restricted` numai după arhivarea unei autorizări specifice, redactate, și fixarea exactă a buildului, realmului, scopului și restricțiilor. Până atunci rămâne `pending_evidence`, fără modes permise.

Orice `public_live` oficial rămâne `denied` în scope-ul actual, inclusiv
realm-uri Classic/legacy și retail. Numai un PTR separat, autorizat explicit,
poate deveni eligibil. Nu stocăm credentiale Battle.net în repo sau telemetry.

## Buget comercial

- Havok este eliminat din roadmap și benchmark.
- Nu există momentan niciun middleware comercial de navigație candidat.
- O componentă sub USD 500 poate fi evaluată, dar nu este cumpărată automat: trebuie să fie locală, licențiabilă pentru produsul standalone și să bată baseline-ul open-source pe benchmark.
- Peste USD 500 este nevoie de o nouă decizie explicită; nu fragmentăm achizițiile ca să ocolim limita.
- Preferăm cost one-time; cloud/recurring dependency nu intră în control loop.

Stackul ales — Recast/Detour, OpenCV/LightGlue după nevoie, pose fusion și PA-MPPI — poate fi construit fără licență obligatorie.

## De ce user-mode este suficient pentru fluiditate

Windows transportă numai rezultatul controllerului. Calitatea vizibilă vine din:

- pose/camera estimate corecte;
- motion model calibrat;
- primitive cu durate și turn-rate realiste;
- feedback la 10–20 Hz și replanning;
- target prediction, contextual yielding și recovery;
- distribuții de mișcare validate față de human traces.

Un kernel driver ar livra aceeași decizie proastă mai „jos” în sistem. Nu rezolvă zig-zag, overshoot, stuck, camera coupling sau pursuit.

## Consecințe

- PA-024B rămâne complet read-only;
- input adapterul se implementează abia în PA-024F și se verifică întâi într-un fake window/input sink;
- bounded emulator course este primul target autorizat;
- PTR rămâne pending până la evidence intake și fingerprint;
- actuatorul fail-closed verifică simultan realm allowlist, client hash, target fingerprint, bounded approval și runtime arm;
- portabilitatea se bazează pe capability profiles, nu pe detectarea sau evitarea protecțiilor platformei;
- orice cerere viitoare de memory read/kernel input necesită înlocuirea explicită a acestui ADR; nu este o optimizare implicită.

### Migrare contract autorizare v1.0 → v2.0

`execution-target-authorization` v1.0 a înlocuit bootstrap-ul v0.1 și a cerut
`client_match.client_build` separat de `build_signature`; build-ul rămâne
comparat prin egalitate exactă, niciodată prin substring. v2.0 adaugă
`actor_binding`, derivă `decision_context`, declară numele de personaj numai ca
`expected_character_name` cu assurance `configured_expected_only` și redenumește
realm-ul configurat `expected_realm_fingerprint`. Pentru un `emulator_local`
aprobat, realmlist-ul canonic și binding-urile exacte
port/process/path/hash/arguments/config ale listenerelor LAB sunt verificate de
operator înaintea inputului. Profilul local fixează suplimentar înregistrarea
sanitizată pe care `realmd` o citește din auth DB; operatorul compară exact realm
ID/address/port/build și leagă rezultatul canonic prin SHA-256 de receipt/arm.
Aceasta dovedește ținta execuției, fără a autoriza server-only knowledge în
Brain.

## Surse primare

- Microsoft `SendInput`: <https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput>
- Microsoft Virtual HID Framework: <https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/virtual-hid-framework--vhf->
- Blizzard EULA: <https://www.blizzard.com/en-us/legal/fba4d00f-c7e4-4883-b8b9-1b4500a402ea/blizzard-end-user-license-agreement>
- Blizzard Anti-Cheating Agreement: <https://www.blizzard.com/legal/cd5930c0-2784-420c-a23d-1e0d6ff8599b/anti-cheating-vereinbarung>
