
## Armory milestone — v0.41 (DONE as UI/data surface)
- Scope is WoW Forever only.
- Player A/B both use the Blizzard-style paperdoll with 17 modeled equipment slots.
- Current Rogue Subtlety/Undead reference loadout: 17/17 verified Forever item records, 11/11 listed enchant effects verified.
- Current Mage Frost/Gnome reference loadout: 16 verified Forever item records + 1 verified empty off-hand because Soulseeker is a two-hand staff; 9/9 listed enchant effects verified.
- Item links/tooltips use WoW Forever sources only; no /classic item fallback is allowed.
- Live Forever talent trees remain embedded in each Armory and support independent 51-point builds for Player A/B.
- Verified gear-contribution subtotals are displayed.
- Final derived character stats intentionally remain `—` until Forever base stats and class conversion formulas receive their own audit. This does not permit a Fight unlock.
- Armory runtime modules: `forever-armory-data.js`, `armory.js`, `armory-talent-tree.js`, `forever-armory.css`.
- Dev preview verified live on Render after commit `5a07536219ce3b286ae4850aaf4d4e41f8fa1cc1`.

# WoW Forever PvP Simulator — Project State

Last authoritative update: 2026-09-18

## Scope — NON-NEGOTIABLE
This project is **WoW Forever only**.

Classic Era is not a supported ruleset, not a selectable mode, not a target for future development and must never be used as an implicit source of truth for combat.

Any older Classic-derived files/data that still exist in the repository are **migration fixtures only**. They may be consulted to accelerate implementation, but no value, formula, build, spell, item, talent effect, proc rate or combat behavior may become authoritative for Forever until it is re-verified against a WoW Forever source.

## Goal
Build a deterministic WoW Forever PvP 1v1 simulator where every class has its own `ClassCombat.lua` decision layer and `CombatEngine.lua` remains a neutral rules resolver.

The simulator must eventually support all WoW Forever classes/specs, verified gear/loadouts, racials, stats, talents, spell ranks, coefficients, cooldowns, proc rules, resistances, resources and PvP control mechanics. Missing or provisional mechanics must remain visibly gated.

## Core architecture
`Forever Armory` -> owns player configuration: class, race, gear, enchants, stats and selected Forever talent build.

`Forever Talent Dataset` -> current Wowhead Forever calculator snapshot with provenance.

`ClassCombat.lua` -> chooses actions/timing and explains decisions. One file per class. Rogue is the primary implementation priority.

`CombatEngine.lua` -> resolves only verified WoW Forever combat rules.

`Fight UI` -> deterministic fight/timeline playback.

`Post-fight analyzer` -> explains why the winner won, why the loser lost and what each class should improve in its own `ClassCombat.lua`.

## Repository
- GitHub repo: `Kotzu/smallProject`
- active development branch: `wow-pvp-dev`
- simulator folder: `wow-pvp-sim/`

## Preview
- dev Render service: `wow-pvp-simulator-dev`
- URL: `https://wow-pvp-simulator-dev.onrender.com`
- Render service id: `srv-dalf8tbl550s73b2t28g`
- workspace id: `tea-dajt3me7bikc73ddj8h0`

Do not claim a change is live until Render actually deploys the commit and the public URL is fetched/verified.

## Forever talent source
Current runtime source:
- Wowhead Forever talent calculator
- endpoint family: `https://nether.wowhead.com/forever/data/talents-classic?...`
- current observed db token: `1789642865`
- 9 classes
- 27 trees
- 351 current talent nodes

The dataset is treated as `PROVISIONAL_UNTIL_BETA_DATAMINING` because Wowhead can revise values after direct beta/client datamining.

Relevant updated examples already verified from the current dataset include:
- Rogue Subtlety: Hemorrhage, Quietus, Cutthroat, Thousand Cuts
- Rogue Assassination: Mutilate, Venom
- Mage Frost: Ice Lance, Fingers of Frost

## Forever build system
- 51-point cap
- tier gates enforced
- prerequisites enforced
- separate build state for Player A and Player B
- left click/tap adds a rank
- right-click / Shift+click removes a rank
- build export includes source db token and provenance
- Classic builds are never auto-converted to Forever

## Armory
Armory is the canonical player configuration UI.

Target: Blizzard-style 1:1 layout for Player A and Player B with:
- character identity
- gear slots
- item IDs
- enchants
- stats
- resistances
- weapons
- talent tree
- selected Forever build X/51
- data integrity/provenance

The Forever talent tree is already wired to the live Forever runtime dataset.

Any gear/stat records still sourced from older Classic calibration must be visibly treated as migration fixtures and cannot unlock combat until re-verified for Forever.

## ClassCombat.lua
There is one top-level `ClassCombat.lua` per class under `wow-pvp-sim/combat/<Class>/ClassCombat.lua`.

Long-term target:
- Rogue
- Mage
- Warrior
- Paladin
- Hunter
- Priest
- Shaman
- Warlock
- Druid

Rogue remains the priority class. Its decision logic must eventually account for the exact selected Forever build, resource state, cooldowns, DR, target state, positional requirements, reset/reopen logic, poison state and matchup-specific policy.

## Fight gate
WoW Forever fights remain locked until all required data for both players and the selected matchup has Forever parity.

A valid fight requires:
1. verified Forever character/loadout data
2. selected valid Forever talent builds
3. combat-relevant talent effects implemented
4. verified Forever spell/ability definitions
5. verified Forever combat mechanics in CombatEngine
6. valid ClassCombat policies
7. passing automated QA

No old Classic calibration may bypass this gate.

## Post-fight analysis requirement
At the end of every valid fight, a dialog must explain:
- why the winner won
- what the winner could still improve
- why the loser lost
- what the loser should improve
- concrete evidence from the timeline
- which class policy / `ClassCombat.lua` decision should be improved

The analyzer must be build-aware and must never recommend a talent/ability unavailable in the selected Forever build.

## Strict data rule
Never invent data.

Unknown data must be represented as `—`, `neverificat`, `provisional`, or remain gated.

Never call anything exact/verified unless it has source provenance and has passed the relevant audit.

## Immediate work order
1. Finish Forever Armory for Player A and Player B.
2. Replace remaining Classic-derived Armory stats/loadouts with verified Forever data.
3. Keep the live Forever talent tree and build allocator authoritative.
4. Make Rogue `ClassCombat.lua` consume the selected Forever build rather than Classic presets.
5. Implement combat-relevant Rogue Forever talents first.
6. Do the same for Mage, then the remaining seven classes.
7. Unlock Fight only after matchup-level Forever parity and QA.

## Resume rule
When resuming after context loss, read this file first. Treat any older Classic/Forever mixed documentation as superseded by this file.