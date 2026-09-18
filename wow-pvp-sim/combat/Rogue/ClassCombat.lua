local Combat = {}

Combat.id = "Rogue_ClassCombat"
Combat.class = "Rogue"
Combat.ruleset = "Forever"
Combat.version = "0.40-forever-expert-system"
Combat.status = "POLICY_READY_FOREVER_KERNEL_GATED"

-- ARCHITECTURE NOTE
-- The uploaded TBC Anniversary Warrior profile is used ONLY as a design reference:
-- state -> memory -> deadline reactions -> resource reservation -> control plan ->
-- kill/reset plan -> damage -> intentional HOLD.
-- No TBC spell ID, stance rule, rage rule, racial, cooldown or mechanic is imported here.
Combat.designReference = {
    source = "uploaded Warrior.lua / Warrior_UI.lua / OnniSharedLib.lua",
    importedMechanics = false,
}

-- Current public Forever facts used only for policy legality/cost awareness.
-- Damage resolution, DR, hit/miss, proc math, cooldown mutation and aura application
-- remain CombatEngine responsibilities.
Combat.foreverFacts = {
    ["Cheap Shot"] = {
        energy = 60, range = 5, comboPoints = 2,
        source = "https://www.wowhead.com/forever/spell=1833/cheap-shot",
    },
    ["Kick"] = {
        energy = 25, range = 5, cooldownMs = 10000, schoolLockMs = 5000,
        source = "https://www.wowhead.com/forever/spell=1769/kick",
    },
    ["Kidney Shot"] = {
        energy = 25, range = 5, cooldownMs = 20000,
        source = "https://www.wowhead.com/forever/spell=408/kidney-shot",
    },
    ["Eviscerate"] = {
        energy = 35, range = 5,
        source = "https://www.wowhead.com/forever/spell=31016/eviscerate",
    },
    ["Hemorrhage"] = {
        energy = 35, range = 5, comboPoints = 1,
        source = "https://www.wowhead.com/forever/spell=17348/hemorrhage",
    },
    ["Gouge"] = {
        energy = 45, range = 5, cooldownMs = 10000, comboPoints = 1,
        source = "https://www.wowhead.com/forever/spell=11286/gouge",
    },
    ["Blind"] = {
        energy = 30, range = 10, cooldownMs = 300000,
        source = "https://www.wowhead.com/forever/spell=2094/blind",
    },
    ["Vanish"] = {
        energy = 0, cooldownMs = 300000, breaksMovementImpairing = true,
        source = "https://www.wowhead.com/forever/spell=1856/vanish",
    },
    ["Sprint"] = {
        energy = 0, cooldownMs = 300000,
        source = "https://www.wowhead.com/forever/spell=11305/sprint",
    },
    ["Evasion"] = {
        energy = 0, cooldownMs = 300000,
        source = "https://www.wowhead.com/forever/spell=5277/evasion",
    },
    ["Preparation"] = {
        energy = 0, cooldownMs = 600000,
        source = "https://www.wowhead.com/forever/spell=14185/preparation",
    },
    ["Cold Blood"] = {
        energy = 0, cooldownMs = 180000,
        source = "https://www.wowhead.com/forever/spell=14177/cold-blood",
    },
    ["Mutilate"] = {
        energy = 60, range = 5, comboPoints = 2,
        source = "https://www.wowhead.com/forever/spell=399956/mutilate",
    },
}

Combat.verifiedTalentFacts = {
    ["Improved Sprint"] = {
        source = "https://www.wowhead.com/forever/spell=13875/improved-sprint",
        note = "At the verified max-rank spell entry, Sprint removes movement impairing effects.",
    },
    ["Improved Gouge"] = {
        source = "https://www.wowhead.com/forever/spell=13792/improved-gouge",
        note = "Verified rank entry increases Gouge duration by 1.5 sec.",
    },
    ["Initiative"] = {
        source = "https://www.wowhead.com/forever/spell=13976/initiative",
        note = "Verified rank entry: Ambush/Garrote/Cheap Shot can grant an additional combo point.",
    },
    ["Thousand Cuts"] = {
        source = "https://www.wowhead.com/forever/spell=1310721/thousand-cuts",
        note = "Rupture ticks can reduce the Energy cost of a later Hemorrhage/Backstab; exact selected-rank modifier comes from the Forever build/engine.",
    },
    ["Quietus"] = {
        source = "https://www.wowhead.com/forever/spell=1310728/quietus",
        note = "Increases Sinister Strike/Ghostly Strike/Hemorrhage damage below 35% HP; selected-rank value is engine data.",
    },
    ["Cutthroat"] = {
        source = "https://www.wowhead.com/forever/spell=462708/cutthroat",
        note = "Backstab can enable Ambush without Stealth for 10 sec; selected-rank proc chance is engine data.",
    },
}

-- These values are POLICY, not WoW mechanics. They are learner-tunable.
Combat.policy = {
    id = "rogue_forever_expert_v1",

    -- Anti-fake / deadline behaviour.
    interruptMinElapsedMs = 300,
    interruptFireProgress = 0.72,
    interruptEmergencyMs = 250,
    interruptHoldGcdMs = 900,

    -- Tactical energy reserves.
    reserveKick = true,
    reserveKidneyBurst = true,
    kidneyFollowupEnergy = 35,
    minimumBuilderSurplus = 0,

    -- Tactical windows.
    killWindowHpPct = 30,
    quietusWindowHpPct = 35,
    defensiveVanishHpPct = 22,
    evasionHpPct = 42,
    resetHpPct = 38,

    -- Control thresholds.
    kidneyMinCp = 5,
    evisMinCp = 4,
    coldBloodMinCp = 5,

    -- Movement.
    sprintReconnectRange = 7,
    openerRange = 5,
}

Combat.layers = {
    HARD_LOCK = 1000,
    RACIAL_EMERGENCY = 950,
    MOVEMENT_EMERGENCY = 930,
    DEADLINE_INTERRUPT = 900,
    DEFENSIVE = 850,
    RESET = 800,
    MOBILITY = 700,
    CONTROL = 650,
    KILL = 600,
    DAMAGE = 500,
    FILLER = 300,
    HOLD = 100,
}

local function nowMs(ctx)
    return ctx.nowMs or ctx.timeMs or ((ctx.time or 0) * 1000)
end

local function call(ctx, method, ...)
    local fn = ctx and ctx[method]
    if type(fn) ~= "function" then return nil end
    local ok, a, b, c = pcall(fn, ctx, ...)
    if ok then return a, b, c end
    ok, a, b, c = pcall(fn, ...)
    if ok then return a, b, c end
    return nil
end

local function ready(ctx, action)
    local value = call(ctx, "ready", action)
    if value ~= nil then return value == true end
    if ctx.readyActions then return ctx.readyActions[action] == true end
    return false
end

local function actionVerified(ctx, action)
    local value = call(ctx, "actionVerified", action)
    if value ~= nil then return value == true end
    if ctx.verifiedActions and ctx.verifiedActions[action] ~= nil then
        return ctx.verifiedActions[action] == true
    end
    return Combat.foreverFacts[action] ~= nil
end

local function actionCost(ctx, action)
    local value = call(ctx, "cost", action)
    if type(value) == "number" then return value end
    local fact = Combat.foreverFacts[action]
    return fact and fact.energy or nil
end

local function talentRank(ctx, name)
    local value = call(ctx, "talentRank", name)
    if type(value) == "number" then return value end

    if ctx.talents then
        local raw = ctx.talents[name]
        if raw == true then return 1 end
        if type(raw) == "number" then return raw end
        if type(raw) == "table" then
            return raw.rank or raw.currentRank or 0
        end
    end

    local selected = ctx.build and (ctx.build.selectedTalents or ctx.build.talents)
    if type(selected) == "table" then
        for _, talent in pairs(selected) do
            if type(talent) == "table" and talent.name == name then
                return talent.rank or talent.currentRank or 0
            end
        end
    end

    return 0
end

local function hasTalent(ctx, name)
    return talentRank(ctx, name) > 0
end

local function inRange(ctx, action)
    local fact = Combat.foreverFacts[action]
    if not fact or not fact.range then return true end
    return (ctx.range or 999) <= fact.range
end

local function canUse(ctx, action)
    if not actionVerified(ctx, action) then return false, "Forever action not verified" end
    if not ready(ctx, action) then return false, "not ready" end
    if not inRange(ctx, action) then return false, "out of range" end
    local cost = actionCost(ctx, action)
    local energy = (ctx.self and ctx.self.energy) or 0
    if cost and energy < cost then return false, "insufficient Energy" end
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
        reserveEnergy = 0,
        evidence = {},
        rejected = {},
    }
end

local function reject(trace, layer, action, reason, evidence)
    trace.rejected[#trace.rejected + 1] = {
        layer = layer,
        action = action,
        reason = reason,
        evidence = evidence,
    }
end

local function choose(trace, candidate)
    trace.layer = candidate.layer
    trace.chosen = candidate.action
    trace.reason = candidate.reason
    trace.plan = candidate.plan
    trace.reserveEnergy = candidate.reserveEnergy or trace.reserveEnergy or 0
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
        reserveEnergy = reserve or 0,
        evidence = evidence or {},
    })
end

local function memoryFor(ctx)
    ctx.memory = ctx.memory or {}
    ctx.memory.Rogue = ctx.memory.Rogue or { opponents = {} }

    local enemy = ctx.enemy or {}
    local key = enemy.guid or enemy.id or enemy.name or "target"
    local mem = ctx.memory.Rogue.opponents[key]

    if not mem then
        mem = {
            key = key,
            castsSeen = 0,
            fakeCastRestarts = 0,
            interruptsLanded = 0,
            lastCastSpell = nil,
            lastCastStartMs = nil,
            lastCastEndMs = nil,
            lastCastOutcome = nil,
            usedAbilities = {},
            usedRacials = {},
            observedDefensives = {},
            plan = "NEUTRAL",
            lastDecision = nil,
            lastEventSeq = 0,
        }
        ctx.memory.Rogue.opponents[key] = mem
    end

    return mem
end

local function observeEvents(ctx, mem)
    local events = ctx.events
    if type(events) ~= "table" then return end

    local start = (mem.lastEventSeq or 0) + 1
    for i = start, #events do
        local ev = events[i]
        if type(ev) == "table" then
            local actor = ev.actor or ev.source
            local enemyKey = (ctx.enemy and (ctx.enemy.guid or ctx.enemy.id or ctx.enemy.name)) or "target"
            local isEnemy = actor == "enemy" or actor == enemyKey

            if isEnemy and ev.type == "cast_start" then
                if mem.lastCastOutcome == "CANCELLED"
                    and mem.lastCastSpell == ev.spell
                    and mem.lastCastEndMs
                    and (ev.tMs or nowMs(ctx)) - mem.lastCastEndMs <= 1500 then
                    mem.fakeCastRestarts = mem.fakeCastRestarts + 1
                end
                mem.castsSeen = mem.castsSeen + 1
                mem.lastCastSpell = ev.spell
                mem.lastCastStartMs = ev.tMs or nowMs(ctx)
                mem.lastCastOutcome = "CASTING"
            elseif isEnemy and ev.type == "cast_cancel" then
                mem.lastCastSpell = ev.spell or mem.lastCastSpell
                mem.lastCastEndMs = ev.tMs or nowMs(ctx)
                mem.lastCastOutcome = "CANCELLED"
            elseif isEnemy and ev.type == "cast_success" then
                mem.lastCastSpell = ev.spell or mem.lastCastSpell
                mem.lastCastEndMs = ev.tMs or nowMs(ctx)
                mem.lastCastOutcome = "SUCCESS"
            elseif isEnemy and ev.type == "ability_used" then
                mem.usedAbilities[ev.ability or ev.spell or "?"] = ev.tMs or nowMs(ctx)
                if ev.defensive then
                    mem.observedDefensives[ev.ability or ev.spell or "?"] = ev.tMs or nowMs(ctx)
                end
            elseif isEnemy and ev.type == "racial_used" then
                mem.usedRacials[ev.ability or ev.spell or "?"] = ev.tMs or nowMs(ctx)
            elseif ev.actor == "self" and ev.type == "interrupt_success" then
                mem.interruptsLanded = mem.interruptsLanded + 1
            end
        end
        mem.lastEventSeq = i
    end
end

local function updateCurrentCastMemory(ctx, mem)
    local enemy = ctx.enemy or {}
    if not enemy.casting then return end

    local spell = enemy.castSpell or enemy.spell or enemy.casting
    local started = enemy.castStartMs
    if spell and started and (mem.lastCastSpell ~= spell or mem.lastCastStartMs ~= started) then
        if mem.lastCastOutcome == "CANCELLED"
            and mem.lastCastSpell == spell
            and mem.lastCastEndMs
            and started - mem.lastCastEndMs <= 1500 then
            mem.fakeCastRestarts = mem.fakeCastRestarts + 1
        end
        mem.castsSeen = mem.castsSeen + 1
        mem.lastCastSpell = spell
        mem.lastCastStartMs = started
        mem.lastCastOutcome = "CASTING"
    end
end

local function racialCapability(ctx, capability)
    local racial = ctx.racial or ctx.racials
    if type(racial) ~= "table" then return nil end

    local caps = racial.capabilities or racial
    local value = caps[capability]
    if type(value) == "table" then
        if value.verified == false then return nil end
        return value
    end
    return nil
end

local function tryRacialEmergency(ctx, trace)
    local me = ctx.self or {}

    if me.stunned then
        local r = racialCapability(ctx, "breakStun")
        if r and r.action and ready(ctx, r.action) then
            return choose(trace, {
                action = r.action,
                layer = "RACIAL_EMERGENCY",
                priority = Combat.layers.RACIAL_EMERGENCY,
                reason = "verified racial stun break",
                plan = "RECOVER_CONTROL",
                evidence = { "self.stunned", "racial.breakStun" },
            })
        end
    end

    if me.feared or me.charmed or me.asleep then
        local r = racialCapability(ctx, "breakFearSleepCharm")
        if r and r.action and ready(ctx, r.action) then
            return choose(trace, {
                action = r.action,
                layer = "RACIAL_EMERGENCY",
                priority = Combat.layers.RACIAL_EMERGENCY,
                reason = "verified racial control break",
                plan = "RECOVER_CONTROL",
                evidence = { "fear/charm/sleep", "racial.breakFearSleepCharm" },
            })
        end
    end

    if me.rooted or me.slowed then
        local r = racialCapability(ctx, "breakRootSnare")
        if r and r.action and ready(ctx, r.action) then
            return choose(trace, {
                action = r.action,
                layer = "RACIAL_EMERGENCY",
                priority = Combat.layers.RACIAL_EMERGENCY,
                reason = "verified racial root/snare break",
                plan = "RECONNECT",
                evidence = { "movement impaired", "racial.breakRootSnare" },
            })
        end
    end

    return nil
end

local function drState(ctx, category)
    local enemy = ctx.enemy or {}
    local dr = enemy.dr or ctx.dr
    if type(dr) ~= "table" then return nil end
    local state = dr[category]
    if type(state) == "number" then
        return { multiplier = state, verified = ctx.drVerified == true }
    end
    if type(state) == "table" then
        return state
    end
    return nil
end

local function drAllows(ctx, category)
    local state = drState(ctx, category)
    if not state or state.verified == false then return false, "DR state unavailable/unverified" end
    if state.immune == true then return false, "target DR immune" end
    if type(state.multiplier) == "number" and state.multiplier <= 0 then return false, "target DR multiplier is zero" end
    return true
end

local function highValueCast(enemy)
    if enemy.castMustInterrupt == true then return true end
    local category = enemy.castCategory
    return category == "CC" or category == "HEAL" or category == "CONTROL" or category == "KILL"
end

local function interruptTiming(ctx, mem)
    local enemy = ctx.enemy or {}
    if not enemy.casting or not highValueCast(enemy) then
        return { relevant = false }
    end

    local remaining = ctx.castRemainingMs or enemy.castRemainingMs
    local duration = enemy.castDurationMs
    local elapsed = enemy.castElapsedMs

    if not elapsed and duration and remaining then elapsed = math.max(0, duration - remaining) end
    if not duration and elapsed and remaining then duration = elapsed + remaining end

    if not remaining then
        return {
            relevant = true,
            fire = false,
            hold = true,
            reason = "high-value cast seen but cast deadline is not available",
        }
    end

    if remaining <= Combat.policy.interruptEmergencyMs then
        return {
            relevant = true,
            fire = true,
            emergency = true,
            reason = "interrupt emergency window",
            remainingMs = remaining,
        }
    end

    if elapsed and elapsed < Combat.policy.interruptMinElapsedMs then
        return {
            relevant = true,
            fire = false,
            hold = true,
            reason = "anti-fake minimum elapsed window",
            elapsedMs = elapsed,
            remainingMs = remaining,
        }
    end

    local progress = nil
    if duration and duration > 0 and elapsed then progress = elapsed / duration end

    -- Opponents observed repeatedly restarting casts are intentionally kicked later,
    -- but the emergency window always wins.
    local targetProgress = Combat.policy.interruptFireProgress
    if (mem.fakeCastRestarts or 0) >= 2 then targetProgress = math.min(0.82, targetProgress + 0.06) end

    if progress and progress >= targetProgress then
        return {
            relevant = true,
            fire = true,
            reason = "anti-fake timing reached",
            progress = progress,
            targetProgress = targetProgress,
            remainingMs = remaining,
        }
    end

    return {
        relevant = true,
        fire = false,
        hold = remaining <= Combat.policy.interruptHoldGcdMs,
        reason = "waiting for safer interrupt timing",
        progress = progress,
        targetProgress = targetProgress,
        remainingMs = remaining,
    }
end

local function reserveEnergy(ctx, mem, plan)
    local me = ctx.self or {}
    local reserve = 0
    local evidence = {}

    if Combat.policy.reserveKick and ready(ctx, "Kick") and actionVerified(ctx, "Kick") then
        local enemy = ctx.enemy or {}
        if enemy.casting and highValueCast(enemy) then
            reserve = math.max(reserve, actionCost(ctx, "Kick") or 25)
            evidence[#evidence + 1] = "reserve Kick"
        elseif enemy.castThreatSoonMs and enemy.castThreatSoonMs <= 2000 then
            reserve = math.max(reserve, actionCost(ctx, "Kick") or 25)
            evidence[#evidence + 1] = "reserve predicted interrupt"
        end
    end

    if Combat.policy.reserveKidneyBurst and me.comboPoints and me.comboPoints >= Combat.policy.kidneyMinCp
        and ready(ctx, "Kidney Shot") and actionVerified(ctx, "Kidney Shot") then
        local drOk = drAllows(ctx, "stun")
        if drOk then
            reserve = math.max(
                reserve,
                (actionCost(ctx, "Kidney Shot") or 25) + Combat.policy.kidneyFollowupEnergy
            )
            evidence[#evidence + 1] = "reserve Kidney + follow-up"
        end
    end

    if plan == "RESET" and ready(ctx, "Gouge") and actionVerified(ctx, "Gouge") then
        reserve = math.max(reserve, actionCost(ctx, "Gouge") or 45)
        evidence[#evidence + 1] = "reserve Gouge reset"
    end

    mem.lastReserveEnergy = reserve
    return reserve, evidence
end

local function resolvePlan(ctx, mem)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local hp = enemy.healthPct or 100
    local myHp = me.healthPct or 100

    local kill = hp <= Combat.policy.killWindowHpPct
    if hasTalent(ctx, "Quietus") and hp <= Combat.policy.quietusWindowHpPct then kill = true end
    local projected = call(ctx, "canKillWith", "Eviscerate")
    if projected == true then kill = true end

    if kill then
        mem.plan = "KILL"
    elseif myHp <= Combat.policy.resetHpPct or enemy.majorDefensiveActive == true then
        mem.plan = "RESET"
    elseif (me.comboPoints or 0) >= Combat.policy.kidneyMinCp then
        mem.plan = "CONTROL"
    else
        mem.plan = "NEUTRAL"
    end

    return mem.plan
end

local function tryHardLocks(ctx, trace)
    local me = ctx.self or {}

    if me.dead or (me.healthPct and me.healthPct <= 0) then
        return hold(trace, "dead", "NONE", 0, { "self.dead" })
    end

    local racial = tryRacialEmergency(ctx, trace)
    if racial then return racial end

    if me.stunned or me.feared or me.charmed or me.asleep or me.incapacitated then
        return hold(trace, "hard crowd control; no verified break available", "RECOVER_CONTROL", 0, {
            "hard CC active",
        })
    end

    if me.casting or me.channeling then
        return hold(trace, "current action is still in progress", "CONTINUE_CURRENT_ACTION", 0)
    end

    return nil
end

local function tryMovementEmergency(ctx, trace)
    local me = ctx.self or {}

    if not (me.rooted or me.slowed) then return nil end

    if hasTalent(ctx, "Improved Sprint") and canUse(ctx, "Sprint") then
        return choose(trace, {
            action = "Sprint",
            layer = "MOVEMENT_EMERGENCY",
            priority = Combat.layers.MOVEMENT_EMERGENCY,
            reason = "Improved Sprint: clear movement impairment and reconnect",
            plan = "RECONNECT",
            evidence = { "movement impaired", "Improved Sprint selected" },
        })
    end

    if canUse(ctx, "Vanish") then
        return choose(trace, {
            action = "Vanish",
            layer = "MOVEMENT_EMERGENCY",
            priority = Combat.layers.MOVEMENT_EMERGENCY - 1,
            reason = "Vanish is verified to break movement impairing effects",
            plan = "RESET_REOPEN",
            evidence = { "movement impaired", "Vanish ready" },
        })
    end

    return nil
end

local function tryDeadlineInterrupt(ctx, trace, mem, reserve)
    local timing = interruptTiming(ctx, mem)
    if not timing.relevant then return nil end

    local usable, why = canUse(ctx, "Kick")
    if timing.fire and usable then
        return choose(trace, {
            action = "Kick",
            layer = "DEADLINE_INTERRUPT",
            priority = Combat.layers.DEADLINE_INTERRUPT,
            reason = timing.reason,
            plan = "DENY_HIGH_VALUE_CAST",
            reserveEnergy = reserve,
            evidence = {
                "category=" .. tostring((ctx.enemy or {}).castCategory),
                "remainingMs=" .. tostring(timing.remainingMs),
                "fakeCastRestarts=" .. tostring(mem.fakeCastRestarts or 0),
            },
        })
    end

    if timing.fire and not usable then
        reject(trace, "DEADLINE_INTERRUPT", "Kick", why or "not usable", timing)
    end

    if timing.hold then
        return hold(trace, timing.reason, "DENY_HIGH_VALUE_CAST", reserve, {
            "preserve GCD/Energy for Kick",
            "remainingMs=" .. tostring(timing.remainingMs),
        })
    end

    return nil
end

local function tryDefensive(ctx, trace, mem)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local myHp = me.healthPct or 100

    if enemy.physicalPressure == true and myHp <= Combat.policy.evasionHpPct and canUse(ctx, "Evasion") then
        return choose(trace, {
            action = "Evasion",
            layer = "DEFENSIVE",
            priority = Combat.layers.DEFENSIVE,
            reason = "physical pressure + defensive HP window",
            plan = "SURVIVE",
            evidence = { "enemy.physicalPressure", "hp=" .. tostring(myHp) },
        })
    end

    if myHp <= Combat.policy.defensiveVanishHpPct and canUse(ctx, "Vanish") then
        return choose(trace, {
            action = "Vanish",
            layer = "DEFENSIVE",
            priority = Combat.layers.DEFENSIVE - 1,
            reason = "emergency reset",
            plan = "RESET_REOPEN",
            evidence = { "hp=" .. tostring(myHp) },
        })
    end

    if myHp <= Combat.policy.defensiveVanishHpPct and hasTalent(ctx, "Preparation")
        and ready(ctx, "Preparation") and actionVerified(ctx, "Preparation")
        and not ready(ctx, "Vanish") then
        return choose(trace, {
            action = "Preparation",
            layer = "DEFENSIVE",
            priority = Combat.layers.DEFENSIVE - 2,
            reason = "reset Rogue cooldowns to recover a defensive/reopen option",
            plan = "RESET_COOLDOWNS",
            evidence = { "low HP", "Vanish unavailable", "Preparation selected" },
        })
    end

    return nil
end

local function tryReset(ctx, trace, mem, reserve)
    if mem.plan ~= "RESET" then return nil end

    local enemy = ctx.enemy or {}
    local safeBreakable = ctx.breakableControlSafe == true

    if safeBreakable and enemy.facingMe == true and canUse(ctx, "Gouge") then
        local drOk, why = drAllows(ctx, "incapacitate")
        if drOk then
            return choose(trace, {
                action = "Gouge",
                layer = "RESET",
                priority = Combat.layers.RESET,
                reason = "create a verified break-on-damage reset window",
                plan = "RESET_REOPEN",
                reserveEnergy = reserve,
                evidence = {
                    "target facing Rogue",
                    "breakable control safe",
                    "Improved Gouge rank=" .. tostring(talentRank(ctx, "Improved Gouge")),
                },
            })
        end
        reject(trace, "RESET", "Gouge", why, nil)
    end

    if safeBreakable and canUse(ctx, "Blind") then
        local drOk, why = drAllows(ctx, "disorient")
        if drOk then
            return choose(trace, {
                action = "Blind",
                layer = "RESET",
                priority = Combat.layers.RESET - 1,
                reason = "create long reset window",
                plan = "RESET_REOPEN",
                reserveEnergy = reserve,
                evidence = { "breakable control safe" },
            })
        end
        reject(trace, "RESET", "Blind", why, nil)
    end

    if canUse(ctx, "Vanish") then
        return choose(trace, {
            action = "Vanish",
            layer = "RESET",
            priority = Combat.layers.RESET - 2,
            reason = "direct reset/reopen",
            plan = "RESET_REOPEN",
            reserveEnergy = reserve,
        })
    end

    return nil
end

local function tryStealthOpener(ctx, trace, mem)
    local me = ctx.self or {}
    if not me.stealthed then return nil end

    if (ctx.range or 999) > Combat.policy.openerRange then
        return choose(trace, {
            action = "MOVE_TO",
            range = Combat.policy.openerRange,
            layer = "MOBILITY",
            priority = Combat.layers.MOBILITY,
            reason = "enter verified melee opener range",
            plan = "OPEN",
        })
    end

    local cheapCost = actionCost(ctx, "Cheap Shot") or 60
    if canUse(ctx, "Cheap Shot") then
        return choose(trace, {
            action = "Cheap Shot",
            layer = "CONTROL",
            priority = Combat.layers.CONTROL,
            reason = "stealth opener; Forever Cheap Shot grants 2 combo points",
            plan = "OPEN_CONTROL",
            reserveEnergy = 0,
            evidence = { "cost=" .. tostring(cheapCost), "stealthed", "range<=5" },
        })
    end

    return hold(trace, "pooling for verified stealth opener", "OPEN", cheapCost)
end

local function tryMobility(ctx, trace)
    local me = ctx.self or {}
    local range = ctx.range or 999

    if range <= 5 then return nil end

    if range >= Combat.policy.sprintReconnectRange and not me.sprintActive and canUse(ctx, "Sprint") then
        return choose(trace, {
            action = "Sprint",
            layer = "MOBILITY",
            priority = Combat.layers.MOBILITY,
            reason = "reconnect to melee",
            plan = "RECONNECT",
            evidence = { "range=" .. tostring(range) },
        })
    end

    return choose(trace, {
        action = "MOVE_TO",
        range = 5,
        layer = "MOBILITY",
        priority = Combat.layers.MOBILITY - 1,
        reason = "recover melee range",
        plan = "RECONNECT",
        evidence = { "range=" .. tostring(range) },
    })
end

local function tryControl(ctx, trace, mem, reserve)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local cp = me.comboPoints or 0

    if cp < Combat.policy.kidneyMinCp or enemy.stunned then return nil end

    local drOk, why = drAllows(ctx, "stun")
    if not drOk then
        reject(trace, "CONTROL", "Kidney Shot", why, nil)
        return nil
    end

    local cost = actionCost(ctx, "Kidney Shot") or 25
    if canUse(ctx, "Kidney Shot") and me.energy >= cost then
        local followup = math.max(0, Combat.policy.kidneyFollowupEnergy)
        if me.energy >= cost + followup or mem.plan == "KILL" then
            return choose(trace, {
                action = "Kidney Shot",
                layer = "CONTROL",
                priority = Combat.layers.CONTROL,
                reason = "full-combo control window with follow-up Energy protected",
                plan = mem.plan == "KILL" and "KILL_CONTROL" or "CONTROL",
                reserveEnergy = reserve,
                evidence = {
                    "comboPoints=" .. tostring(cp),
                    "energy=" .. tostring(me.energy),
                    "followupReserve=" .. tostring(followup),
                },
            })
        end
        return hold(trace, "pool Energy before Kidney so control converts into pressure", "CONTROL", cost + followup)
    end

    return nil
end

local function tryKill(ctx, trace, mem, reserve)
    if mem.plan ~= "KILL" then return nil end

    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local cp = me.comboPoints or 0
    if cp < Combat.policy.evisMinCp then return nil end

    if hasTalent(ctx, "Cold Blood") and cp >= Combat.policy.coldBloodMinCp
        and not me.coldBloodActive and ready(ctx, "Cold Blood") and actionVerified(ctx, "Cold Blood") then
        return choose(trace, {
            action = "Cold Blood",
            layer = "KILL",
            priority = Combat.layers.KILL,
            reason = "prepare guaranteed crit on an eligible Forever finisher",
            plan = "KILL_EVIS",
            reserveEnergy = reserve,
            evidence = {
                "Cold Blood selected",
                "comboPoints=" .. tostring(cp),
                "targetHP=" .. tostring(enemy.healthPct or 100),
            },
        })
    end

    if canUse(ctx, "Eviscerate") then
        return choose(trace, {
            action = "Eviscerate",
            layer = "KILL",
            priority = Combat.layers.KILL - 1,
            reason = "convert combo points in kill window",
            plan = "KILL",
            reserveEnergy = reserve,
            evidence = {
                "comboPoints=" .. tostring(cp),
                "targetHP=" .. tostring(enemy.healthPct or 100),
                "QuietusRank=" .. tostring(talentRank(ctx, "Quietus")),
            },
        })
    end

    return nil
end

local function tryCutthroatProc(ctx, trace, reserve)
    local me = ctx.self or {}
    if not hasTalent(ctx, "Cutthroat") or not me.cutthroatActive then return nil end
    if not actionVerified(ctx, "Ambush") or not ready(ctx, "Ambush") then return nil end

    local cost = actionCost(ctx, "Ambush")
    if not cost then
        reject(trace, "DAMAGE", "Ambush", "Forever Ambush cost not available in runtime data", nil)
        return nil
    end

    if me.energy < cost + reserve then
        return hold(trace, "preserve Energy before Cutthroat Ambush", "CUTTHROAT_PROC", cost + reserve)
    end

    return choose(trace, {
        action = "Ambush",
        layer = "DAMAGE",
        priority = Combat.layers.DAMAGE + 20,
        reason = "consume verified Cutthroat proc",
        plan = "PRESSURE",
        reserveEnergy = reserve,
        evidence = { "Cutthroat active", "rank=" .. tostring(talentRank(ctx, "Cutthroat")) },
    })
end

local function tryBuilder(ctx, trace, mem, reserve)
    local me = ctx.self or {}
    local enemy = ctx.enemy or {}
    local usableEnergy = me.energy - reserve

    local cutthroat = tryCutthroatProc(ctx, trace, reserve)
    if cutthroat then return cutthroat end

    -- Mutilate is a Forever option. The engine decides the selected rank, poison bonus,
    -- weapon legality and damage. The policy only chooses it when those prerequisites
    -- are already represented in state.
    if hasTalent(ctx, "Mutilate") and enemy.poisoned == true
        and me.mainHandEquipped ~= false and me.offHandEquipped ~= false then
        local cost = actionCost(ctx, "Mutilate") or 60
        if canUse(ctx, "Mutilate") and usableEnergy >= cost then
            return choose(trace, {
                action = "Mutilate",
                layer = "DAMAGE",
                priority = Combat.layers.DAMAGE + 10,
                reason = "Forever Mutilate builder on poisoned target",
                plan = "BUILD_COMBO",
                reserveEnergy = reserve,
                evidence = {
                    "poisoned target",
                    "dual weapons present",
                    "usableEnergy=" .. tostring(usableEnergy),
                },
            })
        end
    end

    if hasTalent(ctx, "Hemorrhage") then
        local cost = actionCost(ctx, "Hemorrhage") or 35
        if canUse(ctx, "Hemorrhage") and usableEnergy >= cost + Combat.policy.minimumBuilderSurplus then
            local reason = "Hemorrhage builder without breaking reserved Energy"
            if hasTalent(ctx, "Quietus") and (enemy.healthPct or 100) <= Combat.policy.quietusWindowHpPct then
                reason = "Quietus health window: Hemorrhage pressure"
            elseif hasTalent(ctx, "Thousand Cuts") and (me.thousandCutsStacks or 0) > 0 then
                reason = "consume Thousand Cuts Hemorrhage cost window"
            end

            return choose(trace, {
                action = "Hemorrhage",
                layer = "DAMAGE",
                priority = Combat.layers.DAMAGE,
                reason = reason,
                plan = "BUILD_COMBO",
                reserveEnergy = reserve,
                evidence = {
                    "usableEnergy=" .. tostring(usableEnergy),
                    "ThousandCutsStacks=" .. tostring(me.thousandCutsStacks or 0),
                    "QuietusRank=" .. tostring(talentRank(ctx, "Quietus")),
                },
            })
        end
    end

    -- Generic fallback is allowed only when the runtime explicitly verifies the action.
    if actionVerified(ctx, "Sinister Strike") and ready(ctx, "Sinister Strike") then
        local cost = actionCost(ctx, "Sinister Strike")
        if cost and usableEnergy >= cost then
            return choose(trace, {
                action = "Sinister Strike",
                layer = "FILLER",
                priority = Combat.layers.FILLER,
                reason = "verified builder fallback",
                plan = "BUILD_COMBO",
                reserveEnergy = reserve,
            })
        end
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
    updateCurrentCastMemory(ctx, mem)

    if ctx.ruleset and ctx.ruleset ~= "Forever" then
        return choose(trace, {
            action = "LOCKED",
            layer = "HARD_LOCK",
            priority = Combat.layers.HARD_LOCK,
            reason = "Rogue ClassCombat.lua is Forever-only",
            plan = "NONE",
        })
    end

    if ctx.build and ctx.build.status and ctx.build.status == "ClassicEra" then
        return choose(trace, {
            action = "LOCKED",
            layer = "HARD_LOCK",
            priority = Combat.layers.HARD_LOCK,
            reason = "Classic build data is forbidden in WoW Forever combat",
            plan = "NONE",
        })
    end

    local hard = tryHardLocks(ctx, trace)
    if hard then mem.lastDecision = hard.trace; return hard end

    local movementEmergency = tryMovementEmergency(ctx, trace)
    if movementEmergency then mem.lastDecision = movementEmergency.trace; return movementEmergency end

    local plan = resolvePlan(ctx, mem)
    local reserve, reserveEvidence = reserveEnergy(ctx, mem, plan)
    trace.reserveEnergy = reserve
    trace.evidence = reserveEvidence

    local interrupt = tryDeadlineInterrupt(ctx, trace, mem, reserve)
    if interrupt then mem.lastDecision = interrupt.trace; return interrupt end

    local defensive = tryDefensive(ctx, trace, mem)
    if defensive then mem.lastDecision = defensive.trace; return defensive end

    if ctx.enemy.immuneAll == true or ctx.enemy.immunePhysical == true then
        local answer = hold(trace, "target immunity active; do not waste Energy or cooldowns", "WAIT_IMMUNITY", reserve)
        mem.lastDecision = answer.trace
        return answer
    end

    local opener = tryStealthOpener(ctx, trace, mem)
    if opener then mem.lastDecision = opener.trace; return opener end

    local reset = tryReset(ctx, trace, mem, reserve)
    if reset then mem.lastDecision = reset.trace; return reset end

    local mobility = tryMobility(ctx, trace)
    if mobility then mem.lastDecision = mobility.trace; return mobility end

    local control = tryControl(ctx, trace, mem, reserve)
    if control then mem.lastDecision = control.trace; return control end

    local kill = tryKill(ctx, trace, mem, reserve)
    if kill then mem.lastDecision = kill.trace; return kill end

    local builder = tryBuilder(ctx, trace, mem, reserve)
    if builder then mem.lastDecision = builder.trace; return builder end

    local answer = hold(trace,
        reserve > 0 and "intentional Energy hold for higher-priority future action" or "no verified action beats waiting",
        plan,
        reserve,
        reserveEvidence
    )
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
