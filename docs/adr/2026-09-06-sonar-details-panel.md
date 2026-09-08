# Sonar: distanțe și direcții condiționale în CC

## Decizie

Tab separat „Sonar”, lângă Mers, fără a micșora harta sau a adăuga controale
de execuție. Model pur de prezentare în adaptor; tabul Tk nu citește fișiere
și nu lansează query-uri. Reutilizează LocationLabelReader și aceleași porți
de identitate/prospețime. La expirare sau structură invalidă, tabelul se golește.
Cel mult 8 limite, 8 deschideri, 64 sonde; scroll pe ambele axe și texte
explicative reîncadrate la redimensionare. Rândurile identice nu sunt reconstruite.

## Semantica măsurătorilor

- Limite: distanța XY la segmentul navmesh, nu identificare sigură a unui zid.
- Deschideri: distanță, lățime geometrică, lungime rută. Tipul, înălțimea și
  destinația nu sunt inventate; nu sunt declarate traversabile de corp.
- Sonde: segment liber testat și raza maximă. Valoarea native clearance este
  limita inferioară găsită prin căutare binară, NU distanță exactă la primul hit.
  `hit_distance_yards=null`. Capătul navmesh rămâne neconfirmat când native
  `navmesh_reachable=false`: codul nu face raycast dacă clearance <95% din rază.
- Protocolul actual nativ: 16 direcții, rază 12 yd, înălțime Z+1,20 yd,
  7 iterații de căutare binară. Sonda nu certifică toate înălțimile ori spațiul
  dintre direcții. Nu este sonar acustic sau observație a entităților mobile.
- Unghiuri world: atan2(deltaY, deltaX), +X nord, +Y vest. Verificate față de
  transformarea WorldMapArea deja folosită în proiect. Nu folosim camera și
  nu afișăm față/spate fără facing corelat. Rotunjirea la sector cardinal este
  numai orientativă; unghiul numeric rămâne vizibil.
- Poziția geometrică de referință, etajul neconfirmat și vârsta poziției sunt
  explicite. Nu există eroare metrică măsurată care să transforme estimarea în
  distanță certă față de actor. Golurile și trunchierile nu certifică absența.

Raportul `conditional_spatial_sonar` primește câmpuri opționale aditive pentru
sondele existente și starea inferenței ieșirilor. Rapoartele vechi rămân lizibile
cu mențiunea că detaliile radiale lipsesc. Fără schimbare de addon, native build,
planner, controller sau v34.

## Dovezi

373 teste relevante PASS în 12,11 s; include direcții, raport vechi, valori
malformate, identitate străină, expirare, lățimi/distanțe și actualizarea
tabelului. Ruff pentru fișierele dedicate trece. Nu este întreaga suită.

Integrare offline cu WorldPack real și worker separat cu hash verificat:
exterior XY 1809,584 /1592,794 → 16 rânduri, altitudine estimată 98,875;
criptă XY 1676,370 /1677,467 → 32 rânduri, altitudine estimată 121,797,
două candidate verticale, cea mai apropiată limită 1,57 yd spre E, sondă N
limitată la circa 3,66 yd. Rapoarte de 4022 /7840 bytes, sub limita cititorului.
Acestea sunt interogări offline la coordonate de referință, nu mișcare live
și nu confirmare a etajului. O primă imprimare în terminal a eșuat la codarea
diacriticelor; rerularea cu JSON a reușit, fără schimbare a logicii geometrice.

Verificare vizuală live: CC relansat normal, tab Sonar deschis, 16 sonde
afișate, altitudine estimată 98,88 yd și etaj neconfirmat. Originea a rămas
1809,58 /1592,79. Toate cele 16 sonde au segment liber testat 12 yd la
înălțimea lor; raycast navmesh confirmat pentru 7 capete, neconfirmat pentru 9.
Nu afirmăm că gardul vizibil este detectat de aceste sonde. Vârsta afișată
2,0–2,5 s în capturile făcute; diagnosticul LIVE fără eroare sonar.
Verificată și reîncadrarea la o lățime de fereastră mai mică: tabel și note
lizibile. Nu este un benchmark al tuturor rezoluțiilor. Navigatorul a rămas
oprit, fără input în joc. Skill-ul computer-use a servit verificării tabului
și redimensionării normale a ferestrei, nu controlului Predatorului.
Rollback: revert al commitului dedicat și restart normal CC; workerul v34 și
anti-AFK nu sunt schimbate.

## Urmează

Separarea etajelor prin dovezi independente, eroarea poziției și geometria
verificată pe mai multe înălțimi. Legarea la planner numai după validarea
contextului și a volumului corpului. Tabelul nu închide aceste etape.
