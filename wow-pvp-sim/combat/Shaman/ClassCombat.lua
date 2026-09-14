local Combat = {}
Combat.id = "Shaman_ClassCombat"
Combat.class = "Shaman"
Combat.version = "0.15"
Combat.specStatus = { Elemental = "LOCKED", Enhancement = "LOCKED", Restoration = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Shaman combat policy is not verified yet; strict data gate" }
end
return Combat
