local Combat = {}

Combat.id = "Rogue_Subtlety_21_3_27"
Combat.class = "Rogue"
Combat.spec = "Subtlety"
Combat.version = "0.14"

-- Decision layer only.
-- CombatEngine decides hit/miss/dodge/crit/damage/DR/procs/resources.
function Combat.choose(ctx)
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
        return { action = "MOVE_TO", range = 5, reason = "melee range" }
    end

    if enemy.iceBlock then
        return { action = "WAIT", reason = "target immune" }
    end

    if enemy.casting and me.energy >= 25 and ctx:ready("Kick") then
        return { action = "Kick", reason = "interrupt cast" }
    end

    if me.comboPoints >= 5 and not enemy.stunned and me.energy >= 25 and ctx:ready("Kidney Shot") then
        return { action = "Kidney Shot", reason = "full control window" }
    end

    if me.comboPoints >= 5 and me.energy >= 35 then
        if ctx:ready("Cold Blood") and not me.coldBloodActive then
            return { action = "Cold Blood", reason = "guarantee Eviscerate crit" }
        end
        return { action = "Eviscerate", reason = "5 CP finisher" }
    end

    if me.energy >= 35 then
        return { action = "Hemorrhage", reason = "builder" }
    end

    return { action = "WAIT", reason = "pool energy" }
end

return Combat
