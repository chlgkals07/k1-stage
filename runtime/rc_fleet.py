"""RcFleetBackend — 그 순간 연결된 RadioMaster Pocket **전부**에 명령을 동시에 쏜다.

로봇 식별 설정이 없다: USB 에 꽂힌 Pocket 수가 곧 플릿 크기다 (군무는 전 대가
같은 모션이라 어느 라디오가 어느 로봇인지 구분할 필요가 없다). 각 라디오는
독립 RcBackend(자체 keepalive·시리얼)로 움직이고, 발사는 스레드+Barrier 로
동시에 나간다 — PC 쪽 시차 <1ms, 로봇 간 체감 시차는 라디오 처리 지터(~30ms) 수준.

백엔드 계약(name/submit/stop_motion/status/stop + prepare/motion_duration)을
그대로 구현하므로 app.py 의 State·dance 스케줄러는 단일 로봇 때와 동일하게 동작한다.
"""

import glob
import os
import re
import subprocess
import threading

from .rc_backend import RcBackend
from .rc_serial import RcSerial, BY_ID_PATTERN

# 라디오가 여러 대라 TLM 응답을 짧게만 기다린다 (단일 로봇은 rc_serial.TLM_TIMEOUT_S).
FLEET_TLM_TIMEOUT_S = 0.6


BY_PATH_DIR = "/dev/serial/by-path"


def discover_ports():
    """연결된 Pocket 들의 안정 경로 목록.

    **by-id 를 쓰면 안 된다**: 같은 EdgeTX 빌드를 올린 라디오들이 USB 시리얼 번호를
    똑같이(00000000001B) 보고해 by-id 심볼릭 링크가 하나만 생긴다 — 2대를 꽂아도
    1대만 발견된다 (2026-08-21 실측). 대신 **by-path**(물리 USB 포트 기준)로 열거하고,
    같은 tty 를 가리키는 중복 링크(usb-/usbv2- 두 판)는 하나로 접는다.
    """
    seen, ports = set(), []
    for path in sorted(glob.glob(f"{BY_PATH_DIR}/*")):
        try:
            target = os.path.realpath(path)
        except OSError:
            continue
        if not re.search(r"/ttyACM\d+$", target) or target in seen:
            continue
        if not _is_pocket(target):
            continue
        seen.add(target)
        ports.append(path)
    if ports:
        return ports
    # by-path 가 없는 환경(가상 pty 등)에서는 기존 by-id 방식으로 떨어진다
    return sorted(glob.glob(BY_ID_PATTERN))


def _is_pocket(tty_path):
    """해당 tty 가 RadioMaster Pocket 인지 (VID:PID 0483:5740)."""
    try:
        out = subprocess.run(["udevadm", "info", "-q", "property", "-n", tty_path],
                             capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return True   # udevadm 이 없으면 걸러내지 않는다
    return "ID_MODEL_ID=5740" in out and "ID_VENDOR_ID=0483" in out


def _short_name(port):
    """표시 이름. 시리얼이 겹치므로 물리 포트(by-path) 꼬리를 쓴다."""
    m = re.search(r"usb-0:([0-9.]+):", port)
    if m:
        return f"rc-p{m.group(1)}"
    m = re.search(r"Serial_Port_0*([0-9A-Fa-f]+)-", port)
    return f"rc-{m.group(1)}" if m else port.rsplit("/", 1)[-1]


class RcFleetBackend:
    name = "rc"

    def __init__(self, motions_path, gateway_config_path=None, clips_dir=None):
        self._motions_path = motions_path
        self._clips_dir = clips_dir
        self._lock = threading.Lock()
        self.units = {}   # 이름 -> RcBackend
        self._last_event = {"status": "idle", "msg": "대기"}
        self.rescan()

    # ── 플릿 구성 ─────────────────────────────────────────────

    def rescan(self):
        """USB 를 다시 열거해 현재 꽂힌 Pocket 전부와 연결한다."""
        with self._lock:
            for unit in self.units.values():
                unit.stop()
            self.units = {}
            for port in discover_ports():
                unit_name = _short_name(port)
                self.units[unit_name] = RcBackend(
                    self._motions_path, clips_dir=self._clips_dir,
                    serial=RcSerial(port_pattern=port, tlm_timeout_s=FLEET_TLM_TIMEOUT_S))
            return sorted(self.units)

    def connect_check(self):
        with self._lock:
            units = dict(self.units)
        if not units:
            return False, ("Pocket 이 안 보임 — 전원 ON + 위쪽 USB-C + "
                           "팝업에서 Serial 선택 후 [USB 재탐색]")
        parts, any_ok = [], False
        for unit_name, unit in sorted(units.items()):
            ok, msg = unit.connect_check()
            any_ok = any_ok or ok
            parts.append(f"{unit_name} {'연결됨' if ok else '무응답'}")
        summary = f"{len(units)}대 발견 — " + ", ".join(parts)
        if not any_ok:
            summary += " (라디오에서 VCP=LUA + Tools>K1PC 확인)"
        return any_ok, summary

    # ── 팬아웃 ────────────────────────────────────────────────

    def _fanout(self, fn_name, *args, **kwargs):
        """전 대에 같은 호출을 동시에 (Barrier 로 출발선 정렬). {이름: 결과}."""
        with self._lock:
            units = dict(self.units)
        if not units:
            return {}
        barrier = threading.Barrier(len(units))
        results, threads = {}, []

        def call(unit_name, unit):
            try:
                barrier.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass
            try:
                results[unit_name] = getattr(unit, fn_name)(*args, **kwargs)
            except Exception as exc:
                results[unit_name] = {"ok": False, "msg": f"예외: {exc}"}

        for unit_name, unit in units.items():
            t = threading.Thread(target=call, args=(unit_name, unit), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=10)
        return results

    # ── MotionBackend 계약 ────────────────────────────────────

    def submit(self, motion, source, reason):
        results = self._fanout("submit", motion, source, reason)
        if not results:
            self._last_event = {"status": "rejected", "msg": "연결된 라디오 없음"}
            return {"ok": False, "status": "rejected", "motion": motion,
                    "request_id": None, "msg": "연결된 라디오가 없습니다 — USB 재탐색"}
        ok_units = sorted(n for n, r in results.items() if r.get("ok"))
        bad = {n: r.get("msg", "") for n, r in results.items() if not r.get("ok")}
        if not ok_units:
            first_msg = next(iter(bad.values()), "전 대 실패")
            self._last_event = {"status": "rejected", "msg": first_msg}
            return {"ok": False, "status": "rejected", "motion": motion,
                    "request_id": None, "msg": f"전 대 실패: {first_msg}"}
        msg = f"{len(ok_units)}/{len(results)}대 발사"
        if bad:
            msg += " · 실패: " + ", ".join(f"{n}({m})" for n, m in bad.items())
        sample = results[ok_units[0]]
        self._last_event = {"status": "queued", "msg": msg}
        return {"ok": True, "status": "queued", "motion": motion,
                "request_id": sample.get("request_id"),
                "msg": f"{msg} · {sample.get('msg', '')}"}

    def prepare(self, motion):
        results = self._fanout("prepare", motion)
        return any(bool(r) is True for r in results.values())

    def motion_duration(self, motion):
        with self._lock:
            durs = [u.motion_duration(motion) for u in self.units.values()]
        durs = [d for d in durs if d]
        return max(durs) if durs else None

    def stop_motion(self, source, reason=""):
        results = self._fanout("stop_motion", source, reason)
        ok = any(r.get("ok") for r in results.values()) if results else False
        n_ok = sum(1 for r in results.values() if r.get("ok"))
        msg = (f"{n_ok}/{len(results)}대 정지 펄스" if results
               else "연결된 라디오가 없습니다")
        # 정지 목표(Velocity, 구버전 라디오면 ReadyPose 폴백)는 대별 결과에서 가져온다
        target = next((r.get("motion") for r in results.values() if r.get("ok")),
                      "Velocity")
        self._last_event = {"status": "queued" if ok else "rejected", "msg": msg}
        return {"ok": ok, "status": "queued" if ok else "rejected",
                "motion": target, "request_id": None, "msg": msg}

    def status(self):
        with self._lock:
            units = dict(self.units)
        per_unit, ready, current = {}, 0, None
        for unit_name, unit in sorted(units.items()):
            st = unit.status()
            robot = st.get("robot") or {}
            if st.get("gateway") == "ready":
                ready += 1
            per_unit[unit_name] = {"link": robot.get("rc_link"),
                                   "lq": robot.get("lq"), "rssi": robot.get("rssi")}
            if current is None and st.get("current_request"):
                current = st["current_request"]
        return {
            "gateway": "ready" if ready else "offline",
            "robot": {"fleet": per_unit, "ready": ready, "total": len(units),
                      "note": f"라디오 {ready}/{len(units)}대 응답 (군무 팬아웃)"},
            "current_request": current,
            "stop_state": "Velocity",   # rc_backend 와 동일 (정지 = locomotion 복귀)
            "stop_available": True,
            "last_event": dict(self._last_event),
        }

    def stop(self):
        with self._lock:
            for unit in self.units.values():
                unit.stop()
            self.units = {}
