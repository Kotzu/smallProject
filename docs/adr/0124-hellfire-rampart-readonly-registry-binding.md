# ADR-0124 — Hellfire Rampart read-only registry binding

## Context

Hellfire Rampart (`map_id=543`) now has a client-derived candidate navmesh and
structure-access evidence in the isolated dungeon WorldPack. It has no semantic
destination catalog, so it must not be treated as an autonomous launch route.

## Decizie

Bind `543:HellfireRampart` in the registry to the exact dungeon candidate
WorldPack, structure index and partial access graph. Expose it only as
topographic/read-only awareness and keep `autonomous_ready=false` until a
semantic catalog and route validation exist.

## Evidence

The offline bake validates `72/72` ADTs and independent geometry validates
`72/72`. The read-only access scan completed `1,221/1,221` probes with `177`
accepted WMO observations, `122` access openings and `1,352` boundary chains;
the graph remains `PARTIAL_OBSERVED_COMPONENTS` and `execution_authority=false`.
The registry audit passes `--check` with `83/83` identities, `12`
`topographic_ready` maps and `1` `autonomous_ready` map.
