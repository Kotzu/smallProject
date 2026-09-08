# PA-024B2a — Minimap anchor și pose fusion core v0.1

Data: 2026-08-22

Evidence class: `contract_tested` + `deterministic_fixture_tested`

Controlled-live pose evidence: **nu încă**

## Outcome

Există acum un boundary portabil și determinist între viitorul detector vizual și navigation:

```text
calibrated minimap measurement
            |
MinimapAnchorObservationBuilder
            |
      PoseObservation
            |
       PoseFusionEngine
            |
        PoseEstimate
            |
 movement proposal only; no execution
```

Detectorul nu poate declara o poziție exactă fără covariance, confidence, freshness, build/map identity și evidence reference. Fusion-ul nu consumă server truth și nu primește autoritate de execution.

## Implementare

- `src/perfect_assassin/pose/anchor.py`
  - `PoseIdentity`: leagă observația de session, Champion/LAB clone, target profile, client build, map signature și coordinate space;
  - `MinimapAnchorMeasurement`: măsurătoare normalizată, yaw, variance, confidence și timestamps;
  - `MinimapAnchorObservationBuilder`: produce `PoseObservation` contract-valid și lasă camera `LOST`.
- `src/perfect_assassin/pose/common.py`: freshness, timestamp și covariance helpers fără dependențe de capture/movement.
- `src/perfect_assassin/pose/fusion.py`: `PoseFusionEngine` combină determinist observații client-visible folosind inverse-covariance weighting.
- `tests/test_pose_fusion.py`: 10 teste dedicate.

## Reguli fail-closed

- anchor proaspăt: `ANCHORED`;
- anchor stale: `DEGRADED`, cu greutate redusă;
- anchor expirat sau lipsă: `LOST`, fără pose curent;
- client build, map signature, coordinate space sau context diferit: fusion refuzat;
- `lab_oracle` și `server_ground_truth`: refuzate chiar dacă recordul aparține unui LAB clone;
- camera reference frames diferite: fusion refuzat;
- lipsa tuturor surselor valide pentru o componentă: acea componentă devine `LOST`;
- `execution_authority=false` rămâne obligatoriu.

## Separarea body/camera

Body yaw este combinat numai din componenta `player`; camera yaw/pitch/roll/zoom numai din componenta `camera`. Un anchor de minimap nu inventează camera. Unghiurile sunt combinate circular, astfel încât `179°` și `-179°` produc o direcție apropiată de `180°`, nu `0°`.

## Uncertainty

Poziția, yaw-ul și camera folosesc diagonala covariance și confidence/freshness pentru weighting. Estimarea publică:

- covariance rezultată;
- `position_radius_95`;
- `vertical_error_95`;
- `yaw_error_95_deg`;
- camera angular/zoom error;
- confidence combinat;
- IDs exacte ale observațiilor folosite.

Acesta este un estimator v0.1 controlabil și reproductibil, nu încă un Kalman filter complet sau un model de locomotion.

## Verificare

- pose contract tests: pass;
- minimap anchor/fusion tests: pass;
- suite completă după implementare: 95/95 pass;
- `git diff --check`: pass;
- raw pixel persistence: none;
- gameplay input: none.

## Ce nu revendicăm

- nu există încă detecție reală a player arrow/minimap anchor din frame;
- nu există calibrare per UI scale/resolution/client;
- nu există scene-vision camera provider;
- nu există dead-reckoning bazat pe mișcare observată;
- nu există dovadă controlled-live pentru pose;
- nu există conectare pose -> actuator.

## Următorul gate: PA-024B2b

1. definirea unui minimap ROI profile versionat pentru `2.4.3.8606`;
2. detectarea robustă a cercului minimap și a player arrow pe replay-uri redactate;
3. calibrare pentru UI scale, rezoluție și north-up/rotating minimap;
4. scenarii negative: UI ascuns, loading screen, map open, occlusion, resize și frame stale;
5. probă controlată live read-only, cu comparație manuală și fără persistence implicită a pixelilor.
