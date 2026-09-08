# 13 — TBC 2.4.3 addon offline intake

## Outcome PA-017 / PA-019

Predator are primul port client-facing real: un addon `Interface 20400` exclusiv observer și un importer offline pentru fișierul lui `SavedVariables`. PA-019 a verificat acest traseu într-un probe controlat pe clientul LAB `2.4.3.8606`.

Release-ul curent al addon-ului este `0.3.6`; immediate previous Stable și
singura țintă acceptată pentru rollback este `0.3.5`.

```text
TBC 2.4.3 client-visible state
        ↓ read-only WoW addon APIs
PerfectAssassinObserverDB
        ↓ client-owned SavedVariables write
stopped-client .lua export
        ↓ non-executing restricted parser
TBC 2.4.3 compatibility adapter
        ↓ provenance firewall
ObservationEnvelope → telemetry → replay → Predator Journal
```

Nu există transport live, socket, memory reading, packet sniffing, DLL injection, server/database relay sau input în acest slice.

## Module boundaries

- `integrations/tbc243-addon/PerfectAssassinObserver`: colectorul Lua. Nu conține Brain, scoring ori execution.
- `adapter.saved_variables`: parser pentru un subset strict de Lua data literals; nu folosește `eval` și nu încarcă fișierul ca program.
- `adapter.tbc243_saved_variables`: verifică schema, aplică allowlist-ul de câmpuri și traduce numai către raw facts cunoscute.
- `observer`: capability profile și provenance firewall, neschimbate.
- `application.tbc243_intake`: rulează pipeline-ul comun în `OBSERVE_ONLY`.

## Date observabile în v0.1

- self: level, XP, dead/alive;
- world: zone și subzone vizibile clientului;
- target: GUID, nume, player/NPC, health percentage, dead/alive cât timp targetul este legitim disponibil;
- combat state: intrare/ieșire din combat;
- loot: numai sloturile vizibile când loot window este deschis;
- combat log: maximum 20 de valori scalare brute per eveniment, arhivate cu formatul `tbc243-legacy-v1`.

PA-017 nu interpreta combat log-ul brut. PA-019 admite o singură mapare verificată: `PARTY_KILL` devine `target.dead=true` numai când GUID-ul destinației coincide cu ultimul target activ observat. Celelalte sub-evenimente rămân exclusiv arhivă brută. O mapare greșită ar transforma accidental poziții de argument specifice sub-eventului în informații false; fiecare mapare nouă va fi admisă separat, după captură și verificare.

## Buffer și privacy

Addon-ul păstrează maximum 5.000 de evenimente și contorizează ce elimină din capul bufferului. Nu salvează numele Championului. `champion_id` rămâne `unbound-client-observer` până la binding-ul controlat. Target names pot fi player-identifying; exporturile reale, telemetry și Journals rămân în `data/runtime`/`data/telemetry`, ignorate de Git și nu se comit.

## HUD vizibil și repoziționare în `0.3.6`

HUD-ul pornește ancorat `TOPLEFT` la `16, -100`, sub frame-urile standard de
player și target. Panoul principal este click-through. Pentru mutare, operatorul
ține `Ctrl` și trage cu butonul stâng numai de banda de titlu; fără `Ctrl`, banda
nu interceptează mouse-ul.

Frame-ul are nume stabil, iar poziția este păstrată prin mecanismul nativ al
clientului în `WTF\...\layout-cache.txt`. Aceasta este doar stare de layout: nu
adaugă încă un root în `SavedVariables`, nu intră în observation intake și nu
devine knowledge pentru Predator.

După mutare, la login și după reset, addon-ul limitează întregul footprint al
markerului la regiunea sigură din stânga-sus pe care o caută detectorul vizual.
Astfel HUD-ul poate fi scos de peste character frame fără să fie mutat într-o
zonă pe care capture profile-ul nu o inspectează. Revenirea deterministă la
poziția implicită folosește:

```text
/paohud reset
```

Release-ul exact `0.3.6` are acum dovadă controlată live pentru poziția
implicită, decodare `10/10`, logout normal și persistență în `layout-cache.txt`.
Detaliile și limitele probei sunt în
[raportul HUD `0.3.6`](../reports/2026-08-23-pa024b3-hud-layout-036.md).

## Comandă offline

Clientul trebuie să fie închis înainte de citirea fișierului, ca exportul să fie stabil.

```powershell
.\.venv\Scripts\python.exe -m perfect_assassin import-tbc243-saved-variables `
  --input "<client>\WTF\Account\<account>\SavedVariables\PerfectAssassinObserver.lua" `
  --telemetry "data\telemetry\<session>.jsonl" `
  --journal "data\runtime\journals\<session>.md"
```

Comanda nu pornește clientul și nu scrie în client.

## Deploy și import controlat

1. Clientul rămâne oprit.
2. Se verifică dacă există deja `Interface\AddOns\PerfectAssassinObserver`; o instalare necunoscută este refuzată, iar upgrade-ul exclusiv al immediate previous Stable `0.3.5` cere explicit `-UpgradeVerifiedPrevious` și produce backup înainte de înlocuirea cu `0.3.6`. Versiuni mai vechi nu sunt upgradeable prin acest installer.
3. Se copiază numai setul flat de trei artifacts cunoscute din workspace, prin staging în același `AddOns` și cu verificare SHA-256 înainte și după copiere.
4. Operatorul pornește manual clientul într-un test LAB bounded.
5. Se verifică prezența addon-ului și se execută numai login → target → combat scurt → loot opțional → logout normal.
6. Clientul se închide complet; apoi importerul citește `SavedVariables`.
7. Se compară Journal-ul cu ceea ce operatorul a văzut pe ecran.

Primul probe folosește contul non-GM `PA_OBSERVER`, creat de `scripts/Initialize-LabObserverAccount.ps1`. Parola are maximum 16 caractere pentru compatibilitatea legacy. Secretul local este în `E:\WoWserver\TBC-LAB\database\observer-account.local.json`, cu ACL restricționat. Caracterul probe este un LAB clone temporar, nu Champion.

Rollback-ul versionat al addon-ului folosește exclusiv cel mai recent backup
exact `0.3.5` din `data\runtime\addon-backups`; nu acceptă o cale arbitrară și
nu caută în client sau în afara workspace-ului. Clientul trebuie să fie oprit:

```powershell
.\scripts\Install-Tbc243ObserverAddon.ps1 -RestoreLatestVerifiedPrevious
```

Înainte de restore, installerul cere ca targetul să fie exact versiunea curentă
`0.3.6`, o salvează și o verifică într-un backup separat, apoi reverifică
hash-urile tuturor celor trei artifacts `0.3.5` după instalare. Reparse points, directoare imbricate,
artifacts lipsă sau fișiere suplimentare opresc operația. Revenirea la `0.3.6`
după proba de rollback se face cu:

```powershell
.\scripts\Install-Tbc243ObserverAddon.ps1 -UpgradeVerifiedPrevious
```

Dacă o copiere de backup eșuează, staging-ul incomplet este eliminat numai
după verificarea că este un director flat parțial cu artifacts cunoscute;
targetul instalat nu este atins. Orice intrare neașteptată ori unsafe oprește
cleanup-ul non-destructiv și cere investigație, nu ștergere largă.

Scripturile bounded sunt `scripts/Install-Tbc243ObserverAddon.ps1` și
`scripts/Remove-Tbc243ObserverAddon.ps1`. Cel din urmă suportă `-WhatIf` și
elimină exclusiv folderul exact `PerfectAssassinObserver`; este dezinstalare,
nu rollback versionat. Nu se șterge întregul `Interface`, `WTF` sau alt addon.

## Evidence status

- `contract_tested`: da;
- `replay_tested`: da;
- `addon_static_checked`: da;
- `deployed_to_client`: da;
- `lab_integrated`: da, pentru intake-ul offline observe-only;
- `controlled_live_verified`: da, strict pentru self/world/target/combat state și `PARTY_KILL`;
- `hud_layout_036_controlled_live_verified`: da, release exact `0.3.6`, poziție implicită `TOPLEFT 16,-100`, detector `10/10`, logout normal și intrare nativă `layout-cache.txt`; gestul manual `Ctrl` + drag rămâne acceptance check ergonomic;
- `versioned_addon_rollback_tested_current`: da, într-un client temporar izolat, `0.3.5 → 0.3.6 → 0.3.5 → 0.3.6`, cu toate cele trei hash-uri reverificate și fără reziduuri;
- `versioned_addon_rollback_tested_historical`: da, pentru release-ul `0.3.5`, într-un client temporar izolat, `0.3.5 → 0.3.4 → 0.3.5`, cu verificarea celor trei hash-uri, refuzul versiunilor non-imediate și cleanup verificat al backupului incomplet, fără mutarea clientului real;
- quest acceptance, loot event, spellbook, movement și execution: neverificate.

Sursele de compatibilitate folosite sunt snapshot-ul public de [FrameXML 2.4.3](https://github.com/MOUZU/Blizzard-WoW-Interface/tree/master/2.4.3/FrameXML) și un addon 2.4.3 existent care declară atât [`Interface: 20400`/`SavedVariables`](https://github.com/jdsch/SoundAlerter-2.4.3/blob/master/SoundAlerter.toc), cât și evenimentul [`COMBAT_LOG_EVENT_UNFILTERED`](https://github.com/jdsch/SoundAlerter-2.4.3/blob/master/SoundAlerter.lua). Forma statică și traseul local au fost verificate; acest rezultat nu dovedește portabilitatea Anniversary.
