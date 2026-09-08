# ADR-0129 — ZulAman legat read-only în registry

## Context

`568:ZulAman` are terrain client complet în catalogul TBC, dar nu are semantic
catalog de destinații și nu trebuie promovat ca rută autonomă.

## Decizie

Sigilăm candidatul nou `tbc243-dungeons-candidate-v6`, păstrând v5 și toate
pack-urile anterioare pentru rollback. Legăm map-ul `568` în registry doar ca
awareness topografic read-only; `autonomous_ready` și
`execution_authority` rămân `false`.

## Dovezi

Bake-ul offline acoperă `25/25` ADT și nav tiles, cu `0` dale lipsă sau
eșuate; validatorul geometric independent trece `25/25`. Indexul are `1323`
structuri (`35` WMO, `1288` doodad). Scanarea bounded read-only a închis
`993/993` probe, cu `229` observații acceptate, `53` access openings, `1362`
boundary chains și `0` erori; graful este `PARTIAL_OBSERVED_COMPONENTS`.
WorldPack-ul v6 are `7` hărți, `1873` artefacte și hash-ul
`6e2e4d3eddbaec9df86e8656e63f7f36106f61d65e9e89f90d2df7af642549f2`.
