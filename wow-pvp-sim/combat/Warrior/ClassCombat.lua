local Combat = {}
Combat.id = "Warrior_ClassCombat"
Combat.class = "Warrior"
Combat.version = "0.15"
Combat.specStatus = { Arms = "LOCKED", Fury = "LOCKED", Protection = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Warrior combat policy is not verified yet; strict data gate" }
end
return Combat
