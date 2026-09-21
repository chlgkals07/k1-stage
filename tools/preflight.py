#!/usr/bin/env python3
"""출발 전 점검 — 설정 파일의 어긋남을 노트북에서 찾는다.

    python3 tools/preflight.py                         # solo_stage · default venue
    python3 tools/preflight.py --venue 20260922-bank --app group_stage

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

# 두 앱이 같은 사본을 가져야 하는 파일. 로봇에 평평하게 배포돼 앱 폴더에 남아 있는 것들이다.
# 한쪽만 고치면 드리프트다 — 8/31 에 display.html 이 그렇게 갈렸다.
SHARED_COPIES = ("motions.yaml", "gateway_config.yaml")


def check_apps_agree(apps):
    out = []
    first, rest = apps[0], apps[1:]
    for name in SHARED_COPIES:
        base = (ROOT / first / name).read_bytes()
        for other in rest:
            if (ROOT / other / name).read_bytes() != base:
                out.append(catalog.Problem(
                    catalog.FATAL, f"{first} ↔ {other}  {name}",
                    "두 앱의 사본이 다르다 — 한쪽만 고쳐졌다. 어느 쪽이 맞는지 정하고 맞춰라"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--venue", default="default", help="config/venues/ 의 폴더명")
    ap.add_argument("--app", default="solo_stage", choices=("solo_stage", "group_stage"),
                    help="이번에 띄울 앱 — 음원·클립을 이 앱 폴더에서 찾는다")
    args = ap.parse_args()

    app_dir = ROOT / args.app
    try:
        venue = catalog.load_venue(ROOT / "config" / "venues" / args.venue)
    except catalog.VenueError as exc:
        print(f"venue '{args.venue}' 를 못 읽었다: {exc}")
        return 1

    cat_doc = yaml.safe_load((app_dir / "motions.yaml").read_text())
    policy = yaml.safe_load((app_dir / "gateway_config.yaml").read_text())["policy"]

    problems = check_apps_agree(["solo_stage", "group_stage"])
    problems += catalog.validate(cat_doc, policy, venue,
                                 clips_dir=app_dir / "static" / "clips",
                                 media_dir=app_dir / "media", require_media=True)

    print(f"venue  {venue['name']}  ({args.venue})")
    print(f"앱     {args.app}\n")

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
