# ADR 0046: Precedență MPQ deterministă pentru orice bake de client

## Status

Accepted.

## Context

Clientul TBC 2.4.3 distribuie aceeași cale virtuală în mai multe arhive MPQ.
Fișierul din patch-ul cu prioritate mai mare trebuie să înlocuiască versiunea
de bază. Ordinea aceasta face parte din identitatea datelor, la fel ca build-ul
clientului.

Namigator încărca arhivele în ordinea corectă, dar le stoca într-un
`std::unordered_map`. Citirea unui asset itera apoi acea colecție. În practică,
inventarul standalone vedea 800 de ADT-uri `Expansion01`, iar MapBuilder vedea
numai 776, deoarece WDT-ul și ADT-urile puteau proveni din niveluri de patch
diferite. Repetarea build-ului reproducea amestecul pe aceeași mașină, fără să
îl facă valid.

## Decizie

Arhivele MPQ folosite de parser sunt păstrate într-un vector ordonat. Primul
asset găsit respectă astfel precedența explicită stabilită la inițializare.
Patch-ul este păstrat reproductibil în
`patches/namigator/0001-deterministic-mpq-patch-precedence.patch`.

Nu se promovează niciun navmesh construit înainte de această corecție în
WorldPack-ul comun Azeroth + Kalimdor + Expansion01. Toate cele trei hărți,
semantica drumurilor și biblioteca BVH sunt reconstruite într-un root gol cu
același executabil. O probă izolată pe `Expansion01 (42, 6)`, absentă anterior,
trebuie să producă un tile înainte de rebuild-ul complet.

## Consecințe

- Același client și același builder aleg aceiași bytes MPQ la fiecare rulare.
- Catalogul nu poate combina WDT, ADT, WMO sau doodad din patch-uri diferite
  prin ordinea accidentală a hash buckets.
- Rebuild-ul complet costă timp, dar elimină o clasă de erori care altfel ar
  apărea ca găuri de hartă, blocaje sau reparații locale false.
- Pentru suportul altor clienți, adaptorul poate declara altă listă de arhive,
  însă consumatorul trebuie să păstreze ordinea declarată.
