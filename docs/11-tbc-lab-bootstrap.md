# 11 — TBC LAB bootstrap

## Decizie

LAB-ul inițial folosește CMaNGOS TBC 2.4.3 (client build 8606) și modulul oficial CMaNGOS Playerbots. Acesta oferă oponenți, populație open-world și ajutor controlat pentru questuri. Predator nu extinde și nu importă direct logica Playerbots.

## Separarea pe disc

```text
E:\WoWserver\
├── PerfectAssassin-Workspace\   # proiectul nostru; Git separat
└── TBC-LAB\
    ├── source\                  # checkout-uri upstream pinned
    │   ├── mangos-tbc\
    │   ├── playerbots\
    │   └── tbc-db\
    ├── integration\             # module links/patches generate, nu upstream edits ascunse
    ├── toolchain\               # dependencies locale pinned (de exemplu Boost)
    ├── build\                   # output CMake disposable
    ├── runtime\                 # mangosd/realmd/config/logs
    ├── database\                # scripts, dumps, migrations; secretele nu intră în Git
    ├── client-data\             # maps/dbc/vmaps/mmaps extrase din sursa de client validată
    ├── snapshots\               # rollback artifacts/version manifests
    └── logs\
```

`source` este rebuildable, `build` este disposable, `runtime` este deploy, iar `database` și `client-data` sunt state separat. Niciunul nu intră în repository-ul Predator.

Clientul TBC 2.4.3, build 8606, rămâne separat de server și de repository la:

```text
E:\games\WoW TBC 2.4.3\
```

Acest director este numai sursă pentru validare și extractoare. Pachetul curent este un repack enGB cu proveniență neconfirmată și `Wow.exe` are Authenticode `HashMismatch`; de aceea nu este autorizat pentru execuție. Compatibilitatea datelor a trecut extractoarele și bootul CMaNGOS, dar asta nu transformă executabilul într-un client canonic. Starea exactă este în `TBC-LAB/client-source-manifest.json`.

## Upstream oficial

- `https://github.com/cmangos/mangos-tbc.git`
- `https://github.com/cmangos/playerbots.git`
- `https://github.com/cmangos/tbc-db.git`

Checkout-urile sunt înregistrate cu commit SHA în `TBC-LAB/source-manifest.json`. Update-ul nu se face prin pull direct în timpul unui test; se creează manifest candidat și se rebuild-uiește.

## Build profile inițial

```text
Release
BUILD_GAME_SERVER=ON
BUILD_LOGIN_SERVER=ON
BUILD_SCRIPTDEV=ON
BUILD_PLAYERBOTS=ON
BUILD_AHBOT=OFF
BUILD_EXTRACTORS=ON (build separat sau aceeași configurație inițială)
DEBUG=OFF
```

Auction House automation rămâne oprită în primul slice. Populația Playerbots pornește minim și controlat după validarea bazei de date.

## Politica AFK a LAB-ului

Core-ul upstream deconecta un client la 15 minute după activarea stării AFK, printr-o valoare hardcodată. Patch-ul local expune aceeași regulă drept `Player.AFK.DisconnectTimeout`, în minute: valoarea upstream implicită rămâne `15`, iar `0` dezactivează deconectarea.

`Write-LabRuntimeConfig.ps1` setează explicit `Player.AFK.DisconnectTimeout = 0` și refuză un `mangosd.conf.dist` vechi care nu conține cheia. Astfel, Champion Journey și sesiunile de observație pot rămâne conectate fără mecanisme artificiale anti-AFK. Schimbarea nu dezactivează raportarea AFK din battleground și nu modifică timeout-urile de rețea, logout sau reconectare.

Același generator setează `MaxOverspeedPings = 0` numai în LAB. Core-ul upstream
închide sesiunea după al treilea `CMSG_PING` primit la mai puțin de 27 secunde de
precedentul; clientul 2.4.3 folosit în benchmark poate produce legitim această
cadență. Dezactivarea acestei verificări elimină disconnect-ul fals și nu face
parte din Movement Engine ori din profilurile pentru realm-uri externe.

Build-ul, deploy-ul și două cicluri reale de rollback sunt consemnate în [raportul AFK al LAB-ului](../reports/2026-08-23-lab-afk-disconnect-disabled.md).

Clientul 2.4.3 folosit în LAB nu finalizează stabil handshake-ul modulului Warden al
fork-ului local: logul serverului consemnează încărcarea modulului, urmată de
`WARDEN ... timeout` și închiderea sesiunii. Generatorul runtime păstrează
anticheat-ul server-side activ, dar setează strict `Warden.Enable = 0` în acest
realm izolat. Aceasta evită deconectarea falsă fără a slăbi profilul altui realm și
fără a confunda problema cu AFK-ul.

## Gates

1. Prerequisites detectate și versiuni înregistrate.
2. Configure CMake fără erori.
3. Build core standard verde.
4. Build cu Playerbots verde.
5. Database install pe credențiale locale dedicate.
6. Extractors rulate numai împotriva sursei 2.4.3 furnizate de operator și înregistrate în manifest.
7. `realmd` și `mangosd` pornesc bounded; porturile și logurile sunt verificate.
8. Un cont operator local + cohortă Playerbots controlată; fără integrare Predator.
9. Snapshot `LAB-baseline-001` înainte de primul patch experimental.

## Baseline verificat la 2026-08-22

- Core Release x64, extractoare și Playerbots: build PASS.
- MariaDB dedicat: `127.0.0.1:3307`; niciun serviciu Windows instalat.
- Auth/world/RA: numai loopback pe `3724`, `8085`, `3443`.
- Date extrase: 185 DBC, 3.586 maps, 8.607 vmaps, 2.838 mmaps.
- World boot: PASS, inclusiv mesajul `CMANGOS: World initialized`.
- Operator: `PA_OPERATOR`, TBC enabled, credential local cu ACL restricționat.
- Oponenți: 5 conturi Playerbots, 45 personaje disponibile, maximum 20 active, autologin oprit.
- Snapshot: `E:\WoWserver\TBC-LAB\snapshots\LAB-baseline-001`.

## Operare locală

Din `E:\WoWserver\PerfectAssassin-Workspace`:

```powershell
.\scripts\Start-LabDatabase.ps1
.\scripts\Start-LabRealm.ps1
.\scripts\Start-LabWorld.ps1

.\scripts\Stop-LabWorld.ps1
.\scripts\Stop-LabRealm.ps1
.\scripts\Stop-LabDatabase.ps1
```

Pentru o sesiune care trebuie să rămână activă după închiderea Codex, folosește
launcherul unic:

```powershell
.\scripts\Start-StandaloneLab.ps1
```

Acesta pornește un bootstrap Windows cu `CREATE_BREAKAWAY_FROM_JOB`, apoi
database, realm, world și Movement Engine Control Center. Bootstrapul se
închide după verificarea porturilor, iar cele patru procese rămân independente.
Starea este publicată în
`data/runtime/operator/standalone-lab-status.json`; launcherul refuză
dependințele lipsă și nu creează instanțe duplicate pe baza PID-urilor active.
Oprirea rămâne explicită și grațioasă, în ordinea world, realm, database, prin
scripturile `Stop-LabWorld.ps1`, `Stop-LabRealm.ps1` și
`Stop-LabDatabase.ps1`.

`Start-LabWorld.ps1` setează explicit locația providerului OpenSSL, verifică mesajul de inițializare și cele două porturi world/RA. `Stop-LabWorld.ps1` folosește RA numai pe localhost și cere oprire grațioasă; nu omoară procesul în fluxul normal.
