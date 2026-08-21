#!/usr/bin/env python3
"""로봇 백업(ai_sapiens_backup)의 k1_config selector 테이블에서 motions.yaml의
rc_list 섹션을 재생성한다. 겹치는 동작의 note(길이 등)는 기존 rc_list에서 이어받는다.

사용: python3 gen_rc_list.py <k1_config.yaml> <motions.yaml(수정 대상)>
"""

import sys

import yaml

BANK_INPUT_CODE = {"A": 4, "B": 5}
BANK_CH5 = {"A": 1000, "B": 2000}
SELECTOR_KEY = {"A": "mimic_selector", "B": "mimic_selector_b"}


def main():
    k1_path, motions_path = sys.argv[1], sys.argv[2]
    k1 = yaml.safe_load(open(k1_path))
    motions_raw = open(motions_path, encoding="utf-8").read()
    motions = yaml.safe_load(motions_raw)

    # 기존 rc_list의 note·기존 카탈로그의 ko/safety를 이어받기 위한 인덱스
    old_notes = {}
    for bank in (motions.get("rc_list", {}).get("banks") or {}).values():
        for s in bank.get("slots") or []:
            if s.get("note"):
                old_notes[s["state"]] = s["note"]
    ko_map, safety_map = {}, {}
    for entry in (motions.get("motions") or []) + (motions.get("control_states") or []):
        ko_map[entry["state"]] = entry.get("ko", "")
        safety_map[entry["state"]] = entry.get("safety", "")

    lines = ["rc_list:",
             "  updated: 2026-08-18",
             "  source: ai_sapiens_backup/ai_sapiens_sim2real_20260818 (로봇 실배포 k1_config)",
             "  select:",
             "    bank: CH5    # 1000 = A (input_code 4), 2000 = B (input_code 5)",
             "    slot: CH11   # 1000 부터 20us 간격, tolerance 5",
             "  banks:"]
    for bank_name in ("A", "B"):
        table = k1["selectors"][SELECTOR_KEY[bank_name]]["table"]
        lines.append(f"    {bank_name}:")
        lines.append(f"      ch5: {BANK_CH5[bank_name]}")
        lines.append(f"      input_code: {BANK_INPUT_CODE[bank_name]}")
        lines.append("      slots:")
        for code in sorted(table):
            state = table[code]
            ch11 = 1000 + (int(code) - 200) * 20
            parts = [f"slot: {code}", f"ch11: {ch11}", f"state: {state}"]
            if ko_map.get(state):
                parts.append(f'ko: "{ko_map[state]}"')
            if safety_map.get(state):
                parts.append(f"safety: {safety_map[state]}")
            if old_notes.get(state):
                parts.append(f'note: "{old_notes[state]}"')
            lines.append("      - {" + ", ".join(parts) + "}")
    new_section = "\n".join(lines) + "\n"

    # 기존 rc_list 섹션(다음 최상위 키 전까지)을 통째로 교체
    out, in_rc, replaced = [], False, False
    for line in motions_raw.splitlines(keepends=True):
        if line.startswith("rc_list:"):
            in_rc, replaced = True, True
            out.append(new_section)
            continue
        if in_rc:
            if line[:1] not in (" ", "\t", "\n", "#"):
                in_rc = False
                out.append(line)
            continue
        out.append(line)
    if not replaced:
        sys.exit("rc_list 섹션을 찾지 못했습니다")
    open(motions_path, "w", encoding="utf-8").write("".join(out))

    check = yaml.safe_load(open(motions_path))
    banks = check["rc_list"]["banks"]
    n = sum(len(b["slots"]) for b in banks.values())
    print(f"재생성 완료: 뱅크 {len(banks)}개, 슬롯 {n}개")
    for bn, b in banks.items():
        states = [s["state"] for s in b["slots"]]
        print(f"  {bn}: {len(states)}슬롯, note 승계 {sum(1 for s in b['slots'] if s.get('note'))}건")


if __name__ == "__main__":
    main()
