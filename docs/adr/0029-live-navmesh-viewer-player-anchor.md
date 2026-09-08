# ADR 0029 — Ancoră Predator și context local în viewerul navmesh

## Status

Acceptat pentru instrumentarea LAB read-only.

## Context

Un singur tile ADT afișat lângă poziția observată creează o margine gri artificială
și poate face zona să pară greșită. În plus, un marker cyan se confundă cu navmesh-ul
traversabil și nu comunică orientarea personajului.

## Decizie

1. Viewerul pornește pe harta fizică primită de adaptor (`000 Azeroth` pentru
   Deathknell), fără ca subzona să fie inventată ca hartă separată în dropdown.
2. Poziția Predatorului este ancora camerei, iar primul cadru al bridge-ului reaplică
   centrarea după inițializarea hărții și a tile-urilor.
3. Viewerul încarcă tile-ul poziției și vecinătatea ADT 3×3. Aceasta este doar
   vizualizare locală și streaming de geometrie, nu hardcodare de rută.
4. Predatorul este desenat separat de navmesh și de markerii debug ca pointer de
   compas mov, plin, cu contur albastru și crestătură în coadă. Dimensiunea lui
   rămâne apropiată de amprenta unui personaj, nu de cea a unei clădiri. Vârful reprezintă
   facingul. Markerul folosește depth test normal și un offset Z limitat la
   înălțimea capsulei personajului, astfel încât coada să nu intre în relieful
   înclinat; copacii și clădirile îl pot acoperi, păstrând adevărul spațial al
   scenei.
5. Când clientul nu este în world, viewerul păstrează ultima poziție observată; nu
   fabrică o poziție nouă și nu primește execution authority.
6. Camera viewerului păstrează azimutul în spatele facingului observat al
   Predatorului. În regimul controlat cu click dreapta ținut, acesta este aceeași
   axă verticală a ecranului ca în joc. Pentru a evita terenul, WMO-urile și
   doodads, solverul testează segmentul cameră–Predator și poate modifica numai
   distanța și înălțimea, nu poate alege arbitrar altă rotație a hărții. Tranzițiile
   între pozițiile camerei sunt interpolate, iar markerul rămâne în spațiul 3D cu
   depth test activ.
7. `player_facing` nu este prezentat drept `camera_yaw` în free-look. Dacă adaptorul
   va observa separat orientarea camerei, acel canal va putea înlocui fallback-ul
   RMB fără schimbarea contractului de navmesh sau a adevărului spațial.

## Alternative considerate

- Marker cyan: respins deoarece se confundă cu suprafața traversabilă.
- Încărcarea unui singur ADT: respinsă deoarece marginea tile-ului pare margine de
  hartă și ascunde contextul imediat.
- Selectarea manuală a Deathknell: respinsă deoarece Deathknell este subzonă din
  Azeroth, nu hartă fizică independentă.

## Consecințe

- Zona din jur este mai ușor de recunoscut, cu un cost LAB limitat la maximum nouă
  tile-uri locale.
- Markerul rămâne vizibil când navmesh-ul este activ și nu este șters de `Clear
  markers`.
- Poziția afișată după logout este explicit ultima observație validă, nu telemetrie
  live.

## Verificare

- Testele sursă verifică selecția automată, recentrarea primului frame, încărcarea
  vecinătății și culoarea distinctă a markerului.
- Build-ul MapViewer și o captură LAB confirmă geometria Deathknell, ancora mov și
  săgeata de facing.
