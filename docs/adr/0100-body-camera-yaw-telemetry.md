# ADR-0100 — Telemetrie separată pentru yaw-ul corpului și al camerei

## Context

Într-un client TBC vechi, camera se poate roti înainte ca avatarul să urmeze
aceeași direcție. Un singur câmp numit `heading` ascunde această diferență și
face dificilă explicarea unei abateri live.

## Decizie

Fiecare `HEADING_READY_BEFORE_CONTROL` și `CONTINUOUS_FRAME` scrie separat:

- `body_yaw_observation_rad` și `body_yaw_observation_source`, provenite din
  HUD-ul/markerul vizibil al clientului;
- `camera_yaw_estimate_rad`, headingul integrat din comanda de mouse;
- `body_camera_yaw_delta_rad`, diferența unghiulară bounded dintre cele două.

Estimarea camerei nu este o citire directă a camerei și nici server truth. Lipsa
oricăruia dintre cele trei valori face dovada incompletă în poarta strictă a
evaluatorului.

## Consecințe

Următoarea probă live va arăta dacă abaterea vine din corp, cameră sau din
întârzierea observației. Schimbarea este doar telemetrie și analiză offline;
nu acordă autoritate de input și nu pornește clientul.
