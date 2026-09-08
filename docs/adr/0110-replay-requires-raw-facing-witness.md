# ADR 0110 — Replay-ul cere martorul brut de facing

## Decizie

Evaluatorul offline `replay_heading_integrity.py` nu mai acceptă un
`camera_yaw_estimate_rad` atunci când cadrul declară o sursă client-facing
cunoscută, dar nu conține și yaw-ul brut corespunzător. Pentru
`MINIMAP_VISION_FALLBACK` martorul este `player_facing_rad`; pentru
`COORDINATE_HUD_EXACT` este permisă compatibilitatea cu
`body_yaw_observation_rad` din urmele mai vechi.

## Motiv

Un yaw de cameră poate rămâne numeric chiar după ce markerul vizibil dispare.
Fără această regulă, replay-ul putea părea sănătos deși runtime-ul nu mai avea
dovadă proaspătă de facing. Regula face replay-ul identic cu poarta
facing-first: lipsa martorului brut oprește evaluarea fail-closed.

## Consecințe

- Un rezultat offline nu poate ascunde lipsa facingului în spatele predicției
  camerei.
- Urmele vechi rămân lizibile, dar sunt marcate incomplete și nu promovează
  autonomia.
- Nu se schimbă sursele de input, nu se citește memoria clientului și nu se
  acordă autoritate de execuție.
