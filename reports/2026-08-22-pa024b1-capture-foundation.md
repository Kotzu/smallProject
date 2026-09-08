# PA-024B1 capture foundation — 2026-08-22

## Outcome

- contract `CaptureFrameManifest` implementat și testat;
- capture port fără dependency Windows/NumPy în core;
- deterministic capture replay reader/provider implementat;
- DXcam 0.3.0 + WinRT dependencies pin-uite cu hashes într-un wheelhouse exterior;
- install lock verificat offline cu `--require-hashes`;
- DXGI și WinRT au capturat fiecare un frame BGRA8 în memorie;
- niciun pixel/screenshot nu a fost persistat;
- `execution_authority=false` este impus de contract.

## Evidence scope

- `contract_tested`: da;
- `replay_tested`: da;
- `environment_smoke_tested`: da, DXGI + WinRT monitor;
- `client_region_verified`: nu, WoW nu rula;
- `pose_provider_verified`: nu;
- `movement_execution`: nu.
- full suite: 67/67 teste trecute.

## Smoke evidence

| Backend | Resolution | Duration | Persistence |
|---|---:|---:|---|
| DXGI | 7680×2160×4 | 147.649 ms | none |
| WinRT | 7680×2160×4 | 427.081 ms | none |

Durata este cold one-shot și nu reprezintă control-loop latency.

## Rollback

Schimbarea este aditivă. Rollback înseamnă eliminarea modulului/contractului/manifestului și revenirea la Stable `dd89624`; niciun server/client file nu a fost modificat.
