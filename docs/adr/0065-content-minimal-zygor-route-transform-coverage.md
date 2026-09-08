# ADR 0065 — Acoperire content-minimal a transformării rutelor Zygor

## Context

Pachetul local Zygor Anniversary conține pași RouteTeacher în coordonate 0–100.
Catalogul client `WorldMapArea.dbc` oferă doar transformarea 2D pentru rândurile
auditate; nu oferă înălțime, poligoane navigabile sau autoritate de execuție.
Era necesară o verificare reproductibilă pentru a separa coordonatele care pot
fi transformate de cele pentru care assetul client nu are un rând compatibil.

## Decizie

`scripts/audit_zygor_route_transform_coverage.py` reparsează aceleași șase
fișiere non-Trial prin importatorul bounded și validează fiecare coordonată
împotriva catalogului read-only `WorldMapArea`. Aliasurile de nume sunt numai
compatibilitate între eticheta publică Zygor și numele intern al assetului; nu
sunt waypoints și nu pot genera input.

Artefactul păstrează hash-uri, count-uri, map/area IDs și hash-uri pentru cheile
de transformare nerezolvate. Nu păstrează coordonate, nume de ghid, text NPC
sau payload Lua. Orice zonă fără binding sau coordonată invalidă oprește auditul
fail-closed; o instanță fără rând WorldMapArea rămâne ne-transformată.

## Consecințe

Auditul real `data/runtime/navigation-f3b/zygor-route-transform-coverage-20260901.json`
transformă `11.686/11.687` coordonate candidate (`99,991%`), pe toate cele trei
hărți continentale: Azeroth `3.434/3.434`, Kalimdor `3.918/3.918` și Expansion01
`4.334/4.334`. Singurul candidat nerezolvat este coordonata de pe map ID 564
(Black Temple), pentru care catalogul WorldMapArea auditat nu are rând; starea
rămâne `PARTIAL_CLIENT_2D_TRANSFORM`.

Aceasta este dovadă de conversie 2D și nu promovează semantic/access autonomy,
nu creează rute executabile și nu autorizează test live.
