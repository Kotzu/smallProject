local Racials = {}

Racials.version = "0.40-2026-09-18"
Racials.ruleset = "Forever"
Racials.status = "PUBLIC_EFFECTS_VERIFIED_KERNEL_GATED"
Racials.source = "https://www.wowhead.com/forever/guide/new-race-class-combinations"

-- This registry is descriptive input for future CombatEngine work.
-- Missing cooldowns/durations/numeric values stay nil rather than being inferred.
Racials.Skyborne = {
    shared = {
        ["Walk on Air"] = {
            effect = "Glide downward through the air for 10 sec.",
            durationSec = 10,
            combatTag = "mobility",
        },
        ["Wind Blessed"] = {
            effect = "1% increased melee, ranged, and spellcasting Haste.",
            hastePct = 1,
            passive = true,
        },
        ["Elemental Insight"] = {
            effect = "Damage to Elementals increased by 5%.",
            elementalDamagePct = 5,
            passive = true,
        },
    },
    Alliance = {
        variant = "High Order Skyborne",
        ["Read Ley Line"] = {
            effect = "Activate a ley line to gain 100% increased Health and Mana regeneration.",
            regenIncreasePct = 100,
            combatTag = "recovery",
            durationSec = nil,
            cooldownSec = nil,
        },
    },
    Horde = {
        variant = "Windshaper Skyborne",
        ["Skysight"] = {
            effect = "Receive an Elemental Blessing increasing run speed by 10%.",
            runSpeedPct = 10,
            combatTag = "mobility",
            durationSec = nil,
            cooldownSec = nil,
        },
    },
}

Racials.Undead = {
    ["Will of the Forsaken"] = {
        effect = "Instantly removes all Charm, Fear, and Sleep effects.",
        capabilities = { breakFearSleepCharm = true },
        cooldownSec = nil,
    },
    ["Touch of the Grave"] = {
        effect = "Spells and attacks have a 5% chance to drain Health from the target, up to 5% of maximum Health.",
        procChancePct = 5,
        maxHealthPct = 5,
        passive = true,
    },
    ["Cannibalize"] = {
        effect = "Regenerates 7% total Health and 7% total Mana every 2 sec for 10 sec on a nearby Humanoid/Undead corpse; movement, action or damage cancels it.",
        healthPctPerTick = 7,
        manaPctPerTick = 7,
        tickSec = 2,
        durationSec = 10,
    },
}

Racials.Dwarf = {
    ["Stoneform"] = {
        effect = "Removes and grants immunity to Bleeds, Poisons, and Diseases and reduces Physical damage taken by 10% for 8 sec.",
        capabilities = { cleanseBleedPoisonDisease = true },
        physicalDamageTakenPct = -10,
        durationSec = 8,
    },
    ["Mace Specialization"] = {
        effect = "Increases critical strike chance with mace or two-handed mace equipped by 1%.",
        critPct = 1,
        passive = true,
    },
}

Racials.Gnome = {
    ["Escape Artist"] = {
        effect = "Brief immunity to Roots and Snares.",
        capabilities = { breakRootSnare = true },
        durationSec = nil,
        cooldownSec = nil,
    },
    ["Eureka!"] = {
        effect = "Reduced cost and 10% increased damage or healing on the next 3 spells or abilities.",
        damageHealingPct = 10,
        charges = 3,
        costReductionPct = nil,
    },
    ["Expansive Mind"] = {
        effect = "Increases maximum resource.",
        resourceIncreasePct = nil,
        passive = true,
    },
}

Racials.Human = {
    ["Will to Survive"] = {
        effect = "Removes Stun.",
        capabilities = { breakStun = true },
        cooldownSec = nil,
    },
    ["Perception"] = {
        effect = "Detect Stealthed enemies for 20 sec.",
        durationSec = 20,
        combatTag = "anti_stealth",
    },
    ["Sword Specialization"] = {
        effect = "Swords increase spell and ability Critical Chance by 2%.",
        critPct = 2,
        passive = true,
    },
}

Racials["Night Elf"] = {
    ["Elunes Light"] = {
        effect = "Increases Critical Chance by 10% for 15 sec.",
        critPct = 10,
        durationSec = 15,
    },
    ["Quickness"] = {
        effect = "1% increased Dodge Chance and 2% increased Run Speed.",
        dodgePct = 1,
        runSpeedPct = 2,
        passive = true,
    },
    ["Shadowmeld"] = {
        effect = "Gain Stealth while immobile.",
        combatTag = "stealth",
    },
}

Racials.Orc = {
    ["Blood Fury"] = {
        effect = "Increases Attack Power and Spell Power by 10% for 15 sec.",
        attackPowerPct = 10,
        spellPowerPct = 10,
        durationSec = 15,
    },
    ["Hardiness"] = {
        effect = "Stun durations decreased by 20%.",
        stunDurationPct = -20,
        passive = true,
    },
    ["Shatter Curse"] = {
        effect = "Immunity to Curses and Banes and reduces Magical Damage taken for 8 sec.",
        capabilities = { curseBaneImmunity = true },
        durationSec = 8,
        magicDamageTakenPct = nil,
    },
}

Racials.Tauren = {
    ["War Stomp"] = {
        effect = "Stuns nearby enemies for 2 sec.",
        durationSec = 2,
        combatTag = "aoe_stun",
    },
    ["Endurance"] = {
        effect = "Total Health increased by 5% and Hit Chance increased by 1%.",
        healthPct = 5,
        hitPct = 1,
        passive = true,
    },
    ["Plainsrunning"] = {
        effect = "Gain increased movement speed the longer you stay moving.",
        combatTag = "mobility",
        exactScaling = nil,
    },
}

Racials.Troll = {
    ["Berserking"] = {
        effect = "Increases casting and attack speed by 10% for 10 sec.",
        hastePct = 10,
        durationSec = 10,
    },
    ["Regeneration"] = {
        effect = "10% of Health regeneration continues during combat.",
        inCombatRegenPct = 10,
        passive = true,
    },
    ["Rapid Regeneration"] = {
        effect = "Regenerate 50% of maximum Health over time.",
        maxHealthPct = 50,
        durationSec = nil,
        cooldownSec = nil,
    },
}

function Racials.get(race, faction)
    if race == "Skyborne" then
        local out = { shared = Racials.Skyborne.shared }
        if faction and Racials.Skyborne[faction] then
            out.faction = Racials.Skyborne[faction]
        end
        return out
    end
    return Racials[race]
end

function Racials.kernelReady()
    return false
end

return Racials
