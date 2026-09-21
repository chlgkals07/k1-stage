#!/usr/bin/env python3
"""로봇 k1_config 백업과 solo_stage RC 목록의 정합을 읽기 전용으로 검사한다.

사용:
  python3 tools/verify_robot_rc_config.py <robot-k1_config.yaml> [motions.yaml]

성공(0): A/B selector의 모든 슬롯이 motions.yaml rc_list와 같다.
실패(1): selector 누락 또는 슬롯 차이가 있다.
"""

import sys
from pathlib import Path

import yaml


SELECTOR_KEY = {"A": "mimic_selector", "B": "mimic_selector_b"}


def load_yaml(path):
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def table_value(table, slot):
    """yaml key가 숫자/문자열 어느 쪽으로 읽혀도 슬롯을 찾는다."""
    return table.get(slot, table.get(str(slot)))


def expected_slots(motions):
    banks = motions.get("rc_list", {}).get("banks", {})
    return {
        bank: {int(item["slot"]): item["state"]
               for item in banks.get(bank, {}).get("slots", [])}
        for bank in ("A", "B")
    }


def verify(config, motions):
    """(문제 목록, 검사 슬롯 수)를 반환한다. 파일을 변경하지 않는다."""
    selectors = config.get("selectors", {})
    expected = expected_slots(motions)
    problems = []
    checked = 0
    for bank, selector_name in SELECTOR_KEY.items():
        selector = selectors.get(selector_name)
        if not isinstance(selector, dict) or not isinstance(selector.get("table"), dict):
            problems.append(f"{bank}: selectors.{selector_name}.table 을 찾지 못했습니다")
            continue
        table = selector["table"]
        for slot, wanted in expected[bank].items():
            checked += 1
            actual = table_value(table, slot)
            if actual != wanted:
                problems.append(f"{bank}-{slot}: 로봇={actual!r}, 기대={wanted!r}")
        # 이번 무대 목록 밖의 Mimic selector 슬롯이 남아 있으면, PC와 로봇이
        # 서로 다른 목록을 보게 된다. 200~219 슬롯은 배포 목표와 정확히 같아야 한다.
        actual_slots = {int(key) for key in table if str(key).isdigit()
                        and 200 <= int(key) <= 219}
        for slot in sorted(actual_slots - set(expected[bank])):
            problems.append(f"{bank}-{slot}: 이번 무대 목록 밖 슬롯이 로봇에 남아 있습니다 "
                            f"({table_value(table, slot)!r})")

    return problems, checked


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    config_path = Path(argv[1])
    motions_path = Path(argv[2]) if len(argv) == 3 else Path(__file__).parents[1] / "config" / "solo" / "motions.yaml"
    try:
        problems, checked = verify(load_yaml(config_path), load_yaml(motions_path))
    except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
        print(f"검사 불가: {exc}", file=sys.stderr)
        return 2
    if problems:
        print(f"실패: {len(problems)}개 불일치 / 비교 슬롯 {checked}개")
        print(*[f"- {problem}" for problem in problems], sep="\n")
        print("수정 후 rc_link/gen_rc_list.py로 rc_list를 재생성하고 git diff로 검토하세요.")
        return 1
    print(f"통과: A/B RC 슬롯 {checked}개가 motions.yaml과 일치")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
