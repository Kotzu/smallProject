local Combat = {}

Combat.id = "Rogue_ClassCombat"
Combat.class = "Rogue"
Combat.version = "0.25"
Combat.activeSpec = "Subtlety"

Combat.specStatus = {
    Assassination = "LOCKED",
    Combat = "LOCKED",
    Subtlety = "ACTIVE",
}

Combat.buildStatus = {
    rogue_cb_hemo_21_3_27 = "ACTIVE_CALIBRATED",
    rogue_imp_sprint_backstab_17_12_22 = "VERIFIED_LOCKED_KERNEL",
    rogue_imp_sprint_backstab_16_12_23 = "VERIFIED_LOCKED_KERNEL",
}

-- This block is the ONLY learner-tunable part of Rogue combat.
-- WoW formulas, talent effects, hit/crit/resist/proc rules stay in CombatEngine/data.
Combat.policy = {
    id = "rogue_cb_hemo_champion_g2_evis4_pool55",
    vanishOnRoot = true,
    prepWhenRootedAndVanishDown = true,
    kickEnabled = true,
    kickMinRemainingMs = 0,
    sprintMinRange = 5.1,
    kidneyMinCp = 5,
    kidneyEnergyReserve = 0,
    evisMinCp = 4,
    executeEvisHpPct = 0,
    executeEvisMinCp = 4,
    coldBloodMinCp = 5,
    hemoMinEnergy = 55,
}

Combat.policyEvidence = {
    method = "paired deterministic seeds",
    matchup = "Undead Subtlety CB/Hemo vs Gnome Frost Mage",
    generations = {
        { change = "Eviscerate threshold: 5 CP -> 4 CP", fights = 1000, beforeWins = 838, afterWins = 892, deltaWinRate = 5.4 },
        { change = "Hemorrhage pool: 35 Energy -> 55 Energy", fights = 1000, beforeWins = 892, afterWins = 920, deltaWinRate = 2.8 },
    },
}

local function buildId(ctx)
    return ctx.buildId or (ctx.build and ctx.build.id) or "rogue_cb_hemo_21_3_27"
end

local function hasTalent(ctx, name)
    if ctx.hasTalent then return ctx:hasTalent(name) end
    if ctx.talents then return ctx.talents[name] == true or (ctx.talents[name] or 0) > 0 end
    return false
end

local function modifier(ctx, name, fallback)
    if ctx.build and ctx.build.modifiers and ctx.build.modifiers[name] ~= nil then
        return ctx.build.modifiers[name]
    end
    if ctx.modifier then
        local value = ctx:modifier(name)
        if value ~= nil then return value end
    end
    return fallback
end

local function activePolicy(ctx)
    return ctx.policy or Combat.policy
end

local function chooseCbHemo(ctx)
    local me = ctx.self
    local enemy = ctx.enemy
    local p = activePolicy(ctx)
    local cheapShotEnergy = modifier(ctx, "cheapShotEnergy", 40)

    if me.stunned then
        return { action = "WAIT", reason = "stunned" }
    end

    if me.rooted then
        if p.vanishOnRoot and ctx:ready("Vanish") then
            return { action = "Vanish", reason = "policy: break root and reopen" }
        end
        if p.prepWhenRootedAndVanishDown and hasTalent(ctx, "Preparation") and ctx:ready("Preparation") then
            return { action = "Preparation", reason = "policy: Vanish unavailable while rooted" }
        end
        return { action = "WAIT", reason = "rooted; no verified reset available" }
    end

    if me.stealthed then
        if ctx.range <= 5 and me.energy >= cheapShotEnergy then
            return { action = "Cheap Shot", reason = "verified opener" }
        end
        return { action = "MOVE_TO", range = 5, reason = "enter opener range" }
    end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive and ctx.range >= p.sprintMinRange then
            return { action = "Sprint", reason = "policy: recover melee range" }
        end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if enemy.iceBlock then
        return { action = "WAIT", reason = "target immune" }
    end

    if enemy.casting and p.kickEnabled and me.energy >= 25 and ctx:ready("Kick") then
        local remaining = ctx.castRemainingMs or 9999
        if remaining >= p.kickMinRemainingMs then
            return { action = "Kick", reason = "policy: interrupt cast" }
        end
    end

    if me.comboPoints >= p.kidneyMinCp and not enemy.stunned and me.energy >= (25 + p.kidneyEnergyReserve) and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "policy: control threshold" }
    end

    local hp = enemy.healthPct or 100
    local execute = p.executeEvisHpPct > 0 and hp <= p.executeEvisHpPct and me.comboPoints >= p.executeEvisMinCp
    if (me.comboPoints >= p.evisMinCp or execute) and me.energy >= 35 then
        if me.comboPoints >= p.coldBloodMinCp and hasTalent(ctx, "Cold Blood") and ctx:ready("Cold Blood") and not me.coldBloodActive then
            return { action = "Cold Blood", reason = "policy: prepare guaranteed finisher crit" }
        end
        return { action = "Eviscerate", reason = execute and "policy: execute" or "policy: 4+ CP conversion" }
    end

    if hasTalent(ctx, "Hemorrhage") and me.energy >= p.hemoMinEnergy then
        return { action = "Hemorrhage", reason = "policy: pool to 55 Energy before builder" }
    end

    return { action = "WAIT", reason = "policy: pool Energy" }
end

function Combat.choose(ctx)
    local spec = ctx.spec or Combat.activeSpec
    if spec ~= "Subtlety" then
        return { action = "LOCKED", reason = spec .. " policy is not verified yet" }
    end

    local id = buildId(ctx)
    if id == "rogue_cb_hemo_21_3_27" then
        return chooseCbHemo(ctx)
    end

    return {
        action = "LOCKED",
        reason = "Rogue build is verified/documented but not active in the exact kernel: " .. tostring(id),
    }
end

return Combat
