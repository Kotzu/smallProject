local Combat = {}
Combat.id = "Druid_ClassCombat"
Combat.class = "Druid"
Combat.version = "0.15"
Combat.specStatus = { Balance = "LOCKED", ["Feral Combat"] = "LOCKED", Restoration = "LOCKED" }
function Combat.choose(ctx)
    return { action = "LOCKED", reason = "Druid combat policy is not verified yet; strict data gate" }
end
return Combat
