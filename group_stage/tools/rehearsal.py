#!/usr/bin/env python3
"""최종 mock 리허설 — 패드·운영자·디스플레이 3면을 동시에 흉내 내어 전체 쇼를 돌린다.

디스플레이 시뮬레이터는 display.html 의 폴링·렌더·영상종료 처리를 그대로 재현하고,
화면 전이 로그를 남긴다. "이상한 화면"이나 "대기 화면으로 안 돌아감"을 잡는 것이 목적.

사용: python3 rehearsal.py <port> [--fast]
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
BASE = f"http://127.0.0.1:{PORT}"
FAST = "--fast" in sys.argv

problems = []


def req(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {}


# ────────────────────────────────────────────── 디스플레이 시뮬레이터
class Display(threading.Thread):
    """display.html 재현: 300ms 폴링 + stage_rev 변화 시 렌더 + 영상 ended 처리."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.running = True
        self.screen = None            # idle / preview / executing / dance
        self.transitions = []         # (t, screen, 화면에 뜬 글자)
        self.last_stage_rev = -1
        self.last_rev = -1
        self.dance_key = ""
        self.dance_end_at = None
        self.dance_media_len = {}     # media -> 길이(초). 프리셋 media_len_sec 사용
        self.lock = threading.Lock()

    def note(self, screen, text):
        with self.lock:
            self.transitions.append((round(time.time() - T0, 2), screen, text))
        print(f"    [display {time.time()-T0:6.2f}s] {screen:9s} | {text}")

    def run(self):
        while self.running:
            try:
                _, d = req("GET", "/conversation")
            except Exception:
                time.sleep(0.3)
                continue
            if d.get("stage_rev") != self.last_stage_rev or d.get("rev") != self.last_rev:
                self.last_stage_rev = d.get("stage_rev")
                self.last_rev = d.get("rev")
                self.render(d)
            # 영상 종료 → /dance/stop (display.html 의 ended 핸들러 + 1.2s 지연)
            if self.dance_end_at and time.time() >= self.dance_end_at:
                self.dance_end_at = None
                req("POST", "/dance/stop", {})
                self.note("(영상종료)", "→ /dance/stop 전송")
            time.sleep(0.3)

    def render(self, d):
        stage = d.get("stage", "idle")
        sd = d.get("stage_data") or {}
        if stage != "dance":
            self.dance_key = ""
            self.dance_end_at = None
        if stage == "preview":
            self.screen = "preview"
            self.note("preview", f"클립 재생: {sd.get('motion')} · 자막 {sd.get('ko')!r}")
        elif stage == "executing":
            self.screen = "executing"
            self.note("executing", f"'로봇이 동작 중입니다' · {sd.get('ko')!r}")
        elif stage == "dance":
            self.screen = "dance"
            key = f"{sd.get('name')}:{sd.get('media_at')}"
            title = sd.get("title") or sd.get("ko") or sd.get("name") or ""
            credit = sd.get("credit") or ""
            self.note("dance", f"제목 {title!r} · 출처 {credit!r} · 음원 {sd.get('media')!r}")
            if "체스트팝" in title or "스키즈" in title or "응원 " == title[:4]:
                problems.append(f"무대 자막에 동작 약칭 노출: {title!r}")
            if key != self.dance_key:
                self.dance_key = key
                delta = d["server_now"] - time.time()
                wait = max(0, sd.get("media_at", 0) - delta - time.time())
                length = self.dance_media_len.get(sd.get("media"), 10)
                if FAST:
                    length = min(length, 6)
                self.dance_end_at = time.time() + wait + length
                self.note("dance", f"영상 {wait:.1f}s 뒤 재생 시작, 길이 {length:.1f}s")
        else:
            self.screen = "idle"
            self.note("idle", "대기 화면(전체화면 이미지)")

    def stop(self):
        self.running = False


# ────────────────────────────────────────────── 패드 시뮬레이터
class Pad:
    """pad.html 재현: 폴링 상태 + padLocked + preview → 실행 → 진행바 → idle."""

    def __init__(self):
        self.stage_now = "idle"
        self.busy_until = 0
        self.backend = ""
        self.gateway = "offline"

    def poll(self):
        _, s = req("GET", "/status")
        self.gateway = s.get("gateway", "offline")
        self.backend = s.get("backend", "")
        cur = s.get("current_request")
        if cur and cur.get("motion"):
            self.busy_until = max(self.busy_until, time.time() + 1.5)
        _, c = req("GET", "/conversation")
        self.stage_now = c.get("stage", "idle")

    def locked(self):
        return self.stage_now in ("dance", "executing") or time.time() < self.busy_until

    def can_submit(self):
        return self.backend == "mock" or self.gateway == "ready"

    def press(self, motion):
        self.poll()
        if self.locked():
            return "잠김(터치 무시)"
        s, d = req("POST", "/stage", {"stage": "preview", "motion": motion})
        return "preview" if s == 200 else f"preview 거부 {s} {d}"

    def execute(self, motion, clip_len=3.0):
        self.poll()
        if self.locked() or not self.can_submit():
            return "실행 잠김"
        s, d = req("POST", "/motion", {"motion": motion, "source": "pad"})
        if not d.get("ok"):
            return f"거부: {d.get('msg')}"
        # pad.html: execDuration = 클립길이+2s, busyUntil = execUntil, 같은 시각에 idle 전송
        dur = 2.0 if FAST else clip_len + 2.0
        self.busy_until = time.time() + dur
        time.sleep(dur)
        req("POST", "/stage", {"stage": "idle"})
        return "실행 완료 → idle 복귀"


T0 = time.time()
print("=" * 74)
print("최종 mock 리허설 — 패드/운영자/디스플레이 동시 구동")
print("=" * 74)

_, m = req("GET", "/motions")
pad_list = m["pad_allowed"]
ko = {x["state"]: x.get("ko", x["state"]) for x in m["all"]}
_, pr = req("GET", "/dance/presets")
presets = pr["presets"]

display = Display()
display.dance_media_len = {p["media"]: p.get("media_len_sec") or 10
                           for p in presets.values() if p.get("media")}
display.start()
pad = Pad()
time.sleep(0.6)

print()
print("── 1막: 관객이 패드 버튼 12개를 차례로 누른다 " + "─" * 24)
for i, state in enumerate(pad_list, 1):
    r1 = pad.press(state)
    time.sleep(0.5)
    r2 = pad.execute(state, clip_len=2.0)
    print(f"  {i:02d} {ko.get(state, state):14s} {state:30s} preview={r1:10s} 실행={r2}")
    if "거부" in r2 or "잠김" in r2:
        problems.append(f"패드 {i:02d} {state}: {r2}")
    time.sleep(0.4)

time.sleep(1.2)
if display.screen != "idle":
    problems.append(f"패드 12개 실행 후 디스플레이가 idle 이 아님: {display.screen}")
print(f"  → 12개 종료 후 디스플레이 화면: {display.screen}")

print()
print("── 2막: 관객이 preview 만 하고 취소한다 " + "─" * 30)
pad.press(pad_list[0])
time.sleep(0.6)
req("POST", "/stage", {"stage": "idle"})
time.sleep(0.6)
print(f"  → 취소 후 디스플레이 화면: {display.screen}")
if display.screen != "idle":
    problems.append(f"preview 취소 후 idle 복귀 실패: {display.screen}")

print()
print("── 3막: 무대 3종 (음악 싱크) " + "─" * 40)
stage_presets = [n for n in presets if n.endswith("-api")] or list(presets)
for name in stage_presets:
    print(f"  ▶ 무대 시작: {name}")
    s, d = req("POST", "/dance/start", {"name": name})
    if not d.get("ok"):
        problems.append(f"무대 시작 실패 {name}: {d}")
        continue
    # 무대 중 관객이 눌러 본다 (잠겨야 한다)
    time.sleep(1.0)
    r = pad.press(pad_list[3])
    print(f"     무대 중 패드 터치 → {r}")
    if r == "preview":
        problems.append(f"무대 중 패드가 무대를 가로챘다 ({name})")
    # 영상이 끝날 때까지 대기 (display 가 /dance/stop 을 보낸다)
    deadline = time.time() + (14 if FAST else 100)
    while time.time() < deadline:
        if display.screen == "idle":
            break
        time.sleep(0.4)
    print(f"     무대 종료 후 화면: {display.screen}")
    if display.screen != "idle":
        problems.append(f"무대 {name} 종료 후 idle 복귀 실패: {display.screen}")
    time.sleep(0.8)

print()
print("── 4막: 운영자 수동 실행 → 관객 패드가 풀리는가 " + "─" * 22)
req("POST", "/stage", {"stage": "idle"})
time.sleep(0.5)
s, d = req("POST", "/motion", {"motion": "MimicBowNavel", "source": "manual",
                               "reason": "운영자 수동"})
print(f"  운영자 실행: ok={d.get('ok')}")
t_lock = time.time()
released = None
for _ in range(30):          # 15초 관찰
    pad.poll()
    if not pad.locked():
        released = time.time() - t_lock
        break
    time.sleep(0.5)
if released is None:
    problems.append("운영자 수동 실행 후 15초가 지나도 패드 잠금이 안 풀린다 "
                    "(stage=executing TTL 60초까지 유지)")
    print(f"  → 15초 경과: 패드 여전히 잠김 (stage={pad.stage_now}), 디스플레이={display.screen}")
else:
    print(f"  → {released:.1f}s 만에 해제")
req("POST", "/stage", {"stage": "idle"})

print()
print("── 5막: 운영자 정지 버튼 " + "─" * 44)
s, d = req("POST", "/stop", {"reason": "리허설 정지"})
print(f"  정지 응답: motion={d.get('motion')} · {d.get('msg')}")
if d.get("motion") == "ReadyPose":
    problems.append("정지 버튼이 로봇에 ReadyPose(균형 없는 고정 자세)를 요청한다 "
                    "— 사용자 요구는 locomotion(Velocity) 우선")
time.sleep(1.0)
print(f"  → 정지 후 디스플레이 화면: {display.screen}")

print()
print("── 6막: 디스플레이가 죽었다 살아난다 (재접속 합류) " + "─" * 18)
display.stop()
time.sleep(0.5)
req("POST", "/dance/start", {"name": stage_presets[0]})
time.sleep(1.5)
display2 = Display()
display2.dance_media_len = display.dance_media_len
display2.start()
time.sleep(1.5)
print(f"  → 재접속 디스플레이 화면: {display2.screen} (진행 중 무대에 합류해야 정상)")
if display2.screen != "dance":
    problems.append(f"재접속한 디스플레이가 진행 중 무대에 합류하지 못함: {display2.screen}")
req("POST", "/dance/stop", {})
time.sleep(1.0)
print(f"  → 무대 정지 후: {display2.screen}")
display2.stop()

print()
print("=" * 74)
if problems:
    print(f"리허설에서 발견된 문제 {len(problems)}건")
    for p in problems:
        print(f"  ✗ {p}")
else:
    print("리허설 문제 없음")
print("=" * 74)
