#!/usr/bin/env python3
"""solo 모드 최종 리뷰용 엣지 케이스 실증 — 실행 중인 mock 서버를 상대로 HTTP 로 때린다.

사용: python3 edge_probe.py <port>
프리셋 파일(config/venues/<행사>/presets.json)을 건드리는 테스트는 하지 않는다 (저장 경로는 별도 검증).
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
BASE = f"http://127.0.0.1:{PORT}"

results = []


def req(method, path, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers=headers or ({"Content-Type": "application/json"} if data else {}))
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body)
            except ValueError:
                return resp.status, body[:200]
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body[:200]


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}   {detail}")


def stage():
    return req("GET", "/conversation")[1]


print("=" * 70)
print("A. 패드 기본 흐름")
print("=" * 70)
req("POST", "/stage", {"stage": "idle"})
s, d = req("POST", "/stage", {"stage": "preview", "motion": "MimicWaveHand"})
check("A1 패드 preview 허용", s == 200 and d.get("stage") == "preview", str(d))
check("A2 stage=preview 반영", stage()["stage"] == "preview")

s, d = req("POST", "/motion", {"motion": "MimicWaveHand", "source": "pad"})
check("A3 패드 실행 성공", s == 200 and d.get("ok"), d.get("msg", ""))
v = stage()
check("A4 실행 후 stage=executing", v["stage"] == "executing", v["stage"])
check("A5 current_motion_state 세팅", v["current_motion_state"] == "MimicWaveHand")

s, d = req("POST", "/stage", {"stage": "preview", "motion": "MimicSquat"})
check("A6 실행 중 preview 차단(409)", s == 409, str(d))
s, d = req("POST", "/stage", {"stage": "idle"})
check("A7 실행 중 idle 복귀 허용", s == 200 and stage()["stage"] == "idle", str(d))

print()
print("=" * 70)
print("B. 패드 거부 경로")
print("=" * 70)
s, d = req("POST", "/motion", {"motion": "MimicCartwheel", "source": "pad"})
check("B1 패드 목록 밖 동작 거부", s == 200 and not d.get("ok"), d.get("msg", ""))
s, d = req("POST", "/motion", {"motion": "NoSuchMotion", "source": "pad"})
check("B2 카탈로그에 없는 동작 거부", not d.get("ok"), d.get("msg", ""))
s, d = req("POST", "/stage", {"stage": "preview", "motion": "MimicCartwheel"})
check("B3 패드 밖 동작 preview 거부", s == 400, str(d))
s, d = req("POST", "/stage", {"stage": "preview", "motion": ""})
check("B4 빈 동작 preview 거부", s == 400, str(d))
s, d = req("POST", "/stage", {"stage": "listening"})
check("B5 폐기된 stage 거부", s == 400, str(d))
s, d = req("POST", "/stage", {"stage": "dance"})
check("B6 stage 로 dance 위조 불가", s == 400, str(d))
s, d = req("POST", "/stage", {"stage": "executing"})
check("B7 stage 로 executing 위조 불가", s == 400, str(d))
req("POST", "/stage", {"stage": "idle"})

print()
print("=" * 70)
print("C. LLM/운영자 소스 분리")
print("=" * 70)
s, d = req("POST", "/motion", {"motion": "MimicShadowBoxing", "source": "llm"})
check("C1 llm 은 restricted 실행 불가", not d.get("ok"), d.get("msg", ""))
s, d = req("POST", "/motion", {"motion": "MimicShadowBoxing", "source": "manual"})
check("C2 운영자는 실행 가능", d.get("ok"), d.get("msg", ""))
req("POST", "/stage", {"stage": "idle"})

print()
print("=" * 70)
print("D. 정지 경로")
print("=" * 70)
s, d = req("POST", "/stop", {"reason": "테스트"})
check("D1 정지 응답 ok", d.get("ok"), f"motion={d.get('motion')} msg={d.get('msg')}")
check("D2 정지가 locomotion 으로 보내는가", d.get("motion") == "Velocity",
      f"→ '{d.get('motion')}' (ReadyPose 면 위반)")
st = req("GET", "/status")[1]
check("D3 status.stop_state", st.get("stop_state") == "Velocity", str(st.get("stop_state")))

print()
print("=" * 70)
print("E. 무대(dance) — 자막·차단·세대")
print("=" * 70)
presets = req("GET", "/dance/presets")[1]["presets"]
print("   프리셋:", list(presets))
name = "snucheer-rc" if "snucheer-rc" in presets else list(presets)[0]
s, d = req("POST", "/dance/start", {"name": name})
check("E1 무대 시작", s == 200 and d.get("ok"), str(d)[:120])
v = stage()
sd = v["stage_data"]
check("E2 stage=dance", v["stage"] == "dance")
check("E3 무대 자막=공식 명칭", sd.get("title") == presets[name].get("title"),
      f"title={sd.get('title')!r} credit={sd.get('credit')!r}")
check("E4 무대 중 패드 preview 차단", req("POST", "/stage", {"stage": "preview", "motion": "MimicWaveHand"})[0] == 409)
check("E5 무대 중 패드 idle 차단", req("POST", "/stage", {"stage": "idle"})[0] == 409)

# 무대 중 새 무대로 교체 → 이전 세대 발사 무력화 확인
s, d = req("POST", "/dance/start", {"name": name})
check("E6 무대 재시작 허용", d.get("ok"))
req("POST", "/dance/stop", {})
check("E7 무대 정지 후 idle", stage()["stage"] == "idle")

# 자막 없는 inline preset → 저장본에서 자막 복구되는가 (체스트팝 v2 회귀 방지)
bad = None
for k, p in presets.items():
    if "chestpop" in k.lower() or "Chestpop" in (p.get("motion") or ""):
        bad = (k, p)
        break
if bad:
    k, p = bad
    inline = {"motion": p["motion"], "media": p["media"], "seek": 0,
              "offset_ms": 0, "volume": 100}
    s, d = req("POST", "/dance/start", {"name": k, "preset": inline})
    sd = stage()["stage_data"]
    check("E8 inline preset(자막 없음) → 공식 명칭 복구",
          sd.get("title") == p.get("title"), f"title={sd.get('title')!r}")
    req("POST", "/dance/stop", {})
    # 이름조차 없는 inline (dance 화면의 '직접 설정')
    s, d = req("POST", "/dance/start", {"preset": inline})
    sd = stage()["stage_data"]
    check("E9 이름 없는 inline → 같은 음원 프리셋에서 자막 복구",
          sd.get("title") == p.get("title"), f"title={sd.get('title')!r}")
    req("POST", "/dance/stop", {})
    # 음원이 어떤 프리셋에도 없을 때 → 동작 약칭이 새는가?
    inline2 = {"motion": p["motion"], "media": "", "seek": 0, "offset_ms": 0, "volume": 100}
    s, d = req("POST", "/dance/start", {"preset": inline2})
    sd = stage()["stage_data"]
    check("E10 음원 없는 inline → 약칭이 새지 않는가",
          "체스트팝" not in str(sd.get("title") or ""),
          f"title={sd.get('title')!r} (약칭이면 위반)")
    req("POST", "/dance/stop", {})

print()
print("=" * 70)
print("F. 무대 입력 검증")
print("=" * 70)
s, d = req("POST", "/dance/start", {"name": "존재하지않는프리셋"})
check("F1 없는 프리셋 거부", s == 400 and not d.get("ok"), str(d)[:100])
s, d = req("POST", "/dance/start", {"preset": {"motion": "MimicWaveHand", "media": "없는파일.mp4"}})
check("F2 없는 음원 거부", s == 400, str(d)[:100])
s, d = req("POST", "/dance/start", {"preset": {"motion": "없는동작", "media": ""}})
check("F3 없는 동작 거부", s == 400, str(d)[:100])
s, d = req("POST", "/dance/start", {"preset": {"motion": "MimicWaveHand", "media": "", "offset_ms": "abc"}})
check("F4 숫자 아닌 offset 거부(타이머 전)", s == 400, str(d)[:100])
check("F5 거부 후 stage 오염 없음", stage()["stage"] == "idle", stage()["stage"])
s, d = req("POST", "/dance/start", {"preset": "문자열"})
check("F6 preset 타입 검증", s == 400, str(d)[:100])

print()
print("=" * 70)
print("G. 동시성 — 관객 2명이 동시에 누르기")
print("=" * 70)
req("POST", "/stage", {"stage": "idle"})
out = []
lock = threading.Lock()


def hammer(motion):
    s, d = req("POST", "/motion", {"motion": motion, "source": "pad"})
    with lock:
        out.append((motion, d.get("ok"), d.get("msg")))


ts = [threading.Thread(target=hammer, args=(m,)) for m in
      ["MimicWaveHand", "MimicSquat", "MimicBowNavel", "MimicChefsKiss"]]
[t.start() for t in ts]
[t.join() for t in ts]
oks = sum(1 for _, ok, _ in out if ok)
check("G1 mock 은 동시 요청 전부 수락(로봇 게이트웨이가 막는 구조)", oks == 4,
      f"{oks}/4 수락 — mock 특성. 실기에선 gateway busy 가 거부")
v = stage()
check("G2 동시 요청 후 stage 정상", v["stage"] in ("executing", "idle"), v["stage"])
req("POST", "/stage", {"stage": "idle"})

print()
print("=" * 70)
print("H. RC 모드 토글 (하드웨어 없음)")
print("=" * 70)
t0 = time.time()
s, d = req("POST", "/rc/mode", {"on": True})
dt = time.time() - t0
check("H1 RC 없는데 켜면 실패로 응답", s == 400 and not d.get("ok"), d.get("msg", ""))
check("H2 실패 후 백엔드 원상복귀", d.get("backend") == "mock", str(d.get("backend")))
check("H3 토글 응답시간", dt < 5, f"{dt:.2f}s (State.lock 을 쥐고 있는 구간)")
st = req("GET", "/status")[1]
check("H4 실패 후 status 정상", st.get("backend") == "mock", str(st.get("backend")))
s, d = req("POST", "/rc/mode", {"on": False})
check("H5 RC 끄기(이미 꺼짐) 안전", s == 200 and d.get("ok"), d.get("msg", ""))

print()
print("=" * 70)
print("I. 미디어/클립 전송")
print("=" * 70)
r = urllib.request.Request(BASE + "/clips/MimicWaveHand.mp4", headers={"Range": "bytes=0-99"})
with urllib.request.urlopen(r, timeout=10) as resp:
    check("I1 클립 Range 206", resp.status == 206, resp.headers.get("Content-Range"))
r = urllib.request.Request(BASE + "/clips/MimicWaveHand.mp4", headers={"Range": "bytes=99999999999-"})
try:
    with urllib.request.urlopen(r, timeout=10) as resp:
        check("I2 범위 초과 416", False, f"status={resp.status}")
except urllib.error.HTTPError as e:
    check("I2 범위 초과 416", e.code == 416, str(e.code))
s, d = req("GET", "/clips/..%2F..%2Fetc%2Fpasswd")
check("I3 경로 탈출 차단", s == 404, str(s))
s, d = req("GET", "/media/..%2F..%2Fetc%2Fpasswd")
check("I4 미디어 경로 탈출 차단", s == 404, str(s))
s, d = req("GET", "/clips/MimicCartwheel.mp4")
check("I5 클립 없는 동작 404", s == 404, str(s))

print()
print("=" * 70)
print("J. 잘못된 입력에 대한 서버 강건성")
print("=" * 70)
try:
    r = urllib.request.Request(BASE + "/motion", data=b"{not json",
                               headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(r, timeout=5) as resp:
        check("J1 깨진 JSON", False, f"status={resp.status}")
except urllib.error.HTTPError as e:
    check("J1 깨진 JSON → HTTP 오류 응답", True, f"{e.code}")
except Exception as e:
    check("J1 깨진 JSON → 연결 끊김(응답 없음)", False, f"{type(e).__name__}: {e}")
# 서버가 살아있는지
s, d = req("GET", "/status")
check("J2 깨진 요청 후에도 서버 생존", s == 200)
s, d = req("POST", "/motion", {})
check("J3 빈 payload 처리", s == 200 and not d.get("ok"), d.get("msg", ""))
s, d = req("GET", "/no-such-path")
check("J4 없는 경로 404", s == 404)

print()
print("=" * 70)
n_fail = sum(1 for _, ok, _ in results if not ok)
print(f"총 {len(results)}개 중 실패 {n_fail}개")
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL  {name}  {detail}")
