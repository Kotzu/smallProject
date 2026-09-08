# ADR-0123 — Scholomance read-only registry binding

## Context

Scholomance (`map_id=289`) had a complete client-derived candidate WorldPack,
but the registry still exposed it only as inventory identity. The candidate has
no semantic destination catalog, so it must not become an autonomous launch
profile.

## Decizie

Bind `289:SchoolofNecromancy` in the registry to the two-map dungeon candidate
WorldPack with its exact structure index and partial access graph. Mark it
topographic/read-only only; leave `autonomous_ready=false` until a semantic
catalog and its validation exist.

## Evidence

The registry audit passes `--check` with `83/83` identities, `11`
`topographic_ready` maps and `1` `autonomous_ready` map. Scholomance has
`16/16` geometrically validated nav ADTs and `174/174` completed access-scan
probes (`37` accepted, `0` errors). Execution authority remains false.
