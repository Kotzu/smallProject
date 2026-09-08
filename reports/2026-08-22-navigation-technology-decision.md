# Navigation technology decision — 2026-08-22

## Outcome

Stackul de producție este blocat conceptual:

- Recast/Detour pentru tiled navmesh și global corridors;
- PA-MPPI/MPC pentru steering extern predictiv;
- behavior-tree supervisor pentru replan/recovery/takeover;
- pose belief din surse client-visible, minimap/vision și dead reckoning;
- Windows Graphics Capture, cu DXGI fallback;
- RVO2 și DetourCrowd numai ca benchmark/baseline;
- fără middleware comercial curent; orice candidat viitor trebuie să coste sub USD 500 și să treacă benchmarkul comun.

Nu s-a autorizat și nu s-a executat movement live. Grid A* rămâne un fixture de contract.

## Motivul deciziei

Perfect Assassin nu este integrat în motorul WoW. Middleware-ul comercial poate îmbunătăți navmesh/path queries, dar nu poate furniza singur pose-ul legitim sau transforma o traiectorie într-un control keyboard/mouse stabil. Riscul dominant este bucla percepție -> model de mișcare -> input -> verificare, deci acolo investim întâi.

## Următorul gate

Contractele pose din PA-024B1 sunt livrate; GPU capture/provider replay intake rămâne gate-ul read-only curent. PA-024C adaugă Recast tiles/query. PA-024E construiește benchmarkul și controllerul local. Primul input rămâne PA-024F, bounded emulator, user-mode, cu takeover instant. PTR cere authorization evidence + exact target fingerprint; orice `public_live` oficial, Classic/legacy sau retail, este denied.
