# Tranziția pe scări: dovezi din filmarea existentă

## Probă delimitată

Filmarea originală și cadrele 85/94–100/110/120/140s au fost inspectate offline.
Nu s-a pornit test live, nu s-a modificat CC, navigatorul sau anti-AFK.
Cadrele rămân în directorul runtime ignorat. Banda coordonatelor din cadrele
94–100s a trecut decodarea CRC cu detectorul existent. Numele de mai jos au
fost citite vizual din cadre, nu din noul transport API și nu reprezintă Z.

- 95s și 97s: personajul este vizibil pe scări; minimapa păstrează compoziția
  interiorului și textul Shadow Grave.
- 98s: personajul apare pe platforma de sus, minimapa arată terenul exterior,
  dar textul rămâne Shadow Grave. La 99s situația persistă.
- 100s: personajul este afară și textul devine Deathknell.

Schimbarea imaginii este deci observată în intervalul (97s,98s], separat de
schimbarea textului în (99s,100s]. Nu deducem o latență exactă sau o regulă
universală din eșantionarea la o secundă; pot fi granițe de afișare diferite.

## Comparație cu geometria

Workerul de înălțimi, WorldPack-ul, indexul și bundle-ul WMO au fost verificate
prin mecanismele existente. Interogările sunt pentru XY arhivat, cu seed Z=100
explicit geometric, nu pentru poziția curentă. Compoziția interiorului a fost
comparată la poziția prezisă din XY, rotație/scară fixe, fără căutare liberă
a unui alt petic după ieșire. Suportul are 3760 pixeli.

| Cadru | Corelație la poziția prezisă | Suprafețe candidate native, Z |
| --- | --- | --- |
| 85s | 0.75375 | 121.670, 138.452 |
| 94s | 0.56595 | 126.932, 142.198 |
| 95s | 0.70907 | 129.860, 141.230 |
| 96s | 0.51595 | 156.007, 141.851, 132.477, 141.123 |
| 97s | 0.64378 | 154.361, 137.051 |
| 98s | -0.05834 | 155.150, 141.849, 120.719, 141.015 |
| 99s | -0.05293 | 152.568, 141.851, 120.719, 141.538 |
| 100s | -0.11318 | 139.313 |

La 98s/99s, suprafața WMO inferioară aparține grupului 4, iar cele superioare
grupului 0. Grupul 0 nu are textură în setul minimapei extras anterior.
Suprafețele orientate în sus includ și acoperișuri; nu sunt automat podeaua
ocupată. La 100s nu există hit WMO orientat în sus în bundle-ul verificat.

Seed-ul fix 100 selectează suprafața inferioară 120.719 la 98s/99s, deși
imaginea arată personajul sus. Aceasta demonstrează riscul unei inițializări
prin proiecție; NU demonstrează că observerul live, care poate reutiliza seed-ul
anterior, a făcut aceeași selecție. Toți candidații au rămas păstrați.

Rezultatele complete: `data/runtime/minimap-wmo-probe/transition-audit-v1.json`;
decodări: `archived-position-94.json` până la `archived-position-100.json`.
Nu s-a stabilit un prag general de corelație; UI, occluderi și clipping pot
reduce scorul în alte scene. Absența unei potriviri nu certifică exteriorul.

## Consecință pentru continuare

Păstrăm separat schimbarea texturii, numele subzonei, API interior/exterior și
suprafețele geometrice. Nu eliminăm toate suprafețele WMO când apare minimapa
exterioară și nu atribuim etaj după numele zonei. Următorul pas util este
verificarea continuității dintre suprafețele candidate pe traseul arhivat,
împreună cu această schimbare vizuală; o simplă rază sau apropiere de seed nu
este suficientă. Nu extindem căutarea de texturi înaintea acestei verificări.

Doar documentare și artefacte offline în acest pas; codul nu s-a schimbat,
deci nu repetăm suita de 111 teste deja trecută la commitul f583616.
Goal-ul spațial complet rămâne neîncheiat. Operatorul a semnalat 24% usage
rămas: pași următori mici și delimitați, fără reluarea auditurilor deja făcute.
