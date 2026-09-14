local Combat = {}
Combat.id = "Hunter_ClassCombat"
Combat.class = "Hunter"
Combat.version = "0.15"
Combat.specStatus = { ["Beast Mastery"] = "LOCKED", Marksmanship = "LOCKED", Survival = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Hunter combat policy is not verified yet; strict data gate" }
end
return Combat
