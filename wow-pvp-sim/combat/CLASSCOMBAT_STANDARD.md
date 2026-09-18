# ClassCombat.lua Standard — WoW Forever

This document defines the required combat-brain architecture for every class in the simulator.

## Design reference
The uploaded TBC Anniversary Warrior profile is a **design/architecture reference only**.
It demonstrates expert PvP state management, but **no TBC mechanics are copied** into WoW Forever.

Forbidden imports from the reference include:
- TBC spell IDs or ranks
- TBC talent effects
- TBC stance/rage/cost/cooldown assumptions
- TBC racial effects
- TBC DR rules
- TBC item/set/proc behavior

Every mechanic must come from a WoW Forever source and pass its own audit.

## Required decision pipeline
Every class brain must reason in this order:

1. **Read current state**
   - self HP/resource/position/control state
   - target state
   - range/facing
   - cooldowns/GCD
   - selected Forever talents
   - race/racial state
   - DR state
   - active buffs/debuffs

2. **Update opponent memory**
   - casts seen
   - fake-cast/recast behavior
   - cooldowns/defensives observed
   - racial usage observed
   - escape usage observed
   - repeated tactical patterns

3. **Resolve build capabilities**
   - exact selected Forever talent names/ranks
   - abilities enabled by talents
   - modifiers supplied by CombatEngine
   - never infer a Classic build from a spec label

4. **Emergency reactions**
   - hard-CC breaks
   - lethal defensives
   - root/snare escape
   - unavoidable deadline actions

5. **Interrupt / counter system**
   - classify cast value
   - anti-fake timing
   - emergency late interrupt
   - do not consume another action that makes the interrupt impossible

6. **Defensive plan**

7. **Mobility / reconnect**

8. **CC + DR plan**

9. **Reset / reopen plan**

10. **Kill-window plan**

11. **Resource reservation**
    - reserve resource for higher-priority future actions
    - optional filler may not starve a planned interrupt/control/defensive action

12. **Damage priority**

13. **Filler**

14. **Intentional HOLD**
    - doing nothing is a valid tactical decision

## Structured decision trace
Every decision must expose:

- chosen action
- target
- decision layer
- priority
- reason
- current plan
- resource reserved after/before action
- evidence used
- rejected candidate actions and why

Post-fight analysis must consume this trace instead of guessing intent from damage logs.

## Mechanics ownership
- `ClassCombat.lua` = tactics, planning, memory, policy.
- `CombatEngine.lua` = WoW Forever mechanics and combat math.
- `TalentBuilds.lua` = selected Forever talent build representation.
- `ForeverRacials.lua` = sourced racial facts; still kernel-gated until implemented.
- Armory = player configuration source.

## Strict rule
An elegant policy is not permission to invent a game mechanic.
If a required state/mechanic is not verified, the decision must be gated, rejected, or HOLD.
