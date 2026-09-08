# ADR-0053 — Registry-bound map profile selection

## Context

The Control Center previously embedded the Azeroth/Tirisfal WorldPack,
structure index, access graph and semantic catalog in its launch path. The
registry already inventoried four TBC 2.4.3 maps, but that inventory could not
select a coherent set of evidence for a different map.

## Decision

Each registry entry may declare its semantic catalog, structure index and
structure access graph. The Control Center selects one registry profile and
passes that profile's paths to the awareness service, viewer and supervisor.
Profiles without a complete semantic/structure evidence set remain
`OBSERVE_ONLY`; they are not silently mixed with Azeroth/Tirisfal data.

## Consequences

- Adding a map is an explicit evidence-packaging task rather than a code-level
  coordinate exception.
- A map can be inspected read-only before its semantic catalog and live gate
  are complete.
- The selector does not claim all-map autonomous coverage: Kalimdor and
  Expansion01 currently have no semantic/structure artefacts, and Shadowfang
  has no semantic destination catalog in the Control Center.
- Dynamic entity awareness remains screen-space and viewport-scoped; map
  profile selection does not grant server truth or exact hidden entity
  coordinates.
