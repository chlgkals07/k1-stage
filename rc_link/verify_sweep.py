#!/usr/bin/env python3
"""로봇 등가성 스위프 — 뱅크 A/B × 슬롯 20 전수 검사 (로봇 불필요).

각 슬롯을 PREP 상태로 만들고 라디오의 실제 믹서 출력(CHK)을 읽어 두 기준과 대조한다:

1. **동일성(합격 기준)**: ROBOT.lua 다이얼과 같은 GV·믹서 경로가 내야 할 값
   (pct 모델). 이미 로봇에서 검증된 경로와 값이 같으면, 로봇 입장에서 구분 불가한
   입력임이 보장된다 — "로봇 붙이면 이상 없음"의 근거.
2. **명목값(기록용)**: rc_list 의 ch5/ch11 명목값과의 편차. EdgeTX -100% = 988µs 라
   명목 1000 과 ~12µs 시스템 오프셋이 있고, 이는 기존 다이얼도 동일하다.
   P2(로봇 접속일)에 /ai_sapiens_rc/status 실측과 재대조할 기준표로 남긴다.

전제: RC 전원 ON + USB Serial + VCP=LUA + SYS>Tools>K1PC v2.1(CHK 지원) 실행 중.
사용: python3 verify_sweep.py
종료 시 PREP 는 keepalive 중단으로 라디오가 0.5s 내 자동 해제한다.
"""

import pathlib
import sys
import time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import yaml
from runtime.rc_serial import RcSerial

IDENTITY_TOL = 2    # pct 모델 대비 허용 (정수 반올림 경로 차이만 허용)
CODE_TOL = 50       # 로봇 switch_match_tolerance 와 동일


def model_us(pct):
    """GV(pct) → 믹서 출력 µs — K1PC 화면/CHK 와 같은 변환."""
    raw = int(1024 * pct / 100)
    return 1500 + int(raw / 2 + (0.5 if raw >= 0 else -0.5))


def slot_pct(slot):
    return -100 + (slot - 1) * 4


def main():
    # 라디오가 여러 대면 --port 로 대상을 고른다 (인자 없으면 첫 번째 Pocket).
    port = None
    args = sys.argv[1:]
    if args and args[0] == "--port" and len(args) > 1:
        port = args[1]
    elif args and args[0] == "--list":
        from rc_serial import BY_ID_PATTERN
        import glob
        for path in sorted(glob.glob(BY_ID_PATTERN)):
            print(path)
        return
    motions = yaml.safe_load(open(HERE.parent / "config" / "fleet" / "motions.yaml"))
    banks = motions["rc_list"]["banks"]

    rc = RcSerial(port_pattern=port)
    ping = rc.ping()
    if not ping.get("ok"):
        sys.exit("RC 연결 실패: " + ping.get("msg", ""))
    if not rc.chk().get("ok"):
        sys.exit("CHK 무응답 — K1PC v2.1 이 SD에 반영되고 Tools 에서 재실행됐는지 확인")

    failures, rows = [], []
    for bank_name in sorted(banks):
        bank = banks[bank_name]
        bank_pct = -100 if bank_name == "A" else 100
        exp_ch5_model = model_us(bank_pct)
        for entry in bank["slots"]:
            state = entry["state"]
            nominal_ch11 = int(entry["ch11"])
            nominal_ch5 = int(bank["ch5"])
            slot = (nominal_ch11 - 1000) // 20 + 1
            exp_ch11_model = model_us(slot_pct(slot))

            res = rc.prep(slot, bank_name)
            if not res.get("ok"):
                res = rc.prep(slot, bank_name)  # 지연 스파이크 대비 1회 재시도
            if not res.get("ok"):
                failures.append(f"{bank_name}{slot}: PREP 실패 — {res.get('msg', '')}")
                continue
            time.sleep(0.35)  # sticky 게이트 래치(<=100ms) + 믹서 반영 여유
            got = rc.chk()
            if not got.get("ok"):
                got = rc.chk()
            if not got.get("ok"):
                failures.append(f"{bank_name}{slot}: CHK 실패 — {got.get('msg', '')}")
                continue
            ch5, ch6, ch7, ch11 = (int(got.get(k, "-1")) for k in ("ch5", "ch6", "ch7", "ch11"))

            ident_ok = (abs(ch11 - exp_ch11_model) <= IDENTITY_TOL
                        and abs(ch5 - exp_ch5_model) <= IDENTITY_TOL)
            code_ok = abs(ch7 - 2000) <= CODE_TOL and abs(ch6 - 1500) <= CODE_TOL
            mark = "OK  " if (ident_ok and code_ok) else "FAIL"
            row = (f"{mark} {bank_name}{slot:2d} {state[:36]:36s} "
                   f"ch11 {ch11} (모델 {exp_ch11_model}, 명목 {nominal_ch11} 편차 {ch11 - nominal_ch11:+d}) "
                   f"ch5 {ch5} (명목 {nominal_ch5} 편차 {ch5 - nominal_ch5:+d}) "
                   f"ch7 {ch7} ch6 {ch6}")
            rows.append(row)
            if mark == "FAIL":
                failures.append(row)

    rc.close()  # keepalive 중단 → 라디오가 0.5s 내 PREP 자동 해제

    print("\n".join(rows))
    print()
    total = sum(len(b["slots"]) for b in banks.values())
    if failures:
        print(f"결과: FAIL {len(failures)} / {total}")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print(f"결과: 전 슬롯 통과 ({total}/{total}) — 검증된 다이얼 경로와 출력 동일.")
    print("명목값 편차 열은 P2(로봇 접속일)에 /ai_sapiens_rc/status 실측과 대조할 것.")


if __name__ == "__main__":
    main()
