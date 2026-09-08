# ADR-0067 — Aliasuri explicite pentru reconcilierea Zygor–WorldMapArea

## Context

LibRover din pachetul Zygor TBC Anniversary folosește denumiri de zonă pentru
utilizator (`Tirisfal Glades`, `The Barrens`, `Darnassus`), în timp ce
`WorldMapArea` al clientului 2.4.3 păstrează denumiri interne legacy
(`Tirisfal`, `Barrens`, `Darnassis`). Reconcilierea numai prin egalitate sau
normalizare de text lăsa map-area-uri valide nelegate.

## Decizie

Introducem un tabel mic, versionat în cod, de aliasuri de identitate între cele
două vocabulare. Aliasurile sunt folosite numai pentru audit și pentru
transformarea 2D a unor coordonate statice; nu conțin waypoints, nu produc
înălțime și nu acordă autoritate de execuție. Legarea rămâne fail-closed dacă
rezultatul clientului este lipsă sau ambiguu.

Reconcilierea actualizată raportează separat doar statusuri și count-uri
content-minimal. Datele NPCData și payload-ul licențiat nu sunt persistate în
repository.

## Consecințe

Aliasurile rezolvă denumirile clientului care diferă superficial și ridică
reconcilierea NPCData de la `45/66` la `62/66` map-area-uri. Black Temple și
instanțele sintetice fără rând `WorldMapArea` rămân nerezolvate și nu sunt
promovate implicit.
