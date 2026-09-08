# ADR-0125 — TanarisInstance read-only registry binding

## Context

`209:TanarisInstance` had client terrain in the pinned TBC assets but no
versioned candidate WorldPack or structure-access evidence. It has no semantic
destination catalog, so it must not become an autonomous route.

## Decizie

Add `209:TanarisInstance` to a new four-map dungeon candidate pack, then bind
only its exact runtime profile, structure index and partial access graph in the
registry. Keep `autonomous_ready=false` until semantic destinations and route
validation exist.

## Evidence

The offline bake and independent geometry validator both cover `21/21` ADTs.
The read-only scan completed `2,178/2,178` probes with `418` accepted WMO
observations, `259` access openings and `1,410` boundary chains; the graph is
`PARTIAL_OBSERVED_COMPONENTS` and execution authority remains false. The
registry audit passes `--check` with `83/83` identities, `13`
`topographic_ready` maps and `1` `autonomous_ready` map.
