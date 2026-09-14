local Combat = {}

Combat.id = "Mage_Frost_17_0_34"
Combat.class = "Mage"
Combat.spec = "Frost"
Combat.version = "0.14"

-- Decision layer only.
-- CombatEngine decides hit/miss/resist/crit/damage/DR/procs/resources.
function Combat.choose(ctx)
    local me = ctx.self
    local enemy = ctx.enemy

    if me.iceBlockActive then
        return { action = "WAIT", reason = "Ice Block active" }
    end

    if me.casting then
        return { action = "WAIT", reason = "cast in progress" }
    end

    if me.stunned then
        if ctx.range <= 5 and ctx:ready("Blink") then
            return { action = "Blink", reason = "escape stun/melee" }
        end
        return { action = "WAIT", reason = "stunned" }
    end

    if (me.rooted or me.slowed) and ctx:ready("Escape Artist") then
        return { action = "Escape Artist", reason = "remove root/snare" }
    end

    if me.healthPct < 28 and ctx:ready("Ice Block") then
        return { action = "Ice Block", reason = "emergency immunity" }
    end

    if me.healthPct < 65 and ctx:ready("Arena Grand Master") then
        return { action = "Arena Grand Master", reason = "defensive absorb" }
    end

    if ctx.range <= 6 and ctx:ready("Blink") then
        return { action = "Blink", reason = "create distance" }
    end

    if me.iceBarrierAbsorb <= 0 and ctx:ready("Ice Barrier") then
        return { action = "Ice Barrier", reason = "refresh absorb" }
    end

    if me.manaShieldAbsorb <= 0 and ctx.range <= 8 then
        return { action = "Mana Shield", reason = "melee pressure" }
    end

    if ctx.range <= 10 and not enemy.rooted and ctx:ready("Frost Nova") then
        return { action = "Frost Nova", reason = "root melee target" }
    end

    if ctx.range <= 10 and ctx:ready("Cone of Cold") then
        return { action = "Cone of Cold", reason = "close-range damage + slow" }
    end

    if ctx.range <= 20 and ctx:ready("Fire Blast") then
        return { action = "Fire Blast", reason = "instant pressure" }
    end

    if ctx.range <= 12 and ctx:ready("Cold Snap") and (not ctx:ready("Frost Nova") or not ctx:ready("Ice Barrier")) then
        return { action = "Cold Snap", reason = "reset Frost control/defense" }
    end

    if ctx.range <= 30 then
        return { action = "Frostbolt", reason = "primary ranged cast" }
    end

    return { action = "MOVE_TO", range = 30, reason = "enter cast range" }
end

return Combat
