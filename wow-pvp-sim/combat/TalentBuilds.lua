local TalentBuilds = {}

TalentBuilds.version = "0.40-forever-dynamic"
TalentBuilds.ruleset = "Forever"
TalentBuilds.status = "DYNAMIC_FROM_ARMORY"

-- WoW Forever builds are not static Classic calculator strings.
-- The canonical build is exported by forever-builds.js from the live Forever
-- talent dataset and passed into the combat context.
TalentBuilds.snapshot = {
    source = "https://www.wowhead.com/forever/talent-calc",
    pointCap = 51,
    status = "PROVISIONAL_UNTIL_BETA_DATAMINING",
}

local function selected(build)
    if type(build) ~= "table" then return {} end
    return build.selectedTalents or build.talents or {}
end

function TalentBuilds.talentRank(build, name)
    for _, talent in pairs(selected(build)) do
        if type(talent) == "table" and talent.name == name then
            return tonumber(talent.rank or talent.currentRank or 0) or 0
        end
    end
    return 0
end

function TalentBuilds.hasTalent(build, name)
    return TalentBuilds.talentRank(build, name) > 0
end

function TalentBuilds.totalPoints(build)
    if type(build) ~= "table" then return 0 end
    if type(build.points) == "number" then return build.points end

    local total = 0
    for _, talent in pairs(selected(build)) do
        if type(talent) == "table" then
            total = total + (tonumber(talent.rank or talent.currentRank or 0) or 0)
        end
    end
    return total
end

function TalentBuilds.audit(build, className)
    local issues = {}

    if type(build) ~= "table" then
        issues[#issues + 1] = "missing build"
        return { pass = false, issues = issues, points = 0 }
    end

    if build.ruleset and build.ruleset ~= "forever" and build.ruleset ~= "Forever" then
        issues[#issues + 1] = "non-Forever ruleset"
    end

    if build.status == "ClassicEra" or build.dataset == "ClassicEra" then
        issues[#issues + 1] = "Classic build forbidden"
    end

    if className and build.className and build.className ~= className then
        issues[#issues + 1] = "class mismatch"
    end

    if not build.db then
        issues[#issues + 1] = "missing Forever db provenance"
    end

    local points = TalentBuilds.totalPoints(build)
    if points ~= TalentBuilds.snapshot.pointCap then
        issues[#issues + 1] = "build must contain exactly 51 points"
    end

    return {
        pass = #issues == 0,
        issues = issues,
        points = points,
        db = build.db,
        source = build.source,
    }
end

function TalentBuilds.fromContext(ctx, className)
    if type(ctx) ~= "table" then return nil end
    local build = ctx.build
    local audit = TalentBuilds.audit(build, className)
    if not audit.pass then return nil, audit end
    return build, audit
end

function TalentBuilds.isKernelReady(build, className, parity)
    local audit = TalentBuilds.audit(build, className)
    return audit.pass and parity == true
end

-- Source notes for combat-relevant Forever Rogue talents already identified.
-- These are effect provenance entries, not a prescribed build.
TalentBuilds.RogueFacts = {
    ["Improved Sprint"] = "https://www.wowhead.com/forever/spell=13875/improved-sprint",
    ["Improved Gouge"] = "https://www.wowhead.com/forever/spell=13792/improved-gouge",
    ["Initiative"] = "https://www.wowhead.com/forever/spell=13976/initiative",
    ["Cold Blood"] = "https://www.wowhead.com/forever/spell=14177/cold-blood",
    ["Preparation"] = "https://www.wowhead.com/forever/spell=14185/preparation",
    ["Thousand Cuts"] = "https://www.wowhead.com/forever/spell=1310721/thousand-cuts",
    ["Quietus"] = "https://www.wowhead.com/forever/spell=1310728/quietus",
    ["Cutthroat"] = "https://www.wowhead.com/forever/spell=462708/cutthroat",
}

return TalentBuilds
