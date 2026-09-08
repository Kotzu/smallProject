# ADR-0052 — Ancoră de teren pentru ieșirea dintr-o structură WMO

## Context

Un midpoint din `structure-access-graph` este o dovadă de frontieră, nu
neapărat o poziție traversabilă. În Crypt, aceeași zonă putea fi rezolvată de
navmesh pe suprafața acoperită `wmo`, iar predarea directă producea coliziuni.

## Decizie

`MovementEngine` păstrează legul de apropiere până la opening-ul verificat și
caută apoi o ancoră mică, bounded, pe direcția derivată din centrul WMO către
opening. Fiecare candidat este cerut din navmesh; continuarea este acceptată
numai când awareness-ul de start conține `ground` și nu conține `wmo`.
Fără dovadă de suprafață din adaptorul clientului se păstrează propunerea
baseline, iar execuția rămâne fail-closed.

## Consecințe

Coordonatele rămân date din WorldPack și graful versionat, fără waypoint
hardcodat. Sunt necesare teste de contract și verificări live bounded; o ancoră
validată offline nu demonstrează singură stabilitatea traseului exterior.
