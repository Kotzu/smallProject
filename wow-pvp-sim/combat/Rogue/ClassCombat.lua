local Combat = {}

Combat.id = "Rogue_ClassCombat"
Combat.class = "Rogue"
Combat.version = "0.15"
Combat.activeSpec = "Subtlety"
Combat.specStatus = {
    Assassination = "LOCKED",
    Combat = "LOCKED",
    Subtlety = "ACTIVE_CALIBRATED",
}

local function chooseSubtlety(ctx)
    local me = ctx.self
    local enemy = ctx.enemy

    if me.stunned then
        return { action = "WAIT", reason = "stunned" }
    end

    if me.rooted then
        if ctx:ready("Vanish") then
            return { action = "Vanish", reason = "break root and reopen" }
        end
        return { action = "WAIT", reason = "rooted" }
    end

    if me.stealthed then
        if ctx.range <= 5 and me.energy >= 40 then
            return { action = "Cheap Shot", reason = "stealth opener" }
        end
        return { action = "MOVE_TO", range = 5, reason = "enter opener range" }
    end

    if ctx.range > 5 then
        if ctx:ready("Sprint") and not me.sprintActive then
            return { action = "Sprint", reason = "close distance" }
        end
        return { action = "MOVE_TO", range = 5, reason = "recover melee range" }
    end

    if enemy.iceBlock then
        return { action = "WAIT", reason = "target immune" }
    end

    if enemy.casting and me.energy >= 25 and ctx:ready("Kick") then
        return { action = "Kick", reason = "interrupt dangerous cast" }
    end

    if me.comboPoints >= 5 and not enemy.stunned and me.energy >= 25 and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "create full control window" }
    end

    if me.comboPoints >= 5 and me.energy >= 35 then
        if ctx:ready("Cold Blood") and not me.coldBloodActive then
            return { action = "Cold Blood", reason = "guarantee finisher crit" }
        end
        return { action = "Eviscerate", reason = "5 CP finisher" }
    end

    if me.energy >= 35 then
        return { action = "Hemorrhage", reason = "builder and pressure" }
    end

    return { action = "WAIT", reason = "pool energy" }
end

function Combat.choose(ctx)
    local spec = ctx.spec or Combat.activeSpec
    if spec == "Subtlety" then
        return chooseSubtlety(ctx)
    end
    return {
        action = "LOCKED",
        reason = spec .. " policy is not verified yet; strict data gate",
    }
end

return Combat
