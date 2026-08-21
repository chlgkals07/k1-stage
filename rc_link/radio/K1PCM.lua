-- K1PCM: PC link serial test (MIXES, 믹서 컨텍스트 판정용)
-- K1PCT와 같은 프로토콜, 응답 컨텍스트 표시만 "M".
-- 채널 출력 없음(output 빈 테이블), GV3(index 2)만 만진다.
-- 주의: K1PCT(TOOLS)와 동시에 띄우면 serialRead를 서로 뺏는다 — 하나만 실행할 것.

local buf = ""

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
  if line == "PING" then
    reply("PONG M")
    return
  end
  local n = string.match(line, "^GV3%s+(-?%d+)$")
  if n ~= nil then
    local v = clampGv(tonumber(n))
    local ok = false
    if model ~= nil and model.setGlobalVariable ~= nil then
      ok = pcall(model.setGlobalVariable, 2, 0, v)
    end
    if ok then reply("OK M GV3 " .. v) else reply("ERR M GV") end
    return
  end
  reply("ERR M CMD")
end

local function init()
end

local function run()
  if serialRead == nil then
    return
  end
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

return { init = init, run = run, input = {}, output = {} }
