local TalentBuilds = {}

TalentBuilds.version = "0.18"

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
            builderCritMultiplier = 2.30,
            cheapShotEnergy = 40,
            coldBlood = true,
            hemorrhage = true,
            preparation = true,
            improvedSprint = false,
        },
    },

    rogue_imp_sprint_backstab_17_12_22 = {
        name = "Improved Sprint Backstab - Expose Armor variant",
        class = "Rogue",
        spec = "Subtlety",
        level = 60,
        points = "17/12/22",
        status = "VERIFIED_LOCKED_KERNEL",
        calculator = "005320124-320302002-05024303030011",
        loadoutId = "rogue_p6_pvp_daggers_kingsfall_deaths_sting",
        modifiers = {
            meleeCritPct = 5,
            meleeHitPct = 2,
            ruthlessnessProcPct = 60,
            murderDamagePct = 2,
            relentlessEnergy = 25,
            relentlessChancePerComboPct = 20,
            improvedExposeArmorPct = 50,
            builderCritMultiplier = 2.24,
            gougeDurationBonusMs = 1500,
            sinisterStrikeEnergy = 40,
            backstabCritBonusPct = 30,
            improvedSprint = true,
            opportunityDamagePct = 20,
            ambushCritBonusPct = 45,
            preparation = true,
            cheapShotEnergy = 50,
            hemorrhage = false,
            coldBlood = false,
        },
        kernelBlockers = {
            "positional behind-state model",
            "Gouge control/break-on-damage path",
            "dagger weapon-skill PvP combat-table validation",
            "policy parity QA",
        },
    },

    rogue_imp_sprint_backstab_16_12_23 = {
        name = "Improved Sprint Backstab - 16/12/23",
        class = "Rogue",
        spec = "Subtlety",
        level = 60,
        points = "16/12/23",
        status = "VERIFIED_LOCKED_KERNEL",
        calculator = "305020105-320302002-05024303030012",
        loadoutId = "rogue_p6_pvp_daggers_kingsfall_deaths_sting",
        modifiers = {
            improvedEvisceratePct = 15,
            meleeCritPct = 5,
            murderDamagePct = 2,
            relentlessEnergy = 25,
            relentlessChancePerComboPct = 20,
            builderCritMultiplier = 2.30,
            gougeDurationBonusMs = 1500,
            sinisterStrikeEnergy = 40,
            backstabCritBonusPct = 30,
            meleeHitPct = 2,
            improvedSprint = true,
            opportunityDamagePct = 20,
            elusiveness = true,
            camouflageRank = 4,
            initiativeProcPct = 75,
            ambushCritBonusPct = 45,
            improvedSapStayStealthPct = 90,
            preparation = true,
            cheapShotEnergy = 40,
            hemorrhage = false,
            coldBlood = false,
        },
        kernelBlockers = {
            "positional behind-state model",
            "Initiative extra-combo-point proc path",
            "Gouge control/break-on-damage path",
            "Elusiveness cooldown adjustments",
            "dagger weapon-skill PvP combat-table validation",
            "policy parity QA",
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

function TalentBuilds.isVerified(className, spec, buildId)
    local build = TalentBuilds.get(className, buildId)
    return build ~= nil and build.spec == spec and (build.status == "ACTIVE_CALIBRATED" or build.status == "VERIFIED_LOCKED_KERNEL")
end

function TalentBuilds.isKernelReady(className, spec, buildId)
    local build = TalentBuilds.get(className, buildId)
    return build ~= nil and build.spec == spec and build.status == "ACTIVE_CALIBRATED"
end

return TalentBuilds
