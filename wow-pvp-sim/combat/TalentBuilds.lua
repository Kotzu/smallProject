local TalentBuilds = {}

TalentBuilds.version = "0.16"

TalentBuilds.Rogue = {
    rogue_cb_hemo_21_3_27 = {
        name = "Cold Blood Hemorrhage",
        class = "Rogue",
        spec = "Subtlety",
        level = 60,
        points = "21/3/27",
        status = "ACTIVE_CALIBRATED",
        calculator = "305320115001-3-500253000332121",
        modifiers = {
            improvedEvisceratePct = 15,
            meleeCritPct = 5,
            murderDamagePct = 2,
            relentlessEnergy = 25,
            relentlessChancePerComboPct = 20,
            hemorrhageCritMultiplier = 2.3,
            cheapShotEnergy = 40,
            coldBlood = true,
            hemorrhage = true,
            preparation = true,
        },
    },
}

TalentBuilds.Mage = {
    mage_deep_frost_17_0_34 = {
        name = "Deep Frost PvP",
        class = "Mage",
        spec = "Frost",
        level = 60,
        points = "17/0/34",
        status = "ACTIVE_CALIBRATED",
        calculator = "23001503102--05350233102351001",
        modifiers = {
            frostboltCastMs = 2500,
            frostFireHitPct = 6,
            frostCritMultiplier = 2.0,
            frozenCritBonusPct = 50,
            frostDamagePct = 6,
            frostNovaCooldownMs = 21000,
            chillDurationBonusMs = 3000,
            chillSlowBonusPct = 10,
            coneOfColdDamagePct = 35,
            armorFromIntellectPct = 50,
            counterspellSilenceMs = 4000,
            coldSnap = true,
            iceBlock = true,
            iceBarrier = true,
        },
    },
}

-- Strict placeholders: these classes have a ClassCombat.lua file but no build is
-- allowed to enter the simulator until its talent ranks and numeric modifiers are verified.
TalentBuilds.Locked = {
    Warrior = "NO_VERIFIED_BUILD",
    Paladin = "NO_VERIFIED_BUILD",
    Hunter = "NO_VERIFIED_BUILD",
    Priest = "NO_VERIFIED_BUILD",
    Shaman = "NO_VERIFIED_BUILD",
    Warlock = "NO_VERIFIED_BUILD",
    Druid = "NO_VERIFIED_BUILD",
}

function TalentBuilds.get(className, buildId)
    local classBuilds = TalentBuilds[className]
    if type(classBuilds) ~= "table" then return nil end
    return classBuilds[buildId]
end

function TalentBuilds.isActive(className, spec, buildId)
    local build = TalentBuilds.get(className, buildId)
    return build ~= nil and build.spec == spec and build.status == "ACTIVE_CALIBRATED"
end

return TalentBuilds
