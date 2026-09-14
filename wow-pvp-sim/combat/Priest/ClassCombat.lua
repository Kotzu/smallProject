local Combat = {}
Combat.id = "Priest_ClassCombat"
Combat.class = "Priest"
Combat.version = "0.15"
Combat.specStatus = { Discipline = "LOCKED", Holy = "LOCKED", Shadow = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Priest combat policy is not verified yet; strict data gate" }
end
return Combat
