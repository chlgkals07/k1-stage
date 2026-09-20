"""RcBackend — 명령을 Wi-Fi 게이트웨이 대신 유선 RC(ELRS)로 보내는 백엔드.

경로: server.py → RcBackend → rc_serial(USB) → K1PC.lua → L1 펄스 → ELRS → 로봇.
로봇 쪽에는 정상 RC 입력으로 보이므로 로봇 소프트웨어 수정이 없다.

relay 경로에서 로봇 게이트웨이가 해주던 busy/cooldown 검사는 RC 경로에 없으므로
여기서 직접 구현한다. 완료 신호도 없으므로 동작 길이(rc_list note 의 "Xs", 없으면
기본값)를 타이머로 추정한다.

동작명→다이얼 위치 매핑은 motions.yaml `rc_list` (2026-08-15 로봇 실배포
k1_config 덤프)를 그대로 읽는다. 실배포와의 일치는 로봇 복구 후 재검증(P2).
"""

import re
import threading
import time
from pathlib import Path

import yaml

from . import clip_len
from .rc_serial import RcSerial

DEFAULT_DURATION_SEC = 30.0
# 클립 길이로 추정할 때의 여백. 패드 진행바(클립+2.0s)와 같은 값이라
# 로봇 busy 해제·패드 잠금 해제가 같은 시각에 온다.
BUSY_MARGIN_SEC = 2.0
PREP_VALID_SEC = 8.0  # 라디오 쪽 PREP 자동 해제(10s)보다 짧게


def _parse_duration(note):
    """note 문자열에서 "21.8s" 류를 찾아 초로. 없으면 None."""
    if not note:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)s", note)
    return float(m.group(1)) if m else None


def _model_us(pct):
    """GV(pct)가 믹서를 거쳐 나올 출력 µs — K1PC 화면·CHK 와 같은 변환."""
    raw = int(1024 * pct / 100)
    return 1500 + int(raw / 2 + (0.5 if raw >= 0 else -0.5))


def _parse_obs(line):
    """'OK RUN 6 ch5=.. ch11=..' 응답 꼬리의 관측값 파싱 (없으면 빈 dict)."""
    obs = {}
    for token in (line or "").split():
        if "=" in token:
            key, val = token.split("=", 1)
            try:
                obs[key] = int(val)
            except ValueError:
                pass
    return obs


def _verify_obs(entry, obs):
    """발사 순간 라디오가 보고한 실측 출력 vs 기대값. (판정문, 일치 여부)."""
    if not obs:
        return "관측값 없음 (K1PC v2.2 필요)", True  # 구버전 호환 — 실패로 치지 않음
    exp11 = _model_us(-100 + (entry["slot"] - 1) * 4)
    exp5 = _model_us(-100 if entry["bank"] == "A" else 100)
    ok = (abs(obs.get("ch11", -9999) - exp11) <= 3
          and abs(obs.get("ch5", -9999) - exp5) <= 3
          and obs.get("ch6", 0) >= 1950 and obs.get("ch7", 0) >= 1950)
    verdict = ("발사 관측 OK" if ok else "발사 관측 불일치!")
    return (f"{verdict} ch11 {obs.get('ch11')}/{exp11} ch5 {obs.get('ch5')}/{exp5} "
            f"ch6 {obs.get('ch6')} ch7 {obs.get('ch7')}"), ok


def load_rc_map(motions_path):
    """rc_list → {state: {bank, slot, ko, duration_sec}}. slot 은 1..20 (ch11 기준)."""
    data = yaml.safe_load(open(motions_path, encoding="utf-8"))
    rc = data.get("rc_list") or {}
    mapping = {}
    for bank_name, bank in (rc.get("banks") or {}).items():
        for entry in bank.get("slots") or []:
            ch11 = entry.get("ch11")
            state = entry.get("state")
            if not state or ch11 is None:
                continue
            slot = (int(ch11) - 1000) // 20 + 1
            if not 1 <= slot <= 20:
                continue
            mapping[state] = {
                "bank": bank_name, "slot": slot, "ko": entry.get("ko", state),
                "duration_sec": _parse_duration(entry.get("note")) or DEFAULT_DURATION_SEC,
            }
    cooldowns = {}
    for entry in (data.get("motions") or []) + (data.get("control_states") or []):
        if entry.get("cooldown_sec"):
            cooldowns[entry["state"]] = float(entry["cooldown_sec"])
    return mapping, cooldowns


class RcBackend:
    name = "rc"

    def __init__(self, motions_path, gateway_config_path=None, serial=None):
        motions_path = Path(motions_path)
        self.rc_map, self._cooldowns = load_rc_map(motions_path)
        self._clips = motions_path.parent / "static" / "clips"
        # 주의: api_allowlist **속성**은 일부러 두지 않는다 — 두면 State 가 패드·LLM
        # 목록을 여기에 교집합해 버린다. UI(패드 12개·운영자 목록)는 primary 경로와
        # 완전히 동일해야 한다 (2026-08-18 사용자 확정). 다만 운영자 화면은 목록을
        # /status 의 api_allowlist 에서 읽으므로, 그 값만 primary 와 같게 실어 보낸다.
        # 이게 없으면 RC 모드로 켜는 순간 수동 실행 버튼이 통째로 사라진다.
        self._api_allowlist = []
        if gateway_config_path:
            try:
                cfg = yaml.safe_load(Path(gateway_config_path).read_text(encoding="utf-8"))
                self._api_allowlist = sorted(cfg["policy"].get("api_allowlist") or [])
            except (OSError, ValueError, KeyError, TypeError):
                self._api_allowlist = []
        self.serial = serial or RcSerial()
        self._tlm_cache = ({"ok": False}, 0.0)
        self._tlm_refresh = threading.Lock()
        self._lock = threading.Lock()
        self._busy_motion = None
        self._busy_until = 0.0
        self._cooldown_until = {}
        self._prepared = None       # (motion, expires_monotonic)
        self._last_event = {"status": "idle", "msg": "대기"}
        self._seq = 0

    # ── 내부 ─────────────────────────────────────────────────

    def _reject(self, motion, msg):
        self._last_event = {"status": "rejected", "msg": msg}
        return {"ok": False, "status": "rejected", "motion": motion,
                "request_id": None, "msg": msg}

    def _busy_left(self):
        return max(0.0, self._busy_until - time.monotonic())

    # ── MotionBackend 계약 ────────────────────────────────────

    def submit(self, motion, source, reason):
        with self._lock:
            entry = self.rc_map.get(motion)
            if entry is None:
                return self._reject(motion, "RC 다이얼에 없는 동작입니다")
            if self._busy_left() > 0:
                return self._reject(
                    motion, f"로봇이 이미 동작을 실행 중입니다 ({self._busy_motion}, "
                            f"약 {self._busy_left():.0f}s 남음)")
            cool = self._cooldown_until.get(motion, 0.0) - time.monotonic()
            if cool > 0:
                return self._reject(motion, f"cooldown {cool:.0f}s 남음")

            prepared = self._prepared
            self._prepared = None
            t_send = time.time()
            if prepared and prepared[0] == motion and time.monotonic() < prepared[1]:
                res = self.serial.fire()
                how = "FIRE(사전 준비됨)"
            else:
                res = self.serial.run(entry["slot"], entry["bank"])
                how = f"RUN 뱅크{entry['bank']} 슬롯{entry['slot']}"
            print(f"[rc] {how} {motion} 전송 t={t_send:.3f} → "
                  f"{'OK' if res.get('ok') else res.get('msg', '')}", flush=True)
            if not res.get("ok"):
                return self._reject(motion, res.get("msg", "RC 전송 실패"))

            # 라디오가 발사 순간(코드 유지 종료 시점)의 실측 출력을 응답에 실어 준다 —
            # 화면 육안 확인을 대신하는 매 발사 자동 검증.
            verdict, obs_ok = _verify_obs(entry, _parse_obs(res.get("line")))
            print(f"[rc] {verdict}", flush=True)

            self._seq += 1
            duration = self.motion_duration(motion) or entry["duration_sec"]
            self._busy_motion = motion
            self._busy_until = time.monotonic() + duration
            if motion in self._cooldowns:
                self._cooldown_until[motion] = (
                    self._busy_until + self._cooldowns[motion])
            self._last_event = {"status": "queued" if obs_ok else "warning",
                                "msg": f"RC 발사: {entry['ko']} — {verdict}"}
            return {"ok": True, "status": "queued", "motion": motion,
                    "request_id": f"rc-{self._seq}",
                    "msg": f"RC로 실행 ({how}, 추정 {duration:.0f}s) · {verdict}"}

    def motion_duration(self, motion):
        """추정 길이(초). 무대 자동 종료 fallback 과 busy 잠금이 쓴다.

        rc_list note 에 길이가 적힌 슬롯은 40개 중 2개뿐이라 나머지는 전부 기본 30초로
        잠겼다 — 4초짜리 손인사에도 관객 패드가 30초 멈춘다. 같은 동작으로 구운 sim
        클립 길이가 실제 동작 길이이므로 그걸 먼저 본다 (없으면 기존 값 그대로).
        """
        entry = self.rc_map.get(motion)
        if entry is None:
            return None
        if entry["duration_sec"] != DEFAULT_DURATION_SEC:
            return entry["duration_sec"]        # note 에 명시된 값이 우선
        length = clip_len.clip_duration(self._clips, motion)
        if length is None:
            return entry["duration_sec"]
        # 여백 없이 클립 길이만 쓰면 로봇이 마무리 동작 중일 때 다음 명령이 나갈 수 있다.
        # 패드 진행바(클립+2.0s)와 같은 여백을 둬서 셋(로봇 busy·패드·화면)이 어긋나지 않게 한다.
        return length + BUSY_MARGIN_SEC

    def prepare(self, motion):
        """dance 싱크용 사전 PREP — 발사 엣지(FIRE)의 지터를 ms급으로 줄인다.

        실패해도 치명적이지 않다: submit 이 RUN 으로 폴백한다.
        """
        with self._lock:
            entry = self.rc_map.get(motion)
            if entry is None or self._busy_left() > 0:
                return False
            res = self.serial.prep(entry["slot"], entry["bank"])
            print(f"[rc] PREP 뱅크{entry['bank']} 슬롯{entry['slot']} {motion} "
                  f"t={time.time():.3f} → {'OK' if res.get('ok') else res.get('msg', '')}",
                  flush=True)
            if res.get("ok"):
                self._prepared = (motion, time.monotonic() + PREP_VALID_SEC)
                return True
            return False

    def stop_motion(self, source, reason=""):
        """정지 = locomotion(Velocity, code 3) 복귀.

        ReadyPose(code 2)는 로봇에서 균형 정책이 없는 고정 자세라 동작 중에 선점하면
        넘어질 수 있다. Mimic 도 `on_complete: Velocity` 로 스스로 여기 복귀하므로
        Velocity 가 이 로봇의 정상 대기 상태다 (2026-08-18 사용자 확정).

        라디오의 K1PC.lua 가 아직 VEL 을 모르는 버전이면 ERR 이 오므로 기존 STOP 으로
        폴백한다 — SD 카드를 갱신하지 않아도 예전과 똑같이 동작한다.
        """
        with self._lock:
            self._prepared = None
            target = "Velocity"
            res = self.serial.vel()
            if not res.get("ok") and "ERR" in str(res.get("msg", "")):
                target = "ReadyPose"          # 구버전 K1PC — 예전 동작 유지
                res = self.serial.stop_pulse()
            if not res.get("ok"):
                # 전송이 실패했으면 로봇은 여전히 돌고 있다. busy 를 지우면 다음 명령이
                # 실행 중인 로봇으로 나간다 — 실패 시에는 그대로 둔다.
                self._last_event = {"status": "error", "msg": res.get("msg", "")}
                return {"ok": False, "status": "error", "motion": target,
                        "request_id": None, "msg": res.get("msg", "RC 정지 실패")}
            self._busy_motion = None
            self._busy_until = 0.0
            self._last_event = {"status": "queued", "msg": f"정지({target}) 펄스"}
            return {"ok": True, "status": "queued", "motion": target,
                    "request_id": None, "msg": f"RC 정지 펄스 전송 ({target})"}

    def connect_check(self):
        """토글 ON 시의 연결 진단. (ok, 원인 메시지)를 돌려준다."""
        res = self.serial.ping()
        if res.get("ok"):
            return True, "RC 연결됨"
        msg = res.get("msg", "")
        if "포트" in msg:
            return False, "RC 포트 없음 — 전원 ON + 위쪽 USB-C + 팝업에서 Serial 선택"
        return False, ("RC 무응답 — 라디오에서 USB-VCP=LUA 인지, "
                       "SYS→Tools→K1PC 가 열려 있는지 확인")

    def _tlm_cached(self):
        """TLM 은 1초 캐시 + 동시에 한 번만 갱신한다.

        운영자·패드·댄스 화면이 각자 1~2초마다 /status 를 부르고, TLM 은 시리얼 락을
        잡는다. 라디오가 무응답이면 한 번에 1.5초씩 물고 있어 빨간 정지가 폴링 뒤에
        줄을 선다 (리뷰에서 3개 폴링 기준 7초 지연 재현).

        캐시만으로는 부족하다 — 만료되는 순간 폴러 셋이 동시에 실측으로 몰려간다.
        갱신은 한 번에 하나만 하고, 나머지는 직전 값을 그대로 받아 간다.
        """
        cached, at = self._tlm_cache
        if time.monotonic() - at < 1.0:
            return cached
        if not self._tlm_refresh.acquire(blocking=False):
            return cached                      # 다른 폴러가 이미 갱신 중
        try:
            tlm = self.serial.tlm()
            self._tlm_cache = (tlm, time.monotonic())
            return tlm
        finally:
            self._tlm_refresh.release()

    def status(self):
        tlm = self._tlm_cached()
        with self._lock:
            busy = self._busy_left() > 0
            current = ({"motion": self._busy_motion,
                        "remaining_sec": round(self._busy_left())}
                       if busy else None)
            return {
                # UI(canSubmit)가 아는 상태 라벨로 보고한다: 시리얼이 살아 있으면
                # "ready" — 실행 버튼이 잠기지 않게 하는 핵심.
                "gateway": "ready" if tlm.get("ok") else "offline",
                "robot": {"rc_link": tlm.get("ok", False),
                          "lq": tlm.get("lq"), "rssi": tlm.get("rssi"),
                          "note": self.serial.last_error or "유선 RC 경로 (상태는 추정)"},
                "current_request": current,
                # 운영자 화면의 수동 실행 목록은 이 값에서 나온다 — primary 경로와
                # 같은 목록을 실어야 RC 로 전환해도 버튼이 그대로 남는다.
                "api_allowlist": list(self._api_allowlist),
                "stop_state": "Velocity",
                "stop_available": True,
                "last_event": dict(self._last_event),
            }

    def stop(self):
        self.serial.close()
