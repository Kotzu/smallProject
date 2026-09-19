local Engine = {}

Engine.version = "0.41-forever-reference-contract"
Engine.ruleset = "Forever"
Engine.scope = "WoW Forever PvP rules. ClassCombat.lua chooses tactics; CombatEngine resolves only mechanics independently verified for Forever."
Engine.kernelReady = false
Engine.status = "FOREVER_REFERENCE_RUNTIME_AVAILABLE_PARITY_IN_PROGRESS"

-- IMPORTANT:
-- Functions below that originated during the older Classic calibration remain
-- migration fixtures until each one is re-audited for Forever. The public Fight
-- gate must never use this file as proof of Forever parity merely because a
-- function exists here.
Engine.referenceRuntime = {
    browser = "forever-combat-engine.js",
    status = "FUNCTIONAL_REFERENCE_NOT_PARITY_CERTIFIED",
    clientBuild = "1.60.1.69913",
}

Engine.migration = {
    classicDerivedFunctionsPresent = true,
    authoritativeForForever = false,
}

Engine.verifiedForeverRules = {
    -- Add rule IDs here only after a Forever source + QA test exists.
}

function Engine.markForeverRuleVerified(ruleId, provenance)
    if not ruleId or type(provenance) ~= "table" or not provenance.source then
        return false
    end
    Engine.verifiedForeverRules[ruleId] = provenance
    return true
end

function Engine.isForeverRuleVerified(ruleId)
    return Engine.verifiedForeverRules[ruleId] ~= nil
end

local TAU = math.pi * 2

local function clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

local function atan2(y, x)
    if math.atan2 then return math.atan2(y, x) end
    if x > 0 then return math.atan(y / x) end
    if x < 0 and y >= 0 then return math.atan(y / x) + math.pi end
    if x < 0 and y < 0 then return math.atan(y / x) - math.pi end
    if x == 0 and y > 0 then return math.pi / 2 end
    if x == 0 and y < 0 then return -math.pi / 2 end
    return 0
end

function Engine.normalizeAngle(rad)
    local a = rad or 0
    while a <= -math.pi do a = a + TAU end
    while a > math.pi do a = a - TAU end
    return a
end

function Engine.distance2D(a, b)
    local dx = (b.x or 0) - (a.x or 0)
    local dy = (b.y or 0) - (a.y or 0)
    return math.sqrt(dx * dx + dy * dy)
end

function Engine.angleTo(a, b)
    return atan2((b.y or 0) - (a.y or 0), (b.x or 0) - (a.x or 0))
end

-- CMaNGOS WorldObject::HasInArc semantics: arc is the full angular width.
function Engine.hasInArc(source, target, arc)
    local width = clamp(arc or math.pi, 0, TAU)
    if width >= TAU then return true end
    local delta = math.abs(Engine.normalizeAngle(Engine.angleTo(source, target) - (source.o or 0)))
    return delta <= width / 2 + 0.000000001
end

-- CMaNGOS WorldObject::isInBack uses a default PI rear arc and a distance check.
-- This simulator currently uses center-to-center 2D distance; CMaNGOS combat reach radii
-- remain a separate parity item and are not silently approximated here.
function Engine.isInBack(target, attacker, maxDistance, arc)
    if Engine.distance2D(target, attacker) > (maxDistance or 5) then return false end
    return not Engine.hasInArc(target, attacker, TAU - (arc or math.pi))
end

function Engine.pointBehind(target, distance)
    local d = distance or 2
    local o = target.o or 0
    return {
        x = (target.x or 0) - math.cos(o) * d,
        y = (target.y or 0) - math.sin(o) * d,
        o = Engine.normalizeAngle(o),
    }
end

function Engine.moveToward(from, to, maxDistance)
    local d = Engine.distance2D(from, to)
    local step = math.max(0, maxDistance or 0)
    if d == 0 or step >= d then return { x = to.x or 0, y = to.y or 0, o = from.o or 0 } end
    local r = step / d
    return {
        x = (from.x or 0) + ((to.x or 0) - (from.x or 0)) * r,
        y = (from.y or 0) + ((to.y or 0) - (from.y or 0)) * r,
        o = from.o or 0,
    }
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
    return 2.4
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

function Engine.rogueBuilderCritMultiplier(lethalityRank)
    return 2.0 + 0.06 * (lethalityRank or 0)
end

function Engine.baseSpellCritDamage(damage)
    return damage * 1.5
end

function Engine.frostIceShardsCritDamage(damage)
    return damage * 2.0
end

function Engine.rogueBackstabRaw(args)
    if not args.behindTarget then return nil, "REQUIRES_BEHIND" end
    if args.weaponType ~= "Dagger" then return nil, "REQUIRES_MH_DAGGER" end
    local normalized = Engine.normalizedWeaponDamage(
        args.minDamage, args.maxDamage, args.attackPower, "Dagger", args.roll01 or 0.5, args.flatWeaponDamage
    )
    -- Forever beta 1.60.1.69913, level-60 Backstab rank 9: 150% weapon +150.
    local damage = normalized * 1.50 + 150
    damage = damage * (1 + (args.opportunityDamagePct or 0) / 100)
    return damage
end

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

function Engine.rogueInitiativeExtraCombo(procRoll01, initiativeRank)
    -- Forever ranks: 33% / 67% / 100%.
    local chances = { [1] = 33, [2] = 67, [3] = 100 }
    local chance = chances[initiativeRank or 0] or 0
    if chance <= 0 then return 0 end
    return ((procRoll01 or 1) * 100 < chance) and 1 or 0
end

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

function Engine.regenEnergy(state, dtSeconds, energyPerSecond)
    -- Forever uses continuous Energy gain in the reference runtime.
    -- The exact rate remains a separately-audited input; do not hardcode a Classic tick.
    local dt = math.max(0, dtSeconds or 0)
    local rate = math.max(0, energyPerSecond or 0)
    state.energy = math.min(state.maxEnergy, state.energy + rate * dt)
    return state.energy
end

return Engine
