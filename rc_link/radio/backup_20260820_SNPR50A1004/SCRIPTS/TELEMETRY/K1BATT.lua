local FLAG_SML = SMLSIZE or 0
local FLAG_MID = MIDSIZE or 0
local FLAG_RIGHT = RIGHT or 0
local SCREEN_W = LCD_W or 128
local SCREEN_H = LCD_H or 64
local BATTERY_HOLD_TIME = 80
local sensorCache = {}

local function nowTicks()
  if getTime ~= nil then
    local value = getTime()
    if type(value) == "number" then
      return value
    end
  end
  return 0
end

local function asNumber(value)
  if type(value) == "number" then
    return value
  elseif type(value) == "table" then
    return value.value or value.val or nil
  end
  return nil
end

local function readSensor(name)
  if getSourceValue ~= nil then
    local ok, value, current, fresh = pcall(getSourceValue, name)
    if ok and value ~= nil then
      return asNumber(value), current == true, fresh == true
    end
  end

  local ok, value = pcall(getValue, name)
  if ok and value ~= nil then
    return asNumber(value), true, true
  end

  return nil, false, false
end

local function heldSensorValue(name, value, fresh, now)
  if fresh and value ~= nil then
    sensorCache[name] = { value = value, time = now }
  end

  local cached = sensorCache[name]
  if cached ~= nil and (now - cached.time) <= BATTERY_HOLD_TIME then
    return cached.value, true
  end

  return nil, false
end

local function round(value)
  if value >= 0 then
    return math.floor(value + 0.5)
  end
  return math.ceil(value - 0.5)
end

local function pctText(value, fresh)
  if not fresh or value == nil then
    return "?"
  end
  return string.format("%d%%", math.max(0, math.min(100, round(value))))
end

local function voltsText(value, fresh)
  if not fresh or value == nil then
    return "?V"
  end
  return string.format("%.1fV", value)
end

local function ampsText(value, fresh)
  if not fresh or value == nil then
    return nil
  end
  return string.format("%.1fA", value)
end

local function mahText(value, fresh)
  if not fresh or value == nil then
    return nil
  end
  return string.format("%dmAh", round(value))
end

local function snapshot()
  local now = nowTicks()
  local pct, pctCurrent, pctFresh = readSensor("Bat%")
  local volts, voltsCurrent, voltsFresh = readSensor("RxBt")
  local current, currentOk, currentFresh = readSensor("Curr")
  local capacity, capacityOk, capacityFresh = readSensor("Capa")

  pct, pctFresh = heldSensorValue("Bat%", pct, pctFresh, now)
  volts, voltsFresh = heldSensorValue("RxBt", volts, voltsFresh, now)
  current, currentFresh = heldSensorValue("Curr", current, currentFresh, now)
  capacity, capacityFresh = heldSensorValue("Capa", capacity, capacityFresh, now)

  local battTele = (pctFresh or voltsFresh) and "OK" or "NO BATT"

  return {
    pct = pct,
    pctCurrent = pctCurrent,
    pctFresh = pctFresh,
    volts = volts,
    voltsCurrent = voltsCurrent,
    voltsFresh = voltsFresh,
    current = current,
    currentOk = currentOk,
    currentFresh = currentFresh,
    capacity = capacity,
    capacityOk = capacityOk,
    capacityFresh = capacityFresh,
    battTele = battTele,
  }
end

local function drawRow(y, label, value)
  lcd.drawText(0, y, label, FLAG_SML)
  lcd.drawText(SCREEN_W - 1, y, value, FLAG_SML + FLAG_RIGHT)
end

local function drawSmall()
  local s = snapshot()
  local y = 36

  lcd.clear()
  lcd.drawText(0, 0, "K1 Battery", FLAG_SML)

  lcd.drawText(0, 12, "K1 BATT", FLAG_SML)
  lcd.drawText(58, 12, pctText(s.pct, s.pctFresh), FLAG_SML)
  lcd.drawText(SCREEN_W - 1, 12, voltsText(s.volts, s.voltsFresh), FLAG_SML + FLAG_RIGHT)

  drawRow(24, "BATT TELE", s.battTele)

  local current = ampsText(s.current, s.currentFresh)
  if current ~= nil then
    drawRow(y, "Curr", current)
    y = y + 12
  end

  local capacity = mahText(s.capacity, s.capacityFresh)
  if capacity ~= nil and y <= 52 then
    drawRow(y, "Capa", capacity)
  end
end

local function drawLarge()
  local s = snapshot()
  local y = 86

  lcd.clear()
  lcd.drawText(4, 4, "K1 Battery Diagnostics", FLAG_MID)

  lcd.drawText(4, 34, "K1 BATT", 0)
  lcd.drawText(96, 34, pctText(s.pct, s.pctFresh), 0)
  lcd.drawText(SCREEN_W - 4, 34, voltsText(s.volts, s.voltsFresh), FLAG_RIGHT)

  lcd.drawText(4, 62, "BATT TELE", 0)
  lcd.drawText(SCREEN_W - 4, 62, s.battTele, FLAG_RIGHT)

  local current = ampsText(s.current, s.currentFresh)
  if current ~= nil then
    lcd.drawText(4, y, "Curr", 0)
    lcd.drawText(SCREEN_W - 4, y, current, FLAG_RIGHT)
    y = y + 24
  end

  local capacity = mahText(s.capacity, s.capacityFresh)
  if capacity ~= nil then
    lcd.drawText(4, y, "Capa", 0)
    lcd.drawText(SCREEN_W - 4, y, capacity, FLAG_RIGHT)
  end
end

local function run(event)
  if SCREEN_H <= 64 then
    drawSmall()
  else
    drawLarge()
  end

  return 0
end

return { run = run }
