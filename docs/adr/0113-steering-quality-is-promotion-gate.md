# ADR-0113: Calitatea steering-ului este poartă separată de bake

## Context

Un navmesh poate fi extras complet și poate trece verificarea structurală, dar
coridoarele înguste, scările, doodad-urile și hairpin-urile pot rămâne greu de
urmărit de controller. Un bake `COMPLETE` nu este, singur, dovadă de mers bun.

## Decizie

Un WorldPack candidat nu este promovat în registry doar pentru că are toate
tile-urile și geometria validă. Trebuie să treacă și corpusul bounded de
steering pe tile-urile eligibile, fără query-uri neeligibile și fără coridoare
care depășesc limitele de quality. Un test MPPI izolat nu poate ocoli această
poartă.

## Consecințe

Candidate-urile care au geometrie bună, dar steering slab, rămân sigilate,
nelegate în registry și cu `execution_authority=false`. Diagnosticele rămân
reproductibile și pot ghida repararea geometriei sau a controllerului fără a
schimba WorldPack-ul Stable.
