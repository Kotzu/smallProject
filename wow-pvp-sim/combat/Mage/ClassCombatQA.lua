local QA = {}

QA.version = "0.40"
QA.ruleset = "Forever"

local function baseCtx()
    local ctx = {
        ruleset = "Forever",
        spec = "Frost",
        nowMs = 10000,
        range = 20,
        self = {
            mana = 6258,
            baseMana = 6258,
            maxMana = 6258,
            healthPct = 100,
            iceBarrierAbsorb = 811,
            manaShieldAbsorb = 0,
            fingersOfFrostCharges = 0,
        },
        enemy = {
            healthPct = 100,
            stealthed = false,
            rooted = false,
            frozen = false,
            kickReady = false,
        },
        talents = {
            ["Ice Barrier"] = 1,
            ["Ice Block"] = 1,
            ["Cold Snap"] = 1,
            ["Ice Lance"] = 1,
        },
        readyActions = {},
        cooldowns = {},
        memory = {},
        events = {},
    }

    function ctx:ready(action) return self.readyActions[action] == true end
    function ctx:talentRank(name) return self.talents[name] or 0 end
    function ctx:cooldownRemaining(name) return self.cooldowns[name] or 0 end
    function ctx:cost(action)
        if action == "Blink" then return self.self.baseMana * 0.35 end
        local map = {
            ["Frostbolt"] = 290, ["Frost Nova"] = 145, ["Cone of Cold"] = 555,
            ["Ice Lance"] = 160, ["Ice Barrier"] = 480, ["Fire Blast"] = 340,
            ["Mana Shield"] = 140, ["Ice Block"] = 15, ["Cold Snap"] = 0,
        }
        return map[action]
    end
    return ctx
end

local function mark(ctx, ...)
    for i = 1, select("#", ...) do
        ctx.readyActions[select(i, ...)] = true
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
        ctx.self.stunned = true
        ctx.range = 4
        mark(ctx, "Blink")
        expect(checks, "Blink breaks lethal melee stun", Combat.choose(ctx), "Blink", "break stun")
    end

    do
        local ctx = baseCtx()
        ctx.self.rooted = true
        mark(ctx, "Blink")
        expect(checks, "Blink breaks immobilize", Combat.choose(ctx), "Blink", "break immobilize")
    end

    do
        local ctx = baseCtx()
        ctx.self.healthPct = 18
        ctx.self.iceBarrierAbsorb = 0
        mark(ctx, "Ice Block", "Ice Barrier")
        expect(checks, "Ice Block outranks Barrier at lethal HP", Combat.choose(ctx), "Ice Block", "lethal HP")
    end

    do
        local ctx = baseCtx()
        ctx.self.iceBarrierAbsorb = 0
        mark(ctx, "Ice Barrier", "Frostbolt")
        expect(checks, "Barrier refresh before pressure", Combat.choose(ctx), "Ice Barrier", "restore verified absorb")
    end

    do
        local ctx = baseCtx()
        ctx.range = 7
        ctx.enemy.rooted = false
        mark(ctx, "Frost Nova", "Mana Shield", "Frostbolt")
        expect(checks, "Nova controls melee Rogue", Combat.choose(ctx), "Frost Nova", "root melee Rogue")
    end

    do
        local ctx = baseCtx()
        ctx.range = 6
        ctx.enemy.rooted = true
        mark(ctx, "Blink", "Ice Lance")
        expect(checks, "Blink converts root into separation", Combat.choose(ctx), "Blink", "convert Frost Nova")
    end

    do
        local ctx = baseCtx()
        ctx.range = 20
        ctx.enemy.rooted = true
        mark(ctx, "Ice Lance", "Frostbolt")
        expect(checks, "Ice Lance consumes frozen pressure", Combat.choose(ctx), "Ice Lance", "Frozen-equivalent")
    end

    do
        local ctx = baseCtx()
        ctx.range = 4
        ctx.enemy.kickReady = true
        ctx.self.iceBarrierAbsorb = 811
        mark(ctx, "Frostbolt")
        local d = Combat.choose(ctx)
        local pass = d.action == "Frostbolt" and type(d.fakeAtMs) == "number" and d.fakeAtMs > 0
        checks[#checks + 1] = {
            name = "Frostbolt anti-Kick fake-cast plan",
            pass = pass,
            expected = "Frostbolt + fakeAtMs",
            actual = d.action .. " / " .. tostring(d.fakeAtMs),
            reason = d.reason,
        }
    end

    do
        local ctx = baseCtx()
        ctx.enemy.stealthed = true
        mark(ctx, "Frostbolt")
        expect(checks, "Do not cast into untargetable stealth", Combat.choose(ctx), "HOLD", "not targetable")
    end

    local failed = 0
    for _, c in ipairs(checks) do if not c.pass then failed = failed + 1 end end
    return { pass = failed == 0, passed = #checks - failed, failed = failed, checks = checks }
end

return QA
