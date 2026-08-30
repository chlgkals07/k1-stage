-- toolName = TNS|Robot Mode|TNE

local GV_INDEX = 0   -- GV1
local FM_INDEX = 0   -- Flight Mode 0

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

local selected = 1

local function clamp(v, minv, maxv)
  if v < minv then return minv end
  if v > maxv then return maxv end
  return v
end

local function nearestModeFromGv(value)
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

local function applyMode()
  model.setGlobalVariable(GV_INDEX, FM_INDEX, modes[selected].pct)
end

local function syncFromCh11()
  local gv = model.getGlobalVariable(GV_INDEX, FM_INDEX)

  if gv ~= nil then
    selected = nearestModeFromGv(gv)
  end
end

local function changeMode(delta)
  selected = clamp(selected + delta, 1, #modes)
  applyMode()
end

local function init()
  loadModeTable()
  local gv = model.getGlobalVariable(GV_INDEX, FM_INDEX)

  if gv == nil then
    gv = -100
  end

  selected = nearestModeFromGv(gv)
  applyMode()
end

local function drawScreen()
  syncFromCh11()

  local m = modes[selected]
  local maxMode = #modes - 1

  lcd.clear()

  -- 128x64 작은 화면용
  if LCD_H <= 64 then
    lcd.drawText(0, 0, "Robot Mode CH11", SMLSIZE)

    lcd.drawText(0, 12, "Mode:", SMLSIZE)
    lcd.drawText(42, 12, string.format("%02d/%02d", selected - 1, maxMode), SMLSIZE)

    lcd.drawText(0, 24, "PWM:", SMLSIZE)
    lcd.drawText(42, 24, string.format("%d", m.pwm), SMLSIZE)
    lcd.drawText(80, 24, "us", SMLSIZE)

    lcd.drawText(0, 36, m.name, SMLSIZE)

    lcd.drawText(0, 50, string.format("G1:%+d Roll=Sel", m.pct), SMLSIZE)

  -- 큰 화면용
  else
    lcd.drawText(4, 4, "Robot Mode -> CH11", MIDSIZE)

    lcd.drawText(4, 30, "Mode", 0)
    lcd.drawText(80, 26, string.format("%02d / %02d", selected - 1, maxMode), DBLSIZE)

    lcd.drawText(4, 60, "PWM", 0)
    lcd.drawText(80, 58, string.format("%dus", m.pwm), MIDSIZE)

    lcd.drawText(4, 84, "Name", 0)
    lcd.drawText(80, 82, m.name, MIDSIZE)

    lcd.drawText(4, 108, "G1", 0)
    lcd.drawText(80, 106, string.format("%+d", m.pct), MIDSIZE)

    lcd.drawText(4, 136, "Rotate wheel: select", SMLSIZE)
    lcd.drawText(4, 150, "EXIT: close", SMLSIZE)
  end
end

local function run(event)
  if event == EVT_ROT_RIGHT
     or event == EVT_PLUS_FIRST
     or event == EVT_PLUS_BREAK
     or event == EVT_VIRTUAL_INC
     or event == EVT_VIRTUAL_NEXT then

    changeMode(1)

  elseif event == EVT_ROT_LEFT
     or event == EVT_MINUS_FIRST
     or event == EVT_MINUS_BREAK
     or event == EVT_VIRTUAL_DEC
     or event == EVT_VIRTUAL_PREVIOUS then

    changeMode(-1)

  elseif event == EVT_EXIT_BREAK
     or event == EVT_VIRTUAL_EXIT then

    return 1
  end

  drawScreen()
  return 0
end

return {
  init = init,
  run = run
}
