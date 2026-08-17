"""RC(RadioMaster Pocket) USB 시리얼 클라이언트.

라디오의 SCRIPTS/TOOLS/K1PC.lua(v2)와 줄 단위 프로토콜로 대화한다:

    PING            -> PONG                  (keepalive — 끊기면 라디오가 0.5s 내 자동 해제)
    RUN <n> [A|B]   -> OK RUN <n>            (즉시형 펄스: 다이얼 세팅 + code 4 발사)
    PREP <n> <A|B>  -> OK PREP               (사전 준비: code 0 유지 — dance 싱크용)
    FIRE            -> OK FIRE               (PREP 상태에서 code 4 엣지, ms급)
    VEL             -> OK VEL                (Velocity = locomotion 복귀, 정지 기본값)
    STOP            -> OK STOP               (ReadyPose — 구버전 폴백)
    DAMP            -> OK DAMP               (Damping)
    TLM             -> TLM st=.. lq=.. rssi=..

표준 라이브러리만 사용. 포트가 없거나 끊겨도 예외 대신 실패 dict 를 돌려주고,
다음 명령에서 재연결을 시도한다. keepalive 스레드가 항상 0.2s 간격 PING 을 보내므로
PREP 유지·펄스 중에도 라디오 쪽 타임아웃이 걸리지 않는다.
"""

import glob
import os
import select
import termios
import threading
import time

BY_ID_PATTERN = "/dev/serial/by-id/usb-OpenTX_Radiomaster_Pocket*"
FALLBACK_PATTERN = "/dev/ttyACM*"
KEEPALIVE_SEC = 0.2
DEFAULT_TIMEOUT = 3.0


class RcSerial:
    def __init__(self, port_pattern=None):
        self.port_pattern = port_pattern
        self._fd = None
        self._buf = b""
        self._lock = threading.Lock()        # 명령 왕복 직렬화
        self._write_lock = threading.Lock()  # write 원자성 (keepalive 와 공유)
        self._closed = False
        self.last_error = ""
        self._keepalive = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive.start()

    # ── 포트 관리 ─────────────────────────────────────────────

    def _find_port(self):
        patterns = [self.port_pattern] if self.port_pattern else [BY_ID_PATTERN, FALLBACK_PATTERN]
        for pattern in patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[0]
        return None

    def _ensure_open(self):
        if self._fd is not None:
            return True
        path = self._find_port()
        if path is None:
            self.last_error = "RC 시리얼 포트 없음 (전원/케이블/Serial 모드 확인)"
            return False
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            attrs = termios.tcgetattr(fd)
            attrs[0] = attrs[1] = attrs[3] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[4] = attrs[5] = termios.B115200
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIOFLUSH)
        except OSError as exc:
            self.last_error = f"포트 열기 실패: {exc}"
            return False
        self._fd = fd
        self._buf = b""
        self.last_error = ""
        return True

    def _drop(self, why):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self.last_error = why

    def close(self):
        self._closed = True
        with self._lock:
            self._drop("closed")

    # ── 저수준 입출력 ─────────────────────────────────────────

    def _write_line(self, text):
        if self._fd is None:
            return False
        try:
            with self._write_lock:
                os.write(self._fd, (text + "\n").encode())
            return True
        except OSError as exc:
            self._drop(f"write 실패: {exc}")
            return False

    def _read_line(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while True:
            pos = self._buf.find(b"\n")
            if pos >= 0:
                line = self._buf[:pos].rstrip(b"\r")
                self._buf = self._buf[pos + 1:]
                return line.decode(errors="replace")
            remain = deadline - time.monotonic()
            if remain <= 0 or self._fd is None:
                return None
            try:
                ready, _, _ = select.select([self._fd], [], [], remain)
                if ready:
                    chunk = os.read(self._fd, 256)
                    if chunk:
                        self._buf += chunk
            except OSError as exc:
                self._drop(f"read 실패: {exc}")
                return None

    def _keepalive_loop(self):
        while not self._closed:
            time.sleep(KEEPALIVE_SEC)
            if self._fd is not None and not self._lock.locked():
                # 명령 진행 중이면 명령 자체가 트래픽이므로 건너뛴다
                with self._lock:
                    self._write_line("PING")
                    # PONG 은 다음 명령의 낙오 응답 필터가 삼킨다

    # ── 명령 ─────────────────────────────────────────────────

    def _command(self, cmd, ok_prefixes, timeout_s=DEFAULT_TIMEOUT):
        """명령 하나를 보내고 기대 응답까지 기다린다. 낙오 PONG 등은 걸러 버린다."""
        with self._lock:
            if not self._ensure_open():
                return {"ok": False, "msg": self.last_error}
            # 이전 keepalive 의 PONG 등 잔여물 제거
            self._buf = b""
            try:
                termios.tcflush(self._fd, termios.TCIFLUSH)
            except OSError:
                pass
            if not self._write_line(cmd):
                return {"ok": False, "msg": self.last_error}
            deadline = time.monotonic() + timeout_s
            last_ping = time.monotonic()
            while time.monotonic() < deadline:
                # 펄스 대기 중에도 keepalive 유지 (라디오 0.5s 타임아웃 방지)
                if time.monotonic() - last_ping >= KEEPALIVE_SEC:
                    self._write_line("PING")
                    last_ping = time.monotonic()
                line = self._read_line(0.1)
                if line is None or line == "":
                    continue
                for prefix in ok_prefixes:
                    if line.startswith(prefix):
                        return {"ok": True, "line": line}
                if line == "PONG":  # 다른 명령을 기다리는 중의 keepalive 응답
                    continue
                if line == "BUSY":
                    return {"ok": False, "msg": "RC 펄스 진행 중 (BUSY)"}
                if line == "ABORT":
                    return {"ok": False, "msg": "RC 펄스 중단 (ABORT)"}
                if line.startswith("ERR"):
                    return {"ok": False, "msg": f"RC 거부: {line}"}
                # 그 외 낙오 응답은 무시하고 계속 기다린다
            # 시간 초과 시 포트는 유지한다 — 닫았다 다시 열면 CDC 스택이 출렁여
            # 다음 명령까지 연쇄 실패하는 패턴이 실측됐다 (2026-08-18 스위프).
            # 늦게 도착한 응답은 다음 명령의 낙오 필터가 걸러 준다.
            return {"ok": False, "msg": "RC 응답 시간 초과"}

    def ping(self):
        return self._command("PING", ("PONG",), timeout_s=0.5)

    def run(self, slot, bank="A"):
        return self._command(f"RUN {slot} {bank}", ("OK RUN",))

    def prep(self, slot, bank):
        return self._command(f"PREP {slot} {bank}", ("OK PREP",), timeout_s=2.0)

    def fire(self):
        return self._command("FIRE", ("OK FIRE",))

    def stop_pulse(self):
        return self._command("STOP", ("OK STOP",))

    def vel(self):
        """locomotion(Velocity, code 3) 복귀. 구버전 K1PC 는 ERR CMD 를 돌려준다."""
        return self._command("VEL", ("OK VEL",))

    def damp(self):
        return self._command("DAMP", ("OK DAMP",))

    def _keyvalue_command(self, cmd, prefix, timeout_s=1.5):
        res = self._command(cmd, (prefix,), timeout_s=timeout_s)
        if not res.get("ok"):
            return {"ok": False, "msg": res.get("msg", "")}
        parsed = {"ok": True}
        for token in res["line"].split()[1:]:
            if "=" in token:
                key, val = token.split("=", 1)
                parsed[key] = val
        return parsed

    def tlm(self):
        return self._keyvalue_command("TLM", "TLM")

    def chk(self):
        """현재 믹서 출력(µs) 조회: {"ch5": "988", "ch6": ..., "ch7": ..., "ch11": ...}"""
        return self._keyvalue_command("CHK", "CHK")
