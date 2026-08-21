-- K1PCT: PC link serial test (TOOLS, one-time script)
-- USB-VCP 모드가 LUA일 때 PC와의 줄 단위 왕복을 검증한다.
--   PC -> RC : "PING"        -> RC -> PC : "PONG T"
--   PC -> RC : "GV3 <n>"     -> GV3(index 2) 세팅 후 "OK T GV3 <n>"
--   그 외    -> "ERR T CMD"
-- GV3는 어떤 믹스에도 연결돼 있지 않아 채널 출력에 영향이 없다.
-- 응답의 "T"는 TOOLS 컨텍스트 표시 (믹서판 K1PCM은 "M").

local buf = ""
local rxLines = 0
local lastCmd = "-"
local status = "INIT"

local function clampGv(n)
  if n < -1024 then return -1024 end
  if n > 1024 then return 1024 end
  return n
end

local function reply(s)
  if serialWrite ~= nil then
    pcall(serialWrite, s .. "\n")
  end
end

local function handleLine(line)
  line = string.gsub(line, "%s+$", "")
  if #line == 0 then return end
  rxLines = rxLines + 1
  lastCmd = line
  if line == "PING" then
    reply("PONG T")
    return
  end
  local n = string.match(line, "^GV3%s+(-?%d+)$")
  if n ~= nil then
    local v = clampGv(tonumber(n))
    local ok = false
    if model ~= nil and model.setGlobalVariable ~= nil then
      ok = pcall(model.setGlobalVariable, 2, 0, v)
    end
    if ok then reply("OK T GV3 " .. v) else reply("ERR T GV") end
    return
  end
  reply("ERR T CMD")
end

local function pump()
  if serialRead == nil then
    status = "NO serialRead"
    return
  end
  status = "RUN"
  local ok, data = pcall(serialRead)
  if ok and data ~= nil and #data > 0 then
    buf = buf .. data
    if #buf > 256 then buf = "" end
    while true do
      local pos = string.find(buf, "\n", 1, true)
      if pos == nil then break end
      handleLine(string.sub(buf, 1, pos - 1))
      buf = string.sub(buf, pos + 1)
    end
  end
end

local function gv3Now()
  if model ~= nil and model.getGlobalVariable ~= nil then
    local ok, v = pcall(model.getGlobalVariable, 2, 0)
    if ok and v ~= nil then return v end
  end
  return "?"
end

local function init()
end

local function run(event)
  pump()
  lcd.clear()
  lcd.drawText(1, 1, "K1PC serial test [T]", INVERS)
  lcd.drawText(1, 12, "status: " .. status)
  lcd.drawText(1, 22, "rx lines: " .. rxLines)
  lcd.drawText(1, 32, "last: " .. string.sub(lastCmd, 1, 18))
  lcd.drawText(1, 42, "GV3: " .. tostring(gv3Now()))
  lcd.drawText(1, 54, "[EXIT] close", SMLSIZE)
  if event == EVT_VIRTUAL_EXIT then
    return 2
  end
  return 0
end

return { init = init, run = run }
