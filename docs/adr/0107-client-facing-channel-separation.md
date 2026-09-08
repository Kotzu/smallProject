# ADR-0107: Separarea canalului de facing brut de body yaw

## Context

În clientul TBC, coordonatele HUD pot furniza `facing_rad` exact. Când acest
câmp lipsește, runner-ul poate calcula un heading limitat din markerul
minimapei și îl poate pune în aceeași structură `position` pentru steering.
Valoarea calculată din minimapă descrie însă camera/markerul, nu este dovadă
directă că trupul Predatorului privește în acea direcție.

## Decizie

Păstrăm două canale diferite în telemetrie:

- `player_facing_rad` este valoarea brută a canalului client-facing etichetat
  (`COORDINATE_HUD_EXACT` sau `MINIMAP_VISION_FALLBACK`) și rămâne disponibilă
  pentru replay-ul headingului vizibil;
- `body_yaw_observation_rad` și `body_camera_yaw_delta_rad` sunt populate numai
  când sursa este `COORDINATE_HUD_EXACT`.

Pentru un cadru de minimapă, câmpul body este `null`, iar sursa body este
`UNAVAILABLE`. Evaluatorul și replay-ul strict nu pot trece un cadru de
minimapă folosind accidental câmpul body. Urmele vechi cu body-only rămân
citibile în modul diagnostic, dar nu sunt promovate drept dovadă completă.

## Consecințe

- Se vede clar dacă problema live este în camera/markerul vizibil sau în
  orientarea reală a corpului.
- Poarta `--require-body-camera-separation` cere dovadă HUD exactă; minimapa
  singură nu poate inventa această dovadă.
- Nu se schimbă planner-ul, WorldPack-ul, limitele de input sau autoritatea de
  execuție. Schimbarea este telemetrie și replay offline.

## Verificare

Testele pentru runner, replay și evaluator verifică atât cadrul exact, cât și
respingerea unui minimap body-only. Nu s-a pornit clientul live și nu s-a
trimis input.
