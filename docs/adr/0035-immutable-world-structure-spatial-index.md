# ADR 0035: Immutable world-structure spatial index

## Status

Accepted.

## Context

A Detour navmesh answers where a humanoid capsule can walk, but it does not by
itself identify the static object that owns a wall, enclosure, tree, fence, or
other collision boundary. Movement Engine also needs to know whether the
player is inside a large structure, which static obstacles are nearby, and
whether those objects overlap the exact nav coverage sealed in the active
WorldPack.

Server or emulator object tables are not portable Champion inputs. Asset names
are useful evidence, but a reused model name is not proof that the player is in
the place suggested by that name.

## Decision

`world_structure_index.py` decodes Namigator's immutable `MAP1` instance table
from a verified standalone WorldPack. It indexes both:

- `WMO` bounds as enclosure or large-structure geometry;
- `DOODAD` bounds as static-obstacle candidates.

Every indexed record preserves the exact asset path, transform, 3D bounds,
center, extent, instance identity, geometry confidence, and pinned-map
provenance. The parser rejects invalid signatures, unsafe or unterminated asset
paths, non-finite geometry, inverted bounds, duplicate identities, truncation,
and trailing bytes.

The runtime representation builds a deterministic 128-yard uniform spatial
grid. It supports exact 2D/3D containment and bounded nearby queries up to
1,000 yards without scanning every structure on every pose update.

Static geometry and traversability remain separate facts. Each structure is
labelled `FULL`, `PARTIAL`, or `NONE` according to overlap with the exact nav
tiles declared by the bundled client-world catalog. Knowing that a building
exists is never treated as proof that a route to it is currently available.

Asset-path tokens are retained as classifier input only. They do not become a
door, exit, city, or location label without additional geometry or observed
evidence. Dynamic NPC/player/resource knowledge remains `NONE` in this index
and continues to come only from the client-visible observation boundary.

## Runtime binding

The deterministic JSON sidecar binds to the WorldPack ID, catalog ID, complete
WorldPack content hash, client version/build, map ID/name, and exact `.map`
artifact hash. Both creation and loading verify the sealed WorldPack first.
The sidecar has `execution_authority: false`.

`index_world_structures.py` creates or independently checks an index.
`query_world_structures.py` performs a verified read-only spatial query. The
external Movement Engine displays bounded local counts and containment state;
it does not add UI to the WoW client.

## Controlled evidence

The Shadowfang WorldPack produced 3,097 static records: 29 WMO instances and
3,068 doodads across 25 terrain/nav tiles. A query at the Detour-resolved floor
`(-202.410004, 2179.989990, 79.908943)` returned exact 3D containment in
`ld_shadowfanginterior.wmo`, `FULL` nav overlap, and no dynamic-state claim.
Because its vertical probe was open above, the fused classifier correctly kept
that point as a WMO transition/unresolved surface instead of calling it an
interior merely from the WMO bounding box.

A second data-derived probe at the resolved floor
`(-100, 2120.237793, 155.731476)` combined 3D containment, a WMO nav surface,
and a blocked overhead ray. It therefore classified `INSIDE_STATIC_WMO` with
confidence `0.95`. Its bounded local component reported 128 boundary segments
(diagnostic list truncated) and 31 route-verified covered-to-open transitions.
Those transitions are topological egress candidates, not assumed doors or
building exits; topology remained explicitly incomplete because the boundary
diagnostic hit its configured bound.

The partial Azeroth/Tirisfal pack produced 5,764 static records, while only 8
nav tiles are declared. The index therefore preserves structures outside the
current navigable corridor as known static geometry with `NONE` route coverage
instead of silently presenting them as reachable.

## Consequences

- World awareness remains client-build-derived and standalone at runtime.
- Large structures and small static obstacles share one query interface but
  retain distinct collision roles.
- The next semantic stage can classify walls, gates, doors, and likely exits
  using bounds, BVH/nav topology, and observations without hardcoded routes.
- A new client build needs a compatible offline map importer; the spatial
  awareness and query contracts remain unchanged.
