local Combat = {}

Combat.id = "Rogue_ClassCombat"
Combat.class = "Rogue"
Combat.version = "0.23"
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

-- Only this policy block is learner-tunable.
-- CombatEngine formulas are NEVER optimized by the learner.
Combat.policy = {
    id = "rogue_cb_hemo_champion_g0",
    vanishOnRoot = true,
    prepWhenRootedAndVanishDown = true,
    kickEnabled = true,
    kickMinRemainingMs = 0,
    sprintMinRange = 5.1,
    kidneyMinCp = 5,
    kidneyEnergyReserve = 0,
    evisMinCp = 5,
    executeEvisHpPct = 0,
    executeEvisMinCp = 4,
    coldBloodMinCp = 5,
    hemoMinEnergy = 35,
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
    if ctx.build and ctx.build.modifiers and ctx.build.modifiers[name] ~= nil then return ctx.build.modifiers[name] end
    if ctx.modifier then local value = ctx:modifier(name); if value ~= nil then return value end end
    return fallback
end

local function policy(ctx)
    return ctx.policy or Combat.policy
end

local function canPrep(ctx)
    return hasTalent(ctx, "Preparation") and ctx:ready("Preparation")
end

local function chooseHemo(ctx)
    local me = ctx.self
    local enemy = ctx.enemy
    local p = policy(ctx)
    local cheapShotEnergy = modifier(ctx, "cheapShotEnergy", 40)

    if me.stunned then return { action = "WAIT", reason = "stunned" } end

    if me.rooted then
        if p.vanishOnRoot and ctx:ready("Vanish") then return { action = "Vanish", reason = "policy: break root and reopen" } end
        if p.prepWhenRootedAndVanishDown and canPrep(ctx) then return { action = "Preparation", reason = "policy: Vanish unavailable while rooted" } end
        return { action = "WAIT", reason = "rooted; no policy-approved reset available" }
    end

    if me.stealthed then
        if ctx.range <= 5 and me.energy >= cheapShotEnergy then return { action = "Cheap Shot", reason = "talent-modified opener" } end
        return { action = "MOVE_TO", range = 5, reason = "enter opener range" }
    end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive and ctx.range >= p.sprintMinRange then return { action = "Sprint", reason = "policy: recover melee range" } end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if enemy.iceBlock then return { action = "WAIT", reason = "target immune" } end

    if enemy.casting and p.kickEnabled and me.energy >= 25 and ctx:ready("Kick") then
        local remaining = ctx.castRemainingMs or 9999
        if remaining >= p.kickMinRemainingMs then return { action = "Kick", reason = "policy: interrupt dangerous cast" } end
    end

    if me.comboPoints >= p.kidneyMinCp and not enemy.stunned and me.energy >= (25 + p.kidneyEnergyReserve) and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "policy: control threshold reached" }
    end

    local enemyHpPct = enemy.healthPct or 100
    local execute = p.executeEvisHpPct > 0 and enemyHpPct <= p.executeEvisHpPct and me.comboPoints >= p.executeEvisMinCp
    if (me.comboPoints >= p.evisMinCp or execute) and me.energy >= 35 then
        if me.comboPoints >= p.coldBloodMinCp and ctx:ready("Cold Blood") and not me.coldBloodActive and hasTalent(ctx, "Cold Blood") then
            return { action = "Cold Blood", reason = "policy: guaranteed finisher crit" }
        end
        return { action = "Eviscerate", reason = execute and "policy: execute window" or "policy: finisher threshold" }
    end

    if me.energy >= p.hemoMinEnergy and hasTalent(ctx, "Hemorrhage") then return { action = "Hemorrhage", reason = "policy: builder threshold" } end
    return { action = "WAIT", reason = "policy: pool energy" }
end

local function chooseImprovedSprintBackstab(ctx)
    local me = ctx.self
    local enemy = ctx.enemy
    local behind = ctx.behindTarget == true
    local cheapShotEnergy = modifier(ctx, "cheapShotEnergy", 40)
    local sinisterStrikeEnergy = modifier(ctx, "sinisterStrikeEnergy", 40)

    if me.stunned then return { action = "WAIT", reason = "stunned" } end

    if me.rooted or me.slowed then
        if ctx:ready("Sprint") and hasTalent(ctx, "Improved Sprint") then return { action = "Sprint", reason = "Improved Sprint removes movement-impairing effects" } end
        if ctx:ready("Vanish") then return { action = "Vanish", reason = "fallback movement break and stealth reset" } end
        if canPrep(ctx) then return { action = "Preparation", reason = "Sprint/Vanish unavailable; reset Rogue-family cooldowns" } end
        return { action = "WAIT", reason = "movement impaired; no verified reset available" }
    end

    if me.stealthed then
        if ctx.range > 5 then return { action = "MOVE_TO", range = 5, reason = "enter opener range" } end
        if not behind and (hasTalent(ctx, "Improved Ambush") or hasTalent(ctx, "Improved Backstab")) then return { action = "MOVE_BEHIND", range = 2, reason = "dagger opener requires verified rear arc" } end
        if behind and me.energy >= 60 and hasTalent(ctx, "Improved Ambush") then return { action = "Ambush", reason = "dagger opener: Opportunity + Improved Ambush" } end
        if me.energy >= cheapShotEnergy then return { action = "Cheap Shot", reason = "build-specific Dirty Deeds cost" } end
        return { action = "WAIT", reason = "pool for opener" }
    end

    if enemy.iceBlock then return { action = "WAIT", reason = "target immune" } end
    if enemy.casting and me.energy >= 25 and ctx:ready("Kick") then return { action = "Kick", reason = "interrupt before positional burst" } end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive then return { action = "Sprint", reason = "recover dagger melee range" } end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if not behind and (enemy.stunned or enemy.incapacitated) and me.energy >= 60 then return { action = "MOVE_BEHIND", range = 2, reason = "convert control into legal Backstab position" } end
    if me.comboPoints >= 5 and not enemy.stunned and me.energy >= 25 and ctx:ready("Kidney Shot") then return { action = "Kidney Shot", reason = "lock target for positional follow-up" } end
    if me.comboPoints >= 5 and me.energy >= 35 then return { action = "Eviscerate", reason = "finisher; dagger build has no Cold Blood" } end
    if behind and me.energy >= 60 and hasTalent(ctx, "Improved Backstab") then return { action = "Backstab", reason = "primary dagger builder" } end
    if not behind and me.energy >= 45 and ctx:ready("Gouge") then return { action = "Gouge", reason = "Improved Gouge creates reposition window" } end
    if me.energy >= sinisterStrikeEnergy then return { action = "Sinister Strike", reason = "front-facing fallback" } end
    return { action = "WAIT", reason = "pool energy for positional attack" }
end

function Combat.choose(ctx)
    local spec = ctx.spec or Combat.activeSpec
    if spec ~= "Subtlety" then return { action = "LOCKED", reason = spec .. " policy is not verified yet; strict data gate" } end

    local id = buildId(ctx)
    if id == "rogue_cb_hemo_21_3_27" then return chooseHemo(ctx) end
    if id == "rogue_imp_sprint_backstab_17_12_22" then return chooseImprovedSprintBackstab(ctx) end
    if id == "rogue_imp_sprint_backstab_16_12_23" then return chooseImprovedSprintBackstab(ctx) end
    return { action = "LOCKED", reason = "unknown or unverified Rogue talent build: " .. tostring(id) }
end

return Combat
