# ADR-0094 — Catalog local de cunoștințe TBC cu limite și proveniență

## Context

Ghidurile TBC selectate au mii de pași, iar `NPCData.lua` are mii de rânduri.
Limita inițială de 4.096 intrări și scurtarea oarbă a ID-urilor împiedicau
construirea unui catalog complet, deși parserul bounded putea citi datele.

## Decizie

Contractul `knowledge_broker_catalog` permite cel mult `16.384` intrări.
Importul RouteTeacher păstrează ID-ul lizibil și adaugă un hash determinist
când depășește 128 de caractere, astfel încât fiecare pas rămâne unic.
Importul NPCData poate scrie un catalog local separat; rândurile rămân în
`map_scope=zone_area`, cu poziție `STATIC_SOURCE_CANDIDATE`, confidence și
proveniență. Un catalog nu se leagă automat de un WorldPack și nu acordă
`execution_authority`.

## Consecințe

- Ghidurile Horde și Alliance pot fi păstrate integral ca date advisory locale.
- Trainerii și NPC-urile statice pot fi căutate ulterior după map-area explicită.
- Coordonatele nu sunt poziții live și nu pot porni Movement Engine-ul fără
  confirmare client și gate separat.
- Fișierele originale Zygor rămân în afara repo-ului; se păstrează doar
  catalogul generat local și metadatele lui.
