## Functional combat reference milestone — v0.51
- Scope: exact reference matchup only — Undead Rogue Subtlety `Popular Subtlety 22/3/26` vs Gnome Frost Mage `Popular Frost 18/0/33`.
- Browser runtime modules: `forever-combat-data.js`, `forever-combat-policies.js`, `forever-combat-engine.js`, `forever-combat-qa.js`, `fight-ui.js`.
- Current client-data provenance is WoW Forever beta build `1.60.1.69913` from ForeverChanges beta-client extraction pages.
- Rogue and Frost Mage both have expert-system policies: state read, opponent memory, emergency actions, control/defensive plan, anti-interrupt/fake-cast handling, resource reservation, pressure, and intentional HOLD.
- Canonical policy documentation remains in `combat/Rogue/ClassCombat.lua` and `combat/Mage/ClassCombat.lua`; the browser JS policies are the fast deterministic reference-simulation mirror.
- Mage Lua was refactored from a simple priority list to the same expert-system architecture used for Rogue.
- Functional fight loop includes deterministic seeded RNG, timeline, cooldowns, resource state, movement/range, casts, Mage fake-casts, Rogue anti-fake Kick logic, auto-attacks, poisons, absorbs, control, Vanish/Preparation, Blink, Frost control and post-fight evidence.
- Replay/pause/step and 1,000 / 10,000 / 100,000 batch controls are wired in `fight-ui.js`.
- Reference fights are enabled only after `FOREVER COMBAT REFERENCE QA` passes and the exact two audited presets/loadouts are active.
- The model is explicitly `FOREVER_REFERENCE_MODEL` with `certifiedParity=false`. It must never be presented as exact WoW Forever balance.
- Current beta corrections include Rogue poison effects, Mutilate rank 4, Improved Eviscerate rank 2, Eviscerate rank 9, current Mage Frost spell ranks, Ice Barrier 811 and Fingers of Frost rank 2.
- Still provisional/not parity-certified: final base-stat reconstruction, armor/hit/resist combat tables, spell coefficients, Rogue Energy rate, Mage Spirit/5-second-rule inheritance, effective combat reach, and Forever PvP DR categories.
- A 1,000-seed local smoke run completed deterministically with 17 timeout scenarios; this is a runtime stability check only, not a balance result.

## Armory
Armory is the canonical player configuration UI and is operational for Player A and Player B.

Current active reference profiles:
- Undead Subtlety Rogue: 17/17 verified Forever item-slot state, 11/11 listed enchant effects.
- Gnome Frost Mage: 16 verified items + 1 verified empty off-hand (2H staff), 9/9 listed enchant effects.
- Live Forever talent tree and 51-point allocator.
- Popular public pre-build selector with atomic live-tree validation.
- Talent changes use targeted rerenders rather than rebuilding both paperdolls.

Final derived character stats remain `—` in Armory until Forever base-stat/class-scaling extraction is independently audited. The functional fight runtime therefore labels its reconstructed character profiles `REFERENCE_PROFILE_PROVISIONAL`.

## ClassCombat.lua
There is one top-level `ClassCombat.lua` per class under `wow-pvp-sim/combat/<Class>/ClassCombat.lua`.

Current expert implementations:
- Rogue Subtlety: stateful Forever expert system.
- Mage Frost: stateful Forever expert system.

Both follow the Warrior-reference architecture: state perception, opponent memory, deadline/emergency reactions, control/defensive planning, resource protection, mobility, pressure and intentional HOLD. The uploaded TBC Warrior is an architecture reference only; no TBC mechanic is authoritative.

The browser uses `forever-combat-policies.js` as the fast deterministic runtime mirror for batch simulation. Lua remains the canonical human-readable policy contract and is covered by class-specific QA scenario files.

## Fight gate
Two gates now exist and must not be conflated:

1. **Reference simulation gate** — may open for an explicitly supported matchup when:
   - exact supported class/spec/race/loadout is active;
   - exact audited Forever pre-builds are active;
   - reference combat QA passes.
   Current supported matchup: Undead Subtlety Rogue 22/3/26 vs Gnome Frost Mage 18/0/33.

2. **Certified parity gate** — remains locked until all required character math, combat tables, coefficients, DR categories and other mechanics are independently verified for WoW Forever.

Reference results are always labeled `FOREVER_REFERENCE_MODEL` and `certifiedParity=false`.
No legacy Classic calibration may be silently promoted to certified Forever truth.

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
1. Keep Rogue vs Frost Mage reference simulation stable, deterministic and source-traceable.
2. Extract/verify Forever final base stats and class scaling for the two active reference characters.
3. Audit Forever combat tables: armor, hit/miss, resist, dual-wield, combat reach and PvP DR.
4. Replace each provisional reference rule with a client/source-verified rule and QA.
5. Add remaining build-dependent Rogue/Mage mechanics (including unsupported deep-talent paths) before widening matchup support.
6. Promote the matchup from reference to certified parity only when the provisional-rules list is empty.
7. Then extend the same expert-system architecture class-by-class.

## Resume rule
When resuming after context loss, read this file first. Treat any older Classic/Forever mixed documentation as superseded by this file.