# WoW Forever combat reference sources

Current reference client build: **1.60.1.69913**

The functional simulator distinguishes three evidence classes:

- `CLIENT_VERIFIED` — value read from/currently corroborated by WoW Forever beta-client extraction.
- `CORE_INHERITED_PROVISIONAL` — rule inherited from Classic-era behavior only for the reference simulator; not parity-certified.
- `REFERENCE_PROFILE_PROVISIONAL` — reconstructed level-60 character profile used to make the scenario runnable; not authoritative Forever character math.

## Current beta-client sources

- Rogue spellbook: https://foreverchanges.pro/spellbook/rogue
- Rogue talents: https://foreverchanges.pro/talents/rogue
- Mage spellbook: https://foreverchanges.pro/spellbook/mage
- Mage talents: https://foreverchanges.pro/talents/mage
- Forever talent runtime: https://www.wowhead.com/forever/talent-calc

ForeverChanges identifies the beta-client build as `1.60.1.69913`.

## Client-verified data used by the current reference matchup

### Rogue
- Cheap Shot: 4 sec stun, 2 CP.
- Kick rank 4: 80 damage, 5 sec school lock.
- Kidney Shot: 2/3/4/5/6 sec by 1–5 CP.
- Vanish: improved stealth for 10 sec and movement-impair break.
- Sprint rank 3: +70% for 15 sec.
- Evasion: +50% Dodge for 15 sec.
- Backstab rank 9: 150% weapon +150.
- Ambush rank 6: 250% weapon +290.
- Crippling Poison: 30% proc, 50% slow, 12 sec.
- Mind-numbing Poison: 20% proc, +40% cast time, 10 sec.
- Mutilate rank 4: 75% weapon +50 with each weapon, +20% vs poisoned, 2 CP.
- Eviscerate rank 9: 224–332 / 394–502 / 564–672 / 734–842 / 904–1012 before AP.
- Improved Eviscerate ranks 1/2/3: 7% / 13% / 20%.
- Initiative: 33% / 67% / 100%.
- Hemorrhage: 100% weapon, 145% with dagger, +15% own Rupture, 15 sec, 1 CP.

### Frost Mage
- Frostbolt rank 11: 457–493.
- Frost Nova rank 4: 69–77; root up to 8 sec.
- Cone of Cold rank 5: 325–355; 40% slow for 6 sec.
- Ice Lance rank 6: 133–157; 300% increased damage to Frozen targets.
- Ice Barrier rank 4: 811 absorb.
- Fire Blast rank 7: 402–474.
- Mana Shield rank 6: 570 physical absorb, 2 Mana per damage.
- Blink: 20 yd; breaks Stuns and Immobilizes; 15 sec cooldown; 35% base Mana.
- Fingers of Frost rank 2: 30% chance, next 1 spell treated as Frozen, 15 sec.
- Improved Frostbolt: -0.1 sec cast time per rank.
- Piercing Ice: +2% Frost damage per rank.

## Provisional reference rules

These make the simulation functional but do **not** certify Forever parity:

- reconstructed Rogue/Mage final HP, AP/SP, armor, hit/crit and resistance profiles;
- physical armor reduction and same-level hit/miss combat tables;
- dual-wield white hit table;
- weapon/spell coefficients not directly present in current client tooltips;
- Rogue continuous Energy regeneration rate;
- Mage Spirit mana regeneration and five-second rule;
- effective melee combat-reach tolerance;
- PvP control diminishing-return categories/reset timing.

Every result exposes the provisional rules used.

## Runtime contract

The current supported reference matchup is intentionally narrow:

- Player A: Undead Rogue / Subtlety / exact `Popular Subtlety · 22/3/26` preset.
- Player B: Gnome Mage / Frost / exact `Popular Frost · 18/0/33` preset.
- Both current verified reference gear profiles.
- Any customized build or unsupported class/spec keeps the reference Fight gate closed.

This allows a real deterministic simulation without falsely labelling unresolved rules as exact.
