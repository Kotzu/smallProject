# Windows capture sidecar v0.1

Integrare opțională și read-only pentru captură GPU. Nu aparține Brain-ului, nu citește memoria procesului și nu are autoritate de input.

## Backends

- `dxgi`: Desktop Duplication; backend-ul primar v0.1.
- `winrt`: Windows Graphics Capture la nivel de monitor, folosit pentru comparație/fallback.
- `window_locator.py` selectează fail-closed un singur PID+HWND, vizibil, foreground și ne-minimizat;
- client rectangle este convertit explicit din desktop physical pixels în output physical pixels;
- DXcam 0.3.0 nu oferă în această integrare `CreateForWindow`, deci nu declarăm captură HWND nativă.

Clientul trebuie să fie vizibil. Nu se salvează niciun pixel în proba de mai jos; stdout conține doar metadata despre frame.

## Instalare reproductibilă din wheelhouse extern

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --require-hashes `
  --find-links "E:\WoWserver\PerfectAssassin-Dependencies\capture\dxcam\wheels" `
  -r .\integrations\windows-capture\requirements-lock.txt
```

## Probe în memorie

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_capture.py --backend dxgi
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_capture.py --backend winrt
```

Pentru o regiune deja determinată în coordonate fizice relative la output:

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_capture.py `
  --backend dxgi --region 100,100,1380,820
```

Pentru o fereastră pornită de launcher, transmite simultan PID-ul și HWND-ul:

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_capture.py `
  --backend dxgi --window-pid 1234 --window-hwnd 0x123456 `
  --window-title-exact "World of Warcraft" --window-class-exact "GxWindowClassD3d"
```

Probe-ul refuză fereastra dacă nu este foreground. Pentru diagnostic exclusiv, locatorul poate raporta o fereastră background cu `--allow-background`, dar capture probe nu o acceptă.

Pentru a emite și valida direct contractul, adaugă `--emit-manifest`, `--session-id`, `--client-build`, `--authorization-file` și `--client-executable`. Target profile, build signature, hash și `actor_binding` sunt încărcate/verificate automat din autorizarea versionată. `decision_context` este derivat din rolul actorului; CLI-ul nu poate reclasifica o clonă LAB drept Champion. `expected_character_name` rămâne explicit o așteptare configurată, nu o identitate observată; până la o verificare client-visible separată, captura Champion are scope `unpromoted_evaluation_only`.

Authorization file fixează identitatea targetului/actorului configurat și
verifică faptul că approval-ul bounded este activ, neexpirat și include
capabilitatea read-only necesară. El nu acordă un Predator execution mode:
captura rămâne read-only și fiecare manifest are
`execution_authority=false`.

Fișierul este deschis o singură dată și se citesc cel mult limita plus un byte;
hash-ul și parserul consumă exact același snapshot bounded. Duplicate JSON keys,
constante non-finite și overflow numeric precum `1e9999` sunt refuzate înaintea
validării schemei. Dacă un authorization v2 vechi nu are
`expires_at`, limita se calculează obligatoriu ca
`recorded_at + max_session_minutes`; un expiry explicit mai lung este refuzat.
Pentru clientul legacy, procesul este deschis mai întâi cu
`PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE` și numai eroarea exactă
`ACCESS_DENIED` permite fallback la
`PROCESS_QUERY_INFORMATION | SYNCHRONIZE`. Niciun traseu nu cere drepturi VM.
Același handle leagă path-ul, creation FILETIME și liveness-ul înainte/după
snapshot. Dacă legacy Windows refuză `ProcessIdToSessionId` exact cu
`ACCESS_DENIED`, session ID-ul este rezolvat prin snapshot-ul read-only WTS.

Fallback-ul bazat pe launch receipt v1 verifică aceleași câmpuri native de două
ori, paritatea UTC ↔ FILETIME, session-ul sidecar-ului și semantic SHA-256 al
authorization-ului. În această etapă acceptă numai `identity_origin=operator_launch`
cu parent fields nule. Receipt-urile `legacy_v0_1_continuity_adoption` și
`verified_receipt_renewal` sunt refuzate de fallback până la integrarea trust
marker-ului atomic de issuance; pentru ele rămâne disponibilă calea directă de
identitate nativă a procesului.

Acest probe dovedește source binding și livrarea unui frame BGRA. Nu dovedește localizarea în lume, minimap recognition sau pose fusion.

## Continuous bounded probe

`probe_continuous.py` revalidează PID/HWND/title/class/foreground/client rectangle înainte și după fiecare frame. Folosește frame-uri caller-owned, `new_frame_only=true`, un ring buffer RAM limitat și se oprește la source change, output mismatch sau deadline depășit.

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_continuous.py `
  --backend dxgi --window-pid 1234 --window-hwnd 0x123456 `
  --window-title-exact "World of Warcraft" --window-class-exact "GxWindowClassD3d" `
  --samples 30 --target-fps 10 --deadline-ms 250 --buffer-capacity 3 `
  --session-id "session:capture-probe" --client-build "2.4.3.8606" `
  --authorization-file ".\config\execution-targets\tbc_243_lab.json" `
  --client-executable "E:\Games\WoW TBC 2.4.3\Wow.exe"
```

Durata acceptată a probei este limitată atât prin parametri, cât și printr-un deadline monotonic de 30 secunde verificat înainte și după fiecare apel al backend-ului. Acest deadline refuză rezultatul întârziat, dar nu poate întrerupe din Python un apel nativ `camera.grab` care s-ar bloca definitiv. FPS, samples, capture deadline și capacitatea ring buffer-ului au limite finite explicite. La închidere, ring buffer-ul este golit și camera este eliberată.

## Minimap geometry detector

`minimap_detector.py` folosește numai NumPy-ul deja pin-uit în sidecar. Profilul `config/pose/minimap-tbc243-8606.json` limitează căutarea la o regiune normalizată și la build-ul exact `2.4.3.8606`.

Detectorul poate raporta:

- cercul minimap în screen pixels;
- markerul central și orientarea sa în raport cu partea de sus a ecranului;
- `FOUND`, `DEGRADED` sau `NOT_FOUND`;
- confidence, ring coverage și evidence frame.

Nu raportează world position. Markerul central al minimap-ului nu este o coordonată de hartă, iar `contracts/minimap-vision.schema.json` impune `absolute_pose_available=false`. Profilul curent este `synthetic_only`; nu trebuie folosit pentru navigation până la PA-024B2b2.

## Coordinate HUD one-shot probe și freshness gate

`probe_coordinate_hud.py` este gate-ul read-only pentru verificarea HUD-ului vizibil pe clientul real. Fără argumente de sampling suplimentare păstrează comportamentul one-shot. Cu `--samples 2..30` folosește aceeași cameră deschisă o singură dată și verifică o secvență limitată de cadre. El:

- verifică authorization contract-ul, build-ul `2.4.3.8606` și SHA-256-ul executabilului;
- acceptă numai profilul detectorului revizuit și legat prin SHA-256;
- cere simultan PID, HWND, titlu și clasă exacte, iar fereastra trebuie să fie vizibilă, foreground și neminimizată;
- revalidează identitatea și geometria ferestrei înainte și după captură;
- cere numai frame-uri noi BGRA ale client region-ului, cu buffer RAM de capacitate `1`;
- decodează HUD-ul, validează CRC-ul și emite numai observation JSON;
- eliberează frame-ul și camera fără a scrie pixeli, screenshot-uri sau clipuri pe disc.

În modul multi-frame, fiecare observation trebuie să fie validă contractual și să aibă `tracking_state=VALID`. Contorul protocolului este evaluat modulo 256, deci `255 -> 0` este un avans valid. Sunt tolerate cadre duplicate pentru cel mult 600 ms. Gate-ul refuză stagnarea, timpul de captură ne-monotonic, regresia contorului, un salt incompatibil cu timpul dintre cadre sau schimbarea source binding-ului. Rezultatul este un summary compact validat prin `contracts/coordinate-hud-sequence-summary.schema.json`; nu conține pixeli sau pachetele HUD brute și are întotdeauna `execution_authority=false`.

Cu WoW deschis, logat și adus în foreground, identifică mai întâi fereastra exactă. Valorile de mai jos sunt doar exemplu; folosește PID-ul și HWND-ul raportate în sesiunea curentă:

```powershell
$wowProcess = Get-Process Wow | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$wowHwnd = "0x{0:X}" -f $wowProcess.MainWindowHandle

.\.venv\Scripts\python.exe .\integrations\windows-capture\window_locator.py `
  --pid $wowProcess.Id --hwnd $wowHwnd `
  --title-exact "World of Warcraft" --class-exact "GxWindowClassD3d"
```

După ce locatorul confirmă aceeași fereastră:

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_coordinate_hud.py `
  --backend dxgi --window-pid $wowProcess.Id --window-hwnd $wowHwnd `
  --window-title-exact "World of Warcraft" --window-class-exact "GxWindowClassD3d" `
  --session-id "session:pa024b3b-live" --client-build "2.4.3.8606" `
  --authorization-file ".\config\execution-targets\tbc_243_lab.json" `
  --client-executable "E:\Games\WoW TBC 2.4.3\Wow.exe"
```

Pentru baseline-ul PA-024B3b, folosește o probă scurtă la 10 FPS:

```powershell
.\.venv\Scripts\python.exe .\integrations\windows-capture\probe_coordinate_hud.py `
  --backend dxgi --window-pid $wowProcess.Id --window-hwnd $wowHwnd `
  --window-title-exact "World of Warcraft" --window-class-exact "GxWindowClassD3d" `
  --samples 10 --target-fps 10 `
  --session-id "session:pa024b3b-live" --client-build "2.4.3.8606" `
  --authorization-file ".\config\execution-targets\tbc_243_lab.json" `
  --client-executable "E:\Games\WoW TBC 2.4.3\Wow.exe"
```

CLI-ul limitează `--samples` la `1..30` și `--target-fps` la `1..30`; astfel, proba multi-frame nu poate depăși 30 de secunde prin parametrii acceptați. Frame-urile există numai în RAM și sunt eliberate după decodare. Pentru `--samples 1`, stdout rămâne observation contract-ul one-shot existent. Pentru `--samples >=2`, stdout este freshness summary-ul compact.

Codurile de ieșire sunt fail-closed:

- `0`: observation one-shot validă sau freshness summary cu `gate_state=PASS`;
- `3`: observation one-shot nevalidă pentru navigation ori freshness summary cu `gate_state=FAIL`;
- `1`: identity, hash, profil, captură, deadline sau contract invalid; este emis numai `coordinate_hud_probe_failure`, fără poziție.

Aceeași clasă `CoordinateHudOneShotProbe` poate primi în teste un provider replay care livrează un singur `CapturePacket` cu pixeli BGRA păstrați în memorie. Replay-ul existent bazat numai pe manifest are intenționat `pixels=None` și este refuzat: coordinate HUD nu poate fi reconstituit din metadata și nu inventează poziția.
