# PA-024B1 pose contracts — 2026-08-22

## Outcome

Contractul read-only pentru localizare este implementat:

- `PoseObservation` pentru observații individuale;
- `PoseEstimate` pentru rezultatul fuziunii;
- player/body și camera sunt componente separate;
- pose, velocity, covariance, confidence, freshness și provenance sunt explicite;
- build/map signatures protejează împotriva folosirii hărții greșite;
- `ANCHORED | TRACKED | DEGRADED | LOST` controlează degradarea;
- `LOST` impune pose/uncertainty nule și confidence zero;
- Champion respinge `lab_oracle` și `server_ground_truth`;
- toate recordurile au `execution_authority=false`.

## Evidence scope

`contract_tested`. Nu există încă GPU capture, pose provider, fusion runtime sau movement input. Următoarea jumătate a PA-024B1 este capture/provider replay intake.

Suita completă după integrare: 56 teste trecute.
