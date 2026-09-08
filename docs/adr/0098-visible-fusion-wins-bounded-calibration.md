# ADR-0098 — Fuziunea vizibilă câștigă în calibrarea bounded

## Context

Calibrarea inițială poate păstra temporar un heading derivat dintr-o coardă de
deplasare după o realiniere. Într-o versiune anterioară, această ținere scria
peste rezultatul proaspăt `VISIBLE_CLIENT_HEADING_FUSED`, deși markerul vizibil
era deja disponibil. Astfel, o măsurătoare care trebuia să închidă deriva era
ignorată tocmai în fereastra de calibrare.

## Decizie

În fereastra bounded de calibrare, un rezultat cu sursa
`VISIBLE_CLIENT_HEADING_*` rămâne headingul folosit și consumă un cadru din
fereastră. Ținerea `DISPLACEMENT_INITIAL_DIRECTION_CALIBRATION` se aplică doar
când nu există heading vizibil utilizabil. `COORDINATE_HUD_EXACT` rămâne
prioritar și închide imediat fereastra.

## Consecințe

Fuziunea vizibilă rămâne sursa principală pentru TBC 2.4.3, iar displacement-ul
rămâne doar calibrare bounded și diagnostic. Nu se folosesc wall-slide, A/D,
server truth sau input suplimentar. Schimbarea este verificată offline; nu
dovedește încă stabilitatea în clientul live.
