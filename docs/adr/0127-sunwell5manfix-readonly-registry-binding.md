# ADR-0127 — Sunwell5ManFix legat read-only în registry

## Context

`585:Sunwell5ManFix` are acum un bake local complet, dar nu are semantic
catalog de destinații și nu are dovadă de rută autonomă.

## Decizie

Păstrăm pack-ul existent neschimbat și sigilăm un candidat nou,
`tbc243-dungeons-candidate-v4`, cu hărțile `36`, `209`, `289`, `543` și `585`.
Legăm map-ul `585` în registry numai pentru awareness topografic read-only.
`autonomous_ready` rămâne `false`, iar `execution_authority` rămâne `false`.

## Dovezi

Pack-ul v4 este sigilat și verificat cu hash-ul
`8c7bafb2a18456eadf0ff3475355918c5dec94cc840b3e099f74dbd36bc07aa`, cu `1632`
artefacte și toate dependențele runtime false. Indexul are `1711` structuri
(`11` WMO, `1700` doodad). Scanarea read-only a închis `339/339` probe, cu
`43` observații acceptate, `50` access openings, `449` boundary chains și `0`
erori; graful este `PARTIAL_OBSERVED_COMPONENTS`. Auditul registry trece
`--check` cu `83/83` identități, `14` hărți `topographic_ready` și `1` hartă
`autonomous_ready`. Nu s-a pornit WoW și nu s-a trimis input live.
