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

import yaml

from rc_serial import RcSerial

DEFAULT_DURATION_SEC = 30.0
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
        self.rc_map, self._cooldowns = load_rc_map(motions_path)
        # 주의: api_allowlist 속성을 일부러 두지 않는다 — UI(패드 12개·운영자 목록)는
        # primary 경로와 완전히 동일해야 한다 (2026-08-18 사용자 확정). 다이얼에 없는
        # 동작은 submit 시점에 rc_map 조회로 거부되고, 목록 정합은 추후 로봇 다이얼
        # 테이블을 조정해 맞춘다.
        self.serial = serial or RcSerial()
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
            self._busy_motion = motion
            self._busy_until = time.monotonic() + entry["duration_sec"]
            if motion in self._cooldowns:
                self._cooldown_until[motion] = (
                    self._busy_until + self._cooldowns[motion])
            self._last_event = {"status": "queued" if obs_ok else "warning",
                                "msg": f"RC 발사: {entry['ko']} — {verdict}"}
            return {"ok": True, "status": "queued", "motion": motion,
                    "request_id": f"rc-{self._seq}",
                    "msg": f"RC로 실행 ({how}, 추정 {entry['duration_sec']:.0f}s) · {verdict}"}

    def motion_duration(self, motion):
        """rc_list 에 기록된 추정 길이(초). 무대 자동 종료 fallback 이 쓴다."""
        entry = self.rc_map.get(motion)
        return entry["duration_sec"] if entry else None

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
        with self._lock:
            self._prepared = None
            res = self.serial.stop_pulse()
            self._busy_motion = None
            self._busy_until = 0.0
            if not res.get("ok"):
                self._last_event = {"status": "error", "msg": res.get("msg", "")}
                return {"ok": False, "status": "error", "motion": "ReadyPose",
                        "request_id": None, "msg": res.get("msg", "RC 정지 실패")}
            self._last_event = {"status": "queued", "msg": "정지(ReadyPose) 펄스"}
            return {"ok": True, "status": "queued", "motion": "ReadyPose",
                    "request_id": None, "msg": "RC 정지 펄스 전송"}

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

    def status(self):
        tlm = self.serial.tlm()
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
                "stop_state": "ReadyPose",
                "stop_available": True,
                "last_event": dict(self._last_event),
            }

    def stop(self):
        self.serial.close()
