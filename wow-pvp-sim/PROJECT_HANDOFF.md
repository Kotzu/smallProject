# WoW PvP Classic / Forever Simulator — PROJECT HANDOFF

## Goal
Finish a highly accurate WoW Classic/Forever PvP simulator whose main purpose is to develop and improve one `ClassCombat.lua` per class, with special focus on making the Rogue policy progressively better from simulated fights.

This file is the authoritative handoff for a new ChatGPT chat. Do not restart the project from scratch. Continue from the repository state and constraints below.

## User priorities
1. Accuracy first. Do not invent stats, talents, coefficients, cooldowns, proc rates, resist rules, DR rules, gear values, enchants, racials, or spell behavior.
2. Do not waste time on cartoon-like visuals or fancy animation. Fight playback is only a diagnostic UI for reading what the simulator did.
3. The important artifact is the combat logic, especially `combat/Rogue/ClassCombat.lua`.
4. Learn from every fight: analyze why Rogue won/lost, propose concrete policy changes, test them over deterministic seed suites/batches, keep only changes that improve results without violating WoW rules.
5. `CombatEngine.lua` must remain neutral. Tactical improvements belong in `ClassCombat.lua`, not in game-rule formulas.
6. Strict gate: unsupported/unverified profiles/builds stay locked rather than being guessed.

## Repository / preview
- GitHub: `Kotzu/smallProject`
- Project folder: `wow-pvp-sim/`
- Public preview: https://wow-pvp-simulator-preview.onrender.com
- Render service: `wow-pvp-simulator-preview`
- Render service ID: `srv-dajta2h42hec73a0al60`
- Render workspace ID: `tea-dajt3me7bikc73ddj8h0`
- Render region: Frankfurt

## Current version state
- UI / talent-aware wrapper: v0.16
- First calibrated matchup: Undead Rogue Subtlety/Hemo vs Gnome Frost Mage, Level 60 PvP BiS
- Deterministic duel code/seed supported
- Batch simulation: 1k / 10k / 100k
- Automated QA currently checks stats/formulas/replay/talent build validity/batch accounting

## Core architecture
Target architecture:

`ClassCombat.lua` -> chooses action -> `CombatEngine.lua` -> resolves WoW rules -> fight log -> post-fight analyzer -> candidate policy improvement -> regression tests/batch -> accept/reject policy change

Rule:
- `ClassCombat.lua` = brain / tactics
- `CombatEngine.lua` = WoW rules / physics / combat math

The current browser duel is still driven by the existing JavaScript kernel. Lua files are real and visible in the repo, but are NOT yet the sole runtime authority in the browser. This is an important unfinished architectural task. Do not claim otherwise.

## ClassCombat.lua files
There is now one class-level combat file per Classic class under `wow-pvp-sim/combat/<Class>/ClassCombat.lua`.

Active:
- `combat/Rogue/ClassCombat.lua`
- `combat/Mage/ClassCombat.lua`

Created but intentionally LOCKED until exact spells/talents/gear are verified:
- Warrior
- Paladin
- Hunter
- Priest
- Shaman
- Warlock
- Druid

### Rogue status
`combat/Rogue/ClassCombat.lua`
- Main focus of project
- Active spec: Subtlety
- Current active build: Cold Blood Hemorrhage 21/3/27
- Current policy includes: Cheap Shot opener, Vanish root break/reopen, Sprint for gap close, Kick casts, Kidney control window, Cold Blood + Eviscerate, Hemorrhage builder, energy pooling
- Assassination and Combat policies remain locked until verified.

### Mage status
`combat/Mage/ClassCombat.lua`
- Active spec: Frost
- Active build: Deep Frost PvP 17/0/34
- Policy includes Blink, Escape Artist, Ice Block, AGM, Ice Barrier, Mana Shield, Frost Nova, Cone of Cold, Fire Blast, Cold Snap, Frostbolt.

## Talent builds
Talent selection is now a real part of duel configuration.

Authoritative files:
- `talent-builds.js`
- `combat/TalentBuilds.lua`
- `duel-build-guard-v016.js`

Active calibrated builds:

### Rogue
- ID: `rogue_cb_hemo_21_3_27`
- Name: Cold Blood Hemorrhage
- Points: 21/3/27 = 51
- Calculator string: `305320115001-3-500253000332121`
- Important verified effects currently represented:
  - Improved Eviscerate 3/3 -> +15% Eviscerate damage
  - Malice 5/5 -> +5% melee crit
  - Murder 2/2 -> +2% damage against applicable target type in current kernel
  - Relentless Strikes -> 20% per CP, restores 25 Energy
  - Lethality -> builder crit bonus; Hemo crit currently 2.3x
  - Cold Blood -> guaranteed eligible crit
  - Dirty Deeds 2/2 -> Cheap Shot 40 Energy
  - Hemorrhage 1/1
  - Preparation 1/1

### Mage
- ID: `mage_deep_frost_17_0_34`
- Name: Deep Frost PvP
- Points: 17/0/34 = 51
- Calculator string: `23001503102--05350233102351001`
- Important verified effects represented:
  - Improved Frostbolt 5/5 -> 2.5s cast
  - Elemental Precision 3/3 -> +6% Frost/Fire hit and mana-cost reduction used by kernel
  - Ice Shards 5/5 -> Frost crit total 2.0x
  - Improved Frost Nova 2/2 -> 21s CD
  - Permafrost 3/3
  - Piercing Ice 3/3 -> +6% Frost damage
  - Shatter 5/5 -> +50% crit vs frozen
  - Improved Cone of Cold 3/3 -> +35% damage
  - Arcane Resilience 1/1 -> armor = +50% Intellect
  - Cold Snap / Ice Block / Ice Barrier
  - Improved Counterspell 2/2 -> 4s silence

Strict rule: a selected talent build must match class/spec and pass audit. Unknown or uncalibrated builds must block duel execution.

## Mini Armory / stat audit
Current UI includes mini Armory for Player A/B.
- Gear slots
- Item IDs
- Enchants
- Gems/sockets (Classic Era generally none for current profiles)
- Primary stats
- Combat stats
- Class-specific stat conversion breakdown
- STAT AUDIT PASS/FAIL

Current Rogue baseline is independently recalculated from base stats + verified gear/enchants. Current Mage core profile includes independent mana and armor audits.

Important: each class scales stats differently. Never apply Rogue AGI rules to Mage, etc.

## Current first matchup data
### Rogue
- Undead Rogue 60, Subtlety/Hemo, PvP BiS P6 baseline
- 17 slots verified
- Main hand: Gressil, Dawn of Ruin, 2.7
- Off hand: Harbinger of Doom, 1.6
- Ranged: Nerubian Slavemaker
- Dual-wield same-level white miss: 5% base + 19% DW penalty - hit
- Offhand penalty: 50% without Dual Wield Specialization
- Crippling Poison II raw 30%
- Mind-numbing Poison III raw 20%
- Current Mage Nature Resistance state yields 9% total binary full-resist/miss for poison application in this kernel, so effective application probabilities are 27.3% and 18.2%
- Hand of Justice: 2% extra attack, 2s ICD
- Crusader: 1 PPM, +100 STR 15s, heal 75-125
- Bonescythe 2p: 1 PPM heal 90-110
- Bonescythe 4p: builder crit +5 Energy

### Mage
- Gnome Mage 60 Frost, PvP P6 core
- HP ~4280
- Mana audited to 6258
- INT 355
- Spell Power 596
- Spell Crit 14.16%
- Spell Hit 5% gear + 6% Elemental Precision in Frost/Fire calculations
- Spell Pen 101
- Arcane Resilience armor ~1197
- PvP set 3p -> Blink 13.5s
- PvP gloves -> Mana Shield +285 absorb, total base current shield 855 before other interpretation
- Frostfire 6p is present in loadout; exact Elemental Vulnerability modeling must remain source-verified

## Combat formulas already verified / used
- Physical armor reduction Classic formula from CMaNGOS
- Same-level spell miss logic used in current kernel
- Same-level melee special miss 5%
- Physical crit 200%, spell crit 150% before modifiers
- Dual wield white miss +19%
- Base run speed 7 yd/s
- Several spell coefficients from CMaNGOS Classic data/fixes

Do not expand formulas by assumption. Source-check before enabling new mechanics.

## Fight UI
Fight tab is intentionally diagnostic, not the product focus.
- Start Fight
- HP bars
- resource display
- current action
- play/pause/step/reset
- live log

Do NOT spend development time on making it look like an animation/game. Accuracy and policy evolution are the priorities.

## Post-fight analysis
Current `fight-analyzer.js` creates a final dialog with:
- why winner won
- what winner could improve
- why loser lost
- what loser could improve
- fight facts
- target `ClassCombat.lua` path to edit

This analysis must become increasingly quantitative and talent-aware. It must never recommend an ability/talent the selected build does not have.

## Learning / Rogue improvement loop — REQUIRED NEXT DIRECTION
The simulator should learn from fights in a controlled, reproducible way. Do NOT let it blindly rewrite Rogue logic after one lucky/unlucky duel.

Recommended acceptance loop:
1. Run a fixed evaluation suite (for example 1,000 deterministic seeds) with current Rogue policy.
2. Extract fight metrics: win/loss, duration, HP left, energy wasted/capped, melee uptime, missed Kick windows, delayed Kidney, unused cooldowns, bad Vanish timing, control overlap, finisher efficiency, range downtime, proc dependence.
3. Generate one small candidate policy change in `combat/Rogue/ClassCombat.lua`.
4. Re-run the SAME seed suite A/B: baseline policy vs candidate.
5. Accept only if candidate meaningfully improves objective score and does not create rule violations/regressions.
6. Record policy version, change, before/after metrics and seed suite.
7. Repeat.

Suggested Rogue objective is multi-metric, not win rate only:
- primary: win rate
- secondary: remaining HP, shorter winning fights, fewer avoidable control gaps, lower dependence on favorable procs
- penalty: illegal action, unavailable talent, impossible resource spend, cooldown misuse, excessive regression in previously strong seed clusters

Eventually run counter-training against multiple opponent policies/builds so Rogue does not overfit Frost Mage only.

## Important architecture debt
1. Browser still uses JS duel decision functions; Lua `ClassCombat.lua` is not yet the single runtime authority.
2. Intended final engine is event-driven; current kernel still uses a 100ms stepping loop.
3. Only one matchup is calibrated.
4. Only Rogue Subtlety and Mage Frost are active policies.
5. Other classes/specs/gear levels remain locked.
6. Some set/proc edge cases need deeper source verification before declaring 1:1.

## Next concrete tasks
Priority order:
1. Make Rogue `ClassCombat.lua` the authoritative policy source for the simulator (or create a deterministic parity layer that proves JS runtime and Lua policy are identical on every decision).
2. Add a structured fight-metrics collector.
3. Add baseline-vs-candidate A/B evaluation over fixed seeds.
4. Add policy versioning and a machine-readable Rogue learning history.
5. Improve Rogue Subtlety policy based on data, not anecdotal single fights.
6. Only after that expand to additional Rogue PvP talent builds and additional opponents.
7. Then expand other classes/specs with the same strict data process.

## User communication style
- Romanian preferred.
- Concise and concrete.
- Explain simply.
- Do not give long status stories.
- Do not call the simulator finished until all required classes/specs/matchups/data are genuinely complete.
