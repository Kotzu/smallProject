local Combat = {}

Combat.id = "Rogue_ClassCombat"
Combat.class = "Rogue"
Combat.version = "0.17"
Combat.activeSpec = "Subtlety"
Combat.specStatus = {
    Assassination = "LOCKED",
    Combat = "LOCKED",
    Subtlety = "ACTIVE",
}

Combat.buildStatus = {
    rogue_cb_hemo_21_3_27 = "ACTIVE_CALIBRATED",
    rogue_imp_sprint_backstab_17_12_22 = "VERIFIED_LOCKED_KERNEL",
}

local function buildId(ctx)
    return ctx.buildId or (ctx.build and ctx.build.id) or "rogue_cb_hemo_21_3_27"
end

local function hasTalent(ctx, name)
    if ctx.hasTalent then return ctx:hasTalent(name) end
    if ctx.talents then return ctx.talents[name] == true or (ctx.talents[name] or 0) > 0 end
    return false
end

local function chooseHemo(ctx)
    local me = ctx.self
    local enemy = ctx.enemy

    if me.stunned then return { action = "WAIT", reason = "stunned" } end

    if me.rooted then
        if ctx:ready("Vanish") then return { action = "Vanish", reason = "break root and reopen" } end
        return { action = "WAIT", reason = "rooted" }
    end

    if me.stealthed then
        if ctx.range <= 5 and me.energy >= 40 then
            return { action = "Cheap Shot", reason = "Dirty Deeds 2/2 opener: 40 Energy" }
        end
        return { action = "MOVE_TO", range = 5, reason = "enter opener range" }
    end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive then return { action = "Sprint", reason = "close distance" } end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if enemy.iceBlock then return { action = "WAIT", reason = "target immune" } end

    if enemy.casting and me.energy >= 25 and ctx:ready("Kick") then
        return { action = "Kick", reason = "interrupt dangerous cast" }
    end

    if me.comboPoints >= 5 and not enemy.stunned and me.energy >= 25 and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "create full control window" }
    end

    if me.comboPoints >= 5 and me.energy >= 35 then
        if ctx:ready("Cold Blood") and not me.coldBloodActive and hasTalent(ctx, "Cold Blood") then
            return { action = "Cold Blood", reason = "talent guarantees finisher crit" }
        end
        return { action = "Eviscerate", reason = "5 CP finisher" }
    end

    if me.energy >= 35 and hasTalent(ctx, "Hemorrhage") then
        return { action = "Hemorrhage", reason = "talented builder and pressure" }
    end

    return { action = "WAIT", reason = "pool energy" }
end

local function chooseImprovedSprintBackstab(ctx)
    local me = ctx.self
    local enemy = ctx.enemy
    local behind = ctx.behindTarget == true

    if me.stunned then return { action = "WAIT", reason = "stunned" } end

    -- Improved Sprint 2/2 is this build's anti-kite identity.
    if me.rooted or me.slowed then
        if ctx:ready("Sprint") and hasTalent(ctx, "Improved Sprint") then
            return { action = "Sprint", reason = "Improved Sprint removes movement-impairing effects" }
        end
        if ctx:ready("Vanish") then return { action = "Vanish", reason = "fallback root break and reset" } end
        return { action = "WAIT", reason = "movement impaired" }
    end

    if me.stealthed then
        if ctx.range > 5 then return { action = "MOVE_TO", range = 5, reason = "enter opener range" } end
        if behind and me.energy >= 60 and hasTalent(ctx, "Improved Ambush") then
            return { action = "Ambush", reason = "dagger opener: Opportunity + Improved Ambush" }
        end
        if me.energy >= 50 then
            return { action = "Cheap Shot", reason = "Dirty Deeds 1/2 opener: 50 Energy" }
        end
        return { action = "WAIT", reason = "pool for opener" }
    end

    if enemy.iceBlock then return { action = "WAIT", reason = "target immune" } end

    if enemy.casting and me.energy >= 25 and ctx:ready("Kick") then
        return { action = "Kick", reason = "interrupt before spending positional burst" }
    end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive then return { action = "Sprint", reason = "recover dagger melee range" } end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if me.comboPoints >= 5 and not enemy.stunned and me.energy >= 25 and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "lock target for positional follow-up" }
    end

    if me.comboPoints >= 5 and me.energy >= 35 then
        return { action = "Eviscerate", reason = "finisher; build has no Cold Blood" }
    end

    if behind and me.energy >= 60 and hasTalent(ctx, "Improved Backstab") then
        return { action = "Backstab", reason = "primary dagger builder: +30% crit and Opportunity" }
    end

    if me.energy >= 45 and ctx:ready("Gouge") then
        return { action = "Gouge", reason = "Improved Gouge creates reposition / energy-pool window" }
    end

    if me.energy >= 40 then
        return { action = "Sinister Strike", reason = "front-facing fallback; Improved Sinister Strike costs 40" }
    end

    return { action = "WAIT", reason = "pool energy for positional attack" }
end

function Combat.choose(ctx)
    local spec = ctx.spec or Combat.activeSpec
    if spec ~= "Subtlety" then
        return { action = "LOCKED", reason = spec .. " policy is not verified yet; strict data gate" }
    end

    local id = buildId(ctx)
    if id == "rogue_cb_hemo_21_3_27" then return chooseHemo(ctx) end
    if id == "rogue_imp_sprint_backstab_17_12_22" then return chooseImprovedSprintBackstab(ctx) end

    return { action = "LOCKED", reason = "unknown or unverified Rogue talent build: " .. tostring(id) }
end

return Combat
