local Combat = {}
Combat.id = "Paladin_ClassCombat"
Combat.class = "Paladin"
Combat.version = "0.15"
Combat.specStatus = { Holy = "LOCKED", Protection = "LOCKED", Retribution = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Paladin combat policy is not verified yet; strict data gate" }
end
return Combat
