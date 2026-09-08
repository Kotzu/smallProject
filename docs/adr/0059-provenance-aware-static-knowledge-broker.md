# ADR-0059 — Provenance-aware static Knowledge Broker for trainers and route guidance

- Status: Accepted
- Date: 2026-08-31
- Scope: TBC 2.4.3 static knowledge and future Journey/QuestPlanner integration

## Context

Public TBC research can identify class trainers, profession trainers, class and
profession quests, and useful leveling steps. A route guide can also supply an
ordered advisory route. Those facts are useful even when the addon cannot expose
an exact 3D position for every nearby unit. They must not be confused with a
live entity feed or with server truth.

## Decision

Introduce a versioned, read-only `knowledge_broker_catalog` contract and loader.
Each entry carries:

- semantic kind (`class_trainer`, `profession_trainer`, `class_quest`,
  `profession_quest`, `leveling_step`, `route_step` or `npc_static`);
- exact TBC client/map identity and a bounded level range;
- coordinate scope (`worldpack` for runtime map identities or `zone_area` for
  source UI map-area IDs);
- provider, origin, provider version, retrieval time, URI and content mode;
- confidence and evidence references;
- an optional static source-coordinate candidate explicitly marked
  `STATIC_SOURCE_CANDIDATE`.

Wowhead is represented as `external_cached`; a purchased/user-owned Zygor export
is represented as `route_teacher`/`route_guidance`. A route teacher may contribute
leveling/route steps and advisory trainer or quest references; none of these are
proof that the client currently exposes the target. The catalog never grants execution authority. The
repo is private/local, but any raw guide files remain user-owned local inputs and
are not copied into generated evidence or shared artifacts. A static coordinate
is a candidate for later client confirmation and WorldPack binding, never a claim
about the current nearby unit.

The Zygor `NPCData.lua` importer keeps its `m####` identifiers in the
`zone_area` scope. It requires an explicit caller-provided binding for every
encountered map-area ID and never guesses a conversion to WorldPack continents.
Class and profession trainer sections are typed accordingly; other static NPC
sections are retained as `npc_static` awareness. All such entries remain
advisory and non-authoritative.

## Consequences

- Trainer/quest/profession knowledge can be populated from public or user-owned
  sources without inventing positions.
- The same catalog can be queried by exact map identity and later reconciled with
  client observation before Movement acts.
- Server spawn tables, LAB oracle facts and live-exact position semantics are
  rejected at the contract boundary.
- A future Zygor import needs only a user-owned export and its provider version;
  local storage is allowed by the operator's license, while generated contracts
  retain metadata and bounded summaries only.

## Rollback

Do not load the catalog. Existing client-observed quest and movement behavior
continues unchanged; no execution gateway depends on the new module.
