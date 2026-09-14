local Engine = {}

Engine.version = "0.14-current-kernel"
Engine.scope = "Classic level 60 PvP rules used by the calibrated Rogue Subtlety vs Frost Mage matchup"

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

function Engine.applyPhysicalDamage(rawDamage, armor, attackerLevel)
    return rawDamage * (1 - Engine.physicalArmorReduction(armor, attackerLevel))
end

function Engine.applyOffHandPenalty(damage)
    return damage * 0.50
end

function Engine.meleeCritDamage(damage)
    return damage * 2.0
end

function Engine.baseSpellCritDamage(damage)
    return damage * 1.5
end

function Engine.frostIceShardsCritDamage(damage)
    return damage * 2.0
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
