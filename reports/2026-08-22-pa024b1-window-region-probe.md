# PA-024B1 exact window-region probe — 2026-08-22

## Outcome

Fereastra reală TBC 2.4.3 LAB a trecut one-shot source binding și capture:

- local console session, nu RDP;
- build `2.4.3.8606`, locale `enGB`;
- executable hash verificat: `406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6`;
- match exact PID/HWND/title/class;
- visible + foreground + non-minimized;
- class `GxWindowClassD3d`;
- DPI 144, physical client area `2048×1536`;
- DXGI și WinRT monitor au returnat același crop BGRA8;
- manifestul live a trecut `capture-frame.schema.json`;
- `persisted=false`, retention `none`, `execution_authority=false`.

Checkpointul operatorului a confirmat vizual login screen-ul TBC 2.4.3. Fișierul este runtime-only și ignorat de Git.

## Defect găsit și corectat

Locatorul standalone era inițial DPI-unaware și vedea coordonate virtualizate. Proba a fost respinsă. `SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)` este acum aplicat înainte de enumerare; locatorul și capturatorul raportează aceeași geometrie fizică.

Un manifest intermediar a fost emis cu un locale introdus manual greșit (`enUS`). Nu este păstrat și nu este evidence. Locale-ul real a fost verificat din client (`Data/enGB`, `WTF/Config.wtf`) și proba finală folosește `enGB`.

## Evidence scope

- `contract_tested`: da;
- `controlled_live_verified`: da, strict one-shot window-region capture;
- `continuous_capture_verified`: nu;
- `pose_provider_verified`: nu;
- `movement_execution`: nu.

## Next gate

Continuous provider cu rect/foreground revalidation, resize/move/output-change tests și stale-frame failure. PA-024B2 nu consumă live frames înainte de acest gate.

Status update: gate-ul a fost închis în [PA-024B1 continuous capture](2026-08-22-pa024b1-continuous-capture.md).

## Rollback

Schimbarea este aditivă. Previous Stable: `eea727a`.
