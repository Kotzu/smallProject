# ADR-0064 — Catalog client-derived pentru transformările map-area TBC

## Context

WorldMapArea auditul TBC 2.4.3 conține bounds pentru zone de pe continente,
instanțe și hărți de battleground, dar Movement Engine-ul avea o transformare
revizuită doar pentru Tirisfal și Undercity. RouteTeacher și Control Center
aveau astfel dovezi de hartă mai largi decât stratul de transformare disponibil.

## Decizie

Păstrăm bounds-urile auditate într-un catalog separat,
`config/pose/world-map-zone-transforms-tbc243-8606.json`, cu 68 de chei unice
`(map_id, area_id)`. Loaderul din
`perfect_assassin.adapter.world_map_zone_catalog` validează contractul,
hash-ul assetului, provenance-ul, bounds-urile finite și unicitatea. Catalogul
este read-only și are permanent `execution_authority=false`.

## Consecințe

- conversia normalized-map ↔ world 2D poate fi verificată pentru toate rândurile
  clientului auditat, inclusiv Kalimdor și Expansion01;
- Control Center poate afișa acoperirea fără să confunde transformarea cu un
  traseu, o înălțime sau o poziție live;
- înălțimea, vizibilitatea entităților și autorizarea inputului rămân separate;
- profilele WorldPack fără semantic catalog/access graph continuă să fie
  `OBSERVE_ONLY` și nu pot porni autonomie.

## Dovezi

Catalogul este derivat din
`data/runtime/navigation-f3b/client-world-map-area-audit-20260831.json`, cu
asset SHA-256 și fingerprint păstrate în record. Testele dedicate trec `4/4`,
testele UI aferente `29/29`, iar regresia completă după integrare trece
`1309/1309`.
