# ADR 0088 — Proveniența orientării corpului în TBC 2.4.3

## Decizie

Poziția proprie X/Y rămâne citită din HUD-ul vizibil al addonului și este
considerată client-observed, cu CRC și freshness. Orientarea corpului nu este
numită „exactă” decât dacă același HUD publică explicit `facing_rad` și sursa
runtime este `COORDINATE_HUD_EXACT`.

În clientul TBC 2.4.3, `GetPlayerFacing()` nu este o dovadă disponibilă în
mod normal. Câmpul `api_capabilities.player_facing_api` este publicat separat,
ca să vedem clar dacă API-ul există în sesiunea observată. Minimapul, integrarea
mouse-ului și vectorul de deplasare rămân estimări utile pentru mișcare, dar nu
pot fi prezentate ca orientare exactă pentru combat.

Runner-ul are acum opțiunea explicită `--require-exact-body-heading`. Când este
folosită, orice sursă în afară de HUD-ul exact oprește sesiunea înainte de
mișcare. Opțiunea este fail-closed și nu acordă autoritate nouă.

## Motiv

Run-ul bun vechi a raportat `VISIBLE_CLIENT_HEADING_FUSED`; acesta a fost un
rezultat de fuziune vizuală/deplasare, nu un unghi direct din client. În ME-306
X/Y a continuat să fie prezent, dar sursa de heading a fost
`MOUSE_INTEGRATED_MINIMAP_FALLBACK`, iar camera s-a dus spre tavan. Amestecarea
celor două dovezi ascundea diferența importantă dintre poziție și yaw.

## Consecințe

- Nu declarăm orientarea exactă doar pentru că există o poziție exactă.
- Combatul trebuie să ceară o sursă de heading cu provenance explicită.
- Pentru TBC 2.4.3, rezolvarea practică rămâne calibrarea vizuală bounded și
  verificarea camerei, nu inventarea unui API sau acces la memoria clientului.
- Schimbarea este offline-only; nu reîncarcă addonul și nu pornește test live.
