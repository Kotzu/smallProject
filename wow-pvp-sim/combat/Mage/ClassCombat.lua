local Combat = {}

Combat.id = "Mage_ClassCombat"
Combat.class = "Mage"
Combat.ruleset = "Forever"
Combat.version = "0.40-forever-expert-system"
Combat.status = "POLICY_READY_FOREVER_REFERENCE_KERNEL"
Combat.activeSpec = "Frost"

-- Same architecture standard as Rogue/Warrior reference:
-- state -> opponent memory -> emergency deadlines -> defensive/control plan ->
-- resource protection -> pressure -> intentional HOLD.
-- TBC mechanics are never imported.

Combat.policy = {
    id = "mage_frost_forever_expert_v1",
    lethalIceBlockHpPct = 20,
    barrierRefreshHpPct = 92,
    coldSnapHpPct = 55,
    frostNovaRange = 10,
    blinkSeparationRange = 18,
    fireBlastExecuteHpPct = 25,
    fakeCastEnabled = true,
    fakeCastMaxPerOpponent = 2,
    fakeCastBaseMs = 450,
    fakeCastStepMs = 150,
    minimumManaReserve = 0,
}

Combat.layers = {
    HARD_LOCK = 1000,
    EMERGENCY = 950,
    DEFENSIVE = 850,
    CONTROL = 760,
    MOBILITY = 735,
    RESET = 710,
    KILL = 650,
    DAMAGE = 520,
    HOLD = 100,
}

Combat.foreverFacts = {
    ["Frostbolt"] = { range = 30, mana = 290, castMs = 3000, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Frost Nova"] = { range = 10, mana = 145, cooldownMs = 25000, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Cone of Cold"] = { range = 10, mana = 555, cooldownMs = 10000, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Ice Lance"] = { range = 30, mana = 160, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Ice Barrier"] = { mana = 480, cooldownMs = 30000, absorb = 811, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Blink"] = { baseManaPct = 35, cooldownMs = 15000, distance = 20, breaksStun = true, breaksImmobilize = true, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Fire Blast"] = { range = 20, mana = 340, cooldownMs = 8000, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Mana Shield"] = { mana = 140, absorb = 570, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Polymorph"] = { range = 30, mana = 150, castMs = 1500, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Counterspell"] = { range = 30, mana = 100, cooldownMs = 30000, source = "https://foreverchanges.pro/spellbook/mage" },
    ["Ice Block"] = { mana = 15, cooldownMs = 300000, durationMs = 10000, source = "https://foreverchanges.pro/talents/mage" },
    ["Cold Snap"] = { mana = 0, cooldownMs = 600000, source = "https://foreverchanges.pro/talents/mage" },
}

local function call(ctx, method, ...)
    local fn = ctx and ctx[method]
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c = pcall(fn, ctx, ...)
    if ok then return a, b, c end
    ok, a, b, c = pcall(fn, ...)
    if ok then return a, b, c end
    return nil
end

local function nowMs(ctx)
    return ctx.nowMs or ctx.timeMs or ((ctx.time or 0) * 1000)
end

local function talentRank(ctx, name)
    local value = call(ctx, "talentRank", name)
    if type(value) == "number" then return value end

    local raw = ctx.talents and ctx.talents[name]
    if type(raw) == "number" then return raw end
    if raw == true then return 1 end
    if type(raw) == "table" then return raw.rank or raw.currentRank or 0 end

    local selected = ctx.build and (ctx.build.selectedTalents or ctx.build.talents)
    if type(selected) == "table" then
        for _, talent in pairs(selected) do
            if type(talent) == "table" and talent.name == name then
                return tonumber(talent.rank or talent.currentRank or 0) or 0
            end
        end
    end
    return 0
end

local function hasTalent(ctx, name)
    return talentRank(ctx, name) > 0
end

local function ready(ctx, name)
    local v = call(ctx, "ready", name)
    if v ~= nil then return v == true end
    return ctx.readyActions and ctx.readyActions[name] == true or false
end

local function cooldown(ctx, name)
    local v = call(ctx, "cooldownRemaining", name)
    if type(v) == "number" then return v end
    return 0
end

local function cost(ctx, name)
    local v = call(ctx, "cost", name)
    if type(v) == "number" then return v end
    local f = Combat.foreverFacts[name]
    if not f then return math.huge end
    if f.mana then return f.mana end
    if f.baseManaPct then
        local base = (ctx.self and (ctx.self.baseMana or ctx.self.maxMana)) or 0
        return base * f.baseManaPct / 100
    end
    return 0
end

local function canUse(ctx, name)
    local f = Combat.foreverFacts[name]
    if not f then return false, "Forever action not registered" end
    if not ready(ctx, name) then return false, "not ready" end
    if f.range and (ctx.range or 999) > f.range then return false, "out of range" end
    local mana = (ctx.self and ctx.self.mana) or 0
    local c = cost(ctx, name)
    if mana < c then return false, "insufficient Mana" end
    return true
end

local function newTrace(ctx)
    return {
        ruleset = "Forever",
        policy = Combat.policy.id,
        atMs = nowMs(ctx),
        buildDb = ctx.build and ctx.build.db or nil,
        layer = nil,
        chosen = nil,
        reason = nil,
        plan = nil,
        reserveMana = 0,
        evidence = {},
        rejected = {},
    }
end

local function reject(trace, layer, action, reason, evidence)
    trace.rejected[#trace.rejected + 1] = {
        layer = layer, action = action, reason = reason, evidence = evidence,
    }
end

local function choose(trace, candidate)
    trace.layer = candidate.layer
    trace.chosen = candidate.action
    trace.reason = candidate.reason
    trace.plan = candidate.plan
    trace.reserveMana = candidate.reserveMana or trace.reserveMana or 0
    trace.evidence = candidate.evidence or trace.evidence or {}
    candidate.trace = trace
    return candidate
end

local function hold(trace, reason, plan, reserve, evidence)
    return choose(trace, {
        action = "HOLD",
        layer = "HOLD",
        priority = Combat.layers.HOLD,
        reason = reason,
        plan = plan,
        reserveMana = reserve or 0,
        evidence = evidence or {},
    })
end

local function memoryFor(ctx)
    ctx.memory = ctx.memory or {}
    ctx.memory.Mage = ctx.memory.Mage or { opponents = {} }
    local e = ctx.enemy or {}
    local key = e.guid or e.id or e.name or "target"
    local mem = ctx.memory.Mage.opponents[key]
    if not mem then
        mem = {
            key = key,
            fakeCasts = 0,
            successfulCasts = 0,
            interruptedCasts = 0,
            rogueKickSeen = false,
            rogueVanishSeen = false,
            rogueKidneySeen = false,
            roguePreparationSeen = false,
            lastEnemyAction = nil,
            lastDecision = nil,
            lastEventSeq = 0,
        }
        ctx.memory.Mage.opponents[key] = mem
    end
    return mem
end

local function observeEvents(ctx, mem)
    local events = ctx.events
    if type(events) ~= "table" then return end
    for i = (mem.lastEventSeq or 0) + 1, #events do
        local ev = events[i]
        if type(ev) == "table" then
            local actor = ev.actor or ev.source
            if actor == "enemy" then
                local a = ev.ability or ev.spell or ev.action
                mem.lastEnemyAction = a or mem.lastEnemyAction
                if a == "Kick" then mem.rogueKickSeen = true end
                if a == "Vanish" then mem.rogueVanishSeen = true end
                if a == "Kidney Shot" then mem.rogueKidneySeen = true end
                if a == "Preparation" then mem.roguePreparationSeen = true end
            elseif actor == "self" then
                if ev.type == "cast_cancel" then mem.fakeCasts = mem.fakeCasts + 1 end
                if ev.type == "cast_success" then mem.successfulCasts = mem.successfulCasts + 1 end
                if ev.type == "interrupt_received" then mem.interruptedCasts = mem.interruptedCasts + 1 end
            end
        end
        mem.lastEventSeq = i
    end
end

local function resolvePlan(ctx)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    if (me.healthPct or 100) <= Combat.policy.lethalIceBlockHpPct then return "SURVIVE" end
    if enemy.stealthed then return "DETECT_WAIT" end
    if (ctx.range or 999) <= 8 then return "ESCAPE_MELEE" end
    if enemy.rooted or enemy.frozen or (me.fingersOfFrostCharges or 0) > 0 then return "SHATTER" end
    return "CONTROL_PRESSURE"
end

local function tryHardLocks(ctx, trace)
    local me = ctx.self or {}
    if me.dead or (me.healthPct and me.healthPct <= 0) then
        return hold(trace, "dead", "NONE")
    end
    if me.iceBlockActive then
        return hold(trace, "Ice Block active", "SURVIVE")
    end
    if me.casting or me.channeling then
        return hold(trace, "current cast/channel in progress", "CONTINUE_CAST")
    end
    return nil
end

local function tryEmergency(ctx, trace)
    local me = ctx.self or {}
    local hp = me.healthPct or 100

    if me.stunned then
        local ok = canUse(ctx, "Blink")
        if ok then
            return choose(trace, {
                action = "Blink", layer = "EMERGENCY", priority = Combat.layers.EMERGENCY,
                reason = "break stun and create separation", plan = "ESCAPE_MELEE",
                evidence = { "self.stunned", "Blink ready" },
            })
        end
        if hp <= Combat.policy.lethalIceBlockHpPct and hasTalent(ctx, "Ice Block") then
            local block = canUse(ctx, "Ice Block")
            if block then
                return choose(trace, {
                    action = "Ice Block", layer = "EMERGENCY", priority = Combat.layers.EMERGENCY - 10,
                    reason = "lethal stun with Blink unavailable", plan = "SURVIVE",
                    evidence = { "low HP", "Blink unavailable" },
                })
            end
        end
        return hold(trace, "stunned; no verified escape available", "SURVIVE")
    end

    if me.rooted then
        local ok = canUse(ctx, "Blink")
        if ok then
            return choose(trace, {
                action = "Blink", layer = "EMERGENCY", priority = Combat.layers.EMERGENCY - 20,
                reason = "break immobilize and create separation", plan = "ESCAPE_MELEE",
                evidence = { "self.rooted" },
            })
        end
        return hold(trace, "rooted; no verified root break ready", "RECOVER_CONTROL")
    end

    if me.disoriented or me.incapacitated or me.feared or me.silenced then
        return hold(trace, "hard control active", "RECOVER_CONTROL")
    end

    return nil
end

local function tryDefensive(ctx, trace, plan)
    local me = ctx.self or {}
    local hp = me.healthPct or 100

    if hp <= Combat.policy.lethalIceBlockHpPct and hasTalent(ctx, "Ice Block") then
        local ok = canUse(ctx, "Ice Block")
        if ok then
            return choose(trace, {
                action = "Ice Block", layer = "DEFENSIVE", priority = Combat.layers.DEFENSIVE,
                reason = "emergency immunity at lethal HP", plan = "SURVIVE",
                evidence = { "hp=" .. tostring(hp) },
            })
        end
    end

    if (me.iceBarrierAbsorb or 0) <= 0 and hasTalent(ctx, "Ice Barrier") then
        local ok = canUse(ctx, "Ice Barrier")
        if ok then
            return choose(trace, {
                action = "Ice Barrier", layer = "DEFENSIVE", priority = Combat.layers.DEFENSIVE - 10,
                reason = "restore verified absorb before further melee pressure", plan = "SURVIVE",
                evidence = { "Ice Barrier absent" },
            })
        end
    end

    if plan == "ESCAPE_MELEE" and (me.manaShieldAbsorb or 0) <= 0 then
        local ok = canUse(ctx, "Mana Shield")
        if ok and (ctx.range or 999) <= 7 then
            return choose(trace, {
                action = "Mana Shield", layer = "DEFENSIVE", priority = Combat.layers.DEFENSIVE - 30,
                reason = "extra physical absorb under melee pressure", plan = "SURVIVE",
                evidence = { "Rogue in melee range" },
            })
        end
    end

    return nil
end

local function tryControlMobility(ctx, trace, plan)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local range = ctx.range or 999

    if enemy.stealthed then
        return hold(trace, "Rogue is not targetable while stealthed", "DETECT_WAIT", 0, {
            "preserve control cooldowns",
        })
    end

    if range <= Combat.policy.frostNovaRange and not enemy.rooted then
        local ok = canUse(ctx, "Frost Nova")
        if ok then
            return choose(trace, {
                action = "Frost Nova", layer = "CONTROL", priority = Combat.layers.CONTROL,
                reason = "root melee Rogue before kiting", plan = "ESCAPE_MELEE",
                evidence = { "range=" .. tostring(range) },
            })
        end
    end

    if enemy.rooted and range < Combat.policy.blinkSeparationRange then
        local ok = canUse(ctx, "Blink")
        if ok then
            return choose(trace, {
                action = "Blink", layer = "MOBILITY", priority = Combat.layers.MOBILITY,
                reason = "convert Frost Nova into separation", plan = "SHATTER",
                evidence = { "Rogue rooted", "range=" .. tostring(range) },
            })
        end
    end

    return nil
end

local function tryColdSnap(ctx, trace)
    local me = ctx.self or {}
    if not hasTalent(ctx, "Cold Snap") then return nil end
    if (me.healthPct or 100) >= Combat.policy.coldSnapHpPct then return nil end
    if not ready(ctx, "Cold Snap") then return nil end

    local novaCd = cooldown(ctx, "Frost Nova")
    local barrierCd = cooldown(ctx, "Ice Barrier")
    if novaCd > 8000 and barrierCd > 10000 then
        return choose(trace, {
            action = "Cold Snap", layer = "RESET", priority = Combat.layers.RESET,
            reason = "recover Frost control and defense under sustained pressure", plan = "SURVIVE",
            evidence = { "Frost Nova cd=" .. tostring(novaCd), "Ice Barrier cd=" .. tostring(barrierCd) },
        })
    end
    return nil
end

local function tryDamage(ctx, trace, mem, plan)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local range = ctx.range or 999
    local frozen = enemy.frozen or enemy.rooted or (me.fingersOfFrostCharges or 0) > 0

    if frozen and hasTalent(ctx, "Ice Lance") then
        local ok = canUse(ctx, "Ice Lance")
        if ok then
            return choose(trace, {
                action = "Ice Lance", layer = "DAMAGE", priority = Combat.layers.KILL,
                reason = "instant pressure on Frozen-equivalent target", plan = "SHATTER",
                evidence = { enemy.rooted and "rooted target" or "Fingers of Frost" },
            })
        end
    end

    if range <= 10 then
        local ok = canUse(ctx, "Cone of Cold")
        if ok then
            return choose(trace, {
                action = "Cone of Cold", layer = "DAMAGE", priority = Combat.layers.DAMAGE + 70,
                reason = "instant close-range Frost pressure and slow", plan = "PRESSURE",
            })
        end
    end

    if range <= 20 and ((enemy.healthPct or 100) < Combat.policy.fireBlastExecuteHpPct or range < 12) then
        local ok = canUse(ctx, "Fire Blast")
        if ok then
            return choose(trace, {
                action = "Fire Blast", layer = "DAMAGE", priority = Combat.layers.DAMAGE + 40,
                reason = "instant pressure while kiting", plan = "PRESSURE",
            })
        end
    end

    local frostboltOk = canUse(ctx, "Frostbolt")
    if frostboltOk then
        local kickThreat = enemy.kickReady == true and range <= 5
        local canFake = Combat.policy.fakeCastEnabled and kickThreat
            and (mem.fakeCasts or 0) < Combat.policy.fakeCastMaxPerOpponent

        local fakeAtMs = nil
        local reason = "primary ranged control/pressure cast"
        if canFake then
            fakeAtMs = Combat.policy.fakeCastBaseMs + Combat.policy.fakeCastStepMs * (mem.fakeCasts or 0)
            reason = "start Frostbolt with deliberate anti-Kick fake-cast plan"
        end

        return choose(trace, {
            action = "Frostbolt", layer = "DAMAGE", priority = Combat.layers.DAMAGE,
            reason = reason, plan = "CONTROL_PRESSURE",
            fakeAtMs = fakeAtMs,
            evidence = canFake and { "Rogue Kick ready", "fake-casts=" .. tostring(mem.fakeCasts or 0) }
                or { "safe ranged cast" },
        })
    end

    if range > 30 then
        return choose(trace, {
            action = "MOVE_TO", range = 30, layer = "MOBILITY", priority = Combat.layers.MOBILITY - 50,
            reason = "enter Frostbolt range", plan = "CONTROL_PRESSURE",
        })
    end

    return nil
end

function Combat.choose(ctx)
    ctx = ctx or {}
    ctx.self = ctx.self or {}
    ctx.enemy = ctx.enemy or {}

    local trace = newTrace(ctx)
    local mem = memoryFor(ctx)
    observeEvents(ctx, mem)

    if ctx.ruleset and ctx.ruleset ~= "Forever" then
        return choose(trace, {
            action = "LOCKED", layer = "HARD_LOCK", priority = Combat.layers.HARD_LOCK,
            reason = "Mage ClassCombat.lua is Forever-only", plan = "NONE",
        })
    end
    if ctx.spec and ctx.spec ~= "Frost" then
        return choose(trace, {
            action = "LOCKED", layer = "HARD_LOCK", priority = Combat.layers.HARD_LOCK,
            reason = tostring(ctx.spec) .. " Mage policy is not implemented in the reference matchup", plan = "NONE",
        })
    end

    local hard = tryHardLocks(ctx, trace)
    if hard then mem.lastDecision = hard.trace; return hard end

    local emergency = tryEmergency(ctx, trace)
    if emergency then mem.lastDecision = emergency.trace; return emergency end

    local plan = resolvePlan(ctx)

    local defensive = tryDefensive(ctx, trace, plan)
    if defensive then mem.lastDecision = defensive.trace; return defensive end

    local control = tryControlMobility(ctx, trace, plan)
    if control then mem.lastDecision = control.trace; return control end

    local reset = tryColdSnap(ctx, trace)
    if reset then mem.lastDecision = reset.trace; return reset end

    local pressure = tryDamage(ctx, trace, mem, plan)
    if pressure then mem.lastDecision = pressure.trace; return pressure end

    local answer = hold(trace, "no verified action currently improves position", plan,
        Combat.policy.minimumManaReserve)
    mem.lastDecision = answer.trace
    return answer
end

function Combat.getOpponentMemory(ctx)
    return memoryFor(ctx or {})
end

function Combat.getLastDecisionTrace(ctx)
    local mem = memoryFor(ctx or {})
    return mem.lastDecision
end

return Combat
