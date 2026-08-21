#!/usr/bin/env python3
"""P0 벤치 도구 — PC ↔ RadioMaster Pocket (USB-VCP=LUA + K1PCT/K1PCM) 왕복 검증.

사용:
  python3 bench.py ping [횟수=100]   # PING 왕복 손실·지연 통계
  python3 bench.py gv3 <값>          # GV3 세팅, OK 회신 확인 (K1PCT 전용)
  python3 bench.py run <슬롯 1..20>  # K1PC 펄스: 다이얼 슬롯 Mimic 발사
  python3 bench.py stop              # K1PC 펄스: ReadyPose (CH7 1500)
  python3 bench.py damp              # K1PC 펄스: Damping  (CH7 1000)
  python3 bench.py tlm               # K1PC 상태 1줄 (state/LQ/RSSI)
  python3 bench.py monitor           # 수신 줄 덤프 (Ctrl-C 종료)

표준 라이브러리만 사용. 포트가 없거나 권한이 없으면 안내를 출력한다.
"""

import argparse
import glob
import os
import select
import sys
import termios
import time

BY_ID_PATTERN = "/dev/serial/by-id/usb-OpenTX_Radiomaster_Pocket*"
FALLBACK_PATTERN = "/dev/ttyACM*"
READ_TIMEOUT_S = 0.5


def find_port():
    for pattern in (BY_ID_PATTERN, FALLBACK_PATTERN):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def open_port(path):
    try:
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except PermissionError:
        sys.exit(
            f"권한 없음: {path}\n"
            f"터미널에서 실행: sudo chmod a+rw {os.path.realpath(path)}"
        )
    attrs = termios.tcgetattr(fd)
    # raw 모드, 115200 (VCP라 baud는 형식상이지만 명시해 둔다)
    attrs[0] = 0                      # iflag
    attrs[1] = 0                      # oflag
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
    attrs[3] = 0                      # lflag
    attrs[4] = termios.B115200        # ispeed
    attrs[5] = termios.B115200        # ospeed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


class LineReader:
    def __init__(self, fd):
        self.fd = fd
        self.buf = b""

    def readline(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while True:
            pos = self.buf.find(b"\n")
            if pos >= 0:
                line = self.buf[:pos].rstrip(b"\r")
                self.buf = self.buf[pos + 1:]
                return line.decode(errors="replace")
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            ready, _, _ = select.select([self.fd], [], [], remain)
            if ready:
                try:
                    chunk = os.read(self.fd, 256)
                except OSError:
                    return None
                if chunk:
                    self.buf += chunk


def send_line(fd, text):
    os.write(fd, (text + "\n").encode())


def cmd_ping(fd, reader, count):
    ok, lost, rtts = 0, 0, []
    context = None
    for i in range(count):
        t0 = time.monotonic()
        send_line(fd, "PING")
        line = reader.readline(READ_TIMEOUT_S)
        if line is not None and line.startswith("PONG"):
            rtts.append((time.monotonic() - t0) * 1000.0)
            ok += 1
            parts = line.split()
            if len(parts) > 1:
                context = parts[1]
        else:
            lost += 1
            print(f"  #{i + 1}: 응답 없음/불일치 ({line!r})")
        time.sleep(0.02)
    print(f"\nPING {count}회: 성공 {ok}, 손실 {lost}")
    if rtts:
        print(f"왕복 지연 ms: min {min(rtts):.1f} / avg {sum(rtts) / len(rtts):.1f} / max {max(rtts):.1f}")
    if context:
        name = {"T": "TOOLS(K1PCT)", "M": "MIXES(K1PCM)"}.get(context, context)
        print(f"응답 컨텍스트: {name}")
    return lost == 0


def cmd_gv3(fd, reader, value):
    send_line(fd, f"GV3 {value}")
    # 직전 명령의 지연 응답(PONG 등)이 섞일 수 있어 OK/ERR가 나올 때까지 걸러 읽는다
    deadline = time.monotonic() + READ_TIMEOUT_S * 3
    line = None
    while time.monotonic() < deadline:
        line = reader.readline(READ_TIMEOUT_S)
        if line is None or line.startswith("OK") or line.startswith("ERR"):
            break
        print(f"  (지연 응답 무시: {line!r})")
    print(f"응답: {line!r}")
    if line is not None and line.startswith("OK"):
        print(f"라디오 화면(K1PCT 화면 또는 MDL 글로벌 변수 페이지)에서 GV3={value} 확인할 것")
        return True
    return False


def cmd_pulse(fd, reader, command, timeout_s=3.0):
    """RUN/STOP/DAMP 펄스 명령: 완료 회신까지 100ms 간격 PING(keepalive) 유지."""
    send_line(fd, command)
    deadline = time.monotonic() + timeout_s
    last_ping = 0.0
    while time.monotonic() < deadline:
        if time.monotonic() - last_ping >= 0.1:
            send_line(fd, "PING")
            last_ping = time.monotonic()
        line = reader.readline(0.1)
        if line is None or line == "PONG":
            continue
        print(f"응답: {line!r}")
        if line.startswith("OK"):
            return True
        if line in ("BUSY", "ABORT") or line.startswith("ERR"):
            return False
    print("시간 초과: 완료 회신 없음")
    return False


def cmd_prepfire(fd, reader, slot, bank, delay_s):
    """PREP → delay 초 유지(keepalive) → FIRE. dance 싱크 경로의 수동 재현."""
    if not cmd_pulse(fd, reader, f"PREP {slot} {bank}", timeout_s=1.5):
        return False
    print(f"PREP 유지 {delay_s}s ...")
    t_end = time.monotonic() + delay_s
    while time.monotonic() < t_end:
        send_line(fd, "PING")
        reader.readline(0.01)
        time.sleep(0.1)
    t0 = time.time()
    ok = cmd_pulse(fd, reader, "FIRE")
    print(f"FIRE 전송 시각 t={t0:.3f}")
    return ok


def cmd_tlm(fd, reader):
    send_line(fd, "TLM")
    deadline = time.monotonic() + READ_TIMEOUT_S * 3
    while time.monotonic() < deadline:
        line = reader.readline(READ_TIMEOUT_S)
        if line is None:
            break
        if line.startswith("TLM"):
            print(line)
            return True
    print("TLM 응답 없음")
    return False


def cmd_monitor(fd, reader):
    print("수신 대기 중 (Ctrl-C 종료)")
    try:
        while True:
            line = reader.readline(1.0)
            if line is not None:
                print(f"{time.strftime('%H:%M:%S')}  {line}")
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ping = sub.add_parser("ping")
    p_ping.add_argument("count", nargs="?", type=int, default=100)
    p_gv3 = sub.add_parser("gv3")
    p_gv3.add_argument("value", type=int)
    p_run = sub.add_parser("run")
    p_run.add_argument("slot", type=int)
    p_run.add_argument("bank", nargs="?", choices=["A", "B"], default="A")
    p_prep = sub.add_parser("prep")
    p_prep.add_argument("slot", type=int)
    p_prep.add_argument("bank", nargs="?", choices=["A", "B"], default="A")
    sub.add_parser("fire")
    p_pf = sub.add_parser("prepfire")
    p_pf.add_argument("slot", type=int)
    p_pf.add_argument("bank", nargs="?", choices=["A", "B"], default="A")
    p_pf.add_argument("delay", nargs="?", type=float, default=1.5)
    sub.add_parser("stop")
    sub.add_parser("damp")
    sub.add_parser("tlm")
    sub.add_parser("monitor")
    args = parser.parse_args()

    path = find_port()
    if path is None:
        sys.exit(
            "RC 시리얼 포트를 찾을 수 없음.\n"
            "RC 전원 ON + 위쪽 USB-C 연결 + 팝업에서 'USB Serial (VCP)' 선택 후 재시도."
        )
    print(f"포트: {path}")
    fd = open_port(path)
    reader = LineReader(fd)
    try:
        if args.cmd == "ping":
            success = cmd_ping(fd, reader, args.count)
        elif args.cmd == "gv3":
            success = cmd_gv3(fd, reader, args.value)
        elif args.cmd == "run":
            success = cmd_pulse(fd, reader, f"RUN {args.slot} {args.bank}")
        elif args.cmd == "prep":
            success = cmd_pulse(fd, reader, f"PREP {args.slot} {args.bank}", timeout_s=1.5)
        elif args.cmd == "fire":
            success = cmd_pulse(fd, reader, "FIRE")
        elif args.cmd == "prepfire":
            success = cmd_prepfire(fd, reader, args.slot, args.bank, args.delay)
        elif args.cmd == "stop":
            success = cmd_pulse(fd, reader, "STOP")
        elif args.cmd == "damp":
            success = cmd_pulse(fd, reader, "DAMP")
        elif args.cmd == "tlm":
            success = cmd_tlm(fd, reader)
        else:
            cmd_monitor(fd, reader)
            success = True
        sys.exit(0 if success else 1)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
