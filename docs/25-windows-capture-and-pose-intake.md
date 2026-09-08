# 25 — Windows capture și pose-provider intake

## Outcome v0.1

PA-024B1 are acum o limită executabilă de captură read-only:

```text
Windows desktop / client region
             |
      DXGI or WinRT sidecar
             |
      CapturePacket (pixels in memory)
             |
   CaptureFrameManifest (no raw pixels)
             |
       replay / pose providers
             |
 PoseObservation -> PoseEstimate -> movement proposal
```

Captura nu controlează clientul și nu reprezintă pose. Un frame devine doar evidence pentru un provider ulterior de minimap/scene/optical-flow.

## Module boundaries

- `src/perfect_assassin/capture/ports.py`: `CaptureRegion`, `CapturePacket`, `CaptureProvider`; fără DXcam/NumPy/Win32.
- `src/perfect_assassin/capture/replay.py`: JSONL validation, canonical hash și provider finit/resetabil.
- `contracts/capture-frame.schema.json`: source/backend/image/timing/provenance/privacy/artifact.
- `integrations/windows-capture`: sidecar Windows opțional și dependency lock.
- `config/external-integrations/dxcam-windows-capture.json`: upstream, versiuni, hashes și limite.

Dependency direction rămâne:

```text
pose provider -> CaptureProvider port <- Windows sidecar or replay provider
```

Brain-ul nu importă niciuna dintre implementările din dreapta.

## Contract rules

- BGRA8 top-down rămâne formatul de pixeli al slice-ului v0.1, iar manifestul
  versionat curent este `capture_frame_manifest` v2.0;
- source kind separă `monitor`, `window_region` și `replay_fixture`;
- build signature și target profile sunt obligatorii;
- `actor_binding` v1.0 este obligatoriu în manifestul v2.0; contextul este
  derivat din autorizare, iar `expected_character_name` nu pretinde o identitate
  observată;
- `authorization_sha256` leagă manifestul și observațiile derivate de exact
  bytes ai autorizației validate, nu doar de un ID reutilizabil;
- timestampul sursei poate fi necunoscut, dar monotonic timestamp și frame age sunt obligatorii;
- raw pixels nu apar în manifest;
- default este `in_memory_only`, fără path/hash și fără retenție;
- persistarea cere artifact SHA-256 și clasificare privacy explicită;
- provenance este `window_capture` sau `replay_fixture`, niciodată server truth;
- `execution_authority=false` este impus de schemă.

## Environment probe 2026-08-22

În sesiunea desktop curentă, cu frame-ul păstrat numai în memorie:

| Backend | Frame | Probe duration | Rezultat |
|---|---:|---:|---|
| DXGI Desktop Duplication | 7680×2160 BGRA8 | 147.649 ms | pass |
| WinRT monitor capture | 7680×2160 BGRA8 | 427.081 ms | pass |

Aceste cifre sunt un cold one-shot environment smoke, nu throughput/FPS și nu client benchmark. Nu a fost salvată imaginea.

## Controlled client-region probe 2026-08-22

Clientul LAB real a fost pornit în sesiunea local-console și verificat la login screen:

- build vizibil: `2.4.3 (8606)`, locale instalat `enGB`;
- executable SHA-256: `406DA0C1C22D6E9121FD3BC17740A0D013660A03748CFE2A235768B8C574D3E6`;
- exact PID + HWND, title `World of Warcraft`, class `GxWindowClassD3d`;
- foreground, visible, non-minimized;
- per-monitor DPI: 144;
- client rectangle: `2048×1536` physical pixels;
- DXGI: pass, `114.711 ms` cold one-shot;
- WinRT monitor: pass, `213.017 ms` cold one-shot;
- contract-valid in-memory manifest: pass; valoarea istorică raportată atunci,
  frame age sub `0.2 ms`, folosea vechea semantică în care UTC și monotonic
  timestamp nu erau aliniate la aceeași limită de acquisition. Cifra este
  obsoletă și nu reprezintă latența curentă ori un deadline claim;
- raw frame persistence: none.

Prima comparație a locatorului a expus coordonate DPI-virtualized (`510×500`) într-un proces ne-aware. Rezultatul a fost respins. Locatorul setează acum explicit per-monitor-aware-v2, iar locatorul standalone și backend-ul GPU au produs aceeași regiune fizică (`2048×1536`).

## Limite curente

- RDP nu este un transport valid pentru clientul legacy care se închide la detectarea Remote Desktop.
- DXcam WinRT capturează monitorul; HWND-native WGC rămâne posibil sidecar viitor.
- Continuous move/resize tracking există și este verificat; crop stabilization și schimbarea multi-output rămân fail-closed.
- Minimap geometry detector există în sidecar și este verificat numai pe
  fixture-uri sintetice. Observația v1.0 păstrează actor binding-ul,
  `authorization_sha256` și scope-ul contextual al capturii, dar localizează
  doar cercul și markerul în screen
  pixels; nu produce coordonate absolute în lume. Calibrarea reală și map
  registration sunt încă pending.
- Sursa primară de self map coordinates este Observer HUD v1 vizibil, cu
  fiducials și CRC-16. Rasterul/freshness, două layout-uri, world map occlusion,
  relog și parity offline au trecut matricea și relaunch-ul controlled-live pe
  addonul exact `0.3.5`. Un al treilea current-source resmoke a verificat traseul
  după hardening-ul source binding, timestamp alignment și least-privilege
  fixed-UI authorization. PA-024B3b este închis; zone transition pe un LAB clone
  rămâne gate-ul separat PA-024B3c înainte de promovare.
- `WorldMapArea.dbc` exact-build și hash-pinned oferă transformarea client-asset către world-map 2D. Nu produce `z`; server DB este permis numai ca evaluator LAB.
- Camera/body sunt separate contractual și în fusion; scene/camera provider-ul live este încă pending.
- Captura unui desktop diferit, a unui output greșit sau a unei ferestre stale trebuie să fie fail-closed.

## Următorul gate PA-024B1

Gate închis pentru v0.1:

- continuous provider revalidează PID/HWND/foreground/rect înainte și după fiecare frame;
- caller-owned `new_frame_only` capture;
- ring buffer RAM bounded și șters la close;
- resize și move au trecut controlled-live;
- foreground loss a fost respins live;
- stale/no-new/deadline/source-change/output-mismatch sunt fail-closed;
- DXGI și WinRT au trecut câte 30 frame-uri la 10 Hz.
- probele încarcă target/build/hash din authorization config și verifică executabilul înainte de capture; identity manuală nu mai este acceptată.

Rezultatele complete sunt în [PA-024B1 continuous capture report](../reports/2026-08-22-pa024b1-continuous-capture.md). Core-ul determinist PA-024B2a este documentat în [PA-024B2a pose fusion report](../reports/2026-08-22-pa024b2a-pose-fusion-core.md), detectorul sintetic în [PA-024B2b1 minimap report](../reports/2026-08-22-pa024b2b1-minimap-geometry-detector.md), sursa primară și proba reală în [PA-024B3 visible coordinate HUD](../reports/2026-08-22-pa024b3-visible-coordinate-hud.md), iar transformarea 2D în [PA-024B4 client-asset world map](../reports/2026-08-22-pa024b4-client-asset-world-map.md). Următorul gate este PA-024B3c pe un LAB clone dedicat.
