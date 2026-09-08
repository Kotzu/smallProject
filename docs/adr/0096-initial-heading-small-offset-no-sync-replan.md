# ADR-0096 — Corecția inițială nu replanuiește sincron pentru abatere mică

## Context

Pe clientul live TBC, prima coardă de mers poate arăta că orientarea veche a
camerei nu era bună. Corecția prin deplasare este utilă, dar actorul rămâne de
obicei în coridorul WorldPack deja verificat. Recalcularea sincronă a aceluiași
coridor după această corecție poate ține bucla de captură fără observație
secunde întregi. În offline, navmesh-ul este imediat și problema nu apare.

## Decizie

După o realiniere inițială, runner-ul păstrează coridorul validat și folosește
pivotul staționar deja cerut când abaterea laterală este sub
`INITIAL_DIRECTION_REPLAN_MIN_CROSS_TRACK_WORLD = 2,0` yarzi. Când abaterea
atinge sau depășește pragul, se păstrează replanificarea bounded din poziția
observată. Ambele ramuri emit dovadă în jurnal.

Pragul nu schimbă autorizația de input și nu inventează o poziție. El doar
împiedică o interogare sincronă scumpă atunci când poziția încă este în
coridorul topografic. Observația proaspătă și lease-ul de `450 ms` rămân
obligatorii.

## Consecințe

O mică nepotrivire de heading nu mai produce pauza live de ordinul secundelor;
camera se corectează prin pivot, iar drumul existent continuă. O abatere mare
replanifică în continuare și poate opri fail-closed dacă planul nu este valid.
Replay-ul offline și verificarea WorldPack rămân neschimbate.
