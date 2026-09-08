-- Perfect Assassin Observer v0.5.5
-- TBC 2.4.3 read-only collector. It never emits input, chat, addon messages,
-- protected actions or server queries. The client persists this table itself.

local PAO_SCHEMA_VERSION = "0.4"
local PAO_ADAPTER = "tbc243_saved_variables:0.4.0"
local PAO_EVENT_FORMAT = "tbc243-legacy-v1"
local PAO_MAX_EVENTS = 5000
local PAO_INITIALIZED = false
local PAO_MAP_CONTEXT_READY = false
local PAO_HUD_SEQUENCE = 0
local PAO_HUD_ACCUMULATOR = 0
local PAO_HUD_MAGIC = 165
local PAO_HUD_PROTOCOL_VERSION = 3
local PAO_COMBAT_HUD_MAGIC = 198
local PAO_COMBAT_HUD_PROTOCOL_VERSION = 6
local PAO_COMBAT_HUD_SEQUENCE = 0
local PAO_LOOT_EVENT_SEQUENCE = 0
local PAO_LAST_TARGET_INTERACT_CRC16 = 0
local PAO_LAST_TARGET_INTERACT_X = 0
local PAO_LAST_TARGET_INTERACT_Y = 0
local PAO_COMBAT_STATE = false
local PAO_HUD_LAST_ERROR = nil
local PAO_HUD_DRAGGING = false
local PAO_HUD_MOVER_MOUSE_ENABLED = false
local PAO_HUD_WIDTH = 170
local PAO_HUD_HEIGHT = 79
local PAO_HUD_DEFAULT_X = 16
local PAO_HUD_DEFAULT_Y = -100
local PAO_HUD_CAPTURE_WIDTH_FRACTION = 0.5
local PAO_HUD_CAPTURE_HEIGHT_FRACTION = 0.35
local PAO_HUD_CAPTURE_FOOTPRINT_RIGHT = 164
local PAO_HUD_CAPTURE_FOOTPRINT_BOTTOM = 77
local PAO_HUD_CAPTURE_MARGIN = 8
local PAO_HUD_PARENT_WIDTH = nil
local PAO_HUD_PARENT_HEIGHT = nil
local PAO_TARGET_ARROW_ENABLED = true
local PAO_TARGET_ARROW_SCAN_LIMIT = 512
-- This is the wire-contract tolerance used by the external combat domain too.
-- Keeping a second, tighter value here made offsets in (0.08, 0.12] publish
-- RIGHT/LEFT while their exact CRC-bound geometry correctly meant CENTER.
local PAO_TARGET_ARROW_CENTER_TOLERANCE = 0.12
local PAO_TARGET_ARROW_AMBIGUITY_Y = 18
-- Small units in normal melee framing can legitimately place their nameplate
-- below the upper 40% of the viewport. Reserve BELOW for the much stronger
-- underfoot/behind-camera geometry so ordinary combat keeps using the smooth
-- horizontal magnetic-facing servo.
local PAO_TARGET_ARROW_BELOW_THRESHOLD = 0.62
local PAO_NAMEPLATES_ENABLED_BY_ARROW = false
local PAO_FRIEND_NAMEPLATES_ENABLED_BY_ARROW = false
local PAO_NAMEPLATE_API_REQUESTED = false
local PAO_HIDDEN_NAMEPLATES = {}

local function PAO_Mod(value, divisor)
    return value - (math.floor(value / divisor) * divisor)
end

local function PAO_Scalar(value)
    local valueType = type(value)
    if valueType == "string" then
        if string.len(value) > 256 then
            return string.sub(value, 1, 256)
        end
        return value
    end
    if valueType == "number" or valueType == "boolean" then
        return value
    end
    return nil
end

local function PAO_Text(value)
    if type(value) ~= "string" then
        return nil
    end
    if string.len(value) > 2048 then
        return string.sub(value, 1, 2048)
    end
    return value
end

local function PAO_ClientTimeMs()
    if type(GetTime) == "function" then
        return math.floor(GetTime() * 1000)
    end
    return 0
end

local function PAO_Epoch()
    if type(time) == "function" then
        return time()
    end
    return 1
end

local function PAO_NewDatabase(previousUiBackup)
    local epoch = PAO_Epoch()
    return {
        schema_version = PAO_SCHEMA_VERSION,
        target_profile = "tbc_243_lab",
        adapter = PAO_ADAPTER,
        event_format = PAO_EVENT_FORMAT,
        session_id = "tbc243-session-" .. tostring(epoch) .. "-" .. tostring(PAO_ClientTimeMs()),
        champion_id = "unbound-client-observer",
        synthetic = false,
        max_events = PAO_MAX_EVENTS,
        dropped_events = 0,
        api_capabilities = {
            combat_log_event = true,
            target_state = type(UnitGUID) == "function" and type(UnitHealth) == "function",
            loot_window = type(GetNumLootItems) == "function" and type(GetLootSlotInfo) == "function",
            world_location = type(GetZoneText) == "function",
            map_coordinates = type(GetPlayerMapPosition) == "function" and type(SetMapToCurrentZone) == "function",
            -- TBC 2.4.3 normally does not expose GetPlayerFacing(). Keep the
            -- capability explicit so a capture can never confuse its absence
            -- with an exact body-yaw measurement.
            player_facing_api = type(GetPlayerFacing) == "function",
            quest_dialog = type(GetTitleText) == "function" and type(GetQuestText) == "function",
            quest_log = type(GetNumQuestLogEntries) == "function" and type(GetQuestLogTitle) == "function",
            self_spellbook = type(GetNumSpellTabs) == "function" and type(GetSpellName) == "function",
            action_bar_registry = type(GetActionInfo) == "function" and type(GetBindingKey) == "function",
            focus_unit = type(UnitExists) == "function" and type(UnitGUID) == "function",
            mouseover_unit = type(UnitExists) == "function" and type(UnitGUID) == "function",
        },
        events = {},
        operator_ui_backup = previousUiBackup,
    }
end

local function PAO_FocusPayload()
    local payload = { focus_exists = UnitExists("focus") and true or false }
    if not payload.focus_exists then
        return payload
    end
    if type(UnitGUID) == "function" then
        payload.focus_guid = PAO_Scalar(UnitGUID("focus"))
    end
    payload.focus_name = PAO_Scalar(UnitName("focus"))
    payload.focus_kind = UnitIsPlayer("focus") and "player" or "npc"
    local health = UnitHealth("focus")
    local healthMax = UnitHealthMax("focus")
    if health and healthMax and healthMax > 0 then
        payload.focus_health_pct = math.floor((health * 10000) / healthMax) / 100
        payload.focus_health_current = PAO_Scalar(health)
        payload.focus_health_max = PAO_Scalar(healthMax)
    end
    payload.focus_hostile = type(UnitCanAttack) == "function" and UnitCanAttack("player", "focus") and true or false
    if type(UnitIsDeadOrGhost) == "function" then
        payload.focus_dead = UnitIsDeadOrGhost("focus") and true or false
    end
    if type(UnitCastingInfo) == "function" then
        local castName, castRank, castDisplayName, castIcon, castStartMs, castEndMs = UnitCastingInfo("focus")
        payload.focus_casting = castName and true or false
        if castName then
            payload.focus_cast_name = PAO_Scalar(castName)
            payload.focus_cast_rank = PAO_Scalar(castRank)
            payload.focus_cast_display_name = PAO_Scalar(castDisplayName)
            payload.focus_cast_icon = PAO_Scalar(castIcon)
            payload.focus_cast_start_ms = PAO_Scalar(castStartMs)
            payload.focus_cast_end_ms = PAO_Scalar(castEndMs)
        end
    end
    return payload
end

local function PAO_Append(kind, payload)
    if not PAO_INITIALIZED then
        return
    end
    local events = PerfectAssassinObserverDB.events
    if table.getn(events) >= PAO_MAX_EVENTS then
        table.remove(events, 1)
        PerfectAssassinObserverDB.dropped_events = PerfectAssassinObserverDB.dropped_events + 1
    end
    table.insert(events, {
        seq = PerfectAssassinObserverDB.dropped_events + table.getn(events) + 1,
        kind = kind,
        game_time_ms = PAO_ClientTimeMs(),
        captured_epoch = PAO_Epoch(),
        payload = payload,
    })
end

local function PAO_TargetPayload()
    local payload = { target_exists = UnitExists("target") and true or false }
    if not payload.target_exists then
        return payload
    end
    if type(UnitGUID) == "function" then
        payload.target_guid = PAO_Scalar(UnitGUID("target"))
    end
    payload.target_name = PAO_Scalar(UnitName("target"))
    payload.target_kind = UnitIsPlayer("target") and "player" or "npc"
    local health = UnitHealth("target")
    local healthMax = UnitHealthMax("target")
    if health and healthMax and healthMax > 0 then
        payload.target_health_pct = math.floor((health * 10000) / healthMax) / 100
    end
    if type(UnitIsDeadOrGhost) == "function" then
        payload.target_dead = UnitIsDeadOrGhost("target") and true or false
    end
    return payload
end

-- Mouseover is the only additional public unit token that lets the operator
-- inspect a nearby NPC/player without selecting it.  It is an identity/state
-- witness only: TBC 2.4.3 does not expose a verified world position for this
-- token, so no coordinate or distance is published here.
local function PAO_MouseoverPayload()
    local payload = { mouseover_exists = UnitExists("mouseover") and true or false }
    if not payload.mouseover_exists then
        return payload
    end
    if type(UnitGUID) == "function" then
        payload.mouseover_guid = PAO_Scalar(UnitGUID("mouseover"))
    end
    payload.mouseover_name = PAO_Scalar(UnitName("mouseover"))
    payload.mouseover_kind = UnitIsPlayer("mouseover") and "player" or "npc"
    local health = UnitHealth("mouseover")
    local healthMax = UnitHealthMax("mouseover")
    if health and healthMax and healthMax > 0 then
        payload.mouseover_health_pct = math.floor((health * 10000) / healthMax) / 100
        payload.mouseover_health_current = PAO_Scalar(health)
        payload.mouseover_health_max = PAO_Scalar(healthMax)
    end
    if type(UnitCanAttack) == "function" then
        payload.mouseover_hostile = UnitCanAttack("player", "mouseover") and true or false
    end
    if type(UnitIsDeadOrGhost) == "function" then
        payload.mouseover_dead = UnitIsDeadOrGhost("mouseover") and true or false
    end
    return payload
end

local function PAO_PlayerSnapshot()
    local payload = {
        player_level = UnitLevel("player"),
        player_dead = UnitIsDeadOrGhost("player") and true or false,
    }
    if type(UnitXP) == "function" then
        payload.player_xp = UnitXP("player")
    end
    if type(GetZoneText) == "function" then
        payload.world_zone = PAO_Scalar(GetZoneText())
    end
    if type(GetSubZoneText) == "function" then
        payload.world_subzone = PAO_Scalar(GetSubZoneText())
    end
    payload.target = PAO_TargetPayload()
    PAO_Append("player_snapshot", payload)
end

local function PAO_MapPositionPayload(refreshContext)
    local playerGhost = type(UnitIsGhost) == "function" and UnitIsGhost("player") and true or false
    local playerDeadOrGhost = (
        type(UnitIsDeadOrGhost) == "function" and UnitIsDeadOrGhost("player") and true or false
    ) or playerGhost
    local payload = {
        available = false,
        reason = "api_unavailable",
        coordinate_space = "normalized_current_zone_map",
        player_dead_or_ghost = playerDeadOrGhost,
        player_ghost = playerGhost,
    }
    if type(GetPlayerMapPosition) ~= "function" or type(SetMapToCurrentZone) ~= "function" then
        return payload
    end
    if WorldMapFrame and type(WorldMapFrame.IsShown) == "function" and WorldMapFrame:IsShown() then
        PAO_MAP_CONTEXT_READY = false
        payload.reason = "world_map_visible"
        return payload
    end
    if refreshContext then
        PAO_MAP_CONTEXT_READY = pcall(SetMapToCurrentZone) and true or false
    end
    if not PAO_MAP_CONTEXT_READY then
        payload.reason = "map_context_unavailable"
        return payload
    end
    if type(GetCurrentMapContinent) == "function" then
        payload.map_continent_index = PAO_Scalar(GetCurrentMapContinent())
    end
    if type(GetCurrentMapZone) == "function" then
        payload.map_zone_index = PAO_Scalar(GetCurrentMapZone())
    end
    if type(GetMapInfo) == "function" then
        payload.map_info = PAO_Scalar(GetMapInfo())
    end
    payload.world_zone = type(GetZoneText) == "function" and PAO_Scalar(GetZoneText()) or nil
    payload.world_subzone = type(GetSubZoneText) == "function" and PAO_Scalar(GetSubZoneText()) or nil
    local x, y = GetPlayerMapPosition("player")
    if type(x) ~= "number" or type(y) ~= "number" then
        payload.reason = "position_unavailable"
        return payload
    end
    if x < 0 or x > 1 or y < 0 or y > 1 then
        payload.reason = "position_unavailable"
        return payload
    end
    if x == 0 and y == 0 then
        payload.reason = "position_unavailable"
        return payload
    end
    payload.available = true
    payload.reason = "position_observed"
    payload.x = x
    payload.y = y
    if type(GetPlayerFacing) == "function" then
        local facing = GetPlayerFacing()
        if type(facing) == "number" and facing >= 0 and facing < (2 * math.pi) then
            payload.facing_rad = facing
        end
    end
    return payload
end

local function PAO_Xor16(left, right)
    local result = 0
    local place = 1
    local index
    for index = 1, 16 do
        local leftBit = PAO_Mod(left, 2)
        local rightBit = PAO_Mod(right, 2)
        if leftBit ~= rightBit then
            result = result + place
        end
        left = math.floor(left / 2)
        right = math.floor(right / 2)
        place = place * 2
    end
    return result
end

local function PAO_Crc16Ccitt(bytes)
    local crc = 65535
    local byteIndex
    for byteIndex = 1, table.getn(bytes) do
        crc = PAO_Xor16(crc, bytes[byteIndex] * 256)
        local bitIndex
        for bitIndex = 1, 8 do
            local high = crc >= 32768
            crc = PAO_Mod(crc * 2, 65536)
            if high then
                crc = PAO_Xor16(crc, 4129)
            end
        end
    end
    return crc
end

local function PAO_ClampByte(value)
    value = math.floor(value or 0)
    if value < 0 then return 0 end
    if value > 255 then return 255 end
    return value
end

local function PAO_ClampUInt16(value)
    value = math.floor(value or 0)
    if value < 0 then return 0 end
    if value > 65535 then return 65535 end
    return value
end

local function PAO_ClampUInt24(value)
    value = math.floor(value or 0)
    if value < 0 then return 0 end
    if value > 16777215 then return 16777215 end
    return value
end

local function PAO_PercentByte(current, maximum)
    if type(current) ~= "number" or type(maximum) ~= "number" or maximum <= 0 then
        return 0
    end
    return PAO_ClampByte(math.floor(((current * 255) / maximum) + 0.5))
end

local function PAO_TargetIdentityCrc16()
    if not UnitExists("target") then return 0 end
    local guid = type(UnitGUID) == "function" and UnitGUID("target") or ""
    local name = UnitName("target") or ""
    local text = tostring(guid or "") .. string.char(31) .. tostring(name or "")
    if string.len(text) > 512 then text = string.sub(text, 1, 512) end
    local bytes = {}
    local index
    for index = 1, string.len(text) do
        table.insert(bytes, string.byte(text, index))
    end
    local crc = PAO_Crc16Ccitt(bytes)
    if crc == 0 then return 1 end
    return crc
end

local function PAO_FindSpellTexture(expectedName)
    if type(GetNumSpellTabs) ~= "function" or type(GetSpellTabInfo) ~= "function" then
        return nil
    end
    local tab
    for tab = 1, GetNumSpellTabs() do
        local _, _, offset, count = GetSpellTabInfo(tab)
        local index
        for index = 1, count do
            local spellIndex = offset + index
            local name = GetSpellName(spellIndex, BOOKTYPE_SPELL or "spell")
            if name == expectedName then
                return GetSpellTexture(spellIndex, BOOKTYPE_SPELL or "spell")
            end
        end
    end
    return nil
end

local function PAO_FindSpellIndex(expectedName)
    if
        type(GetNumSpellTabs) ~= "function" or
        type(GetSpellTabInfo) ~= "function" or
        type(GetSpellName) ~= "function"
    then
        return nil
    end
    local tab
    for tab = 1, GetNumSpellTabs() do
        local _, _, offset, count = GetSpellTabInfo(tab)
        local index
        for index = 1, count do
            local spellIndex = offset + index
            local name = GetSpellName(spellIndex, BOOKTYPE_SPELL or "spell")
            if name == expectedName then return spellIndex end
        end
    end
    return nil
end

local function PAO_ActionMatchesSpell(slot, expectedName)
    if type(GetActionInfo) ~= "function" or type(GetActionTexture) ~= "function" then
        return false
    end
    local actionType = GetActionInfo(slot)
    if actionType ~= "spell" then return false end
    local expectedTexture = PAO_FindSpellTexture(expectedName)
    local actionTexture = GetActionTexture(slot)
    return expectedTexture and actionTexture and expectedTexture == actionTexture and true or false
end

local function PAO_CombatActionSlotState()
    if
        PAO_ActionMatchesSpell(2, "Sinister Strike") and
        PAO_ActionMatchesSpell(3, "Eviscerate")
    then
        return "profile"
    end
    if
        PAO_ActionMatchesSpell(2, "Eviscerate") and
        PAO_ActionMatchesSpell(3, "Sinister Strike")
    then
        return "inverse"
    end
    if
        type(GetActionInfo) == "function" and
        GetActionInfo(2) == nil and
        PAO_ActionMatchesSpell(3, "Sinister Strike")
    then
        return "legacy_3_only"
    end
    return "unknown"
end

local function PAO_TransitionCombatActionSlots(expectedBefore, expectedAfter)
    local before = PAO_CombatActionSlotState()
    if before ~= expectedBefore then return false, "combat slots changed before exact move" end
    if
        type(ClearCursor) ~= "function" or
        type(PickupAction) ~= "function" or
        type(PlaceAction) ~= "function"
    then
        return false, "action placement API unavailable"
    end
    ClearCursor()
    if expectedBefore == "inverse" and expectedAfter == "profile" then
        PickupAction(2)
        PlaceAction(3)
        PlaceAction(2)
    elseif expectedBefore == "profile" and expectedAfter == "inverse" then
        PickupAction(2)
        PlaceAction(3)
        PlaceAction(2)
    elseif expectedBefore == "legacy_3_only" and expectedAfter == "profile" then
        if type(PickupSpell) ~= "function" then return false, "spell pickup API unavailable" end
        local eviscerateIndex = PAO_FindSpellIndex("Eviscerate")
        if type(eviscerateIndex) ~= "number" then return false, "Eviscerate is absent from the spellbook" end
        PickupAction(3)
        PlaceAction(2)
        PickupSpell(eviscerateIndex, BOOKTYPE_SPELL or "spell")
        PlaceAction(3)
    elseif expectedBefore == "profile" and expectedAfter == "legacy_3_only" then
        PickupAction(3)
        ClearCursor()
        PickupAction(2)
        PlaceAction(3)
    else
        return false, "unsupported combat slot transition"
    end
    ClearCursor()
    if PAO_CombatActionSlotState() ~= expectedAfter then
        return false, "combat slot move verification failed"
    end
    return true, nil
end

local function PAO_ActionState(slot, exactBinding)
    if not exactBinding then
        return { usable = false, current = false, range_known = false, in_range = false, cooldown_ready = false, cooldown_remaining_ms = 0 }
    end
    local usable = false
    if type(IsUsableAction) == "function" then
        local actionUsable = IsUsableAction(slot)
        usable = actionUsable == 1 and true or false
    end
    local current = type(IsCurrentAction) == "function" and IsCurrentAction(slot) == 1 and true or false
    local rangeKnown = false
    local inRange = false
    if type(IsActionInRange) == "function" then
        local range = IsActionInRange(slot)
        if range ~= nil then
            rangeKnown = true
            inRange = range == 1 and true or false
        end
    end
    local cooldownRemainingMs = 0
    local cooldownReady = false
    if type(GetActionCooldown) == "function" and type(GetTime) == "function" then
        local start, duration, enabled = GetActionCooldown(slot)
        if type(start) == "number" and type(duration) == "number" and enabled == 1 then
            cooldownRemainingMs = math.max(0, math.floor((((start + duration) - GetTime()) * 1000) + 0.5))
            cooldownReady = cooldownRemainingMs == 0
        end
    end
    return {
        usable = usable,
        current = current,
        range_known = rangeKnown,
        in_range = inRange,
        cooldown_ready = cooldownReady,
        cooldown_remaining_ms = cooldownRemainingMs,
    }
end

local function PAO_CombatHudPayload(targetGuidance, acquisitionGuidance)
    local targetExists = UnitExists("target") and true or false
    local playerDead = type(UnitIsDeadOrGhost) == "function" and UnitIsDeadOrGhost("player") and true or false
    local targetDead = targetExists and type(UnitIsDeadOrGhost) == "function" and UnitIsDeadOrGhost("target") and true or false
    local attackExact = type(IsAttackAction) == "function" and IsAttackAction(1) == 1 and true or false
    local sinisterExact = PAO_ActionMatchesSpell(2, "Sinister Strike")
    local eviscerateExact = PAO_ActionMatchesSpell(3, "Eviscerate")
    local attack = PAO_ActionState(1, attackExact)
    local sinister = PAO_ActionState(2, sinisterExact)
    local eviscerate = PAO_ActionState(3, eviscerateExact)
    local targetLevel = targetExists and UnitLevel("target") or 0
    if type(targetLevel) ~= "number" or targetLevel < 1 then targetLevel = 255 end
    local targetReaction = targetExists and type(UnitReaction) == "function" and UnitReaction("player", "target") or 0
    if type(targetReaction) ~= "number" or targetReaction < 1 or targetReaction > 8 then targetReaction = 1 end
    local comboPoints = type(GetComboPoints) == "function" and GetComboPoints("player", "target") or 0
    local targetHealthCurrent = targetExists and PAO_ClampUInt24(UnitHealth("target") or 0) or 0
    local targetHealthMax = targetExists and PAO_ClampUInt24(UnitHealthMax("target") or 0) or 0
    local targetIdentity = targetExists and PAO_TargetIdentityCrc16() or 0
    if
        targetExists and not targetDead and
        type(targetGuidance) == "table" and
        type(targetGuidance.interact_x) == "number" and
        type(targetGuidance.interact_y) == "number"
    then
        PAO_LAST_TARGET_INTERACT_CRC16 = targetIdentity
        PAO_LAST_TARGET_INTERACT_X = PAO_ClampByte(math.floor((targetGuidance.interact_x * 255) + 0.5))
        PAO_LAST_TARGET_INTERACT_Y = PAO_ClampByte(math.floor((targetGuidance.interact_y * 255) + 0.5))
    end
    local playerAttackPower = 0
    if type(UnitAttackPower) == "function" then
        local base, positive, negative = UnitAttackPower("player")
        playerAttackPower = PAO_ClampUInt16((base or 0) + (positive or 0) + (negative or 0))
    end
    local targetBearingCode = 0
    if targetExists and type(targetGuidance) == "table" then
        if targetGuidance.state == "AMBIGUOUS" then
            targetBearingCode = 1
        elseif targetGuidance.state == "CENTER" then
            targetBearingCode = 4
        elseif targetGuidance.state == "LEFT" then
            targetBearingCode = (targetGuidance.offset or 0) < -0.20 and 2 or 3
        elseif targetGuidance.state == "RIGHT" then
            targetBearingCode = (targetGuidance.offset or 0) > 0.20 and 6 or 5
        elseif targetGuidance.state == "BELOW" then
            targetBearingCode = 7
        end
    end
    if not targetExists and type(acquisitionGuidance) == "table" then
        if acquisitionGuidance.state == "AMBIGUOUS" then
            targetBearingCode = 1
        elseif acquisitionGuidance.state == "CENTER" then
            targetBearingCode = 4
        elseif acquisitionGuidance.state == "LEFT" then
            targetBearingCode = (acquisitionGuidance.offset or 0) < -0.20 and 2 or 3
        elseif acquisitionGuidance.state == "RIGHT" then
            targetBearingCode = (acquisitionGuidance.offset or 0) > 0.20 and 6 or 5
        end
    end
    return {
        player_alive = not playerDead,
        in_combat = (type(UnitAffectingCombat) == "function" and UnitAffectingCombat("player") and true or false) or PAO_COMBAT_STATE,
        target_exists = targetExists,
        target_hostile = targetExists and type(UnitCanAttack) == "function" and UnitCanAttack("player", "target") and true or false,
        target_dead = targetDead,
        target_player = targetExists and UnitIsPlayer("target") and true or false,
        attack_exact = attackExact,
        sinister_exact = sinisterExact,
        eviscerate_exact = eviscerateExact,
        player_health = PAO_PercentByte(UnitHealth("player"), UnitHealthMax("player")),
        player_energy = PAO_ClampByte(UnitMana("player") or 0),
        target_health = targetExists and PAO_PercentByte(UnitHealth("target"), UnitHealthMax("target")) or 0,
        target_health_current = targetHealthCurrent,
        target_health_max = targetHealthMax,
        player_attack_power = playerAttackPower,
        combo_points = PAO_ClampByte(comboPoints),
        player_level = PAO_ClampByte(UnitLevel("player") or 0),
        target_level = targetExists and PAO_ClampByte(targetLevel) or 0,
        target_reaction = targetExists and PAO_ClampByte(targetReaction) or 0,
        attack = attack,
        sinister = sinister,
        eviscerate = eviscerate,
        target_identity_crc16 = targetIdentity,
        target_bearing_code = targetBearingCode,
        target_frame_x = (
            targetExists and type(targetGuidance) == "table"
        ) and targetGuidance.x or nil,
        target_frame_y = (
            targetExists and type(targetGuidance) == "table"
        ) and targetGuidance.y or nil,
        loot_event_sequence = PAO_LOOT_EVENT_SEQUENCE,
        target_interact_x = (
            targetDead and targetIdentity == PAO_LAST_TARGET_INTERACT_CRC16
        ) and PAO_LAST_TARGET_INTERACT_X or 0,
        target_interact_y = (
            targetDead and targetIdentity == PAO_LAST_TARGET_INTERACT_CRC16
        ) and PAO_LAST_TARGET_INTERACT_Y or 0,
        acquisition_candidates = (
            not targetExists and type(acquisitionGuidance) == "table"
        ) and PAO_ClampByte(acquisitionGuidance.candidates or 0) or 0,
        acquisition_x = (
            not targetExists and type(acquisitionGuidance) == "table" and
            type(acquisitionGuidance.x) == "number"
        ) and PAO_ClampByte(math.floor((acquisitionGuidance.x * 255) + 0.5)) or 0,
        acquisition_y = (
            not targetExists and type(acquisitionGuidance) == "table" and
            type(acquisitionGuidance.y) == "number"
        ) and PAO_ClampByte(math.floor((acquisitionGuidance.y * 255) + 0.5)) or 0,
    }
end

local function PAO_CombatHudBytes(payload)
    local flags = 0
    if payload.player_alive then flags = flags + 1 end
    if payload.in_combat then flags = flags + 2 end
    if payload.target_exists then flags = flags + 4 end
    if payload.target_hostile then flags = flags + 8 end
    if payload.target_dead then flags = flags + 16 end
    if payload.target_player then flags = flags + 32 end
    if payload.attack_exact then flags = flags + 64 end
    if payload.sinister_exact then flags = flags + 128 end
    local actionFlags = 0
    if payload.attack.usable then actionFlags = actionFlags + 1 end
    if payload.attack.current then actionFlags = actionFlags + 2 end
    if payload.attack.range_known then actionFlags = actionFlags + 4 end
    if payload.attack.in_range then actionFlags = actionFlags + 8 end
    if payload.sinister.usable then actionFlags = actionFlags + 16 end
    if payload.sinister.range_known then actionFlags = actionFlags + 32 end
    if payload.sinister.in_range then actionFlags = actionFlags + 64 end
    if payload.sinister.cooldown_ready then actionFlags = actionFlags + 128 end
    local eviscerateFlags = 0
    if payload.eviscerate_exact then eviscerateFlags = eviscerateFlags + 1 end
    if payload.eviscerate.usable then eviscerateFlags = eviscerateFlags + 2 end
    if payload.eviscerate.range_known then eviscerateFlags = eviscerateFlags + 4 end
    if payload.eviscerate.in_range then eviscerateFlags = eviscerateFlags + 8 end
    if payload.eviscerate.cooldown_ready then eviscerateFlags = eviscerateFlags + 16 end
    eviscerateFlags = eviscerateFlags + (payload.target_bearing_code * 32)
    PAO_COMBAT_HUD_SEQUENCE = PAO_Mod(PAO_COMBAT_HUD_SEQUENCE + 1, 256)
    local cooldownTicks = PAO_ClampByte(math.floor((payload.sinister.cooldown_remaining_ms / 50) + 0.5))
    local identity = payload.target_identity_crc16
    local targetHealthByte1 = math.floor(payload.target_health_current / 65536)
    local targetHealthByte2 = PAO_Mod(math.floor(payload.target_health_current / 256), 256)
    local targetHealthByte3 = PAO_Mod(payload.target_health_current, 256)
    if payload.target_dead and payload.target_interact_x > 0 and payload.target_interact_y > 0 then
        targetHealthByte1 = payload.target_interact_x
        targetHealthByte2 = payload.target_interact_y
        targetHealthByte3 = 165
    elseif not payload.target_exists and payload.acquisition_candidates > 0 then
        targetHealthByte1 = payload.acquisition_candidates
        targetHealthByte2 = payload.acquisition_x
        targetHealthByte3 = payload.acquisition_y
    end
    local bytes = {
        PAO_COMBAT_HUD_MAGIC, PAO_COMBAT_HUD_PROTOCOL_VERSION, flags, PAO_COMBAT_HUD_SEQUENCE,
        payload.player_health, payload.player_energy, payload.target_health,
        payload.combo_points + (payload.loot_event_sequence * 8),
        payload.player_level, payload.target_level, payload.target_reaction, actionFlags,
        cooldownTicks, eviscerateFlags, math.floor(identity / 256), PAO_Mod(identity, 256),
        targetHealthByte1, targetHealthByte2, targetHealthByte3,
        math.floor(payload.target_health_max / 65536),
        PAO_Mod(math.floor(payload.target_health_max / 256), 256),
        PAO_Mod(payload.target_health_max, 256),
        math.floor(payload.player_attack_power / 256),
        PAO_Mod(payload.player_attack_power, 256),
        type(payload.target_frame_x) == "number" and
            PAO_ClampByte(math.floor((payload.target_frame_x * 255) + 0.5)) or 0,
        type(payload.target_frame_y) == "number" and
            PAO_ClampByte(math.floor((payload.target_frame_y * 255) + 0.5)) or 0,
    }
    local crc = PAO_Crc16Ccitt(bytes)
    table.insert(bytes, math.floor(crc / 256))
    table.insert(bytes, PAO_Mod(crc, 256))
    return bytes
end

local function PAO_HudBytes(payload)
    local flags = 0
    if payload.available then flags = flags + 1 end
    if PAO_MAP_CONTEXT_READY then flags = flags + 2 end
    if payload.reason == "world_map_visible" then flags = flags + 4 end
    if type(payload.facing_rad) == "number" then flags = flags + 8 end
    if payload.player_dead_or_ghost then flags = flags + 16 end
    if payload.player_ghost then flags = flags + 32 end
    local xQuantized = payload.available and math.floor((payload.x * 65535) + 0.5) or 0
    local yQuantized = payload.available and math.floor((payload.y * 65535) + 0.5) or 0
    local facingQuantized = type(payload.facing_rad) == "number" and math.floor((payload.facing_rad * 65535 / (2 * math.pi)) + 0.5) or 0
    PAO_HUD_SEQUENCE = PAO_Mod(PAO_HUD_SEQUENCE + 1, 256)
    local bytes = {
        PAO_HUD_MAGIC,
        PAO_HUD_PROTOCOL_VERSION,
        flags,
        PAO_HUD_SEQUENCE,
        math.floor(xQuantized / 256), PAO_Mod(xQuantized, 256),
        math.floor(yQuantized / 256), PAO_Mod(yQuantized, 256),
        PAO_ClampByte(payload.map_continent_index),
        PAO_ClampByte(payload.map_zone_index),
        math.floor(facingQuantized / 256), PAO_Mod(facingQuantized, 256),
    }
    local crc = PAO_Crc16Ccitt(bytes)
    table.insert(bytes, math.floor(crc / 256))
    table.insert(bytes, PAO_Mod(crc, 256))
    return bytes
end

local PAO_Hud = CreateFrame("Frame", "PerfectAssassinObserverHUD", UIParent)
PAO_Hud:SetWidth(PAO_HUD_WIDTH)
PAO_Hud:SetHeight(PAO_HUD_HEIGHT)
PAO_Hud:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PAO_HUD_DEFAULT_X, PAO_HUD_DEFAULT_Y)
PAO_Hud:SetFrameStrata("HIGH")
PAO_Hud:EnableMouse(false)
PAO_Hud:SetMovable(true)
PAO_Hud:SetClampedToScreen(true)
PAO_Hud:SetUserPlaced(true)
PAO_Hud:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 10, insets = { left = 2, right = 2, top = 2, bottom = 2 } })
PAO_Hud:SetBackdropColor(0, 0, 0, 0.92)
PAO_Hud:SetBackdropBorderColor(0.2, 0.8, 1, 1)

local PAO_HudTitle = PAO_Hud:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
PAO_HudTitle:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 8, -7)
PAO_HudTitle:SetText("PA TELEMETRY v2")
local PAO_HudText = PAO_Hud:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
PAO_HudText:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 112, -31)
PAO_HudText:SetJustifyH("LEFT")
PAO_HudText:SetText("POSITION UNAVAILABLE")
PAO_HudText:Hide()

local PAO_CombatHudText = PAO_Hud:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
PAO_CombatHudText:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 112, -78)
PAO_CombatHudText:SetJustifyH("LEFT")
PAO_CombatHudText:SetText("COMBAT UNAVAILABLE")
PAO_CombatHudText:Hide()

local PAO_TargetArrow = CreateFrame("Frame", "PerfectAssassinTargetArrow", UIParent)
PAO_TargetArrow:SetWidth(180)
PAO_TargetArrow:SetHeight(34)
PAO_TargetArrow:SetPoint("TOP", UIParent, "TOP", 0, -118)
PAO_TargetArrow:SetFrameStrata("HIGH")
PAO_TargetArrow:EnableMouse(false)
local PAO_TargetArrowText = PAO_TargetArrow:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
PAO_TargetArrowText:SetPoint("CENTER", PAO_TargetArrow, "CENTER", 0, 0)
PAO_TargetArrowText:SetText("")
PAO_TargetArrow:Hide()

local PAO_HudMover = CreateFrame("Frame", nil, PAO_Hud)
PAO_HudMover:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 0, 0)
PAO_HudMover:SetPoint("TOPRIGHT", PAO_Hud, "TOPRIGHT", 0, 0)
PAO_HudMover:SetHeight(22)
PAO_HudMover:EnableMouse(false)
PAO_HudMover:RegisterForDrag("LeftButton")

local function PAO_Clamp(value, minimum, maximum)
    if value < minimum then return minimum end
    if value > maximum then return maximum end
    return value
end

local function PAO_ResetHudPosition()
    PAO_Hud:SetUserPlaced(false)
    PAO_Hud:ClearAllPoints()
    PAO_Hud:SetPoint("TOPLEFT", UIParent, "TOPLEFT", PAO_HUD_DEFAULT_X, PAO_HUD_DEFAULT_Y)
    PAO_Hud:SetUserPlaced(true)
end

local function PAO_ClampHudToCaptureRegion()
    local parentLeft = UIParent:GetLeft()
    local parentTop = UIParent:GetTop()
    local parentWidth = UIParent:GetWidth()
    local parentHeight = UIParent:GetHeight()
    local hudLeft = PAO_Hud:GetLeft()
    local hudTop = PAO_Hud:GetTop()
    if
        type(parentLeft) ~= "number" or type(parentTop) ~= "number" or
        type(parentWidth) ~= "number" or type(parentHeight) ~= "number" or
        type(hudLeft) ~= "number" or type(hudTop) ~= "number" or
        parentWidth <= 0 or parentHeight <= 0
    then
        PAO_ResetHudPosition()
        return
    end

    local minimumX = PAO_HUD_CAPTURE_MARGIN
    local maximumX = (parentWidth * PAO_HUD_CAPTURE_WIDTH_FRACTION) - PAO_HUD_CAPTURE_FOOTPRINT_RIGHT - PAO_HUD_CAPTURE_MARGIN
    local minimumY = -((parentHeight * PAO_HUD_CAPTURE_HEIGHT_FRACTION) - PAO_HUD_CAPTURE_FOOTPRINT_BOTTOM - PAO_HUD_CAPTURE_MARGIN)
    local maximumY = -PAO_HUD_CAPTURE_MARGIN
    if maximumX < minimumX or minimumY > maximumY then
        PAO_ResetHudPosition()
        return
    end

    local x = PAO_Clamp(hudLeft - parentLeft, minimumX, maximumX)
    local y = PAO_Clamp(hudTop - parentTop, minimumY, maximumY)
    PAO_Hud:ClearAllPoints()
    PAO_Hud:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x, y)
end

local function PAO_ClampHudIfParentChanged()
    local parentWidth = UIParent:GetWidth()
    local parentHeight = UIParent:GetHeight()
    if type(parentWidth) ~= "number" or type(parentHeight) ~= "number" then return end
    if parentWidth <= 0 or parentHeight <= 0 then return end
    if parentWidth == PAO_HUD_PARENT_WIDTH and parentHeight == PAO_HUD_PARENT_HEIGHT then return end
    PAO_HUD_PARENT_WIDTH = parentWidth
    PAO_HUD_PARENT_HEIGHT = parentHeight
    if not PAO_HUD_DRAGGING then
        PAO_ClampHudToCaptureRegion()
    end
end

local function PAO_ControlKeyDown()
    return type(IsControlKeyDown) == "function" and IsControlKeyDown() and true or false
end

local function PAO_UpdateHudMoverMouse()
    local shouldEnable = PAO_HUD_DRAGGING or PAO_ControlKeyDown()
    if shouldEnable ~= PAO_HUD_MOVER_MOUSE_ENABLED then
        PAO_HudMover:EnableMouse(shouldEnable)
        PAO_HUD_MOVER_MOUSE_ENABLED = shouldEnable
    end
end

local function PAO_HudDragStart()
    if not PAO_ControlKeyDown() then return end
    PAO_HUD_DRAGGING = true
    PAO_Hud:StartMoving()
end

local function PAO_HudDragStop()
    PAO_Hud:StopMovingOrSizing()
    PAO_HUD_DRAGGING = false
    PAO_ClampHudToCaptureRegion()
    PAO_UpdateHudMoverMouse()
end

PAO_HudMover:SetScript("OnDragStart", PAO_HudDragStart)
PAO_HudMover:SetScript("OnDragStop", PAO_HudDragStop)

SLASH_PERFECTASSASSINOBSERVERHUD1 = "/paohud"
SlashCmdList["PERFECTASSASSINOBSERVERHUD"] = function(message)
    if string.lower(message or "") == "reset" then
        PAO_ResetHudPosition()
        PAO_ClampHudToCaptureRegion()
    end
end

local function PAO_HudMarker(red, green, blue, x, y)
    local texture = PAO_Hud:CreateTexture(nil, "OVERLAY")
    texture:SetWidth(6)
    texture:SetHeight(6)
    texture:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", x, -y)
    texture:SetTexture(red, green, blue, 1)
    return texture
end

local PAO_HudMarkers = {
    PAO_HudMarker(0, 1, 1, 6, 32),
    PAO_HudMarker(1, 0, 1, 98, 32),
    PAO_HudMarker(1, 1, 0, 6, 66),
    PAO_HudMarker(0, 1, 0, 98, 66),
}

local function PAO_SetHudMarkersVisible(visible)
    local index
    for index = 1, table.getn(PAO_HudMarkers) do
        if visible then
            PAO_HudMarkers[index]:Show()
        else
            PAO_HudMarkers[index]:Hide()
        end
    end
end

local PAO_HudCells = {}
local row
for row = 0, 6 do
    local column
    for column = 0, 15 do
        local texture = PAO_Hud:CreateTexture(nil, "ARTWORK")
        texture:SetWidth(4)
        texture:SetHeight(4)
        texture:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 14 + (column * 5), -(34 + (row * 5)))
        texture:SetTexture(0, 0, 0, 1)
        PAO_HudCells[(row * 16) + column + 1] = texture
    end
end

local PAO_CombatHudCells = {}
for row = 0, 13 do
    local column
    for column = 0, 15 do
        local texture = PAO_Hud:CreateTexture(nil, "ARTWORK")
        texture:SetWidth(2)
        texture:SetHeight(2)
        texture:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 112 + (column * 3), -(34 + (row * 3)))
        texture:SetTexture(0, 0, 0, 1)
        PAO_CombatHudCells[(row * 16) + column + 1] = texture
    end
end

-- Separate AFK strip v1, above both existing CRC HUDs. Read-only state;
-- the external exact-LAB input gateway owns the one-shot Space action.
local PAO_AfkHudCells = {}
for row = 0, 47 do
    local texture = PAO_Hud:CreateTexture(nil, "ARTWORK")
    texture:SetWidth(2)
    texture:SetHeight(2)
    texture:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 14 + row * 3, -22)
    texture:SetTexture(0, 0, 0, 1)
    PAO_AfkHudCells[row + 1] = texture
end

local function PAO_AfkHudBytes()
    local flags = 0
    if type(UnitIsAFK) == "function" then
        flags = flags + 1
        if UnitIsAFK("player") then flags = flags + 2 end
    end
    if PAO_INITIALIZED and PAO_MAP_CONTEXT_READY and UnitName("player") == "Predator" then
        flags = flags + 4
    end
    local blocked = type(GetCurrentKeyBoardFocus) ~= "function"
    if not blocked then blocked = GetCurrentKeyBoardFocus() ~= nil end
    if GameMenuFrame and GameMenuFrame:IsShown() then blocked = true end
    local index
    for index = 1, 4 do
        local popup = getglobal("StaticPopup" .. index)
        if popup and popup:IsShown() then blocked = true end
    end
    if blocked then flags = flags + 8 end
    if UnitIsDeadOrGhost("player") or UnitAffectingCombat("player") then flags = flags + 16 end
    local bytes = {175, 1, PAO_HUD_SEQUENCE, flags}
    local crc = PAO_Crc16Ccitt(bytes)
    table.insert(bytes, math.floor(crc / 256))
    table.insert(bytes, PAO_Mod(crc, 256))
    return bytes
end

-- Independent API-label packet: 144 bytes in 96 RGB-nibble cells. Existing
-- coordinate/combat/AFK cells and marker locations are unchanged.
local PAO_LocationCells = {}
for row = 0, 95 do
    local texture = PAO_Hud:CreateTexture(nil, "ARTWORK")
    texture:SetWidth(2)
    texture:SetHeight(2)
    texture:SetPoint("TOPLEFT", PAO_Hud, "TOPLEFT", 14 + PAO_Mod(row, 48) * 3, -(26 + math.floor(row / 48) * 3))
    texture:SetTexture(0, 0, 0, 1)
    PAO_LocationCells[row + 1] = texture
end

-- Preserve the actual return kind, including nil vs false; neither confirms
-- the actor's physical floor. A missing or failing API is not an outdoor flag.
local function PAO_EnvironmentReturnKind(api)
    if type(api) ~= "function" then return 0 end
    local ok, value = pcall(api)
    if not ok then return 6 end
    if value == nil then return 1 end
    if value == false then return 2 end
    if value == true then return 3 end
    if value == 0 then return 4 end
    if value == 1 then return 5 end
    return 7
end

local function PAO_UpdateLocationHud()
    local region = type(GetZoneText) == "function" and GetZoneText() or nil
    local subzone = type(GetSubZoneText) == "function" and GetSubZoneText() or nil
    local flags = 0
    if type(region) == "string" then flags = flags + 1 else region = "" end
    if type(subzone) == "string" then flags = flags + 2 else subzone = "" end
    if PAO_INITIALIZED and PAO_MAP_CONTEXT_READY and UnitName("player") == "Predator" then flags = flags + 4 end
    if string.len(region) > 64 then flags = flags + 8; region = "" end
    if string.len(subzone) > 64 then flags = flags + 16; subzone = "" end
    local session = PerfectAssassinObserverDB and PerfectAssassinObserverDB.session_id or ""
    local sessionBytes = {}
    local index
    for index = 1, string.len(session) do sessionBytes[index] = string.byte(session, index) end
    local tag = PAO_Crc16Ccitt(sessionBytes)
    local millis = PAO_Mod(PAO_ClientTimeMs(), 4294967296)
    local environment = PAO_EnvironmentReturnKind(IsIndoors) + 8 * PAO_EnvironmentReturnKind(IsOutdoors)
    local capabilities = 0
    if type(UnitPosition) == "function" then capabilities = capabilities + 1 end
    if type(GetPlayerFacing) == "function" then capabilities = capabilities + 2 end
    local bytes = {215, 2, PAO_HUD_SEQUENCE, flags, math.floor(tag / 256), PAO_Mod(tag, 256),
        string.len(region), string.len(subzone), math.floor(millis / 16777216),
        PAO_Mod(math.floor(millis / 65536), 256), PAO_Mod(math.floor(millis / 256), 256),
        PAO_Mod(millis, 256), environment, capabilities}
    for index = 1, 64 do bytes[14 + index] = string.byte(region, index) or 0 end
    for index = 1, 64 do bytes[78 + index] = string.byte(subzone, index) or 0 end
    local crc = PAO_Crc16Ccitt(bytes)
    bytes[143] = math.floor(crc / 256)
    bytes[144] = PAO_Mod(crc, 256)
    local nibbles = {}
    for index = 1, 144 do
        nibbles[index * 2 - 1] = math.floor(bytes[index] / 16)
        nibbles[index * 2] = PAO_Mod(bytes[index], 16)
    end
    for index = 1, 96 do
        PAO_LocationCells[index]:SetTexture((8 + nibbles[index * 3 - 2] * 16) / 255,
            (8 + nibbles[index * 3 - 1] * 16) / 255, (8 + nibbles[index * 3] * 16) / 255, 1)
    end
end

local function PAO_RenderHudBytes(cells, bytes)
    local bitIndex = 1
    local byteIndex
    for byteIndex = 1, table.getn(bytes) do
        local divisor = 128
        local index
        for index = 1, 8 do
            local bit = math.floor(bytes[byteIndex] / divisor)
            bytes[byteIndex] = PAO_Mod(bytes[byteIndex], divisor)
            if bit == 1 then
                cells[bitIndex]:SetTexture(1, 1, 1, 1)
            else
                cells[bitIndex]:SetTexture(0, 0, 0, 1)
            end
            bitIndex = bitIndex + 1
            divisor = divisor / 2
        end
    end
end

local function PAO_FrameHasExactText(frame, expected)
    if not frame or type(frame.GetRegions) ~= "function" then return false end
    local regions = { frame:GetRegions() }
    local index
    for index = 1, table.getn(regions) do
        local region = regions[index]
        if
            region and type(region.GetObjectType) == "function" and
            region:GetObjectType() == "FontString" and
            type(region.GetText) == "function" and
            region:GetText() == expected
        then
            return true
        end
    end
    return false
end

local function PAO_NameplateHealthBar(frame)
    if not frame or type(frame.GetChildren) ~= "function" then return nil end
    local children = { frame:GetChildren() }
    local index
    for index = 1, table.getn(children) do
        local child = children[index]
        if
            child and type(child.GetObjectType) == "function" and
            child:GetObjectType() == "StatusBar" and
            type(child.GetStatusBarColor) == "function"
        then
            return child
        end
    end
    return nil
end

local function PAO_NameplateTargetState(frame, targetName)
    local matches = PAO_FrameHasExactText(frame, targetName)
    if not frame or type(frame.GetChildren) ~= "function" then return false end
    local children = { frame:GetChildren() }
    local index
    for index = 1, table.getn(children) do
        if PAO_FrameHasExactText(children[index], targetName) then matches = true end
    end
    if not matches then return false, false end

    -- TBC fades the native nameplate parent, not the StatusBar child.  Mature
    -- legacy nameplate addons preserve the same parent-alpha signal while
    -- replacing the bar visuals.  Reading healthBar:GetAlpha() here makes all
    -- same-name units look selected because that child normally stays opaque.
    local selected = false
    if type(frame.GetAlpha) == "function" then
        local alpha = frame:GetAlpha()
        selected = type(alpha) == "number" and alpha >= 0.99
    end
    return true, selected
end

local function PAO_IsNativeNameplate(frame)
    if not frame or type(frame.GetRegions) ~= "function" then return false end
    local regions = { frame:GetRegions() }
    local index
    for index = 1, table.getn(regions) do
        local region = regions[index]
        if
            region and type(region.GetObjectType) == "function" and
            region:GetObjectType() == "Texture" and
            type(region.GetTexture) == "function"
        then
            local texture = region:GetTexture()
            if
                type(texture) == "string" and
                string.find(string.lower(texture), "nameplate-border", 1, true)
            then
                return true
            end
        end
    end
    local children = { frame:GetChildren() }
    local healthBar = children[1]
    if
        healthBar and type(healthBar.GetObjectType) == "function" and
        healthBar:GetObjectType() == "StatusBar"
    then
        for index = 1, table.getn(regions) do
            local region = regions[index]
            if
                region and type(region.GetObjectType) == "function" and
                region:GetObjectType() == "FontString"
            then
                return true
            end
        end
    end
    return false
end

-- Follow the registry pattern used by established vanilla/TBC nameplate
-- addons: discover newly-created WorldFrame children once, then inspect only
-- cached native plate parents at the 20 Hz telemetry cadence.  This remains
-- compatible with visual replacement addons because the original parent and
-- its semantic StatusBar continue to own the unit data.
local PAO_NAMEPLATE_REGISTRY = {}
local PAO_NAMEPLATE_WORLD_CHILD_COUNT = 0

local function PAO_RefreshNameplateRegistry()
    if not WorldFrame or type(WorldFrame.GetChildren) ~= "function" then
        return PAO_NAMEPLATE_REGISTRY
    end
    local worldChildren = { WorldFrame:GetChildren() }
    local childCount = math.min(
        table.getn(worldChildren),
        PAO_TARGET_ARROW_SCAN_LIMIT
    )
    if childCount < PAO_NAMEPLATE_WORLD_CHILD_COUNT then
        PAO_NAMEPLATE_REGISTRY = {}
        PAO_NAMEPLATE_WORLD_CHILD_COUNT = 0
    end
    if childCount > PAO_NAMEPLATE_WORLD_CHILD_COUNT then
        local index
        for index = PAO_NAMEPLATE_WORLD_CHILD_COUNT + 1, childCount do
            local frame = worldChildren[index]
            if PAO_IsNativeNameplate(frame) then
                PAO_NAMEPLATE_REGISTRY[frame] = true
            end
        end
        PAO_NAMEPLATE_WORLD_CHILD_COUNT = childCount
    end
    return PAO_NAMEPLATE_REGISTRY
end

local function PAO_HideNativeNameplate(frame)
    if not frame or type(frame.SetAlpha) ~= "function" then return end
    if not PAO_HIDDEN_NAMEPLATES[frame] then
        PAO_HIDDEN_NAMEPLATES[frame] = frame:GetAlpha()
    end
    frame:SetAlpha(0)
end

local function PAO_RestoreNativeNameplateVisuals()
    local frame, alpha
    for frame, alpha in pairs(PAO_HIDDEN_NAMEPLATES) do
        if frame and type(frame.SetAlpha) == "function" then frame:SetAlpha(alpha or 1) end
    end
    PAO_HIDDEN_NAMEPLATES = {}
end

local function PAO_HideAllNativeNameplates()
    if not WorldFrame or type(WorldFrame.GetChildren) ~= "function" then return end
    local worldChildren = { WorldFrame:GetChildren() }
    local count = math.min(table.getn(worldChildren), PAO_TARGET_ARROW_SCAN_LIMIT)
    local index
    for index = 1, count do
        local frame = worldChildren[index]
        if PAO_IsNativeNameplate(frame) then PAO_HideNativeNameplate(frame) end
    end
end

local function PAO_NormalizedFrameCenter(frame)
    if
        not frame or type(frame.GetCenter) ~= "function" or
        type(frame.GetEffectiveScale) ~= "function" or
        not UIParent or type(UIParent.GetWidth) ~= "function" or
        type(UIParent.GetHeight) ~= "function" or
        type(UIParent.GetEffectiveScale) ~= "function"
    then
        return nil, nil
    end
    local centerX, centerY = frame:GetCenter()
    local frameScale = frame:GetEffectiveScale()
    local parentWidth = UIParent:GetWidth()
    local parentHeight = UIParent:GetHeight()
    local parentScale = UIParent:GetEffectiveScale()
    if
        type(centerX) ~= "number" or type(centerY) ~= "number" or
        type(frameScale) ~= "number" or frameScale <= 0 or
        type(parentWidth) ~= "number" or parentWidth <= 0 or
        type(parentHeight) ~= "number" or parentHeight <= 0 or
        type(parentScale) ~= "number" or parentScale <= 0
    then
        return nil, nil
    end
    -- WorldFrame children and UIParent may have different effective scales.
    -- GetCenter() is frame-scaled, so first convert both points and root size
    -- into the same scale-independent coordinate system.
    return (centerX * frameScale) / (parentWidth * parentScale),
        1 - ((centerY * frameScale) / (parentHeight * parentScale))
end

local function PAO_TargetScreenGuidance()
    if
        not PAO_TARGET_ARROW_ENABLED or
        type(UnitExists) ~= "function" or not UnitExists("target") or
        not WorldFrame or type(WorldFrame.GetChildren) ~= "function"
    then
        return { state = "LOST", offset = nil, candidates = 0 }
    end
    local targetName = UnitName("target")
    if
        type(targetName) ~= "string" or targetName == ""
    then
        return { state = "LOST", offset = nil, candidates = 0 }
    end
    local candidates = {}
    local frame
    for frame in pairs(PAO_RefreshNameplateRegistry()) do
        local matches, selected = PAO_NameplateTargetState(frame, targetName)
        if frame and frame:IsShown() and matches then
            local healthBar = PAO_NameplateHealthBar(frame)
            local centerX, centerY = PAO_NormalizedFrameCenter(healthBar)
            local frameWidth, frameHeight = nil, nil
            if healthBar then
                frameWidth = healthBar:GetWidth()
                frameHeight = healthBar:GetHeight()
            end
            if
                type(centerX) == "number" and type(centerY) == "number" and
                type(frameWidth) == "number" and type(frameHeight) == "number" and
                centerX >= 0 and centerX <= 1 and centerY >= 0 and centerY <= 1 and
                frameWidth >= 20 and frameWidth <= 300 and
                frameHeight >= 4 and frameHeight <= 180
            then
                table.insert(candidates, { x = centerX, y = centerY, selected = selected })
            end
        end
        -- Keep the client's native plate visible.  It is legitimate world UI
        -- and remains valuable evidence when validating the visual servo.
    end
    if table.getn(candidates) == 0 then
        return { state = "LOST", offset = nil, candidates = 0 }
    end
    local selectedCandidates = {}
    local index
    for index = 1, table.getn(candidates) do
        if candidates[index].selected then table.insert(selectedCandidates, candidates[index]) end
    end
    local chosen = nil
    if table.getn(selectedCandidates) == 1 then
        chosen = selectedCandidates[1]
    elseif table.getn(candidates) == 1 then
        chosen = candidates[1]
    else
        return { state = "AMBIGUOUS", offset = nil, candidates = table.getn(candidates) }
    end
    local offset = PAO_Clamp((chosen.x - 0.5) / 0.5, -1, 1)
    local topOriginY = chosen.y
    local state = "CENTER"
    if offset < -PAO_TARGET_ARROW_CENTER_TOLERANCE then state = "LEFT" end
    if offset > PAO_TARGET_ARROW_CENTER_TOLERANCE then state = "RIGHT" end
    -- Horizontal centering is not sufficient when the selected nameplate is
    -- underneath/behind the player or the camera pitch is too low.
    if topOriginY > PAO_TARGET_ARROW_BELOW_THRESHOLD then state = "BELOW" end
    return {
        state = state,
        offset = offset,
        x = chosen.x,
        y = chosen.y,
        candidates = table.getn(candidates),
        interact_x = PAO_Clamp(chosen.x, 0.05, 0.95),
        -- Nameplates sit above the model.  Move the visible hardware click
        -- downward into the unit/corpse silhouette, using top-origin client
        -- coordinates expected by Win32.
        interact_y = PAO_Clamp(chosen.y + 0.11, 0.12, 0.82),
    }
end

local function PAO_VisibleAttackableGuidance()
    if not WorldFrame or type(WorldFrame.GetChildren) ~= "function" then
        return { state = "LOST", offset = nil, candidates = 0 }
    end
    local candidates = {}
    local frame
    for frame in pairs(PAO_RefreshNameplateRegistry()) do
        if frame and frame:IsShown() and PAO_IsNativeNameplate(frame) then
            local healthBar = PAO_NameplateHealthBar(frame)
            if healthBar and type(healthBar.GetStatusBarColor) == "function" then
                local red, green, blue = healthBar:GetStatusBarColor()
                local attackableColor =
                    type(red) == "number" and type(green) == "number" and type(blue) == "number" and
                    ((red >= 0.70 and green <= 0.35) or (red >= 0.70 and green >= 0.55 and blue <= 0.35))
                if attackableColor then
                    local centerX, centerY = PAO_NormalizedFrameCenter(healthBar)
                    local frameWidth = healthBar:GetWidth()
                    local frameHeight = healthBar:GetHeight()
                    if
                        type(centerX) == "number" and type(centerY) == "number" and
                        type(frameWidth) == "number" and type(frameHeight) == "number" and
                        centerX >= 0 and centerX <= 1 and centerY >= 0 and centerY <= 1 and
                        frameWidth >= 20 and frameWidth <= 300 and
                        frameHeight >= 4 and frameHeight <= 180
                    then
                        local offset = PAO_Clamp((centerX - 0.5) / 0.5, -1, 1)
                        table.insert(candidates, {
                            offset = offset,
                            distance = math.abs(offset),
                            x = centerX,
                            y = centerY,
                        })
                    end
                end
            end
        end
    end
    if table.getn(candidates) == 0 then
        return { state = "LOST", offset = nil, candidates = 0 }
    end
    table.sort(candidates, function(left, right)
        if left.distance ~= right.distance then
            return left.distance < right.distance
        end
        if left.x ~= right.x then return left.x < right.x end
        return left.y < right.y
    end)
    local offset = candidates[1].offset
    local state = "CENTER"
    if offset < -PAO_TARGET_ARROW_CENTER_TOLERANCE then state = "LEFT" end
    if offset > PAO_TARGET_ARROW_CENTER_TOLERANCE then state = "RIGHT" end
    return {
        state = state,
        offset = offset,
        candidates = table.getn(candidates),
        x = PAO_Clamp(candidates[1].x, 0.01, 0.99),
        y = PAO_Clamp(candidates[1].y, 0.01, 0.99),
    }
end

local function PAO_EnsureEnemyNameplates()
    if not PAO_TARGET_ARROW_ENABLED then return end
    if PAO_NAMEPLATE_API_REQUESTED then return end
    PAO_NAMEPLATE_API_REQUESTED = true
    if type(GetCVar) == "function" and type(SetCVar) == "function" then
        local currentDistance = GetCVar("nameplateMaxDistance")
        if currentDistance ~= nil then pcall(SetCVar, "nameplateMaxDistance", "41") end
    end
    local wereEnabled = NAMEPLATES_ON and true or false
    local friendWereEnabled = FRIENDNAMEPLATES_ON and true or false
    if type(ShowNameplates) == "function" then
        ShowNameplates()
        PAO_NAMEPLATES_ENABLED_BY_ARROW = not wereEnabled
        NAMEPLATES_ON = 1
    elseif type(SetCVar) == "function" then
        SetCVar("nameplateShowEnemies", "1")
        PAO_NAMEPLATES_ENABLED_BY_ARROW = not wereEnabled
    end
    -- Neutral/yellow attackable NPCs are represented by the friendly plate
    -- channel on some 2.4.3 clients.  Enable both channels, then match only the
    -- exact selected target name and selected health-bar opacity.
    if type(ShowFriendNameplates) == "function" then
        ShowFriendNameplates()
        PAO_FRIEND_NAMEPLATES_ENABLED_BY_ARROW = not friendWereEnabled
        FRIENDNAMEPLATES_ON = 1
    end
end

local function PAO_RestoreEnemyNameplates()
    if
        not PAO_NAMEPLATES_ENABLED_BY_ARROW and
        not PAO_FRIEND_NAMEPLATES_ENABLED_BY_ARROW and
        not next(PAO_HIDDEN_NAMEPLATES)
    then
        return
    end
    if PAO_NAMEPLATES_ENABLED_BY_ARROW then
        if type(HideNameplates) == "function" then
            HideNameplates()
        elseif type(SetCVar) == "function" then
            SetCVar("nameplateShowEnemies", "0")
        end
    end
    PAO_NAMEPLATES_ENABLED_BY_ARROW = false
    if PAO_FRIEND_NAMEPLATES_ENABLED_BY_ARROW then
        if type(HideFriendNameplates) == "function" then HideFriendNameplates() end
        PAO_FRIEND_NAMEPLATES_ENABLED_BY_ARROW = false
    end
    PAO_RestoreNativeNameplateVisuals()
    PAO_NAMEPLATE_API_REQUESTED = false
end

local function PAO_UpdateTargetArrow(guidance)
    if not PAO_TARGET_ARROW_ENABLED or not UnitExists("target") then
        PAO_TargetArrow:Hide()
        return
    end
    if guidance.state == "LEFT" then
        PAO_TargetArrowText:SetText("<<<  TARGET")
        PAO_TargetArrowText:SetTextColor(1, 0.82, 0, 1)
    elseif guidance.state == "RIGHT" then
        PAO_TargetArrowText:SetText("TARGET  >>>")
        PAO_TargetArrowText:SetTextColor(1, 0.82, 0, 1)
    elseif guidance.state == "CENTER" then
        PAO_TargetArrowText:SetText("TARGET  ^")
        PAO_TargetArrowText:SetTextColor(0.2, 1, 0.3, 1)
    elseif guidance.state == "BELOW" then
        PAO_TargetArrowText:SetText("TARGET BEHIND / CAMERA LOW  >>>")
        PAO_TargetArrowText:SetTextColor(1, 0.35, 0, 1)
    elseif guidance.state == "AMBIGUOUS" then
        PAO_TargetArrowText:SetText("TARGET  ?")
        PAO_TargetArrowText:SetTextColor(1, 0.45, 0, 1)
    else
        PAO_TargetArrowText:SetText("TARGET BEYOND PLATE RANGE")
        PAO_TargetArrowText:SetTextColor(0.7, 0.7, 0.7, 1)
    end
    PAO_TargetArrow:Show()
end

SLASH_PERFECTASSASSINOBSERVERARROW1 = "/paoarrow"
SlashCmdList["PERFECTASSASSINOBSERVERARROW"] = function(message)
    local command = string.lower(message or "")
    if command == "off" then
        PAO_TARGET_ARROW_ENABLED = false
        PAO_TargetArrow:Hide()
        PAO_RestoreEnemyNameplates()
    elseif command == "on" then
        PAO_TARGET_ARROW_ENABLED = true
        PAO_NAMEPLATE_API_REQUESTED = false
        PAO_EnsureEnemyNameplates()
    else
        if DEFAULT_CHAT_FRAME then
            DEFAULT_CHAT_FRAME:AddMessage("Perfect Assassin: use /paoarrow on or /paoarrow off")
        end
    end
end

local function PAO_UpdateHud()
    -- Another visible addon may change the shared map context between frames.
    -- Re-anchor to the player's current zone before every live measurement.
    PAO_EnsureEnemyNameplates()
    local payload = PAO_MapPositionPayload(true)
    local bytes = PAO_HudBytes(payload)
    PAO_RenderHudBytes(PAO_HudCells, bytes)
    PAO_RenderHudBytes(PAO_AfkHudCells, PAO_AfkHudBytes())
    PAO_UpdateLocationHud()
    local targetGuidance = PAO_TargetScreenGuidance()
    local acquisitionGuidance = PAO_VisibleAttackableGuidance()
    local combatPayload = PAO_CombatHudPayload(targetGuidance, acquisitionGuidance)
    PAO_RenderHudBytes(PAO_CombatHudCells, PAO_CombatHudBytes(combatPayload))
    PAO_UpdateTargetArrow(targetGuidance)
    if payload.available then
        PAO_HudText:SetText(string.format("X %.5f  Y %.5f\nMAP %s:%s  SEQ %d", payload.x, payload.y, tostring(payload.map_continent_index or 0), tostring(payload.map_zone_index or 0), PAO_HUD_SEQUENCE))
    else
        PAO_HudText:SetText("POSITION UNAVAILABLE\n" .. string.upper(payload.reason or "unknown"))
    end
    local targetState = combatPayload.target_exists and string.format("TGT %d%% L%s", math.floor((combatPayload.target_health * 100 / 255) + 0.5), tostring(combatPayload.target_level)) or "NO TARGET"
    PAO_CombatHudText:SetText(string.format("HP %d%%  E %d  CP %d\n%s  %s  %s", math.floor((combatPayload.player_health * 100 / 255) + 0.5), combatPayload.player_energy, combatPayload.combo_points, targetState, combatPayload.in_combat and "COMBAT" or "READY", targetGuidance.state))
end

local function PAO_SafeUpdateHud()
    local ok, errorMessage = pcall(PAO_UpdateHud)
    if ok then
        PAO_HUD_LAST_ERROR = nil
        PAO_SetHudMarkersVisible(true)
        return true
    end
    PAO_HUD_LAST_ERROR = tostring(errorMessage or "unknown")
    PAO_SetHudMarkersVisible(false)
    PAO_HudText:SetText("HUD ERROR\n" .. string.sub(PAO_HUD_LAST_ERROR, 1, 80))
    return false
end

local function PAO_HudOnUpdate(frame, elapsed)
    PAO_ClampHudIfParentChanged()
    PAO_UpdateHudMoverMouse()
    local delta = elapsed
    if type(delta) ~= "number" and type(arg1) == "number" then
        delta = arg1
    end
    if type(delta) ~= "number" then
        return
    end
    PAO_HUD_ACCUMULATOR = PAO_HUD_ACCUMULATOR + delta
    -- Movement/facing is a visual servo.  A 200 ms sample period produced
    -- visible stop-turn-go pulses and let strafing outrun target centering.
    -- 20 Hz is still bounded and inexpensive for the small nameplate scan,
    -- while giving the external controller a fresh frame for every correction.
    if PAO_HUD_ACCUMULATOR < 0.05 then return end
    PAO_HUD_ACCUMULATOR = 0
    PAO_SafeUpdateHud()
end

PAO_Hud:SetScript("OnUpdate", PAO_HudOnUpdate)

local function PAO_CombatLogPayload()
    -- The legacy payload is deliberately archived without retail-era decoding.
    -- Named scalar slots avoid losing nil holes when WoW saves the table.
    return {
        a01 = PAO_Scalar(arg1), a02 = PAO_Scalar(arg2),
        a03 = PAO_Scalar(arg3), a04 = PAO_Scalar(arg4),
        a05 = PAO_Scalar(arg5), a06 = PAO_Scalar(arg6),
        a07 = PAO_Scalar(arg7), a08 = PAO_Scalar(arg8),
        a09 = PAO_Scalar(arg9), a10 = PAO_Scalar(arg10),
        a11 = PAO_Scalar(arg11), a12 = PAO_Scalar(arg12),
        a13 = PAO_Scalar(arg13), a14 = PAO_Scalar(arg14),
        a15 = PAO_Scalar(arg15), a16 = PAO_Scalar(arg16),
        a17 = PAO_Scalar(arg17), a18 = PAO_Scalar(arg18),
        a19 = PAO_Scalar(arg19), a20 = PAO_Scalar(arg20),
    }
end

local function PAO_LootPayload()
    local items = {}
    if type(GetNumLootItems) ~= "function" or type(GetLootSlotInfo) ~= "function" then
        return { items = items }
    end
    local count = GetNumLootItems()
    local slot
    for slot = 1, count do
        local icon, name, quantity, quality, locked = GetLootSlotInfo(slot)
        local link = nil
        if type(GetLootSlotLink) == "function" then
            link = GetLootSlotLink(slot)
        end
        table.insert(items, {
            slot = slot,
            name = PAO_Scalar(name),
            link = PAO_Scalar(link),
            quantity = PAO_Scalar(quantity),
            quality = PAO_Scalar(quality),
            locked = locked and true or false,
        })
    end
    return { items = items }
end

local function PAO_NpcIdentity(payload)
    if type(UnitExists) == "function" and UnitExists("npc") then
        if type(UnitGUID) == "function" then
            payload.npc_guid = PAO_Scalar(UnitGUID("npc"))
        end
        payload.npc_name = PAO_Scalar(UnitName("npc"))
    end
end

local function PAO_QuestTriples(values, count)
    local quests = {}
    local index
    for index = 1, count do
        local base = ((index - 1) * 3) + 1
        table.insert(quests, {
            title = PAO_Scalar(values[base]),
            level = PAO_Scalar(values[base + 1]),
            trivial = values[base + 2] and true or false,
        })
    end
    return quests
end

local function PAO_QuestNpcPayload(source)
    local payload = { source = source, available_quests = {}, active_quests = {} }
    PAO_NpcIdentity(payload)
    if source == "gossip" then
        if type(GetGossipText) == "function" then
            payload.dialog_text = PAO_Text(GetGossipText())
        end
        if type(GetNumGossipAvailableQuests) == "function" and type(GetGossipAvailableQuests) == "function" then
            payload.available_quests = PAO_QuestTriples(
                { GetGossipAvailableQuests() }, GetNumGossipAvailableQuests()
            )
        end
        if type(GetNumGossipActiveQuests) == "function" and type(GetGossipActiveQuests) == "function" then
            payload.active_quests = PAO_QuestTriples(
                { GetGossipActiveQuests() }, GetNumGossipActiveQuests()
            )
        end
    else
        if type(GetGreetingText) == "function" then
            payload.dialog_text = PAO_Text(GetGreetingText())
        end
        local index
        if type(GetNumAvailableQuests) == "function" and type(GetAvailableTitle) == "function" then
            for index = 1, GetNumAvailableQuests() do
                table.insert(payload.available_quests, {
                    title = PAO_Scalar(GetAvailableTitle(index)),
                    trivial = type(IsAvailableQuestTrivial) == "function" and IsAvailableQuestTrivial(index) and true or false,
                })
            end
        end
        if type(GetNumActiveQuests) == "function" and type(GetActiveTitle) == "function" then
            for index = 1, GetNumActiveQuests() do
                table.insert(payload.active_quests, {
                    title = PAO_Scalar(GetActiveTitle(index)),
                    trivial = type(IsActiveQuestTrivial) == "function" and IsActiveQuestTrivial(index) and true or false,
                })
            end
        end
    end
    return payload
end

local function PAO_QuestDetailPayload()
    local payload = {
        quest_title = type(GetTitleText) == "function" and PAO_Scalar(GetTitleText()) or nil,
        quest_text = type(GetQuestText) == "function" and PAO_Text(GetQuestText()) or nil,
        quest_objective_text = type(GetObjectiveText) == "function" and PAO_Text(GetObjectiveText()) or nil,
        quest_suggested_group = type(GetSuggestedGroupNum) == "function" and PAO_Scalar(GetSuggestedGroupNum()) or nil,
    }
    PAO_NpcIdentity(payload)
    return payload
end

local function PAO_QuestLogPayload()
    local payload = { quests = {} }
    if type(GetNumQuestLogEntries) ~= "function" or type(GetQuestLogTitle) ~= "function" then
        return payload
    end
    local numEntries = GetNumQuestLogEntries()
    local index
    for index = 1, numEntries do
        local title, level, questTag, suggestedGroup, isHeader, isCollapsed, isComplete, isDaily = GetQuestLogTitle(index)
        if title and not isHeader then
            local quest = {
                title = PAO_Scalar(title),
                level = PAO_Scalar(level),
                tag = PAO_Scalar(questTag),
                suggested_group = PAO_Scalar(suggestedGroup),
                complete = isComplete and true or false,
                daily = isDaily and true or false,
                objectives = {},
            }
            if type(GetNumQuestLeaderBoards) == "function" and type(GetQuestLogLeaderBoard) == "function" then
                local objectiveIndex
                for objectiveIndex = 1, GetNumQuestLeaderBoards(index) do
                    local text, objectiveType, finished = GetQuestLogLeaderBoard(objectiveIndex, index)
                    table.insert(quest.objectives, {
                        text = PAO_Text(text),
                        objective_type = PAO_Scalar(objectiveType),
                        finished = finished and true or false,
                    })
                end
            end
            table.insert(payload.quests, quest)
        end
    end
    return payload
end

local function PAO_SpellbookPayload()
    local payload = { spells = {} }
    if type(GetNumSpellTabs) ~= "function" or type(GetSpellTabInfo) ~= "function" or type(GetSpellName) ~= "function" then
        return payload
    end
    local tabIndex
    for tabIndex = 1, GetNumSpellTabs() do
        local tabName, texture, offset, numSpells = GetSpellTabInfo(tabIndex)
        if offset and numSpells then
            local spellIndex
            for spellIndex = offset + 1, offset + numSpells do
                local spellName, spellRank = GetSpellName(spellIndex, BOOKTYPE_SPELL or "spell")
                if spellName then
                    table.insert(payload.spells, {
                        book_index = spellIndex,
                        tab = PAO_Scalar(tabName),
                        name = PAO_Scalar(spellName),
                        rank = PAO_Scalar(spellRank),
                        passive = type(IsPassiveSpell) == "function" and IsPassiveSpell(spellIndex, BOOKTYPE_SPELL or "spell") and true or false,
                    })
                end
            end
        end
    end
    return payload
end

local function PAO_ActionBarSurface(page, currentPage)
    if page == 1 then return "main_page_1", "ACTIONBUTTON", currentPage == 1 end
    if page == 2 then return "main_page_2", "ACTIONBUTTON", currentPage == 2 end
    if page == 3 then return "right", "MULTIACTIONBAR3BUTTON", true end
    if page == 4 then return "left", "MULTIACTIONBAR4BUTTON", true end
    if page == 5 then return "bottom_right", "MULTIACTIONBAR2BUTTON", true end
    return "bottom_left", "MULTIACTIONBAR1BUTTON", true
end

local function PAO_ActionBarPayload()
    local currentPage = type(GetActionBarPage) == "function" and GetActionBarPage() or 1
    local payload = {
        profile_id = "tbc243_default_24_direct_v1",
        current_page = currentPage,
        total_slots = 72,
        directly_bound_slots = 24,
        slots = {},
    }
    payload.visible_bars = {
        bottom_left = MultiBarBottomLeft and MultiBarBottomLeft:IsShown() and true or false,
        bottom_right = MultiBarBottomRight and MultiBarBottomRight:IsShown() and true or false,
        right = MultiBarRight and MultiBarRight:IsShown() and true or false,
        left = MultiBarLeft and MultiBarLeft:IsShown() and true or false,
    }
    if type(GetActionInfo) ~= "function" then
        return payload
    end
    local slot
    for slot = 1, 72 do
        local page = math.floor((slot - 1) / 12) + 1
        local button = PAO_Mod(slot - 1, 12) + 1
        local surface, bindingPrefix, direct = PAO_ActionBarSurface(page, currentPage)
        local bindingCommand = bindingPrefix .. tostring(button)
        local actionType, actionId, actionSubtype = GetActionInfo(slot)
        local entry = {
            slot = slot,
            page = page,
            button = button,
            surface = surface,
            binding_command = bindingCommand,
            directly_addressable = direct,
            has_action = type(HasAction) == "function" and HasAction(slot) and true or false,
        }
        if type(GetBindingKey) == "function" then
            local key1, key2 = GetBindingKey(bindingCommand)
            entry.binding_key_1 = PAO_Scalar(key1)
            entry.binding_key_2 = PAO_Scalar(key2)
        end
        entry.action_type = PAO_Scalar(actionType)
        entry.action_id = PAO_Scalar(actionId)
        entry.action_subtype = PAO_Scalar(actionSubtype)
        entry.action_text = type(GetActionText) == "function" and PAO_Scalar(GetActionText(slot)) or nil
        entry.texture = type(GetActionTexture) == "function" and PAO_Scalar(GetActionTexture(slot)) or nil
        table.insert(payload.slots, entry)
    end
    return payload
end

local PAO_BINDING_KEYS = { "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=" }

local function PAO_ManagedBindings()
    local bindings = {
        { key = "A", command = "STRAFELEFT" },
        { key = "D", command = "STRAFERIGHT" },
        { key = "TAB", command = "TARGETNEARESTENEMY" },
        { key = "SHIFT-TAB", command = "TARGETPREVIOUSENEMY" },
        { key = "F", command = "FOCUSTARGET" },
        { key = "SHIFT-F", command = "TARGETFOCUS" },
        { key = "Y", command = "TURNORACTION" },
    }
    local index
    for index = 1, 12 do
        table.insert(bindings, { key = PAO_BINDING_KEYS[index], command = "ACTIONBUTTON" .. tostring(index) })
        table.insert(bindings, { key = "SHIFT-" .. PAO_BINDING_KEYS[index], command = "MULTIACTIONBAR1BUTTON" .. tostring(index) })
    end
    return bindings
end

local function PAO_Chat(message)
    if DEFAULT_CHAT_FRAME and type(DEFAULT_CHAT_FRAME.AddMessage) == "function" then
        DEFAULT_CHAT_FRAME:AddMessage("Perfect Assassin: " .. tostring(message))
    end
end

local function PAO_UiConfigurationAllowed()
    return type(InCombatLockdown) ~= "function" or not InCombatLockdown()
end

local function PAO_CaptureUiBackup()
    local toggle1, toggle2, toggle3, toggle4 = nil, nil, nil, nil
    if type(GetActionBarToggles) == "function" then
        toggle1, toggle2, toggle3, toggle4 = GetActionBarToggles()
    end
    local backup = {
        version = "1.0",
        binding_set = type(GetCurrentBindingSet) == "function" and GetCurrentBindingSet() or 1,
        action_bar_toggles = {
            toggle1 and true or false,
            toggle2 and true or false,
            toggle3 and true or false,
            toggle4 and true or false,
        },
        bindings = {},
        combat_slots_previous_state = nil,
    }
    local bindings = PAO_ManagedBindings()
    local index
    for index = 1, table.getn(bindings) do
        local item = bindings[index]
        local previous = type(GetBindingAction) == "function" and GetBindingAction(item.key) or ""
        table.insert(backup.bindings, { key = item.key, command = PAO_Scalar(previous or "") or "" })
    end
    return backup
end

local function PAO_ApplyUiBackup(backup)
    if type(backup) ~= "table" or backup.version ~= "1.0" or type(backup.bindings) ~= "table" then
        return false, "backup invalid"
    end
    if type(SetBinding) ~= "function" or type(SaveBindings) ~= "function" then
        return false, "binding API unavailable"
    end
    if type(backup.combat_slots_previous_state) == "string" then
        local slotState = PAO_CombatActionSlotState()
        if slotState == "profile" then
            local moved, moveDetail = PAO_TransitionCombatActionSlots(
                "profile", backup.combat_slots_previous_state
            )
            if not moved then return false, moveDetail end
        elseif slotState ~= backup.combat_slots_previous_state then
            return false, "combat slots changed before restore"
        end
    end
    local index
    for index = 1, table.getn(backup.bindings) do
        local item = backup.bindings[index]
        if type(item) ~= "table" or type(item.key) ~= "string" or type(item.command) ~= "string" then
            return false, "backup entry invalid"
        end
        SetBinding(item.key)
        if item.command ~= "" then
            SetBinding(item.key, item.command)
        end
    end
    if type(SetActionBarToggles) == "function" and type(backup.action_bar_toggles) == "table" then
        SetActionBarToggles(
            backup.action_bar_toggles[1],
            backup.action_bar_toggles[2],
            backup.action_bar_toggles[3],
            backup.action_bar_toggles[4]
        )
        SHOW_MULTI_ACTIONBAR_1 = backup.action_bar_toggles[1] and 1 or nil
        SHOW_MULTI_ACTIONBAR_2 = backup.action_bar_toggles[2] and 1 or nil
        SHOW_MULTI_ACTIONBAR_3 = backup.action_bar_toggles[3] and 1 or nil
        SHOW_MULTI_ACTIONBAR_4 = backup.action_bar_toggles[4] and 1 or nil
    end
    if type(MultiActionBar_Update) == "function" then MultiActionBar_Update() end
    SaveBindings(backup.binding_set)
    return true, nil
end

local function PAO_ApplyPredatorUiProfile()
    if not PAO_UiConfigurationAllowed() then
        return false, "leave combat before changing bindings"
    end
    if type(SetBinding) ~= "function" or type(GetBindingAction) ~= "function" or type(SaveBindings) ~= "function" or type(SetActionBarToggles) ~= "function" then
        return false, "required TBC UI API unavailable"
    end
    if type(PerfectAssassinObserverDB.operator_ui_backup) ~= "table" then
        PerfectAssassinObserverDB.operator_ui_backup = PAO_CaptureUiBackup()
    end
    local bindings = PAO_ManagedBindings()
    local ok, detail = pcall(function()
        SetActionBarToggles(true, true, true, true)
        SHOW_MULTI_ACTIONBAR_1 = 1
        SHOW_MULTI_ACTIONBAR_2 = 1
        SHOW_MULTI_ACTIONBAR_3 = 1
        SHOW_MULTI_ACTIONBAR_4 = 1
        if type(MultiActionBar_Update) == "function" then MultiActionBar_Update() end
        if
            not MultiBarBottomLeft:IsShown() or
            not MultiBarBottomRight:IsShown() or
            not MultiBarRight:IsShown() or
            not MultiBarLeft:IsShown()
        then
            error("action bar visibility verification failed")
        end
        local index
        for index = 1, table.getn(bindings) do
            SetBinding(bindings[index].key, bindings[index].command)
            if GetBindingAction(bindings[index].key) ~= bindings[index].command then
                error("binding verification failed for " .. bindings[index].key)
            end
        end
        local slotState = PAO_CombatActionSlotState()
        if slotState == "inverse" or slotState == "legacy_3_only" then
            local moved, moveDetail = PAO_TransitionCombatActionSlots(slotState, "profile")
            if not moved then error(moveDetail) end
            PerfectAssassinObserverDB.operator_ui_backup.combat_slots_previous_state = slotState
        elseif slotState ~= "profile" then
            error("combat action slots 2 and 3 are not the exact reviewed pair")
        end
        SaveBindings(PerfectAssassinObserverDB.operator_ui_backup.binding_set)
    end)
    if not ok then
        PAO_ApplyUiBackup(PerfectAssassinObserverDB.operator_ui_backup)
        return false, PAO_Scalar(detail) or "profile apply failed"
    end
    PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())
    return true, nil
end

SLASH_PERFECTASSASSINOBSERVERBARS1 = "/paobars"
SlashCmdList["PERFECTASSASSINOBSERVERBARS"] = function(message)
    local command = string.lower(message or "")
    if command == "apply" then
        local ok, detail = PAO_ApplyPredatorUiProfile()
        if ok then
            PAO_Chat("24 direct action slots, exact Rogue combat slots, A/D strafe, target cycle and focus bindings enabled; /paobars restore reverts them.")
        else
            PAO_Chat("profile refused: " .. tostring(detail))
        end
        return
    end
    if command == "restore" then
        if not PAO_UiConfigurationAllowed() then
            PAO_Chat("leave combat before restoring bindings.")
            return
        end
        local ok, detail = PAO_ApplyUiBackup(PerfectAssassinObserverDB.operator_ui_backup)
        if ok then
            PerfectAssassinObserverDB.operator_ui_backup = nil
            PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())
            PAO_Chat("previous action bars and bindings restored.")
        else
            PAO_Chat("restore refused: " .. tostring(detail))
        end
        return
    end
    if command == "snapshot" then
        PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())
        PAO_Append("focus_snapshot", PAO_FocusPayload())
        PAO_Chat("action bars and focus recorded locally.")
        return
    end
    PAO_Chat("use /paobars apply, /paobars restore, or /paobars snapshot")
end

function PerfectAssassinObserver_OnEvent()
    if event == "VARIABLES_LOADED" then
        local previousUiBackup = nil
        if type(PerfectAssassinObserverDB) == "table" and type(PerfectAssassinObserverDB.operator_ui_backup) == "table" then
            previousUiBackup = PerfectAssassinObserverDB.operator_ui_backup
        end
        PerfectAssassinObserverDB = PAO_NewDatabase(previousUiBackup)
        PAO_INITIALIZED = true
        return
    end
    if event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" then
        if event == "PLAYER_LOGIN" then
            PAO_ClampHudToCaptureRegion()
        end
        PAO_PlayerSnapshot()
        PAO_Append("map_position_snapshot", PAO_MapPositionPayload(true))
        PAO_SafeUpdateHud()
        PAO_Append("spellbook_snapshot", PAO_SpellbookPayload())
        PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())
        PAO_Append("focus_snapshot", PAO_FocusPayload())
        return
    end
    if event == "ZONE_CHANGED" or event == "ZONE_CHANGED_INDOORS" or event == "ZONE_CHANGED_NEW_AREA" then
        PAO_PlayerSnapshot()
        PAO_Append("map_position_snapshot", PAO_MapPositionPayload(true))
        PAO_SafeUpdateHud()
        return
    end
    if event == "PLAYER_TARGET_CHANGED" or (event == "UNIT_HEALTH" and arg1 == "target") then
        PAO_Append("target_snapshot", PAO_TargetPayload())
        return
    end
    if event == "PLAYER_FOCUS_CHANGED" or (event == "UNIT_HEALTH" and arg1 == "focus") then
        PAO_Append("focus_snapshot", PAO_FocusPayload())
        return
    end
    if event == "UPDATE_MOUSEOVER_UNIT" or (event == "UNIT_HEALTH" and arg1 == "mouseover") then
        PAO_Append("mouseover_snapshot", PAO_MouseoverPayload())
        return
    end
    if event == "PLAYER_REGEN_DISABLED" then
        PAO_COMBAT_STATE = true
        PAO_Append("combat_state", { state = "started" })
        return
    end
    if event == "PLAYER_REGEN_ENABLED" then
        PAO_COMBAT_STATE = false
        PAO_Append("combat_state", { state = "ended" })
        return
    end
    if event == "PLAYER_DEAD" or event == "PLAYER_ALIVE" then
        PAO_Append("player_state", { player_dead = UnitIsDeadOrGhost("player") and true or false })
        return
    end
    if event == "PLAYER_XP_UPDATE" then
        PAO_Append("level_progress", { player_level = UnitLevel("player"), player_xp = UnitXP("player") })
        return
    end
    if event == "PLAYER_LEVEL_UP" then
        PAO_Append("level_progress", { player_level = PAO_Scalar(arg1), player_level_reached = PAO_Scalar(arg1) })
        return
    end
    if event == "LOOT_OPENED" then
        PAO_LOOT_EVENT_SEQUENCE = PAO_Mod(PAO_LOOT_EVENT_SEQUENCE + 1, 32)
        PAO_Append("loot_snapshot", PAO_LootPayload())
        return
    end
    if event == "GOSSIP_SHOW" then
        PAO_Append("quest_npc_snapshot", PAO_QuestNpcPayload("gossip"))
        return
    end
    if event == "QUEST_GREETING" then
        PAO_Append("quest_npc_snapshot", PAO_QuestNpcPayload("quest_greeting"))
        return
    end
    if event == "QUEST_DETAIL" then
        PAO_Append("quest_detail", PAO_QuestDetailPayload())
        return
    end
    if event == "QUEST_LOG_UPDATE" then
        PAO_Append("quest_log_snapshot", PAO_QuestLogPayload())
        return
    end
    if event == "SPELLS_CHANGED" or event == "LEARNED_SPELL_IN_TAB" then
        PAO_Append("spellbook_snapshot", PAO_SpellbookPayload())
        return
    end
    if event == "ACTIONBAR_SLOT_CHANGED" or event == "UPDATE_BINDINGS" then
        PAO_Append("action_bar_snapshot", PAO_ActionBarPayload())
        return
    end
    if event == "COMBAT_LOG_EVENT_UNFILTERED" then
        PAO_Append("combat_log_raw", PAO_CombatLogPayload())
        return
    end
end

local PAO_Frame = CreateFrame("Frame", "PerfectAssassinObserverFrame")
PAO_Frame:RegisterEvent("VARIABLES_LOADED")
PAO_Frame:RegisterEvent("PLAYER_LOGIN")
PAO_Frame:RegisterEvent("PLAYER_ENTERING_WORLD")
PAO_Frame:RegisterEvent("ZONE_CHANGED")
PAO_Frame:RegisterEvent("ZONE_CHANGED_INDOORS")
PAO_Frame:RegisterEvent("ZONE_CHANGED_NEW_AREA")
PAO_Frame:RegisterEvent("PLAYER_TARGET_CHANGED")
PAO_Frame:RegisterEvent("PLAYER_FOCUS_CHANGED")
PAO_Frame:RegisterEvent("UPDATE_MOUSEOVER_UNIT")
PAO_Frame:RegisterEvent("UNIT_HEALTH")
PAO_Frame:RegisterEvent("PLAYER_REGEN_DISABLED")
PAO_Frame:RegisterEvent("PLAYER_REGEN_ENABLED")
PAO_Frame:RegisterEvent("PLAYER_DEAD")
PAO_Frame:RegisterEvent("PLAYER_ALIVE")
PAO_Frame:RegisterEvent("PLAYER_XP_UPDATE")
PAO_Frame:RegisterEvent("PLAYER_LEVEL_UP")
PAO_Frame:RegisterEvent("LOOT_OPENED")
PAO_Frame:RegisterEvent("GOSSIP_SHOW")
PAO_Frame:RegisterEvent("QUEST_GREETING")
PAO_Frame:RegisterEvent("QUEST_DETAIL")
PAO_Frame:RegisterEvent("QUEST_LOG_UPDATE")
PAO_Frame:RegisterEvent("SPELLS_CHANGED")
PAO_Frame:RegisterEvent("LEARNED_SPELL_IN_TAB")
PAO_Frame:RegisterEvent("ACTIONBAR_SLOT_CHANGED")
PAO_Frame:RegisterEvent("UPDATE_BINDINGS")
PAO_Frame:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED")
PAO_Frame:SetScript("OnEvent", PerfectAssassinObserver_OnEvent)
