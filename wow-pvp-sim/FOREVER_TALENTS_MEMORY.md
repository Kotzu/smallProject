# WoW Forever Talent Memory

## Purpose
This project treats WoW Forever talents as a separate ruleset from Classic Era. Classic builds are never silently reused as Forever builds.

## Current source
- Calculator: `https://www.wowhead.com/forever/talent-calc`
- Live data endpoint pattern: `https://nether.wowhead.com/forever/data/talents-classic?dv=20&db=<CURRENT_DB>`
- The server discovers the current `db` token from the live Wowhead Forever calculator page, then downloads and parses the complete `WH.setPageData("wow.talentCalcClassic.classicplus.data", ...)` object.
- Runtime endpoint inside this simulator: `/api/forever-talents`

## Stored fields per talent
The runtime memory preserves the source fields without translating them into Classic equivalents:
- talent `id`
- `row`
- `col`
- `icon`
- `name`
- `ranks` / max rank
- `requires` prerequisites
- `requiredPoints`
- rank-by-rank `descriptions`
- optional `cost`
- optional `requiresText`

Tree metadata is also preserved (`tree id`, source description, role/mastery fields if present).

## Class coverage
The expected WoW Forever player classes are:
- Druid
- Hunter
- Mage
- Paladin
- Priest
- Rogue
- Shaman
- Warlock
- Warrior

Each class is expected to expose three talent trees. `forever-qa.js` validates the live dataset rather than trusting a hard-coded historical node count.

## Important status
`PROVISIONAL_UNTIL_BETA_DATAMINING`

Wowhead currently states that these Forever trees were reconstructed from BlizzCon testing and streams and will be refreshed once the beta client can be datamined. Therefore:
- current tree names/positions/ranks/tooltips are usable as the current Forever snapshot;
- they are not labeled final Blizzard datamined truth;
- any placeholder or malformed source value stays visible as source data and must not be silently corrected by the simulator;
- Forever combat stays strict-locked until the selected Forever build and every combat-relevant talent effect have kernel parity.

## Armory integration
Both Player A and Player B Armory panels read the same runtime talent memory. In Forever mode the Armory shows the three live trees for that character's class, node positions, icons, rank caps, prerequisites and rank tooltips. Classic Armory continues to use the independent calibrated Classic build registry.

## Combat integration rule
`Talent dataset -> selected verified build -> ClassCombat.lua -> CombatEngine.lua`

Talent data changes what actions/modifiers are available. `CombatEngine.lua` must remain a neutral rules engine; tactical decisions belong in each class `ClassCombat.lua`.
