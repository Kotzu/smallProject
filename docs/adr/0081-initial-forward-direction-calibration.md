# ADR-0081: Calibrarea direcției înainte de primul W

## Stare

Acceptată — 2026-09-01

## Decizie

La începutul fiecărui coridor validat, runnerul armează o singură probă de
direcție. După primul chord de deplasare continuă, compară vectorul observat
din poziția clientului cu tangenta coridorului. Dacă sunt foarte diferite, iar
actorul nu este deja în afara coridorului, direcția mouse-integrată este
înlocuită temporar cu vectorul observat. Următorul tick intră în pivotul
staționar forțat, cu W eliberat, până când camera ajunge la tangenta
coridorului. Abia după această aliniere controllerul poate ține din nou W.
Pragul chordului este `0.75` unități de lume, iar abaterea acceptată este
`0.50` radiani. Astfel o direcție greșită este observată devreme, fără a
folosi zgomot sub pragul de deplasare.

Un facing exact din HUD câștigă mereu. Un chord cu abatere mare și cross-track
mare este clasificat `UNSAFE`, nu este folosit pentru calibrare și rămâne sub
protecția fail-closed existentă. Proba se rearmează la un coridor nou sau la o
handoff semantică.

## Motiv

După reset, camera salvată și forward-ul personajului pot avea direcții
diferite. În v49, coridorul Crypt→Brill cerea vest, dar primul chord real a
mers est; minimapa nu a fost o dovadă suficientă pentru această diferență.

## Limite

Regula folosește doar poziția observată de client, tangenta coridorului
navmesh și starea de mișcare. Nu folosește server truth, coordonate inventate,
waypoints hardcodate, combat sau autoritate nouă de input.
