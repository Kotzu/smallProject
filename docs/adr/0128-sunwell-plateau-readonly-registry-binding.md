# ADR-0128 — Sunwell Plateau legat read-only în registry

## Context

`580:SunwellPlateau` are terrain client complet în catalogul TBC, dar nu are
semantic catalog de destinații și nu trebuie promovat ca rută autonomă.

## Decizie

Sigilăm candidatul nou `tbc243-dungeons-candidate-v5`, păstrând v4 și toate
pack-urile anterioare pentru rollback. Legăm map-ul `580` în registry doar ca
awareness topografic read-only; `autonomous_ready` și
`execution_authority` rămân `false`.

## Dovezi

Bake-ul offline acoperă `30/30` ADT și nav tiles, cu `0` dale lipsă sau
eșuate; validatorul geometric independent trece `30/30`. Indexul are `1565`
structuri (`14` WMO, `1551` doodad). Scanarea bounded read-only a închis
`453/453` probe, cu `47` observații acceptate, `32` access openings, `418`
boundary chains și `0` erori; graful este `PARTIAL_OBSERVED_COMPONENTS`.
WorldPack-ul v5 are `6` hărți, `1700` artefacte și hash-ul
`67f15af4b319b0d014420cb49691bb2a5661ee24c3f36e3994e9e67fba7d4bd3`.
