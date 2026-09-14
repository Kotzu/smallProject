local Combat = {}
Combat.id = "Warlock_ClassCombat"
Combat.class = "Warlock"
Combat.version = "0.15"
Combat.specStatus = { Affliction = "LOCKED", Demonology = "LOCKED", Destruction = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Warlock combat policy is not verified yet; strict data gate" }
end
return Combat
