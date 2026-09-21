#!/usr/bin/env python3
"""출발 전 점검 — 설정 파일의 어긋남을 노트북에서 찾는다.

    python3 tools/preflight.py                         # solo 모드 · 기본 venue(20260922-bank)
    python3 tools/preflight.py --venue 20260922-bank --mode fleet

서버 부팅이 부르는 것과 **같은 함수**(core/catalog.validate)를 쓴다. 두 벌이면 "preflight 는
통과하는데 부팅은 실패하는" 날이 온다. 차이는 하나다 — 부팅은 FATAL 만 막고 WARN 은 5건까지만
보여 주지만, 여기서는 전부 보여 주고 음원·클립이 없으면 FATAL 로 친다(무대에 나갈 PC 라면 있어야 한다).

**코드가 못 잡는 것**: 프리셋의 동작이 카탈로그에 있고 허용돼 있으면 통과한다. 그게 그 곡의
동작이 맞는지는 알 수 없다 — 8/21 의 "영상은 뉴진스, 로봇은 체스트팝" 이 그 모양이다.
그래서 끝에 짝 확인표를 찍는다. 사람이 한 번 눈으로 본다.
"""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import catalog  # noqa: E402

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    # app.py 의 DEFAULT_VENUE 와 같아야 한다 — tests/test_catalog.py 가 지킨다
    ap.add_argument("--venue", default="20260922-bank", help="config/venues/ 의 폴더명")
    ap.add_argument("--mode", default="solo", choices=("solo", "fleet"),
                    help="app.py --mode 와 같다 — 카탈로그·정책을 config/<모드>/ 에서 읽는다")
    args = ap.parse_args()

    mode_dir = ROOT / "config" / args.mode
    try:
        venue = catalog.load_venue(ROOT / "config" / "venues" / args.venue)
    except catalog.VenueError as exc:
        print(f"venue '{args.venue}' 를 못 읽었다: {exc}")
        return 1

    cat_doc = yaml.safe_load((mode_dir / "motions.yaml").read_text())
    policy = yaml.safe_load((mode_dir / "gateway_config.yaml").read_text())["policy"]

    # 모드끼리 카탈로그·정책이 같은지는 여기서 안 본다: solo(16/14)와 fleet(139/79)은 의도적으로
    # 다르다 — 로봇의 RC 다이얼 덤프가 다르기 때문이다(데이터이지 코드가 아니다).
    problems = catalog.validate(cat_doc, policy, venue,
                                clips_dir=ROOT / "clips",
                                media_dir=ROOT / "media", require_media=True)

    print(f"venue  {venue['name']}  ({args.venue})")
    print(f"모드   {args.mode}\n")

    print("── 프리셋 짝 확인표 (코드가 못 잡는 '의도' 는 여기서 눈으로) ──")
    for name, p in venue["presets"].items():
        off = p.get("offset_ms", 0)
        print(f"  {name:20s} 동작 {p.get('motion') or '-':30s} 음원 {p.get('media') or '-':28s} 오프셋 {off:>6}")
    print()

    fatal = [p for p in problems if p.level == catalog.FATAL]
    warn = [p for p in problems if p.level != catalog.FATAL]
    for p in fatal + warn:
        print(f"  {p}")
    if problems:
        print()
    print(f"결과  FATAL {len(fatal)} · WARN {len(warn)}  →  " + ("출발 불가" if fatal else "출발 가능"))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
