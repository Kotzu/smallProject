local QA = {}

QA.version = "0.40"
QA.ruleset = "Forever"

local function baseCtx()
    local ctx = {
        ruleset = "Forever",
        nowMs = 10000,
        range = 4,
        drVerified = true,
        self = {
            energy = 100,
            comboPoints = 0,
            healthPct = 100,
            stealthed = false,
            mainHandEquipped = true,
            offHandEquipped = true,
        },
        enemy = {
            healthPct = 100,
            dr = {
                stun = { verified = true, multiplier = 1 },
                incapacitate = { verified = true, multiplier = 1 },
                disorient = { verified = true, multiplier = 1 },
            },
        },
        talents = {},
        readyActions = {},
        verifiedActions = {},
        memory = {},
        events = {},
    }

    function ctx:ready(action)
        return self.readyActions[action] == true
    end

    function ctx:actionVerified(action)
        if self.verifiedActions[action] ~= nil then
            return self.verifiedActions[action]
        end
        return nil
    end

    function ctx:talentRank(name)
        return self.talents[name] or 0
    end

    function ctx:cost(action)
        return nil
    end

    return ctx
end

local function mark(ctx, ...)
    for i = 1, select("#", ...) do
        local action = select(i, ...)
        ctx.readyActions[action] = true
    end
    return ctx
end

local function expect(checks, name, decision, action, reasonContains)
    local pass = decision and decision.action == action
    if pass and reasonContains then
        pass = tostring(decision.reason or ""):find(reasonContains, 1, true) ~= nil
    end
    checks[#checks + 1] = {
        name = name,
        pass = pass,
        expected = action,
        actual = decision and decision.action or "nil",
        reason = decision and decision.reason or "nil",
    }
end

function QA.run(Combat)
    local checks = {}

    do
        local ctx = baseCtx()
        ctx.enemy.casting = true
        ctx.enemy.castMustInterrupt = true
        ctx.enemy.castCategory = "CC"
        ctx.enemy.castDurationMs = 1500
        ctx.enemy.castElapsedMs = 100
        ctx.enemy.castRemainingMs = 1400
        mark(ctx, "Kick")
        expect(checks, "anti-fake early cast holds", Combat.choose(ctx), "HOLD", "anti-fake")
    end

    do
        local ctx = baseCtx()
        ctx.enemy.casting = true
        ctx.enemy.castMustInterrupt = true
        ctx.enemy.castCategory = "HEAL"
        ctx.enemy.castDurationMs = 1500
        ctx.enemy.castElapsedMs = 1320
        ctx.enemy.castRemainingMs = 180
        mark(ctx, "Kick")
        expect(checks, "emergency interrupt fires", Combat.choose(ctx), "Kick", "emergency")
    end

    do
        local ctx = baseCtx()
        ctx.self.rooted = true
        ctx.talents["Improved Sprint"] = 2
        mark(ctx, "Sprint")
        expect(checks, "Improved Sprint movement emergency", Combat.choose(ctx), "Sprint", "movement impairment")
    end

    do
        local ctx = baseCtx()
        ctx.self.healthPct = 35
        ctx.enemy.physicalPressure = true
        mark(ctx, "Evasion")
        expect(checks, "physical pressure defensive", Combat.choose(ctx), "Evasion", "physical pressure")
    end

    do
        local ctx = baseCtx()
        ctx.self.comboPoints = 5
        ctx.self.energy = 70
        mark(ctx, "Kidney Shot")
        expect(checks, "Kidney protects follow-up Energy", Combat.choose(ctx), "Kidney Shot", "follow-up Energy")
    end

    do
        local ctx = baseCtx()
        ctx.self.comboPoints = 5
        ctx.enemy.healthPct = 20
        ctx.talents["Cold Blood"] = 1
        mark(ctx, "Cold Blood", "Eviscerate")
        expect(checks, "Cold Blood kill setup", Combat.choose(ctx), "Cold Blood", "guaranteed crit")
    end

    do
        local ctx = baseCtx()
        ctx.self.comboPoints = 5
        ctx.self.coldBloodActive = true
        ctx.enemy.healthPct = 20
        mark(ctx, "Eviscerate")
        expect(checks, "Eviscerate kill conversion", Combat.choose(ctx), "Eviscerate", "kill window")
    end

    do
        local ctx = baseCtx()
        ctx.talents["Hemorrhage"] = 1
        ctx.self.energy = 45
        ctx.enemy.castThreatSoonMs = 1000
        mark(ctx, "Kick", "Hemorrhage")
        expect(checks, "builder does not spend reserved Kick Energy", Combat.choose(ctx), "HOLD", "higher-priority")
    end

    do
        local ctx = baseCtx()
        ctx.enemy.immunePhysical = true
        expect(checks, "target immunity holds", Combat.choose(ctx), "HOLD", "immunity")
    end

    do
        local ctx = baseCtx()
        ctx.talents["Mutilate"] = 1
        ctx.enemy.poisoned = true
        ctx.self.energy = 100
        mark(ctx, "Mutilate")
        expect(checks, "Mutilate build uses poisoned-target builder", Combat.choose(ctx), "Mutilate", "Mutilate")
    end

    local failed = 0
    for _, check in ipairs(checks) do
        if not check.pass then failed = failed + 1 end
    end

    return {
        pass = failed == 0,
        passed = #checks - failed,
        failed = failed,
        checks = checks,
    }
end

return QA
