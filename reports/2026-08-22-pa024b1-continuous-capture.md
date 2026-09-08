# PA-024B1 continuous capture — 2026-08-22

## Outcome

Continuous Windows capture provider v0.1 este implementat și verificat pe clientul TBC 2.4.3 LAB:

- PID/HWND/title/class/foreground/client rectangle revalidate înainte și după fiecare frame;
- `new_frame_only=true` și caller-owned frame memory;
- ring buffer RAM bounded, capacity 3 în probe;
- buffer golit și camera eliberată la close;
- capture deadline fail-closed;
- source/geometry change în timpul unui frame este respins;
- schimbarea stabilă între frame-uri este acceptată și contorizată;
- raw pixels nu intră în telemetry și nu au fost persistați;
- fiecare frame acceptat produce `CaptureFrameManifest` valid;
- target/build signature este încărcat din autorizarea versionată, iar SHA-256 al executabilului este recalculat înainte de deschiderea camerei;
- `execution_authority=false` rămâne obligatoriu.

## Controlled-live results

Client: `2.4.3.8606 enGB`, client area inițial `2048×1536`, DPI 144.

| Scenario | Frames | p50 | p95 | max | Result |
|---|---:|---:|---:|---:|---|
| DXGI stable, 10 Hz | 30/30 | 11.454 ms | 12.907 ms | 14.847 ms | pass |
| WinRT stable, 10 Hz | 30/30 | 11.776 ms | 12.374 ms | 15.552 ms | pass |
| DXGI live move | 30/30 | 11.132 ms | 12.273 ms | 12.637 ms | pass, `region_changes=1` |
| DXGI live resize | 30/30 | 9.956 ms | 11.305 ms | 12.701 ms | pass, `region_changes=1` |
| DXGI identity-bound final | 5/5 | 13.063 ms | 15.755 ms | 15.755 ms | pass |

Duratele includ cele două verificări ale ferestrei, acquisition, contract build și validation; nu sunt numai timpul intern DXcam.

Resize-ul controlat a schimbat client area la `1848×1436`; manifestul și frame-ul au reflectat exact noua dimensiune. Poziția și dimensiunea ferestrei au fost restaurate după probe.

## Negative gates

- foreground mutat pe Codex: `0` frame-uri acceptate, `WindowSelectionError`, pass;
- hidden/minimized/empty/multiple HWND: contract/unit tests, pass;
- source geometry schimbată în interiorul capturii: frame respins, pass;
- frame nou indisponibil: frame respins, pass;
- deadline depășit: frame respins, pass;
- client rectangle în afara output-ului selectat: frame respins, pass.
- executable hash mismatch sau client build absent din configured signature: camera nu se deschide, pass.

GPU-ul curent expune un singur output DXcam (`7680×2160`), deci o tranziție live între două outputs nu poate fi probată aici. Failure behavior este testat determinist și rămâne fail-closed.

## Evidence scope

- `contract_tested`: da;
- `continuous_capture_controlled_live_verified`: da;
- `move_resize_controlled_live_verified`: da;
- `multi_output_transition_controlled_live_verified`: indisponibil pe hardware-ul curent;
- `pose_provider_verified`: nu;
- `movement_execution`: nu.

Suita completă: 85/85 teste trecute.

## Decision

PA-024B1 este complete pentru v0.1. Următorul milestone este PA-024B2: minimap anchor/localization, camera/body separation runtime și uncertainty-aware pose fusion.

## Rollback

Schimbarea este aditivă. Previous Stable: `6317f1b`.
