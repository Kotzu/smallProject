# ADR-0083 — Portal lateral clearance for bridges

## Context

Un actor care merge pe mijlocul unui pod poate avea încă loc liber în stânga
și în dreapta. O linie de traseu singură nu arată această informație. În
combat, o strafe automată poate consuma acel spațiu și poate face actorul să
pară blocat sau să ajungă la margine.

## Decizie

Detour `NavPortal` păstrează capetele portalului și lățimea lui. Movement
Engine calculează, lângă portalul cel mai apropiat, distanța centrului actorului
până la ambele margini și scade raza actorului plus o marjă mică. Rezultatul
este `PortalLateralClearance`, o dovadă locală de geometrie a clientului.

Această dovadă:

- nu este waypoint și nu acordă autoritate de execuție;
- se aplică generic la poduri, scări, uși și alte coridoare înguste;
- este `None` când nu există un portal apropiat, deci lipsa dovezii nu este
  tratată ca spațiu liber;
- oprește orbitarea laterală automată în combat când actorul este prea aproape
  de margine, dar păstrează camera și ținta observabile.

## Consecințe

Podurile nu mai sunt tratate doar ca o linie fără lățime. În viitor, atlasul
static poate păstra aceste măsurători pe tile, iar layer-ul dinamic poate
decide dacă un mob sau un jucător ocupă banda. Pozițiile dinamice rămân numai
cele observate de client; nu se folosește server truth.

## Verificare

Testele offline acoperă un actor centrat, un actor lângă margine și frâna de
strafe în combat. Niciun test live nu este pornit de această decizie.
