local FLAG_SML = SMLSIZE or 0
local FLAG_RIGHT = RIGHT or 0
local SCREEN_W = LCD_W or 128

local SENSORS = {
  { label = "1RSS", unit = "dB" },
  { label = "2RSS", unit = "dB" },
  { label = "RQly", unit = "%" },
  { label = "RSNR", unit = "dB" },
  { label = "ANT", unit = "" },
}

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
    local ok, value, current = pcall(getSourceValue, name)
    if ok and value ~= nil then
      return asNumber(value), current == true
    end
  end

  local ok, value = pcall(getValue, name)
  if ok and value ~= nil then
    return asNumber(value), true
  end

  return nil, false
end

local function round(value)
  if value >= 0 then
    return math.floor(value + 0.5)
  end
  return math.ceil(value - 0.5)
end

local function formatValue(value, unit)
  if value == nil then
    return nil
  end

  if unit == "%" then
    return string.format("%d%%", math.max(0, math.min(100, round(value))))
  elseif unit == "" then
    return string.format("%d", round(value))
  end

  return string.format("%d%s", round(value), unit)
end

local function drawRows(title)
  local y = 12
  local rows = 0

  lcd.clear()
  lcd.drawText(0, 0, title, FLAG_SML)

  for i = 1, #SENSORS do
    local sensor = SENSORS[i]
    local value, current = readSensor(sensor.label)
    local text = current and formatValue(value, sensor.unit) or nil
    if text ~= nil then
      lcd.drawText(0, y, sensor.label, FLAG_SML)
      lcd.drawText(SCREEN_W - 1, y, text, FLAG_SML + FLAG_RIGHT)
      y = y + 10
      rows = rows + 1
    end
  end

  if rows == 0 then
    lcd.drawText(0, 28, "No current link data", FLAG_SML)
  end
end

local function run(event)
  drawRows("ELRS Link")
  return 0
end

return { run = run }
