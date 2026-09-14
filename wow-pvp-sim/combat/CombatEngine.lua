local Engine = {}

Engine.version = "0.21-rogue-dagger-math"
Engine.scope = "Classic level 60 PvP combat rules. ClassCombat.lua chooses actions; CombatEngine resolves verified mechanics."

local function clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

function Engine.physicalArmorReduction(armor, attackerLevel)
    local x = 0.1 * armor / (8.5 * attackerLevel + 40)
    return clamp(x / (1 + x), 0, 0.75)
end

function Engine.sameLevelSpellMiss(spellHitPct)
    return math.max(1, 4 - spellHitPct)
end

function Engine.sameLevelMeleeSpecialMiss(hitPct)
    return math.max(0, 5 - hitPct)
end

function Engine.dualWieldWhiteMiss(hitPct)
    return math.max(0, 5 + 19 - hitPct)
end

function Engine.ppmProcChancePct(ppm, weaponSpeedSeconds)
    return ppm * weaponSpeedSeconds / 60 * 100
end

function Engine.binaryMagicResistPct(attackerLevel, targetResistance, spellPenetration, spellHitPct)
    local effectiveResistance = math.max(0, targetResistance - spellPenetration)
    local skill = attackerLevel * 5
    local resistancePct = clamp((effectiveResistance / skill) * 100 * 0.75, 0, 75)
    local missPct = Engine.sameLevelSpellMiss(spellHitPct)
    return clamp(missPct + resistancePct, 0, 100)
end

function Engine.weaponDamage(minDamage, maxDamage, attackPower, weaponSpeed, roll01)
    local base = minDamage + (maxDamage - minDamage) * roll01
    return base + (attackPower / 14) * weaponSpeed
end

-- Patch 1.8+ normalization used by instant weapon attacks in Classic.
function Engine.normalizedWeaponSpeed(weaponType)
    if weaponType == "Dagger" then return 1.7 end
    if weaponType == "Ranged" then return 2.8 end
    if weaponType == "TwoHand" then return 3.3 end
    return 2.4 -- other one-handed weapons
end

function Engine.normalizedWeaponDamage(minDamage, maxDamage, attackPower, weaponType, roll01, flatWeaponDamage)
    local base = minDamage + (maxDamage - minDamage) * roll01
    base = base + (flatWeaponDamage or 0)
    return base + (attackPower / 14) * Engine.normalizedWeaponSpeed(weaponType)
end

function Engine.applyPhysicalDamage(rawDamage, armor, attackerLevel)
    return rawDamage * (1 - Engine.physicalArmorReduction(armor, attackerLevel))
end

function Engine.applyOffHandPenalty(damage)
    return damage * 0.50
end

function Engine.meleeCritDamage(damage)
    return damage * 2.0
end

-- Classic Lethality adds 6 percentage points to the critical multiplier per rank
-- for Sinister Strike, Gouge, Backstab, Ghostly Strike and Hemorrhage. It does NOT affect Ambush.
function Engine.rogueBuilderCritMultiplier(lethalityRank)
    return 2.0 + 0.06 * (lethalityRank or 0)
end

function Engine.baseSpellCritDamage(damage)
    return damage * 1.5
end

function Engine.frostIceShardsCritDamage(damage)
    return damage * 2.0
end

-- Backstab Rank 9: 60 Energy, 150% normalized MH dagger damage +210, requires behind.
-- Opportunity 5/5: +20% Backstab damage. Improved Backstab changes crit chance, not base damage.
function Engine.rogueBackstabRaw(args)
    if not args.behindTarget then return nil, "REQUIRES_BEHIND" end
    if args.weaponType ~= "Dagger" then return nil, "REQUIRES_MH_DAGGER" end
    local normalized = Engine.normalizedWeaponDamage(
        args.minDamage, args.maxDamage, args.attackPower, "Dagger", args.roll01 or 0.5, args.flatWeaponDamage
    )
    local damage = normalized * 1.50 + 210
    damage = damage * (1 + (args.opportunityDamagePct or 0) / 100)
    return damage
end

-- Ambush Rank 6: 60 Energy, 250% normalized MH dagger damage +290, requires Stealth + behind.
-- Opportunity applies; Lethality does not affect Ambush critical damage in Classic.
function Engine.rogueAmbushRaw(args)
    if not args.stealthed then return nil, "REQUIRES_STEALTH" end
    if not args.behindTarget then return nil, "REQUIRES_BEHIND" end
    if args.weaponType ~= "Dagger" then return nil, "REQUIRES_MH_DAGGER" end
    local normalized = Engine.normalizedWeaponDamage(
        args.minDamage, args.maxDamage, args.attackPower, "Dagger", args.roll01 or 0.5, args.flatWeaponDamage
    )
    local damage = normalized * 2.50 + 290
    damage = damage * (1 + (args.opportunityDamagePct or 0) / 100)
    return damage
end

-- Gouge Rank 5: 45 Energy, 75 physical damage, 4s incapacitate, 10s cooldown.
-- Improved Gouge 3/3 adds 1.5s. Any damage breaks the incapacitate.
function Engine.rogueGougeDurationMs(improvedGougeRank)
    return 4000 + 500 * (improvedGougeRank or 0)
end

function Engine.applyGouge(state, nowMs, improvedGougeRank)
    state.incapacitateUntil = nowMs + Engine.rogueGougeDurationMs(improvedGougeRank)
    state.autoAttackEnabled = false
    return state.incapacitateUntil
end

function Engine.breakIncapacitateOnDamage(state, nowMs)
    if (state.incapacitateUntil or 0) > nowMs then
        state.incapacitateUntil = nowMs
        return true
    end
    return false
end

-- Initiative 3/3: 75% chance to add one CP on Ambush/Garrote/Cheap Shot.
function Engine.rogueInitiativeExtraCombo(procRoll01, initiativeRank)
    local chance = 25 * (initiativeRank or 0)
    if chance <= 0 then return 0 end
    return ((procRoll01 or 1) * 100 < chance) and 1 or 0
end

-- Improved Sprint 2/2: 100% chance to remove movement-impairing effects when Sprint is activated.
function Engine.applyImprovedSprint(state, improvedSprintRank)
    if (improvedSprintRank or 0) >= 2 then
        state.rootUntil = 0
        state.slowUntil = 0
        state.slowPct = 0
        return true
    end
    return false
end

function Engine.consumeManaShield(state, incomingPhysicalDamage)
    local absorb = math.min(incomingPhysicalDamage, state.manaShieldAbsorb, state.mana / 2)
    state.manaShieldAbsorb = state.manaShieldAbsorb - absorb
    state.mana = state.mana - absorb * 2
    return incomingPhysicalDamage - absorb, absorb
end

function Engine.energyTick(state)
    state.energy = math.min(state.maxEnergy, state.energy + 20)
end

return Engine
