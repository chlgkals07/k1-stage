-- K1PC v2: PC 유선 명령 수신기 (TOOLS, 운영판)
-- USB-VCP=LUA 상태에서 PC의 줄 명령을 받아 "펄스"로 채널을 잠깐 오버라이드한다.
-- 평소에는 완전 물리 조종. 펄스(~1초) 동안만 L1 게이트가 켜지고 즉시 물리 복귀.
--
--   PING             -> PONG              (keepalive)
--   RUN <1..20> [A|B]-> OK RUN <n>        (즉시형: 다이얼+뱅크 세팅, code 4 발사)
--   PREP <1..20> <A|B>-> OK PREP          (사전 준비: code 0 유지 — dance 싱크용)
--   FIRE             -> OK FIRE           (PREP 상태에서 code 4 엣지 — GV 즉시 쓰기)
--   STOP             -> OK STOP           (ReadyPose, CH7 1500 — 구버전 호환)
--   VEL              -> OK VEL            (Velocity=locomotion 복귀, code 3 — 정지 기본)
--   DAMP             -> OK DAMP           (Damping,  CH7 1000)
--   TLM              -> TLM st=.. lq=.. rssi=..
--   CHK              -> CHK ch5=.. ch6=.. ch7=.. ch11=..  (믹서 출력 µs, 검증용)
--   펄스 중 새 명령 -> BUSY / 인자 오류 -> ERR ARG / PREP 없이 FIRE -> ERR NOPREP
--   PREP·펄스 중 0.5s 시리얼 무소식 -> 즉시 해제 + ABORT / PREP 10s 경과 -> 자동 해제
--
-- 뱅크: A -> CH5 1000 (GV6=-100), B -> CH5 2000 (GV6=+100)  [motions.yaml rc_list 기준]
-- GV: GV1(idx0)=다이얼, GV4(idx3)=CH6, GV5(idx4)=CH7, GV6(idx5)=CH5.
--     GV2(estop)는 절대 만지지 않는다. 게이트: L1(FUNC_STICKY, 반영 지연 <=100ms)

local GV_MODE = 0
local GV_CH6 = 3
local GV_CH7 = 4
local GV_BANK = 5
local FM = 0
local LS_GATE = 0

-- getTime()은 10ms 틱
local T_GATE_LAG = 15    -- sticky 10Hz 버퍼 여유 150ms
local T_HOLD_CODE = 40   -- 코드 유지 400ms
local T_HOLD_ZERO = 20   -- code 0 유지 200ms
local T_KEEPALIVE = 50   -- 무소식 한계 500ms
local T_PREP_MAX = 1000  -- PREP 자동 해제 10s

local buf = ""
local rxLines = 0
local lastCmd = "-"
local state = "IDLE"
local lastRxTick = 0
local pulse = nil   -- { kind, slot, stage, tstage, lag }
local prep = nil    -- { slot, bank, deadline }

local function now()
  local ok, t = pcall(getTime)
  if ok and type(t) == "number" then return t end
  return 0
end

local function setGv(idx, v)
  if v < -1024 then v = -1024 end
  if v > 1024 then v = 1024 end
  if model ~= nil and model.setGlobalVariable ~= nil then
    pcall(model.setGlobalVariable, idx, FM, v)
  end
end

local function gate(on)
  if setStickySwitch ~= nil then
    pcall(setStickySwitch, LS_GATE, on)
  end
end

local function reply(s)
  if serialWrite ~= nil then
    pcall(serialWrite, s .. "\n")
  end
end

local function readNum(name)
  local ok, v = pcall(getValue, name)
  if ok and type(v) == "number" then return v end
  return nil
end

local function chText(name)
  local v = readNum(name)
  if v == nil then return "?" end
  return tostring(1500 + math.floor(v / 2 + 0.5))
end

local function releaseAll()
  gate(false)
  setGv(GV_CH6, 0)
  setGv(GV_CH7, 0)
  setGv(GV_BANK, 0)
end

local function slotPct(slot)
  return -100 + (slot - 1) * 4
end

local function bankPct(bank)
  if bank == "B" then return 100 end
  return -100
end

-- GV는 믹스 weight(% 단위): +100 -> CH 약 2000, 0 -> 1500, -100 -> 약 1000

local function startPulse(kind, slot, bank, ch7pct, lag)
  if kind == "RUN" or kind == "FIRE" then
    setGv(GV_MODE, slotPct(slot))
    setGv(GV_BANK, bankPct(bank))
    setGv(GV_CH6, 100)   -- code 4/5 조합 (CH6 2000)
    setGv(GV_CH7, 100)   -- (CH7 2000)
  else
    -- VEL = code 3 (CH7 2000 + CH6 1000). STOP/DAMP 는 CH6 중앙(무해).
    setGv(GV_CH6, kind == "VEL" and -100 or 0)
    setGv(GV_CH7, ch7pct)
  end
  if kind ~= "FIRE" then
    gate(true)           -- FIRE 는 PREP 에서 게이트가 이미 켜져 있다
  end
  pulse = { kind = kind, slot = slot, stage = 1, tstage = now(), lag = lag }
  state = "PULSE " .. kind
end

local function startPrep(slot, bank)
  setGv(GV_MODE, slotPct(slot))
  setGv(GV_BANK, bankPct(bank))
  setGv(GV_CH6, 0)       -- code 0: 전이 없음, 로봇 무해
  setGv(GV_CH7, 100)
  gate(true)
  prep = { slot = slot, bank = bank, deadline = now() + T_PREP_MAX }
  state = "PREP"
end

local function finishPulse(tag)
  releaseAll()
  pulse = nil
  state = "IDLE"
  reply(tag)
end

local function abortAll(tag)
  releaseAll()
  pulse = nil
  prep = nil
  state = "ABORT"
  if tag then reply(tag) end
end

local function stepPulse()
  local t = now()
  if prep ~= nil and pulse == nil then
    if t - lastRxTick > T_KEEPALIVE or t > prep.deadline then
      abortAll("ABORT")
    end
    return
  end
  if pulse == nil then return end
  if t - lastRxTick > T_KEEPALIVE then
    abortAll("ABORT")
    return
  end
  local dt = t - pulse.tstage
  if pulse.stage == 1 then
    if dt >= pulse.lag + T_HOLD_CODE then
      -- 코드 유지가 끝나는 순간의 실제 믹서 출력을 기록 — OK 응답에 실어
      -- PC가 "정말 그 값이 전파로 나갔는지"를 매 발사마다 자동 검증한다
      pulse.obs = " ch5=" .. chText("ch5") .. " ch6=" .. chText("ch6")
                  .. " ch7=" .. chText("ch7") .. " ch11=" .. chText("ch11")
      if pulse.kind == "RUN" or pulse.kind == "FIRE" then
        setGv(GV_CH6, 0)  -- CH6 1500 = code 0 (전이 없음)
        pulse.stage = 2
      else
        gate(false)
        pulse.stage = 3
      end
      pulse.tstage = t
    end
  elseif pulse.stage == 2 then
    if dt >= T_HOLD_ZERO then
      gate(false)
      pulse.stage = 3
      pulse.tstage = t
    end
  elseif pulse.stage == 3 then
    if dt >= T_GATE_LAG then
      local obs = pulse.obs or ""
      if pulse.kind == "RUN" then
        finishPulse("OK RUN " .. pulse.slot .. obs)
      else
        finishPulse("OK " .. pulse.kind .. obs)
      end
    end
  end
end

local function handleLine(line)
  line = string.gsub(line, "%s+$", "")
  if #line == 0 then return end
  rxLines = rxLines + 1
  lastRxTick = now()
  if line == "PING" then
    reply("PONG")
    return
  end
  lastCmd = line
  if line == "TLM" then
    reply("TLM st=" .. state .. " lq=" .. tostring(readNum("RQly"))
          .. " rssi=" .. tostring(readNum("1RSS")))
    return
  end
  if line == "CHK" then
    -- 믹서 출력값(= ELRS로 나가는 값) 보고. 펄스/PREP 중에도 동작 — 스위프 검증용
    reply("CHK ch5=" .. chText("ch5") .. " ch6=" .. chText("ch6")
          .. " ch7=" .. chText("ch7") .. " ch11=" .. chText("ch11"))
    return
  end
  if pulse ~= nil then
    reply("BUSY")
    return
  end
  if line == "FIRE" then
    if prep == nil then
      reply("ERR NOPREP")
      return
    end
    local p = prep
    prep = nil
    setGv(GV_CH6, 100)   -- code 4/5 엣지 — GV 쓰기는 즉시라 ms급
    pulse = { kind = "FIRE", slot = p.slot, stage = 1, tstage = now(), lag = 0 }
    state = "PULSE FIRE"
    return
  end
  local slot, bank = string.match(line, "^RUN%s+(%d+)%s*([AB]?)$")
  local pslot, pbank = string.match(line, "^PREP%s+(%d+)%s+([AB])$")
  if slot ~= nil or pslot ~= nil then
    local n = tonumber(slot or pslot)
    local b = (bank ~= "" and bank) or pbank or "A"
    if n == nil or n < 1 or n > 20 then
      reply("ERR ARG")
      return
    end
    if prep ~= nil then  -- 새 명령이 오면 이전 PREP 는 폐기
      releaseAll()
      prep = nil
    end
    if pslot ~= nil then
      startPrep(n, b)
      reply("OK PREP")
    else
      startPulse("RUN", n, b, nil, T_GATE_LAG)
    end
    return
  end
  if line == "STOP" or line == "DAMP" or line == "VEL" then
    if prep ~= nil then
      releaseAll()
      prep = nil
    end
    if line == "STOP" then
      startPulse("STOP", nil, nil, 0, T_GATE_LAG)      -- CH7 1500 = ReadyPose
    elseif line == "VEL" then
      startPulse("VEL", nil, nil, 100, T_GATE_LAG)     -- CH7 2000 (+CH6 1000) = Velocity
    else
      startPulse("DAMP", nil, nil, -100, T_GATE_LAG)   -- CH7 1000 = Damping
    end
    return
  end
  reply("ERR CMD")
end

local function pump()
  if serialRead == nil then
    state = "NO serialRead"
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

local function init()
  lastRxTick = now()
  releaseAll()
end

local function run(event)
  pump()
  stepPulse()
  lcd.clear()
  lcd.drawText(1, 1, "K1PC v2.3 " .. state, INVERS)
  lcd.drawText(1, 11, "cmd:" .. string.sub(lastCmd, 1, 15) .. " rx:" .. rxLines, SMLSIZE)
  lcd.drawText(1, 21, "CH5 " .. chText("ch5") .. "  CH6 " .. chText("ch6"), SMLSIZE)
  lcd.drawText(1, 30, "CH7 " .. chText("ch7") .. "  CH11 " .. chText("ch11"), SMLSIZE)
  lcd.drawText(1, 40, "LQ " .. tostring(readNum("RQly")) .. "  RSSI " .. tostring(readNum("1RSS")), SMLSIZE)
  lcd.drawText(1, 54, "[EXIT] release+close", SMLSIZE)
  if event == EVT_VIRTUAL_EXIT then
    releaseAll()
    return 2
  end
  return 0
end

return { init = init, run = run }
