# WoW PvP Classic / Forever Simulator — Project State

Last authoritative update: 2026-09-16

## Goal
Build a WoW Classic/Forever PvP 1v1 simulator where every class has its own `ClassCombat.lua` decision layer, while `CombatEngine.lua` stays neutral and resolves WoW combat rules. The simulator must use verified class/race stats, gear, enchants, gems/sockets where applicable, talents, racials, spell ranks, coefficients, proc rules, resistances, cooldowns and PvP control rules. No invented values.

The project is not finished until it supports all Classic classes/specs and can run reproducible 1v1s plus large batches/self-play.

## Core architecture

`ClassCombat.lua` -> chooses the action and explains why.

`CombatEngine.lua` -> resolves hit/miss/dodge/crit/damage/resist/procs/resources/CC rules.

Fight UI -> replays the deterministic duel timeline.

Post-fight analyzer -> explains why each side won/lost and what should improve in that class's `ClassCombat.lua`.

## Repository
- GitHub repo: `Kotzu/smallProject`
- simulator folder: `wow-pvp-sim/`

## Live preview
- Render public preview: https://wow-pvp-simulator-preview.onrender.com
- Render service: `wow-pvp-simulator-preview`
- service id: `srv-dajta2h42hec73a0al60`
- workspace id: `tea-dajt3me7bikc73ddj8h0`

## Current version/state
- UI / talent-aware duel wrapper: v0.16
- current calibrated duel kernel: Rogue Subtlety vs Frost Mage, lvl 60 PvP BiS
- QA was last reported PASS for the calibrated profile after talent-build integration

## Current active talent builds
### Rogue
- build id: `rogue_cb_hemo_21_3_27`
- name: Cold Blood Hemorrhage
- points: 21/3/27
- calculator code: `305320115001-3-500253000332121`
- active/calibrated for current kernel
- important active talents/effects include Malice, Improved Eviscerate, Ruthlessness, Murder, Relentless Strikes, Lethality, Cold Blood, Dirty Deeds, Hemorrhage, Preparation, etc.

### Mage
- build id: `mage_deep_frost_17_0_34`
- name: Deep Frost PvP
- points: 17/0/34
- calculator code: `23001503102--05350233102351001`
- active/calibrated for current kernel
- important active effects include Improved Frostbolt, Elemental Precision, Ice Shards, Improved Frost Nova, Permafrost, Piercing Ice, Shatter, Improved Cone of Cold, Arcane Resilience, Cold Snap, Ice Block, Ice Barrier, Improved Counterspell.

## ClassCombat.lua files
There is one top-level `ClassCombat.lua` per class under `wow-pvp-sim/combat/<Class>/ClassCombat.lua`.

Active logic today:
- `combat/Rogue/ClassCombat.lua` — Subtlety active/calibrated; Assassination and Combat locked until verified.
- `combat/Mage/ClassCombat.lua` — Frost active/calibrated; Arcane and Fire locked until verified.

The other 7 class files exist but remain locked until their spells/talents/gear are verified.

## Fight UI
Fight-first UI is live. It shows:
- Start Fight
- HP/resource bars
- current action
- deterministic timeline playback
- Play / Pause / Step / Reset
- full duel log

## Post-fight analysis
At the end of a fight, a dialog explains:
- why the winner won
- what the winner can still improve
- why the loser lost
- what the loser should improve
- concrete fight facts from the timeline
- which `ClassCombat.lua` should be changed

Behavior improvements belong in `ClassCombat.lua`; `CombatEngine.lua` must remain neutral.

## Armory / stats
Mini Armory exists for both sides with gear slots, item IDs, enchants, gems/socket status, primary/combat stats and class-specific stat scaling.

Strict stat audit is required before a profile can run.

Current calibrated profiles:
- Undead Rogue Subtlety lvl 60 PvP BiS
- Gnome Frost Mage lvl 60 PvP BiS

## Important verified mechanics already in kernel/data
- Classic armor reduction formula
- same-level melee special miss
- same-level spell miss floor
- physical and spell crit multipliers
- dual-wield white miss penalty
- off-hand damage penalty
- Crippling Poison II and Mind-numbing Poison III proc/application logic
- binary Nature resistance for current Mage target
- Hand of Justice proc
- Crusader 1 PPM
- Bonescythe 2p 1 PPM
- Bonescythe 4p energy-on-builder-crit
- Mage PvP 3p Blink cooldown reduction
- Mana Shield gloves bonus
- Ice Barrier coefficient
- Mage Armor resistances
- Arcane Resilience armor contribution
- Frost talent modifiers listed above

## Strict data rule
A duel/profile/build must remain locked if required data is not verified. Do not infer or invent missing spell ranks, talent modifiers, item stats, proc rates, or formulas.

## Important correction for future work
A recent Firecrawl extraction for a supposed alternate Rogue build returned Season of Discovery data and is NOT valid for this Classic project. Do not use it as a verified build.

## Immediate next work
1. Keep the calibrated Rogue Subtlety vs Frost Mage matchup stable.
2. Make Rogue `ClassCombat.lua` more matchup-aware: energy pooling, reset/reopen, cooldown conservation, DR awareness, finisher choice, Kick timing, Vanish timing.
3. Add a second real Classic Rogue PvP build only after exact 51-point distribution and every combat-relevant modifier are verified.
4. Extend talent build library/UI and strict gating to each additional class/spec.
5. Add verified profiles and combat policies class by class.
6. Eventually refactor the current 100ms JS simulation loop toward the intended event-driven architecture.

## User-facing rule
When resuming after context loss, read this file first and continue from here instead of reconstructing the project from memory/chat.