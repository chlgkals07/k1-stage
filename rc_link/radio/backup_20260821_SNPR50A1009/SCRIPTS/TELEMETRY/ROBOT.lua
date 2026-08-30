local GV_INDEX = 0
local ESTOP_GV_INDEX = 1
local FM_INDEX = 0

local ESTOP_INACTIVE = -100
local ESTOP_ACTIVE = 100
local ESTOP_ACTIVATE_TIME = 50
local ESTOP_DEACTIVATE_TIME = 300
local ESTOP_HINT_TIME = 50
local ESTOP_RESULT_TIME = 50
local ESTOP_TRIM_RESCAN_TIME = 100
local BATTERY_HOLD_TIME = 80
local LED_UPDATE_TIME = 50
local LED_TELEMETRY_MAX_AGE_MS = 2000
local LED_OVERRIDE_TIME_MS = 1500
local ESTOP_TRIM_A_NAMES = { "Rud-", "TrimRudLeft", "T1-", "TR1-" }
local ESTOP_TRIM_B_NAMES = { "Ail+", "TrimAilRight", "T4+", "TR4+" }

local FLAG_SML = SMLSIZE or 0
local FLAG_MID = MIDSIZE or 0
local FLAG_DBL = DBLSIZE or 0
local FLAG_RIGHT = RIGHT or 0
local FLAG_BLINK = BLINK or 0
local FLAG_SOLID = SOLID or 0
local SCREEN_W = LCD_W or 128
local SCREEN_H = LCD_H or 64

local modes = {
  { name = "Mimic_squat"  , pwm = 1000, pct = -100 },
  { name = "Mimic_dance1" , pwm = 1020, pct =  -96 },
  { name = "Mimic_dance2" , pwm = 1040, pct =  -92 },
  { name = "Mimic_custom1", pwm = 1060, pct =  -88 },
  { name = "Mimic_custom2", pwm = 1080, pct =  -84 },
  { name = "Mimic_custom3", pwm = 1100, pct =  -80 },
  { name = "Mimic_custom4", pwm = 1120, pct =  -76 },
  { name = "Mimic_custom5", pwm = 1140, pct =  -72 },
  { name = "Mimic_custom6", pwm = 1160, pct =  -68 },
  { name = "Mimic_custom7", pwm = 1180, pct =  -64 },
  { name = "Mimic_custom8", pwm = 1200, pct =  -60 },
  { name = "Mimic_custom9", pwm = 1220, pct =  -56 },
  { name = "Mimic_custom10", pwm = 1240, pct =  -52 },
  { name = "Mimic_custom11", pwm = 1260, pct =  -48 },
  { name = "Mimic_custom12", pwm = 1280, pct =  -44 },
  { name = "Mimic_custom13", pwm = 1300, pct =  -40 },
  { name = "Mimic_custom14", pwm = 1320, pct =  -36 },
  { name = "Mimic_custom15", pwm = 1340, pct =  -32 },
  { name = "Mimic_custom16", pwm = 1360, pct =  -28 },
  { name = "Mimic_custom17", pwm = 1380, pct =  -24 },
}

local function loadModeTable()
  local file = io.open("/RADIO/k1-modes.txt", "r")
  if file == nil then return end

  local content = io.read(file, 4096)
  io.close(file)
  if content == nil or #content == 0 then return end

  local loaded = {}
  for line in string.gmatch(content, "[^\r\n]+") do
    local name, pwmText, pctText = string.match(
      line,
      "^%s*([^#][^,]-)%s*,%s*(%-?%d+)%s*,%s*(%-?%d+)%s*$"
    )
    local pwm = tonumber(pwmText)
    local pct = tonumber(pctText)
    if name ~= nil and #name > 0 and pwm ~= nil and pct ~= nil
       and pwm >= 1000 and pwm <= 2000 and pct >= -100 and pct <= 100 then
      loaded[#loaded + 1] = { name = name, pwm = pwm, pct = pct }
    elseif string.match(line, "^%s*$") == nil
       and string.match(line, "^%s*#") == nil then
      loaded = {}
      break
    end
  end

  if #loaded >= 10 and #loaded <= 50 then
    for index = 1, #loaded do
      loaded[index].pwm = 1000 + (index - 1) * 20
      loaded[index].pct = -100 + (index - 1) * 4
    end
    modes = loaded
  end
end

loadModeTable()

local selected = 1
local cursor = 1
local fieldIds = {}
local batteryCache = {}
local gvValue = nil
local ch11Pct = nil
local ch12Pct = nil
local gvWrite = "INIT"
local estopGvValue = nil
local estopWrite = "INIT"
local estopActive = false
local estopInitialized = false
local estopHoldStart = nil
local estopHoldAction = nil
local estopHoldLatched = false
local estopOverlay = nil
local estopOverlayUntil = 0
local estopTrimAIds = nil
local estopTrimBIds = nil
local estopTrimScanTime = nil
local estopTrimStatus = "--"
local edit = false
local lastRunTime = nil
local exitResetDone = true
local lastStatusLedTime = nil
local lastStatusLedPct = nil
local lastBatteryTelemetryOkTime = nil
local RESET_DELAY = 50

local function clamp(v, minv, maxv)
  if v < minv then return minv end
  if v > maxv then return maxv end
  return v
end

local function nowTicks()
  if getTime ~= nil then
    local value = getTime()
    if type(value) == "number" then
      return value
    end
  end
  return 0
end

local function findFieldId(names)
  for i = 1, #names do
    local ok, field = pcall(getFieldInfo, names[i])
    if ok and field ~= nil and field.id ~= nil then
      return field.id
    end
  end
  return nil
end

local function readSource(key, names)
  local id = fieldIds[key]

  if id == nil then
    id = findFieldId(names)
    fieldIds[key] = id or false
  elseif id == false then
    id = nil
  end

  if id ~= nil then
    local ok, value, current, fresh
    if getSourceValue ~= nil then
      ok, value, current, fresh = pcall(getSourceValue, id)
    else
      ok, value = pcall(getValue, id)
    end
    if ok and value ~= nil then
      return value, current, fresh
    end
  end

  for i = 1, #names do
    local ok, value, current, fresh
    if getSourceValue ~= nil then
      ok, value, current, fresh = pcall(getSourceValue, names[i])
    else
      ok, value = pcall(getValue, names[i])
    end
    if ok and value ~= nil then
      return value, current, fresh
    end
  end

  return nil
end

local function readValue(name)
  return readSource(name, { name, string.lower(name) })
end

local function readSourceAge(key, names)
  if getSourceAge == nil then
    return nil, nil
  end

  local id = fieldIds[key]
  if id ~= nil and id ~= false then
    local ok, age, current = pcall(getSourceAge, id)
    if ok and age ~= nil then
      return tonumber(age), current
    end
  end

  for i = 1, #names do
    local ok, age, current = pcall(getSourceAge, names[i])
    if ok and age ~= nil then
      return tonumber(age), current
    end
  end

  return nil, nil
end

local function readAge(name)
  return readSourceAge(name, { name, string.lower(name) })
end

local function asNumber(value)
  if type(value) == "number" then
    return value
  elseif type(value) == "table" then
    return value.value or value.val or nil
  end
  return nil
end

local function sourceToPct(value)
  value = asNumber(value)
  if value == nil then
    return nil
  end

  if value < -100 or value > 100 then
    value = value * 100 / 1024
  end

  if value >= 0 then
    value = math.floor(value + 0.5)
  else
    value = math.ceil(value - 0.5)
  end

  return clamp(value, -100, 100)
end

local function nameInList(name, names)
  for i = 1, #names do
    if name == names[i] then
      return true
    end
  end
  return false
end

local function addSwitchId(ids, id)
  if type(id) ~= "number" then
    return
  end

  for i = 1, #ids do
    if ids[i] == id then
      return
    end
  end

  ids[#ids + 1] = id
end

local function addSwitchByName(ids, name)
  if getSwitchIndex == nil then
    return
  end

  local ok, id = pcall(getSwitchIndex, name)
  if ok then
    addSwitchId(ids, id)
  end
end

local function collectTrimIds(names)
  local ids = {}

  for i = 1, #names do
    addSwitchByName(ids, names[i])
  end

  if switches ~= nil then
    local ok, iterator, state, first = pcall(switches)
    if ok and iterator ~= nil then
      while true do
        local id, name = iterator(state, first)
        if id == nil then
          break
        end
        first = id

        if nameInList(name, names) then
          addSwitchId(ids, id)
        end
      end
    end
  end

  return ids
end

local function resolveEstopTrims(force)
  local now = nowTicks()
  if not force and estopTrimAIds ~= nil and estopTrimBIds ~= nil
      and estopTrimScanTime ~= nil and now - estopTrimScanTime < ESTOP_TRIM_RESCAN_TIME then
    return
  end

  estopTrimAIds = collectTrimIds(ESTOP_TRIM_A_NAMES)
  estopTrimBIds = collectTrimIds(ESTOP_TRIM_B_NAMES)
  estopTrimScanTime = now
  estopTrimStatus = string.format("%d/%d", #estopTrimAIds, #estopTrimBIds)
end

local function anySwitchPressed(ids)
  if ids == nil or getSwitchValue == nil then
    return false
  end

  for i = 1, #ids do
    local ok, value = pcall(getSwitchValue, ids[i])
    if ok and value == true then
      return true
    end
  end

  return false
end

local function readEstopTrims()
  resolveEstopTrims(false)
  return anySwitchPressed(estopTrimAIds), anySwitchPressed(estopTrimBIds)
end

local function text(value, empty)
  if value == nil then
    return empty or "--"
  end
  return tostring(value)
end

local function shortText(value, maxLen)
  value = tostring(value)
  if #value <= maxLen then
    return value
  end
  return string.sub(value, 1, maxLen - 2) .. ".."
end

local function nearestMode(value)
  local best = 1
  local bestDiff = math.abs(value - modes[1].pct)

  for i = 2, #modes do
    local diff = math.abs(value - modes[i].pct)
    if diff < bestDiff then
      best = i
      bestDiff = diff
    end
  end

  return best
end

local function switchPos(name)
  local pct = sourceToPct(readValue(name))
  if pct == nil then
    return 0, nil, nil
  elseif pct < -33 then
    return 0, pct, 1000
  elseif pct > 33 then
    return 2, pct, 2000
  end
  return 1, pct, 1500
end

local function heldBatteryValue(key, value, fresh, now)
  value = asNumber(value)

  if fresh and value ~= nil then
    batteryCache[key] = { value = value, time = now }
  end

  local cached = batteryCache[key]
  if cached ~= nil and (now - cached.time) <= BATTERY_HOLD_TIME then
    return cached.value, true
  end

  return nil, false
end

local function scModeName(pos)
  if pos == 0 then
    return "Passive"
  elseif pos == 1 then
    return "Fixstand"
  end
  return "Demo_Mode"
end

local function batteryStatus()
  local now = nowTicks()
  local pct, pctCurrent, pctFresh = readValue("Bat%")
  local volts, voltsCurrent, voltsFresh = readValue("RxBt")

  pct, pctFresh = heldBatteryValue("Bat%", pct, pctFresh, now)
  volts, voltsFresh = heldBatteryValue("RxBt", volts, voltsFresh, now)

  if pct ~= nil then
    pct = clamp(math.floor(pct + 0.5), 0, 100)
  end

  return pct, volts, pctCurrent, voltsCurrent, pctFresh, voltsFresh
end

local function batteryLedColor(pct, pctFresh)
  if not pctFresh or pct == nil then
    return "white"
  elseif pct < 20 then
    return "red"
  elseif pct < 50 then
    return "yellow"
  elseif pct < 80 then
    return "cyan"
  end
  return "green"
end

local function updateStatusLed()
  if setStatusLedOverride == nil then
    return
  end

  local now = nowTicks()
  if lastStatusLedTime ~= nil and (now - lastStatusLedTime) < LED_UPDATE_TIME then
    return
  end

  local batPct, batPctCurrent, batPctFresh = readValue("Bat%")
  local _, _, batVoltsFresh = readValue("RxBt")
  local batPctAge = readAge("Bat%")
  local batVoltsAge = readAge("RxBt")
  local batTelAgeOk = (batPctAge ~= nil and batPctAge <= LED_TELEMETRY_MAX_AGE_MS) or
      (batVoltsAge ~= nil and batVoltsAge <= LED_TELEMETRY_MAX_AGE_MS)
  local batTelOk = batTelAgeOk or (getSourceAge == nil and (batPctFresh or batVoltsFresh))
  batPct = asNumber(batPct)

  if batTelOk then
    lastBatteryTelemetryOkTime = now
  end

  if batTelOk and batPct ~= nil and
      (batPctAge == nil or batPctAge <= LED_TELEMETRY_MAX_AGE_MS or batPctCurrent ~= false) then
    lastStatusLedPct = clamp(math.floor(batPct + 0.5), 0, 100)
  end

  local batPctHeld = nil
  local batPctHeldFresh = false
  if lastStatusLedPct ~= nil and lastBatteryTelemetryOkTime ~= nil and
      (now - lastBatteryTelemetryOkTime) <= math.floor(LED_TELEMETRY_MAX_AGE_MS / 10) then
    batPctHeld = lastStatusLedPct
    batPctHeldFresh = true
  end

  local color = batteryLedColor(batPctHeld, batPctHeldFresh)
  pcall(setStatusLedOverride, color, LED_OVERRIDE_TIME_MS)
  lastStatusLedTime = now
end

local function qualityStatus(value, fallbackActive)
  if value ~= nil then
    value = clamp(math.floor(value + 0.5), 0, 100)
    if value <= 0 then
      return "LOST", value
    elseif value < 70 then
      return "WEAK", value
    end
    return "OK", value
  end

  if fallbackActive then
    return "OK", nil
  end

  return "LOST", nil
end

local function qualityText(value)
  if value == nil then
    return "?"
  end
  return string.format("%d%%", value)
end

local function pctText(value)
  if value == nil then
    return "?"
  end
  return string.format("%d%%", value)
end

local function voltsText(value)
  if value == nil then
    return "?V"
  end
  return string.format("%.1fV", value)
end

local function batteryTelemetryStatus(pctFresh, voltsFresh)
  if pctFresh or voltsFresh then
    return "OK"
  end
  return "NO BATT"
end

local function statusSnapshot()
  local batPct, batVolts, batPctCurrent, batVoltsCurrent, batPctFresh, batVoltsFresh = batteryStatus()
  local batTel = batteryTelemetryStatus(batPctFresh, batVoltsFresh)
  local hasBatteryTelemetry = batTel == "OK"
  local rqly, rqlyCurrent = readValue("RQly")
  local tqly, tqlyCurrent = readValue("TQly")
  local uplink, uplinkPct = qualityStatus(rqlyCurrent ~= false and asNumber(rqly) or nil, false)
  local downlink, downlinkPct = qualityStatus(tqlyCurrent ~= false and asNumber(tqly) or nil, hasBatteryTelemetry)

  return {
    uplink = uplink,
    uplinkPct = uplinkPct,
    downlink = downlink,
    downlinkPct = downlinkPct,
    batPct = batPct,
    batVolts = batVolts,
    batPctCurrent = batPctCurrent,
    batVoltsCurrent = batVoltsCurrent,
    batPctFresh = batPctFresh,
    batVoltsFresh = batVoltsFresh,
    batTel = batTel,
  }
end

local function fillRect(x, y, w, h)
  if w <= 0 or h <= 0 then
    return
  end

  if lcd.drawFilledRectangle ~= nil then
    lcd.drawFilledRectangle(x, y, w, h)
  elseif lcd.drawLine ~= nil then
    for i = 0, w - 1 do
      lcd.drawLine(x + i, y, x + i, y + h - 1, FLAG_SOLID, 0)
    end
  else
    for i = 0, h - 1 do
      lcd.drawRectangle(x, y + i, w, 1)
    end
  end
end

local function drawBatteryIcon(x, y, w, h, pct)
  lcd.drawRectangle(x, y, w, h)
  lcd.drawRectangle(x + w, y + math.floor(h / 3), 2, math.floor(h / 3) + 1)

  if pct == nil then
    lcd.drawText(x + 5, y + 1, "?", FLAG_SML)
    return
  end

  local fill = math.floor((w - 4) * pct / 100)
  if fill > 0 then
    fillRect(x + 2, y + 2, fill, h - 4)
  end
end

local function drawGauge(x, y, w, h, pct)
  pct = clamp(pct or 0, 0, 100)
  lcd.drawRectangle(x, y, w, h)

  local fill = math.floor((w - 2) * pct / 100)
  if fill > 0 then
    fillRect(x + 1, y + 1, fill, h - 2)
  end
end

local function estopGaugePct()
  if estopHoldStart ~= nil then
    local now = nowTicks()
    local disarming = estopHoldAction == "deactivate"
    local target = disarming and ESTOP_DEACTIVATE_TIME or ESTOP_ACTIVATE_TIME
    local progress = clamp((now - estopHoldStart) * 100 / target, 0, 100)

    if disarming then
      return 100 - progress
    end
    return progress
  end

  if estopActive then
    return 100
  end
  return 0
end

local function estopVisible()
  if estopActive or estopHoldStart ~= nil then
    return true
  end
  return estopOverlay ~= nil and nowTicks() < estopOverlayUntil
end

local function estopTitle()
  if estopOverlay == "arming" then
    return "ACTIVATING"
  elseif estopOverlay == "disarming" then
    return "DEACTIVATING"
  elseif estopOverlay == "deactivated" then
    return "DEACTIVATED"
  elseif estopActive or estopOverlay == "activated" then
    return "ACTIVATED"
  end
  return "HOW TO USE"
end

local function drawEstopSmall()
  local pct = estopGaugePct()

  lcd.clear()
  lcd.drawText(0, 0, "E-STOP", FLAG_DBL)

  if estopOverlay == "hint" then
    lcd.drawText(0, 19, "OUT+OUT 0.5s: ACTIVATE", FLAG_SML)
    lcd.drawText(0, 30, "OUT+OUT 3s: DEACTIVATE", FLAG_SML)
    drawGauge(8, 43, SCREEN_W - 16, 8, pct)
  else
    lcd.drawText(0, 20, estopTitle(), FLAG_SML + (estopActive and FLAG_BLINK or 0))
    drawGauge(8, 34, SCREEN_W - 16, 11, pct)

    if estopOverlay == "disarming" then
      lcd.drawText(0, 49, "OUT+OUT 3s: DEACTIVATE", FLAG_SML)
    elseif estopOverlay == "arming" then
      lcd.drawText(0, 49, "OUT+OUT 0.5s: ACTIVATE", FLAG_SML)
    elseif estopActive then
      lcd.drawText(0, 49, "OUT+OUT 3s: DEACTIVATE", FLAG_SML)
    else
      lcd.drawText(0, 49, "Released", FLAG_SML)
    end
  end
end

local function drawEstopLarge()
  local pct = estopGaugePct()

  lcd.clear()
  lcd.drawText(4, 4, "E-STOP", FLAG_DBL)

  if estopOverlay == "hint" then
    lcd.drawText(4, 42, "OUT+OUT 0.5s: ACTIVATE", FLAG_MID)
    lcd.drawText(4, 70, "OUT+OUT 3s: DEACTIVATE", 0)
  else
    lcd.drawText(4, 42, estopTitle(), FLAG_MID + (estopActive and FLAG_BLINK or 0))
    drawGauge(4, 78, SCREEN_W - 8, 18, pct)
  end
end

local function syncFromGv(updateSelection)
  if model ~= nil and model.getGlobalVariable ~= nil then
    gvValue = asNumber(model.getGlobalVariable(GV_INDEX, FM_INDEX))
    if gvValue ~= nil and updateSelection ~= false then
      selected = nearestMode(gvValue)
      cursor = selected
    end

    estopGvValue = asNumber(model.getGlobalVariable(ESTOP_GV_INDEX, FM_INDEX))
    if estopGvValue ~= nil and estopInitialized then
      estopActive = estopGvValue > 0
    end
  end

  ch11Pct = sourceToPct(readSource("CH11", { "ch11", "CH11", "Ch11", "chan11", "Chan11" }))
  ch12Pct = sourceToPct(readSource("CH12", { "ch12", "CH12", "Ch12", "chan12", "Chan12" }))
end

local function setMode(index, label)
  if model ~= nil and model.setGlobalVariable ~= nil then
    local ok = pcall(model.setGlobalVariable, GV_INDEX, FM_INDEX, modes[index].pct)
    gvWrite = ok and label or "ERR"
  else
    gvWrite = "NOAPI"
  end

  syncFromGv()
end

local function setEstop(active, label)
  estopActive = active
  estopGvValue = active and ESTOP_ACTIVE or ESTOP_INACTIVE

  if model ~= nil and model.setGlobalVariable ~= nil then
    local ok = pcall(model.setGlobalVariable, ESTOP_GV_INDEX, FM_INDEX, estopGvValue)
    estopWrite = ok and label or "ERR"
  else
    estopWrite = "NOAPI"
  end

  ch12Pct = sourceToPct(readSource("CH12", { "ch12", "CH12", "Ch12", "chan12", "Chan12" }))
end

local function ensureEstopInitialized()
  if estopInitialized then
    return
  end

  estopInitialized = true
  syncFromGv(false)

  if estopGvValue == nil or (estopGvValue > -50 and estopGvValue < 50) then
    setEstop(false, "INIT")
  else
    estopActive = estopGvValue > 0
  end
end

local function updateEstop()
  ensureEstopInitialized()

  local now = nowTicks()
  local trimA, trimB = readEstopTrims()
  local combo = trimA and trimB
  local single = trimA ~= trimB

  if combo then
    if estopHoldStart == nil then
      estopHoldStart = now
      estopHoldAction = estopActive and "deactivate" or "activate"
      estopHoldLatched = false
    end

    local disarming = estopHoldAction == "deactivate"
    local target = disarming and ESTOP_DEACTIVATE_TIME or ESTOP_ACTIVATE_TIME
    estopOverlay = disarming and "disarming" or "arming"
    estopOverlayUntil = now + ESTOP_HINT_TIME

    if estopHoldLatched then
      estopOverlay = disarming and "deactivated" or "activated"
    elseif now - estopHoldStart >= target then
      estopHoldLatched = true

      if disarming then
        setEstop(false, "OFF")
        estopOverlay = "deactivated"
        estopOverlayUntil = now + ESTOP_RESULT_TIME
      else
        setEstop(true, "ON")
        estopOverlay = "activated"
        estopOverlayUntil = now + ESTOP_RESULT_TIME
      end
    end

    return
  end

  estopHoldStart = nil
  estopHoldAction = nil
  estopHoldLatched = false

  if single then
    estopOverlay = estopActive and "activated" or "hint"
    estopOverlayUntil = now + ESTOP_HINT_TIME
  elseif estopOverlay ~= nil and now >= estopOverlayUntil then
    estopOverlay = nil
  end
end

local function applyMode()
  setMode(selected, "OK")
end

local function changeCursor(delta)
  cursor = clamp(cursor + delta, 1, #modes)
end

local function commitCursor()
  selected = cursor
  applyMode()
end

local function resetMode()
  selected = 1
  cursor = 1
  edit = false
  setMode(selected, "RST")
  exitResetDone = true
end

local function isEvent(event, value)
  return value ~= nil and event == value
end

local function isIncEvent(event)
  return isEvent(event, EVT_ROT_RIGHT)
end

local function isDecEvent(event)
  return isEvent(event, EVT_ROT_LEFT)
end

local function isEnterEvent(event)
  return isEvent(event, EVT_VIRTUAL_ENTER)
end

local function isExitEvent(event)
  return isEvent(event, EVT_VIRTUAL_EXIT)
    or isEvent(event, EVT_EXIT_BREAK)
    or isEvent(event, EVT_EXIT_LONG)
end

local function drawSmall()
  local status = statusSnapshot()
  local batPct = status.batPctFresh and pctText(status.batPct) or "?"
  local batVolts = status.batVoltsFresh and voltsText(status.batVolts) or "?V"

  lcd.clear()
  lcd.drawText(0, 2, "UPLINK", FLAG_SML)
  lcd.drawText(58, 2, status.uplink, FLAG_SML)
  lcd.drawText(SCREEN_W - 1, 2, qualityText(status.uplinkPct), FLAG_SML + FLAG_RIGHT)

  lcd.drawText(0, 16, "DOWNLINK", FLAG_SML)
  lcd.drawText(58, 16, status.downlink, FLAG_SML)
  lcd.drawText(SCREEN_W - 1, 16, qualityText(status.downlinkPct), FLAG_SML + FLAG_RIGHT)

  lcd.drawText(0, 30, "K1 BATT", FLAG_SML)
  lcd.drawText(58, 30, batPct, FLAG_SML)
  lcd.drawText(SCREEN_W - 1, 30, batVolts, FLAG_SML + FLAG_RIGHT)

  lcd.drawText(0, 44, "BATT TELE", FLAG_SML)
  lcd.drawText(58, 44, status.batTel, FLAG_SML)
end

local function drawLarge()
  local status = statusSnapshot()
  local batPct = status.batPctFresh and pctText(status.batPct) or "?"
  local batVolts = status.batVoltsFresh and voltsText(status.batVolts) or "?V"

  lcd.clear()
  lcd.drawText(4, 4, "Robot Status", FLAG_MID)

  lcd.drawText(4, 34, "UPLINK", 0)
  lcd.drawText(96, 34, status.uplink, 0)
  lcd.drawText(SCREEN_W - 4, 34, qualityText(status.uplinkPct), FLAG_RIGHT)

  lcd.drawText(4, 66, "DOWNLINK", 0)
  lcd.drawText(96, 66, status.downlink, 0)
  lcd.drawText(SCREEN_W - 4, 66, qualityText(status.downlinkPct), FLAG_RIGHT)

  lcd.drawText(4, 98, "K1 BATT", 0)
  lcd.drawText(96, 98, batPct, 0)
  lcd.drawText(SCREEN_W - 4, 98, batVolts, FLAG_RIGHT)

  lcd.drawText(4, 130, "BATT TELE", 0)
  lcd.drawText(96, 130, status.batTel, 0)
end

local function background()
  updateEstop()
  updateStatusLed()
end

local function run(event)
  lastRunTime = nowTicks()
  exitResetDone = false

  updateEstop()
  updateStatusLed()

  if estopVisible() then
    if SCREEN_H <= 64 then
      drawEstopSmall()
    else
      drawEstopLarge()
    end
  else
    if SCREEN_H <= 64 then
      drawSmall()
    else
      drawLarge()
    end
  end

  return 0
end

return {
  background = background,
  run = run
}
