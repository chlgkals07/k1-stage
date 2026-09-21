"""venue 로딩과 정합 검증.

이 파일이 하는 일은 하나다 — 설정 파일 셋(카탈로그 · 정책 · venue)이 서로 어긋나지 않는지
무대에 나가기 전에 알려 준다. 무대에서 발견하던 것을 노트북에서 발견하게 하는 것이다.

`core/` 는 어댑터를 모른다. 하드웨어도 네트워크도 없이 파일만 읽으므로 테스트가 밀리초로 돈다.
로봇 컨테이너에는 배포하지 않는다 — 로봇(--robot)은 UI 가 없어 venue 를 안 쓴다.

**왜 같은 함수를 두 곳에서 부르나**: 서버 부팅(FATAL 이면 기동 거부)과 tools/preflight.py
(출발 전 전수 검사). 두 벌이면 "preflight 는 통과하는데 부팅은 실패"하는 날이 온다.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

FATAL, WARN = "FATAL", "WARN"

# venue 폴더 = 사람이 쓰는 파일 + 서버가 쓰는 파일. 한 파일에 섞으면 /dance 에서 오프셋을
# 저장할 때마다 서버가 YAML 을 통째로 다시 써서 사람이 적은 주석이 사라진다.
VENUE_FILE = "venue.yaml"
PRESETS_FILE = "presets.json"

_NUMERIC_PRESET_FIELDS = ("offset_ms", "seek", "volume", "media_len_sec")


class VenueError(ValueError):
    """venue 폴더를 아예 못 읽는다. validate() 이전의 문제라 예외로 올린다."""


@dataclass(frozen=True)
class Problem:
    level: str   # FATAL | WARN
    where: str   # 어디 — "presets.snucheer-api" 처럼 사람이 바로 찾아갈 수 있게
    msg: str

    def __str__(self):
        return f"{self.level:5s}  {self.where}  —  {self.msg}"


def load_venue(venue_dir):
    """venue 폴더 → dict. 사람 파일이 없거나 깨졌으면 VenueError."""
    venue_dir = Path(venue_dir)
    doc_path = venue_dir / VENUE_FILE
    if not doc_path.is_file():
        raise VenueError(f"{doc_path} 가 없다")
    try:
        doc = yaml.safe_load(doc_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise VenueError(f"{doc_path} 를 못 읽는다: {exc}") from exc
    if not isinstance(doc, dict):
        raise VenueError(f"{doc_path} 최상위가 매핑이 아니다")

    presets = {}
    presets_path = venue_dir / PRESETS_FILE
    if presets_path.is_file():
        try:
            presets = json.loads(presets_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise VenueError(f"{presets_path} 를 못 읽는다: {exc}") from exc
        if not isinstance(presets, dict):
            raise VenueError(f"{presets_path} 최상위가 객체가 아니다")

    return {
        "dir": venue_dir,
        "name": doc.get("name") or venue_dir.name,
        "date": doc.get("date"),
        "notes": doc.get("notes") or "",
        # 보관용 venue(옛 행사의 이력). 지금 카탈로그·정책으로는 검증도 기동도 못 한다.
        "archived": bool(doc.get("archived")),
        "pad_grid": doc.get("pad_grid"),   # 없으면 None — validate 가 FATAL 로 잡는다
        "presets": presets,
    }


def catalog_states(catalog_doc):
    """카탈로그에 존재하는 모든 state 이름 (동작 + 제어 상태)."""
    items = list(catalog_doc.get("motions") or []) + list(catalog_doc.get("control_states") or [])
    return {m["state"] for m in items if isinstance(m, dict) and "state" in m}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _rc_duplicates(catalog_doc):
    """다이얼에서 같은 동작이 두 자리에 있거나, 한 뱅크에서 슬롯 번호가 겹치는 곳."""
    banks = (catalog_doc.get("rc_list") or {}).get("banks") or {}
    where, dup = {}, []
    for bank, body in banks.items():
        slots_seen = set()
        for s in (body or {}).get("slots") or []:
            if s.get("slot") in slots_seen:
                dup.append(Problem(WARN, f"rc_list.{bank}", f"슬롯 {s.get('slot')} 가 한 뱅크에서 겹친다"))
            slots_seen.add(s.get("slot"))
            where.setdefault(s.get("state"), []).append(f"{bank}:{s.get('slot')}")
    for state, spots in where.items():
        if state and len(spots) > 1:
            dup.append(Problem(WARN, f"rc_list.{state}",
                               f"다이얼 {len(spots)}자리에 있다 ({', '.join(spots)}) — RC 에서 어느 쪽이 나갈지 모호"))
    return dup


def validate(catalog_doc, policy, venue, *, clips_dir=None, media_dir=None, require_media=True):
    """설정 셋의 정합을 검사해 Problem 목록을 돌려준다. 예외는 던지지 않는다.

    require_media=False 는 로봇 없이 UI 만 띄우는 개발 실행용이다 — 음원은 저작권물이라
    저장소에 없고, 그게 없다고 mock 실행까지 막으면 아무도 화면을 못 본다. 음원이 없다는
    사실 자체는 여전히 WARN 으로 보인다.
    """
    if venue.get("archived"):
        # 옛 행사가 가리키던 동작이 지금 카탈로그에서 줄었을 수 있다(main 이 9/22 를 위해 139→16 으로 줄였다).
        # 그런 venue 로 무대를 띄우면 안 되므로 검증 결과가 아니라 **이 사실 자체**를 FATAL 로 알린다.
        return [Problem(FATAL, "venue", "보관된 venue 다(archived: true) — 지금 카탈로그·정책으로 검증할 수 없고 "
                        "이 venue 로는 기동하지 않는다. --venue 로 현재 행사의 venue 를 골라라")]
    out = []
    states = catalog_states(catalog_doc)
    api = set(policy.get("api_allowlist") or [])

    # load_catalog 는 {state: 항목} 을 만들어서 같은 state 가 두 번 있으면 뒤의 것이 앞의 것을 **조용히** 덮어쓴다
    # (옛 전체 카탈로그에 MimicCartwheelin 이 '옆돌기 연속' 과 '카트휠린' 으로 두 번 있었다).
    items = list(catalog_doc.get("motions") or []) + list(catalog_doc.get("control_states") or [])
    for state, n in sorted(Counter(m.get("state") for m in items if isinstance(m, dict)).items()):
        if state and n > 1:
            out.append(Problem(WARN, f"catalog.{state}", f"카탈로그에 {n}번 있다 — 뒤의 항목이 앞의 것을 덮어쓴다"))

    # ── pad_grid ────────────────────────────────────────────────────
    grid = venue.get("pad_grid")
    if not isinstance(grid, list) or not grid:
        out.append(Problem(FATAL, "venue.pad_grid", "없거나 비어 있다 — 관객 패드에 버튼이 하나도 안 뜬다"))
        grid = []
    seen = set()
    for i, motion in enumerate(grid, 1):
        where = f"venue.pad_grid[{i}] {motion}"
        if motion not in states:
            out.append(Problem(FATAL, where, "카탈로그에 없다 — 눌러도 거부되는 버튼"))
        elif motion not in api:
            out.append(Problem(FATAL, where, "api_allowlist 에 없다 — 눌러도 거부되는 버튼"))
        if motion in seen:
            out.append(Problem(WARN, where, "같은 동작이 두 번 있다"))
        seen.add(motion)
        if clips_dir is not None and not (Path(clips_dir) / f"{motion}.mp4").is_file():
            out.append(Problem(WARN, where, "미리보기 클립이 없다 — 화면에 동작 이름만 뜬다"))
    if grid and len(grid) != 12:
        out.append(Problem(WARN, "venue.pad_grid", f"{len(grid)}개다 — 패드 그리드는 4×3 = 12칸이다"))

    # ── 프리셋 ──────────────────────────────────────────────────────
    for name, p in (venue.get("presets") or {}).items():
        where = f"presets.{name}"
        if not isinstance(p, dict):
            out.append(Problem(FATAL, where, "객체가 아니다"))
            continue
        motion, media = p.get("motion") or "", p.get("media") or ""
        if motion and motion not in states:
            # 8/21 에 실제로 났다: 뉴진스 프리셋인데 체스트팝이 나갔다 (영상은 A, 로봇은 B).
            out.append(Problem(FATAL, where, f"motion {motion!r} 가 카탈로그에 없다"))
        elif motion and motion not in api:
            out.append(Problem(FATAL, where, f"motion {motion!r} 가 api_allowlist 에 없다 — 무대를 시작해도 로봇이 조용히 거부한다"))
        for key in _NUMERIC_PRESET_FIELDS:
            if key in p and p[key] is not None and not _is_number(p[key]):
                out.append(Problem(FATAL, where, f"{key} 가 숫자가 아니다: {p[key]!r}"))
        if media:
            if media_dir is not None and not (Path(media_dir) / media).is_file():
                out.append(Problem(FATAL if require_media else WARN, where, f"음원 {media!r} 가 media/ 에 없다"))
            if not p.get("media_len_sec"):
                # 없으면 무대 자동종료가 기본 60초로 떨어져 84초짜리 무대가 곡 중간에 끊긴다 (2026-08-18).
                out.append(Problem(WARN, where, "media_len_sec 가 없다 — 자동종료가 기본 60초로 떨어진다"))
        if _is_number(p.get("media_len_sec")) and p["media_len_sec"] <= 0:
            out.append(Problem(WARN, where, "media_len_sec 가 0 이하다"))

    out.extend(_rc_duplicates(catalog_doc))
    return out
