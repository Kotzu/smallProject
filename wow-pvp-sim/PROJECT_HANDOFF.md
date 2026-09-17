# WoW Forever PvP Simulator — PROJECT HANDOFF

## Authoritative scope
This project is **WoW Forever only**.

Do not implement, expose, or maintain a Classic Era mode. Do not auto-convert Classic builds into Forever builds. Any older Classic-derived code/data still present in the repository is migration scaffolding only and cannot become combat-authoritative until re-verified for Forever.

If another file/chat says “Classic / Forever”, this handoff and `PROJECT_STATE.md` supersede it.

## Goal
Finish a highly accurate WoW Forever PvP 1v1 simulator centered on one `ClassCombat.lua` per class, with special focus on making Rogue progressively smarter through deterministic simulated fights.

## User priorities
1. Accuracy first. Never invent stats, talents, coefficients, cooldowns, proc rates, resistance rules, DR rules, gear values, enchants, racials or spell behavior.
2. Armory must be Blizzard-style and exist for both Player A and Player B.
3. Armory owns the combat configuration: class, race, gear/loadout, stats and selected Forever talent build.
4. The most important combat artifact is `combat/Rogue/ClassCombat.lua`.
5. `CombatEngine.lua` must remain neutral. Tactical improvements belong in `ClassCombat.lua`.
6. Unsupported/unverified Forever profiles/builds/mechanics remain locked rather than guessed.
7. Fight replay is diagnostic. Do not prioritize flashy animation over combat accuracy.

## Repository
- GitHub: `Kotzu/smallProject`
- active branch: `wow-pvp-dev`
- project folder: `wow-pvp-sim/`

## Render dev preview
- service: `wow-pvp-simulator-dev`
- URL: `https://wow-pvp-simulator-dev.onrender.com`
- service ID: `srv-dalf8tbl550s73b2t28g`
- workspace ID: `tea-dajt3me7bikc73ddj8h0`
- region: Frankfurt

Do not claim a commit is live until Render has actually deployed it and the public URL has been fetched/verified.

## Core architecture
`Forever Armory` -> `Forever Talent Build` -> `ClassCombat.lua` -> `CombatEngine.lua` -> fight log -> post-fight analyzer -> candidate policy improvement -> deterministic regression tests -> accept/reject policy change.

- `ClassCombat.lua` = brain / tactics.
- `CombatEngine.lua` = verified WoW Forever rules / combat math.
- Fight UI = diagnostic playback.
- Post-fight analyzer = explains winner/loser and what each class policy should improve.

## Forever talents
Runtime source is the current Wowhead Forever talent calculator dataset.

Current observed dataset:
- db token: `1789642865`
- 9 classes
- 27 talent trees
- 351 current talent nodes
- status: `PROVISIONAL_UNTIL_BETA_DATAMINING`

The simulator currently stores/uses tree IDs, node IDs, names, icons, row/column, max ranks, prerequisites, required points, rank descriptions, costs and `requiresText` where supplied.

Known updated examples already present in the current source:
- Rogue Subtlety: Hemorrhage, Quietus, Cutthroat, Thousand Cuts
- Rogue Assassination: Mutilate, Venom
- Mage Frost: Ice Lance, Fingers of Frost

## Forever build allocator
Player A and Player B have separate build state.

Rules already enforced:
- maximum 51 points
- tier gates
- prerequisite talents
- rank caps
- dependency-safe point removal
- build export includes Wowhead db token/provenance

No Classic build string is authoritative for Forever.

## Armory
Armory target is Blizzard-style 1:1 for both players, with:
- identity / class / race / spec
- gear slots
- exact item IDs
- enchants
- weapon data
- primary stats
- combat stats
- resistances
- talent tree
- selected build X/51
- source/provenance and audit state

The Forever talent tree is already wired to the live Forever runtime dataset.

Important: some current gear/stat code is still inherited from the earlier Classic calibration. It is migration-only. It must be replaced or re-verified for Forever before it can unlock Fight.

## ClassCombat.lua files
One top-level file per class under `wow-pvp-sim/combat/<Class>/ClassCombat.lua`:
- Rogue
- Mage
- Warrior
- Paladin
- Hunter
- Priest
- Shaman
- Warlock
- Druid

Rogue is the priority.

Rogue policy must eventually read the exact selected Forever build and account for energy, combo points, cooldowns, DR, positioning, poisons, target state, reset/reopen logic and matchup-specific decisions.

## Fight gate
Forever Fight is intentionally locked until matchup-level parity is complete.

A fight may unlock only when both players have:
1. verified Forever loadout/stats
2. valid selected Forever build
3. all combat-relevant selected talent effects implemented
4. verified Forever spell/ability definitions
5. verified Forever CombatEngine mechanics
6. valid class policy
7. passing QA

No legacy Classic calibration can bypass this gate.

## Post-fight analysis
At the end of every valid fight, show a dialog that explains:
- why the winner won
- what the winner can still improve
- why the loser lost
- what the loser should improve
- evidence from the fight timeline
- which `ClassCombat.lua` behavior should change

The analyzer must be talent-aware and may not recommend an ability/talent absent from the selected Forever build.

## Rogue learning loop
Use fixed deterministic seed suites.

1. Run baseline Rogue policy.
2. Collect metrics: win/loss, duration, HP left, energy waste/cap, melee uptime, Kick windows, Kidney timing, cooldown usage, Vanish/reset timing, control overlap, finisher efficiency, range downtime and proc dependence.
3. Generate one small candidate policy change.
4. Re-run the exact same seeds baseline vs candidate.
5. Accept only if it improves objective metrics without illegal actions or regressions.
6. Record version/change/results.
7. Repeat against multiple opponents/builds to avoid overfitting.

## Strict data rule
Unknown data is `—`, `neverificat`, `provisional`, or gated.

Never call anything exact/verified without source provenance and an audit.

## Immediate priority
1. Finish Forever Armory for Player A and Player B.
2. Replace/re-verify all legacy gear/stat fixtures for Forever.
3. Keep Forever talent tree + X/51 build allocator authoritative.
4. Make Rogue `ClassCombat.lua` consume the selected Forever build.
5. Implement Rogue Forever talent effects first.
6. Implement Mage next, then the other seven classes.
7. Unlock Fight only after full Forever parity for the selected matchup.

## Communication
Romanian preferred. Be concise and concrete. Do not report a feature as live unless actually verified.