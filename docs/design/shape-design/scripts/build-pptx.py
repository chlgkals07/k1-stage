#!/usr/bin/env python3
"""SHAPE 공식 발표자료 템플릿(.pptx)을 만듭니다.

    python3 -m pip install python-pptx
    python3 design-system/scripts/build-pptx.py

만들어진 파일은 `frontend/public/downloads/` 로 들어가고, 자료실에서 그 주소를
그대로 내려받습니다. public/downloads 에는 1년 불변 캐시가 걸려 있으므로
**내용을 바꿀 때는 파일 이름의 판 번호를 반드시 올리고 자료실 주소도 함께
바꾸세요.** 같은 주소로 내용만 갈아 끼우면 옛 파일을 1년 동안 들고 있는
사람이 생깁니다.

## 왜 python-pptx 의 도형 API 를 안 쓰고 XML 을 직접 쓰나

세 가지가 그 API 로 안 됩니다. (1) 슬라이드 레이아웃에 도형을 넣는 일,
(2) 웹의 '나타나기'를 옮긴 등장 애니메이션(`p:timing`), (3) 자간·한글 줄바꿈
같은 글자 속성. 어차피 XML 을 써야 해서, 슬라이드와 레이아웃이 같은 코드로
그려지도록 그리기를 전부 XML 한 벌로 통일했습니다.

## 좌표는 1280×720 px 입니다

16:9 슬라이드(13.333in × 7.5in)는 96dpi 에서 정확히 1280×720 px 이고,
1px = 9525 EMU 로 딱 떨어집니다. 그래서 `kit/slide.html` 의 값을 그대로 옮겨
쓸 수 있습니다. 글자 크기만 px × 0.75 = pt 로 바꿉니다(24px 본문 = 18pt).
"""

from __future__ import annotations

import json
import os
import pathlib
import struct
import sys
import zlib
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from pptx import Presentation
    from pptx.oxml.ns import nsmap, qn
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("python-pptx 가 필요합니다:  python3 -m pip install python-pptx")

from lxml import etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                      # shape_web/
STAMP = "2026-09"

# ── 두 벌을 찍어 냅니다 ────────────────────────────────────────────────────
# 같은 배치로 파워포인트용과 구글 슬라이드용을 만듭니다. 다른 것은 글꼴 하나뿐인데,
# 그 하나 때문에 파일을 나눠야 합니다.
#
# **Pretendard 는 구글 폰트에 없습니다**(1,900여 가족을 훑어 확인했습니다). 구글
# 슬라이드는 구글 폰트에 있는 글꼴만 고를 수 있고 글꼴 파일을 올릴 수도 없으므로,
# Pretendard 로 짠 파일을 슬라이드로 열면 아무 글꼴로나 바뀝니다. 그래서 슬라이드
# 판은 Noto Sans KR 로 짭니다 — `foundations/typography.md` 가 이미 대체 글꼴로
# 적어 둔 바로 그 글꼴이라, 새로 정하는 것이 아닙니다.
VARIANTS = {
    "pptx":   {"font": "Pretendard",   "file": f"shape-ppt-template-{STAMP}.pptx"},
    "slides": {"font": "Noto Sans KR", "file": f"shape-slides-template-{STAMP}.pptx"},
}
MODE = "pptx"

# ── 값 ────────────────────────────────────────────────────────────────────
# tokens/tokens.json 에서 그대로 옮긴 것입니다. 새 색을 지어내지 마세요.
BLUE       = "2855F3"
BLUE_PRESS = "1D4EB5"
NAVY       = "0C245E"
NAVY_MID   = "163C91"
NAVY_SOLID = "243E78"
SKY        = "90AFFF"
INK900, INK800, INK700 = "111111", "20242B", "39404D"
INK600, INK500, INK400, INK300 = "4C5360", "69717F", "8A9099", "9AA4B6"
LINE_STRONG, LINE_BASE, LINE_SOFT, LINE_FAINT = "CBD3E2", "D6DCE6", "E2E6EE", "EEF0F4"
WHITE      = "FFFFFF"
SUBTLE     = "F7F8FB"
SUNKEN     = "F4F6FA"
SURF_BLUE  = "F4F7FF"
SURF_BLUE_STRONG = "E8EFFF"
BLUE_PAGE  = "F0F5FF"
ST = {  # 상태색은 언제나 글자색과 배경색이 짝입니다.
    "info":    ("1B4BC4", "E7EDFF"),
    "success": ("1D6B40", "E7F6ED"),
    "warn":    ("7A5405", "FDF1D8"),
    "danger":  ("B62446", "FDF3F5"),
    "staff":   ("93341F", "FFE9DF"),
}

FONT = VARIANTS[MODE]["font"]

# 자간 — 큰 글자일수록 좁게. em 단위이므로 크기를 곱해 pt 로 바꿉니다.
TR_HERO, TR_DISPLAY, TR_TITLE, TR_CARD, TR_EYEBROW = -0.075, -0.06, -0.05, -0.04, 0.14

# 배치 — kit/slide.html 과 같은 뼈대
M       = 80    # 좌우 여백
BODY_T  = 196   # 본문이 시작하는 줄
BODY_B  = 612   # 본문이 끝나는 줄
FOOT_Y  = 632
CW      = 1280 - M * 2   # 본문 폭 1120

PX = 9525       # 1px 의 EMU


def out_path() -> Path:
    override = os.environ.get("SHAPE_PPTX_OUT")
    if override:
        return Path(override)
    name = VARIANTS[MODE]["file"]
    if (ROOT / "frontend").is_dir():
        return ROOT / "frontend" / "public" / "downloads" / name
    return Path.cwd() / name


def emu(v: float) -> int:
    return int(round(v * PX))


# ── XML 조각 만들기 ────────────────────────────────────────────────────────
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = f'xmlns:a="{A}" xmlns:p="{P}" xmlns:r="{R}"'


def fill_xml(color: str | None, alpha: float | None = None) -> str:
    if color is None:
        return "<a:noFill/>"
    if alpha is None:
        return f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
    return (f'<a:solidFill><a:srgbClr val="{color}">'
            f'<a:alpha val="{int(alpha * 100000)}"/></a:srgbClr></a:solidFill>')


def line_xml(color: str | None, width: float = 1.0, alpha: float | None = None) -> str:
    if color is None:
        return "<a:ln><a:noFill/></a:ln>"
    return f'<a:ln w="{emu(width)}" cap="rnd">{fill_xml(color, alpha)}</a:ln>'


def geom_xml(prst: str, radius: float | None, w: float, h: float) -> str:
    if prst != "roundRect":
        return f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>'
    adj = min(50000, int(round((radius or 0) / max(1.0, min(w, h)) * 100000)))
    return (f'<a:prstGeom prst="roundRect"><a:avLst>'
            f'<a:gd name="adj" fmla="val {adj}"/></a:avLst></a:prstGeom>')


def run_xml(text: str, sz: float, *, b: bool = False, color: str = INK600,
            spc: float = 0.0, alpha: float | None = None,
            font: str | None = None) -> str:
    """한 줄기 글자. spc 는 em 단위 자간이고 pt 의 1/100 으로 바뀝니다."""
    font = font or FONT
    parts = []
    for i, piece in enumerate(text.split("\n")):
        if i:
            parts.append("<a:br/>")
        parts.append(
            f'<a:r><a:rPr lang="ko-KR" altLang="en-US" sz="{int(sz * 100)}"'
            f' b="{1 if b else 0}" spc="{int(round(spc * sz * 100))}" dirty="0">'
            f'{fill_xml(color, alpha)}'
            f'<a:latin typeface="{font}"/><a:ea typeface="{font}"/><a:cs typeface="{font}"/>'
            f'</a:rPr><a:t>{escape(piece)}</a:t></a:r>')
    return "".join(parts)


def para_xml(spec: dict) -> str:
    """문단 하나. spec 은 아래 열쇠를 씁니다.

    t/runs 글자 · sz 크기(pt) · b 굵게 · c 색 · spc 자간(em) · ln 줄간격
    · sb/sa 앞뒤 여백(pt) · al 정렬 · bullet 글머리 표시 · marL 들여쓰기
    """
    sz = spec.get("sz", 18)
    al = {"l": "l", "c": "ctr", "r": "r", "j": "just"}[spec.get("al", "l")]
    ln = spec.get("ln", 1.55)
    mar_l = spec.get("marL", 0)
    bullet = spec.get("bullet")
    bu = "<a:buNone/>"
    if bullet:
        bu = (f'<a:buClr><a:srgbClr val="{bullet.get("c", BLUE)}"/></a:buClr>'
              f'<a:buSzPct val="{int(bullet.get("size", 1.0) * 100000)}"/>'
              f'<a:buFont typeface="Arial"/><a:buChar char="{escape(bullet.get("char", "●"))}"/>')
    ppr = (f'<a:pPr marL="{emu(mar_l)}" indent="{emu(-mar_l)}" algn="{al}"'
           f' eaLnBrk="0" hangingPunct="0">'
           f'<a:lnSpc><a:spcPct val="{int(ln * 100000)}"/></a:lnSpc>'
           f'<a:spcBef><a:spcPts val="{int(spec.get("sb", 0) * 100)}"/></a:spcBef>'
           f'<a:spcAft><a:spcPts val="{int(spec.get("sa", 0) * 100)}"/></a:spcAft>'
           f'{bu}</a:pPr>')
    if "runs" in spec:
        body = "".join(
            run_xml(t, o.get("sz", sz), b=o.get("b", spec.get("b", False)),
                    color=o.get("c", spec.get("c", INK600)),
                    spc=o.get("spc", spec.get("spc", 0.0)),
                    alpha=o.get("alpha", spec.get("alpha")),
                    font=o.get("font"))
            for t, o in spec["runs"])
    elif spec.get("field") == "slidenum":
        # 쪽 번호. 장을 넣거나 지워도 스스로 다시 셉니다.
        body = (f'<a:fld id="{{B7C3A4E1-6D2F-4C58-9E10-{spec["fid"]:012X}}}" type="slidenum">'
                f'<a:rPr lang="ko-KR" altLang="en-US" sz="{int(sz * 100)}"'
                f' b="{1 if spec.get("b") else 0}" spc="{int(round(spec.get("spc", 0.0) * sz * 100))}">'
                f'{fill_xml(spec.get("c", INK300))}'
                f'<a:latin typeface="{FONT}"/><a:ea typeface="{FONT}"/></a:rPr>'
                f'<a:t>{spec.get("t", "1")}</a:t></a:fld>')
    else:
        body = run_xml(spec.get("t", ""), sz, b=spec.get("b", False),
                       color=spec.get("c", INK600), spc=spec.get("spc", 0.0),
                       alpha=spec.get("alpha"))
    return f"<a:p>{ppr}{body}</a:p>"


def tx_body_xml(paras: list[dict], anchor: str, pad: tuple, wrap: bool) -> str:
    ins = "".join(f' {k}Ins="{emu(v)}"' for k, v in
                  zip(("l", "t", "r", "b"), pad))
    return (f'<p:txBody><a:bodyPr wrap="{"square" if wrap else "none"}"{ins}'
            f' anchor="{anchor}" anchorCtr="0"><a:noAutofit/></a:bodyPr>'
            f'<a:lstStyle/>{"".join(para_xml(p) for p in paras)}</p:txBody>')


def sp_xml(sid: int, name: str, x: float, y: float, w: float, h: float, *,
           paras: list[dict] | None = None, fill: str | None = None,
           fill_alpha: float | None = None, line: str | None = None,
           line_w: float = 1.0, prst: str = "rect", radius: float | None = None,
           anchor: str = "t", pad: tuple = (0, 0, 0, 0), wrap: bool = True,
           rot: int | None = None, shadow: str | None = None) -> str:
    xfrm_rot = f' rot="{rot * 60000}"' if rot else ""
    shadow_xml = ""
    if shadow:
        # 그림자는 검정이 아니라 파란 기가 도는 남색입니다(shadow.card).
        shadow_xml = (f'<a:effectLst><a:outerShdw blurRad="{emu(35)}" dist="{emu(16)}"'
                      f' dir="5400000" rotWithShape="0">'
                      f'<a:srgbClr val="{shadow}"><a:alpha val="8000"/></a:srgbClr>'
                      f'</a:outerShdw></a:effectLst>')
    body = tx_body_xml(paras or [{"t": ""}], anchor, pad, wrap)
    return (f'<p:sp {NS}><p:nvSpPr>'
            f'<p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm{xfrm_rot}><a:off x="{emu(x)}" y="{emu(y)}"/>'
            f'<a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
            f'{geom_xml(prst, radius, w, h)}{fill_xml(fill, fill_alpha)}'
            f'{line_xml(line, line_w)}{shadow_xml}</p:spPr>{body}</p:sp>')


def lst_style_xml(d: dict) -> str:
    """자리 표시자의 기본 글자 모양. 슬라이드가 실제로 물려받는 것은 이쪽입니다."""
    sz = d.get("sz", 18)
    al = {"l": "l", "c": "ctr", "r": "r"}[d.get("al", "l")]
    return (f'<a:lstStyle><a:lvl1pPr marL="{emu(d.get("marL", 0))}"'
            f' indent="{emu(-d.get("marL", 0))}" algn="{al}" eaLnBrk="0" hangingPunct="0">'
            f'<a:lnSpc><a:spcPct val="{int(d.get("ln", 1.55) * 100000)}"/></a:lnSpc>'
            f'<a:spcBef><a:spcPts val="{int(d.get("sb", 0) * 100)}"/></a:spcBef>'
            f'<a:spcAft><a:spcPts val="{int(d.get("sa", 0) * 100)}"/></a:spcAft>'
            + ('<a:buNone/>' if not d.get("bullet") else
               f'<a:buClr><a:srgbClr val="{BLUE}"/></a:buClr><a:buSzPct val="100000"/>'
               f'<a:buFont typeface="Arial"/><a:buChar char="\u25cf"/>')
            + f'<a:defRPr sz="{int(sz * 100)}" b="{1 if d.get("b") else 0}"'
              f' spc="{int(round(d.get("spc", 0.0) * sz * 100))}">'
              f'{fill_xml(d.get("c", INK600))}'
              f'<a:latin typeface="{FONT}"/><a:ea typeface="{FONT}"/><a:cs typeface="{FONT}"/>'
              f'</a:defRPr></a:lvl1pPr></a:lstStyle>')


def ph_xml(sid: int, name: str, ph_type: str, idx: int | None,
           x: float, y: float, w: float, h: float, prompt: str,
           style: dict, anchor: str = "t") -> str:
    """레이아웃에 넣는 자리 표시자. 사람이 '새 슬라이드' 로 만들 때 쓰입니다."""
    idx_attr = f' idx="{idx}"' if idx is not None else ""
    type_attr = f' type="{ph_type}"' if ph_type else ""
    ins = ' lIns="0" tIns="0" rIns="0" bIns="0"'
    return (f'<p:sp {NS}><p:nvSpPr>'
            f'<p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr><p:ph{type_attr}{idx_attr}/></p:nvPr></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/>'
            f'<a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square"{ins} anchor="{anchor}"><a:noAutofit/></a:bodyPr>'
            f'{lst_style_xml(style)}'
            f'<a:p><a:r><a:rPr lang="ko-KR" dirty="0"/><a:t>{escape(prompt)}</a:t></a:r></a:p>'
            f'</p:txBody></p:sp>')


# ── 그리는 판 ──────────────────────────────────────────────────────────────

class Canvas:
    """슬라이드 하나 또는 레이아웃 하나에 도형을 얹는 판.

    `add()` 로 넣은 도형은 순서대로 등장 애니메이션을 받습니다(웹의 '나타나기').
    배경처럼 움직이지 않아야 하는 것은 `add(..., still=True)` 로 넣습니다.
    """

    def __init__(self, part, element):
        self.part = part
        self.spTree = element.find(qn("p:cSld")).find(qn("p:spTree"))
        self._id = 1 + max(
            [1] + [int(e.get("id")) for e in self.spTree.iter(qn("p:cNvPr"))])
        self.motion: list[int] = []
        # 글자가 상자 밖으로 새는지 나중에 기계로 검사하려고 자리를 적어 둡니다.
        # scripts/check-pptx.py 가 이 목록과 뽑아낸 PDF 를 맞춰 봅니다.
        self.boxes: list[tuple[float, float, float, float]] = []

    def _next(self) -> int:
        self._id += 1
        return self._id

    def add(self, maker, *, still: bool = False, **kw) -> int:
        sid = self._next()
        self.spTree.append(etree.fromstring(maker(sid, **kw)))
        if not still:
            self.motion.append(sid)
        return sid

    def shape(self, name, x, y, w, h, *, still=False, **kw) -> int:
        self.boxes.append((x, y, w, h))
        return self.add(lambda sid: sp_xml(sid, name, x, y, w, h, **kw), still=still)

    def group(self, *builders) -> None:
        """여러 도형을 한 덩어리로 나타나게 합니다. 첫 도형만 순서를 잡습니다."""
        first = None
        for build in builders:
            sid = build()
            if first is None:
                first = sid
            elif sid in self.motion:
                self.motion.remove(sid)

    def picture(self, path: Path, x, y, w, h, *, still=True) -> int:
        image_part, rid = self.part.get_or_add_image_part(str(path))
        sid = self._next()
        xml = (f'<p:pic {NS}><p:nvPicPr>'
               f'<p:cNvPr id="{sid}" name="배경 {sid}"/>'
               f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
               f'<p:nvPr/></p:nvPicPr>'
               f'<p:blipFill><a:blip r:embed="{rid}"/>'
               f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
               f'<p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/>'
               f'<a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
               f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
        self.spTree.append(etree.fromstring(xml))
        if not still:
            self.motion.append(sid)
        return sid


# ── 등장 애니메이션 ────────────────────────────────────────────────────────
# 웹의 '나타나기'(아래에서 22px 올라오며 흐려짐이 걷힌다, 550ms, 45ms 스태거)를
# 파워포인트로 옮긴 것입니다. 슬라이드가 열리면 클릭 없이 스스로 돕니다.
# 발표 중에 거슬리면 [애니메이션] 탭에서 통째로 지우면 됩니다.

RISE = 0.03      # 슬라이드 높이의 3% ≈ 21px. 웹의 22px 과 같은 정도입니다.
REVEAL = 550     # foundations/motion.md 의 duration.reveal
STAGGER = 120    # 슬라이드는 웹(45ms)보다 느긋해야 눈이 따라갑니다


def timing_xml(shape_ids: list[int]) -> str | None:
    if not shape_ids:
        return None
    seq, nid = [], 100
    for i, sid in enumerate(shape_ids):
        nid += 4
        seq.append(
            f'<p:par><p:cTn id="{nid}" presetID="42" presetClass="entr"'
            f' presetSubtype="4" fill="hold" grpId="0"'
            f' nodeType="{"afterEffect" if i else "withEffect"}">'
            f'<p:stCondLst><p:cond delay="{i * STAGGER}"/></p:stCondLst>'
            f'<p:childTnLst>'
            f'<p:set><p:cBhvr><p:cTn id="{nid + 1}" dur="1" fill="hold">'
            f'<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
            f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>'
            f'<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
            f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
            f'<p:anim calcmode="lin" valueType="num">'
            f'<p:cBhvr additive="base"><p:cTn id="{nid + 2}" dur="{REVEAL}" fill="hold"/>'
            f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>'
            f'<p:attrNameLst><p:attrName>ppt_y</p:attrName></p:attrNameLst></p:cBhvr>'
            f'<p:tavLst>'
            f'<p:tav tm="0"><p:val><p:strVal val="#ppt_y+{RISE}"/></p:val></p:tav>'
            f'<p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/></p:val></p:tav>'
            f'</p:tavLst></p:anim>'
            f'<p:animEffect transition="in" filter="fade">'
            f'<p:cBhvr><p:cTn id="{nid + 3}" dur="{REVEAL}"/>'
            f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
            f'</p:childTnLst></p:cTn></p:par>')
    return (
        f'<p:timing {NS}><p:tnLst><p:par>'
        f'<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        f'<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        f'<p:childTnLst><p:par><p:cTn id="3" fill="hold">'
        f'<p:stCondLst><p:cond delay="indefinite"/>'
        f'<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst>'
        f'<p:childTnLst>{"".join(seq)}</p:childTnLst>'
        f'</p:cTn></p:par></p:childTnLst></p:cTn>'
        f'<p:prevCondLst><p:cond evt="onPrev" delay="0">'
        f'<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        f'<p:nextCondLst><p:cond evt="onNext" delay="0">'
        f'<p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')


def apply_motion(slide, canvas: Canvas) -> None:
    """장이 넘어갈 때의 흐려짐과 도형의 등장을 함께 겁니다."""
    sld = slide.element
    sld.append(etree.fromstring(
        f'<p:transition {NS} spd="med" advClick="1"><p:fade/></p:transition>'))
    timing = timing_xml(canvas.motion)
    if timing is not None:
        sld.append(etree.fromstring(timing))


# ── 모눈 배경 그림 ─────────────────────────────────────────────────────────
# 표지의 모눈은 웹 히어로와 같은 것입니다(32px 간격, rgba(43,70,110,.045)).
# 선을 도형으로 60개 넣으면 편집할 때 자꾸 잡히므로 그림 한 장으로 만듭니다.
# 흰 바탕에 4.5% 로 겹친 색을 미리 계산해 둔 것이 아래 GRID_LINE 입니다.
GRID_BG, GRID_LINE = (255, 255, 255), (245, 247, 248)


def write_grid_png(path: Path, w: int = 2560, h: int = 1440, step: int = 64) -> Path:
    plain = bytearray()
    for x in range(w):
        plain += bytes(GRID_LINE if x % step == 0 else GRID_BG)
    ruled = bytes(GRID_LINE) * w
    raw = b"".join(b"\x00" + (ruled if y % step == 0 else bytes(plain)) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b""))
    return path


# ── 테마 · 슬라이드 마스터 · 레이아웃 ──────────────────────────────────────

def restyle_theme(prs) -> None:
    """색 고르개와 글꼴이 SHAPE 값을 내놓게 합니다.

    이걸 해 두면 부원이 [색] 단추를 눌렀을 때 나오는 첫 줄이 SHAPE 의 파랑·
    남색이 됩니다. 아무 색이나 고르는 일이 줄어드는 가장 값싼 방법입니다.
    """
    part = next(p for p in prs.part.package.iter_parts()
                if str(p.partname) == "/ppt/theme/theme1.xml")
    root = etree.fromstring(part.blob)
    ns = {"a": A}
    wanted = {
        "dk1": INK900, "lt1": WHITE, "dk2": NAVY, "lt2": SUNKEN,
        "accent1": BLUE, "accent2": NAVY, "accent3": NAVY_MID, "accent4": SKY,
        "accent5": INK500, "accent6": LINE_SOFT, "hlink": BLUE, "folHlink": BLUE_PRESS,
    }
    scheme = root.find(".//a:clrScheme", ns)
    scheme.set("name", "SHAPE")
    for child in scheme:
        key = etree.QName(child).localname
        if key not in wanted:
            continue
        for old in list(child):
            child.remove(old)
        etree.SubElement(child, f"{{{A}}}srgbClr").set("val", wanted[key])

    fonts = root.find(".//a:fontScheme", ns)
    fonts.set("name", "SHAPE")
    for group in ("majorFont", "minorFont"):
        node = fonts.find(f"a:{group}", ns)
        for tag in ("latin", "ea", "cs"):
            node.find(f"a:{tag}", ns).set("typeface", FONT)
    root.set("name", "SHAPE")
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                               standalone=True)


def drop_thumbnail(prs) -> None:
    """python-pptx 기본 판에 딸려 오는 미리보기 그림을 뗍니다.

    그대로 두면 파일 탐색기와 파인더가 SHAPE 와 아무 상관 없는 4:3 그림을
    이 파일의 얼굴로 보여 줍니다. 없는 편이 낫습니다.
    """
    package = prs.part.package
    for rid, rel in list(package._rels.items()):
        if rel.reltype.endswith("/thumbnail"):
            package.drop_rel(rid)


def clear_shapes(element) -> None:
    """spTree 에서 도형만 걷어 냅니다(그룹 속성 두 개는 남겨야 합니다)."""
    spTree = element.find(qn("p:cSld")).find(qn("p:spTree"))
    for child in list(spTree):
        if etree.QName(child).localname not in ("nvGrpSpPr", "grpSpPr"):
            spTree.remove(child)


def paint_background(element, color: str) -> None:
    cSld = element.find(qn("p:cSld"))
    for old in cSld.findall(qn("p:bg")):
        cSld.remove(old)
    bg = etree.fromstring(
        f'<p:bg {NS}><p:bgPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:effectLst/></p:bgPr></p:bg>')
    cSld.insert(0, bg)


def footer_shapes(canvas: Canvas, *, on_dark: bool = False, mark_only: bool = False) -> None:
    """꼬리말 — 왼쪽에 SHAPE, 오른쪽에 쪽 번호."""
    canvas.shape("꼬리말 SHAPE", M, FOOT_Y, 300, 22, still=True, paras=[{
        "t": "SHAPE", "sz": 11, "b": True, "spc": -0.02,
        "c": WHITE if on_dark else NAVY, "ln": 1.2}])
    if mark_only:
        return
    canvas.shape("쪽 번호", 1280 - M - 200, FOOT_Y, 200, 22, still=True, paras=[{
        "field": "slidenum", "fid": 1, "t": "2", "sz": 11, "b": True, "al": "r",
        "c": SKY if on_dark else INK300, "ln": 1.2}])


LAYOUTS = [
    # (이름, 만드는 함수 이름). 순서가 [새 슬라이드] 메뉴에 그대로 나옵니다.
    "SHAPE 표지",
    "SHAPE 섹션 표지",
    "SHAPE 제목과 내용",
    "SHAPE 두 단",
    "SHAPE 제목만",
    "SHAPE 사진과 설명",
    "SHAPE 마무리",
    "SHAPE 빈 화면",
]

TITLE_STYLE  = {"sz": 34, "b": True, "c": INK900, "spc": TR_TITLE, "ln": 1.15}
BODY_STYLE   = {"sz": 18, "c": INK600, "ln": 1.55, "sa": 10}
BULLET_STYLE = {**BODY_STYLE, "bullet": True, "marL": 30, "sa": 14}


def build_layouts(prs, grid_png: Path) -> list:
    master = prs.slide_masters[0]
    layouts = list(master.slide_layouts)

    # 마스터는 흰 종이 한 장입니다. 장식은 레이아웃이 저마다 얹습니다.
    paint_background(master.element, WHITE)
    clear_shapes(master.element)

    keep = layouts[:len(LAYOUTS)]
    for name, layout in zip(LAYOUTS, keep):
        el = layout.element
        el.set("preserve", "1")
        el.find(qn("p:cSld")).set("name", name)
        clear_shapes(el)
        paint_background(el, WHITE)
        canvas = Canvas(layout.part, el)
        sid = canvas._next

        if name == "SHAPE 표지":
            canvas.picture(grid_png, 0, 0, 1280, 720)
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "ctrTitle", None, M, 236, 940, 212,
                "제목을 적으세요",
                {"sz": 57, "b": True, "c": INK900, "spc": TR_HERO, "ln": 1.1},
                anchor="b")))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "부제", "subTitle", 1, M, 466, 800, 60,
                "한 줄 설명을 적으세요",
                {"sz": 20, "c": INK500, "ln": 1.4})))
            footer_shapes(canvas, mark_only=True)

        elif name == "SHAPE 섹션 표지":
            canvas.shape("남색 바탕", 0, 0, 1280, 720, still=True, fill=NAVY)
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, M, 300, 940, 100, "섹션 제목",
                {"sz": 44, "b": True, "c": WHITE, "spc": TR_DISPLAY, "ln": 1.15})))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "설명", "body", 1, M, 412, 800, 60,
                "이 섹션에서 다룰 것을 한 줄로",
                {"sz": 18, "c": SKY, "ln": 1.5})))
            footer_shapes(canvas, on_dark=True)

        elif name == "SHAPE 제목과 내용":
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, M, 88, CW, 66, "제목", TITLE_STYLE)))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "내용", "body", 1, M, BODY_T, CW, BODY_B - BODY_T,
                "내용을 적으세요", BULLET_STYLE)))
            footer_shapes(canvas)

        elif name == "SHAPE 두 단":
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, M, 88, CW, 66, "제목", TITLE_STYLE)))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "왼쪽", "body", 1, M, BODY_T, 540, BODY_B - BODY_T,
                "왼쪽 내용", BULLET_STYLE)))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "오른쪽", "body", 2, M + 580, BODY_T, 540, BODY_B - BODY_T,
                "오른쪽 내용", BULLET_STYLE)))
            footer_shapes(canvas)

        elif name == "SHAPE 제목만":
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, M, 88, CW, 66, "제목", TITLE_STYLE)))
            footer_shapes(canvas)

        elif name == "SHAPE 사진과 설명":
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, 660, 150, 540, 100, "제목", TITLE_STYLE)))
            canvas.spTree.append(etree.fromstring(
                f'<p:sp {NS}><p:nvSpPr><p:cNvPr id="{sid()}" name="사진"/>'
                f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                f'<p:nvPr><p:ph type="pic" idx="1"/></p:nvPr></p:nvSpPr>'
                f'<p:spPr><a:xfrm><a:off x="{emu(M)}" y="{emu(120)}"/>'
                f'<a:ext cx="{emu(520)}" cy="{emu(480)}"/></a:xfrm>'
                f'<a:prstGeom prst="roundRect"><a:avLst>'
                f'<a:gd name="adj" fmla="val {int(16 / 520 * 100000)}"/></a:avLst></a:prstGeom>'
                f'</p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "설명", "body", 2, 660, 268, 540, 300, "설명을 적으세요",
                BODY_STYLE)))
            footer_shapes(canvas)

        elif name == "SHAPE 마무리":
            canvas.shape("남색 바탕", 0, 0, 1280, 720, still=True, fill=NAVY)
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "제목", "title", None, M, 250, 1000, 180, "마무리 한마디",
                {"sz": 48, "b": True, "c": WHITE, "spc": TR_DISPLAY, "ln": 1.15})))
            canvas.spTree.append(etree.fromstring(ph_xml(
                sid(), "설명", "body", 1, M, 452, 800, 60, "연락처나 주소",
                {"sz": 20, "c": SKY, "ln": 1.5})))
            footer_shapes(canvas, on_dark=True)

        else:  # SHAPE 빈 화면 — 아래 예시 장들이 얹히는 판입니다.
            pass

    # 쓰지 않는 기본 레이아웃은 지웁니다. [새 슬라이드] 메뉴가 깨끗해집니다.
    id_list = master.element.find(qn("p:sldLayoutIdLst"))
    for entry in list(id_list)[len(LAYOUTS):]:
        rid = entry.get(qn("r:id"))
        id_list.remove(entry)
        master.part.drop_rel(rid)
    return keep


# ── 장을 짓는 조각들 ───────────────────────────────────────────────────────

def head(c: Canvas, eyebrow: str, title: str) -> None:
    """구획 라벨 + 제목. 본문 장은 전부 이 머리를 씁니다."""
    if eyebrow:
        c.shape("구획 라벨", M, 56, CW, 24, paras=[{
            "t": eyebrow, "sz": 13.5, "b": True, "c": BLUE,
            "spc": TR_EYEBROW, "ln": 1.2}])
    c.shape("제목", M, 86, CW, 74, paras=[{
        "t": title, "sz": 34, "b": True, "c": INK900, "spc": TR_TITLE, "ln": 1.15}])


def foot(c: Canvas, *, dark: bool = False) -> None:
    footer_shapes(c, on_dark=dark)


def bullets(c: Canvas, x, y, w, h, items, *, sz=18, gap=16, color=INK600,
            anchor="ctr") -> int:
    """글머리 목록. 굵은 앞머리와 설명을 `앞머리 — 설명` 으로 적습니다."""
    paras = []
    for line in items:
        strong, _, rest = line.partition(" — ")
        runs = [(strong, {"b": True, "c": INK900})]
        if rest:
            runs.append((" — " + rest, {"b": False, "c": color}))
        paras.append({"runs": runs, "sz": sz, "ln": 1.5, "sa": gap,
                      "marL": 30, "bullet": {"c": BLUE, "char": "●", "size": 0.65}})
    return c.shape("글머리", x, y, w, h, paras=paras, anchor=anchor)


def panel(c: Canvas, x, y, w, h, title, body, *, tone="plain") -> None:
    """두 단 비교에 쓰는 넓은 상자. tone 은 plain·blue·navy 셋뿐입니다."""
    fill, tcolor, bcolor, border = {
        "plain": (SUBTLE, INK900, INK600, None),
        "blue":  (BLUE, WHITE, WHITE, None),
        "navy":  (NAVY, WHITE, SKY, None),
        "line":  (WHITE, INK900, INK600, LINE_SOFT),
    }[tone]
    alpha = 0.8 if tone == "blue" else None
    c.shape(f"패널 {title}", x, y, w, h, fill=fill, line=border,
            prst="roundRect", radius=22, pad=(34, 32, 34, 30), anchor="t", paras=[
                {"t": title, "sz": 20, "b": True, "c": tcolor, "spc": TR_CARD,
                 "ln": 1.25, "sa": 12},
                {"t": body, "sz": 16, "c": bcolor, "alpha": alpha, "ln": 1.7}])


def card(c: Canvas, x, y, w, h, meta, title, body, *, tone="plain", action=None) -> None:
    """홈의 카드와 같은 것입니다. 세 장을 나란히 둘 때 흰·파랑·남색 순으로."""
    fill, border, mcolor, tcolor, bcolor = {
        "plain": (WHITE, LINE_SOFT, BLUE, INK900, INK500),
        "blue":  (BLUE, None, WHITE, WHITE, WHITE),
        "navy":  (NAVY_MID, None, SKY, WHITE, WHITE),
    }[tone]
    alpha = None if tone == "plain" else (0.75 if tone != "plain" else None)
    paras = [{"t": meta, "sz": 13, "b": True, "c": mcolor,
              "alpha": None if tone == "plain" else 0.9, "ln": 1.2, "sa": 16}]
    paras.append({"t": title, "sz": 20, "b": True, "c": tcolor, "spc": TR_CARD,
                  "ln": 1.25, "sa": 10})
    paras.append({"t": body, "sz": 15, "c": bcolor, "alpha": alpha, "ln": 1.7})
    if action:
        paras.append({"t": action + "  →", "sz": 14, "b": True,
                      "c": BLUE if tone == "plain" else WHITE, "ln": 1.4, "sb": 16})
    c.shape(f"카드 {title}", x, y, w, h, fill=fill, line=border, prst="roundRect",
            radius=18, pad=(30, 30, 30, 28), paras=paras)


def stat(c: Canvas, x, y, w, h, number, label, *, unit="") -> None:
    c.shape(f"숫자 {label}", x, y, w, h, fill=SURF_BLUE, prst="roundRect", radius=22,
            pad=(30, 30, 30, 28), anchor="ctr", paras=[
                {"runs": [(number, {"sz": 51, "b": True, "c": BLUE, "spc": TR_TITLE}),
                          (unit, {"sz": 22, "b": True, "c": BLUE, "spc": TR_CARD})],
                 "ln": 1.0, "sa": 12},
                {"t": label, "sz": 15, "b": True, "c": INK600, "ln": 1.3}])


def badge(c: Canvas, x, y, w, text, kind) -> None:
    fg, bg = ST[kind]
    c.shape(f"배지 {text}", x, y, w, 26, fill=bg, prst="roundRect", radius=13,
            anchor="ctr", paras=[{"t": text, "sz": 11, "b": True, "c": fg,
                                  "al": "c", "ln": 1.0}])


def photo_slot(c: Canvas, x, y, w, h, note="사진을 넣으세요", *, radius=16,
               circle=False) -> None:
    """사진 자리. 여기를 지우고 [삽입 → 그림] 으로 갈아 끼우면 됩니다."""
    c.shape("사진 자리", x, y, w, h, fill=SUNKEN, line=LINE_FAINT,
            prst="ellipse" if circle else "roundRect", radius=radius, anchor="ctr",
            paras=[{"t": note, "sz": 12, "b": True, "c": INK400, "al": "c", "ln": 1.3}])


def note_box(c: Canvas, x, y, w, h, text, *, kind="info") -> None:
    fg, bg = ST[kind]
    c.shape("안내", x, y, w, h, fill=bg, prst="roundRect", radius=14,
            pad=(18, 14, 18, 14), anchor="ctr",
            paras=[{"t": text, "sz": 14, "b": True, "c": fg, "ln": 1.5}])


def rail(c: Canvas, x, y, w) -> None:
    """가로 레일. 일정과 로드맵이 씁니다."""
    c.shape("레일", x, y, w, 2, fill=LINE_BASE, still=True)


def add_table(slide, c: Canvas, x, y, w, h, head_row, rows, widths,
              tints: dict[tuple[int, int], str] | None = None) -> None:
    """진짜 표를 넣습니다(도형으로 흉내 내면 칸을 못 고칩니다).

    기본 표 서식은 파란 줄무늬라 SHAPE 와 전혀 다릅니다. 머리는 옅은 회색,
    본문은 흰색, 칸 아래에만 옅은 선 — 사이트의 `.sh-table` 과 같게 다시 칠합니다.
    """
    from pptx.util import Emu
    c.boxes.append((x, y, w, h))
    frame = slide.shapes.add_table(len(rows) + 1, len(head_row),
                                   Emu(emu(x)), Emu(emu(y)), Emu(emu(w)), Emu(emu(h)))
    table = frame.table
    tbl = table._tbl
    props = tbl.find(qn("a:tblPr"))
    props.set("firstRow", "1")
    props.set("bandRow", "0")
    for child in list(props):
        props.remove(child)            # 기본 표 스타일(파란 줄무늬)을 뗍니다
    for i, width in enumerate(widths):
        table.columns[i].width = Emu(emu(width))
    table.rows[0].height = Emu(emu(48))
    for r in range(1, len(rows) + 1):
        table.rows[r].height = Emu(emu(46))

    for r, line in enumerate([head_row] + rows):
        for col, text in enumerate(line):
            cell = table.cell(r, col)
            is_head = r == 0
            align = "r" if (col == len(line) - 1 and not is_head) else "l"
            tc = cell._tc
            tc_pr = tc.get_or_add_tcPr()
            for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB", "a:lnTlToBr",
                        "a:lnBlToTr", "a:solidFill", "a:noFill"):
                for old in tc_pr.findall(qn(tag)):
                    tc_pr.remove(old)
            tc_pr.set("marL", str(emu(18)))
            tc_pr.set("marR", str(emu(18)))
            tc_pr.set("marT", str(emu(0)))
            tc_pr.set("marB", str(emu(0)))
            tc_pr.set("anchor", "ctr")
            # 사이트의 표는 칸 아래에만 선이 있습니다. 왼쪽·오른쪽·위는 명시적으로
            # 지워야 합니다 — 안 그러면 파워포인트가 기본 표 서식을 그려 넣습니다.
            for tag in ("lnL", "lnR", "lnT"):
                tc_pr.append(etree.fromstring(
                    f'<a:{tag} {NS} w="0"><a:noFill/></a:{tag}>'))
            tc_pr.append(etree.fromstring(
                f'<a:lnB {NS} w="{emu(1)}" cap="flat"><a:solidFill>'
                f'<a:srgbClr val="{LINE_SOFT}"/></a:solidFill></a:lnB>'))
            tc_pr.append(etree.fromstring(
                f'<a:solidFill {NS}><a:srgbClr val="{SUBTLE if is_head else WHITE}"/>'
                f'</a:solidFill>'))
            body = tc.find(qn("a:txBody"))
            for old in body.findall(qn("a:p")):
                body.remove(old)
            tint = (tints or {}).get((r, col))
            para = para_xml({"t": text, "sz": 15, "b": is_head or bool(tint),
                             "al": align, "ln": 1.3,
                             "c": tint or (INK500 if is_head else INK700)})
            body.append(etree.fromstring(para.replace("<a:p>", f"<a:p {NS}>", 1)))
    c.motion.append(int(frame.element.find(qn("p:nvGraphicFramePr"))
                        .find(qn("p:cNvPr")).get("id")))


# ── 예시 장 ────────────────────────────────────────────────────────────────
# 부원이 이 중에서 골라 복사해 쓰는 것이 이 파일의 쓰임새입니다.
# 그래서 장 수가 많고, 종류가 겹치지 않게 골랐습니다.

def new_slide(prs, layouts, kind="빈 화면"):
    layout = layouts[LAYOUTS.index(f"SHAPE {kind}")]
    slide = prs.slides.add_slide(layout)
    return slide, Canvas(slide.part, slide.element)


def ph_text(slide, idx: int, text: str, c: Canvas | None = None) -> int:
    """레이아웃에서 물려받은 자리 표시자를 채웁니다. 글자 모양은 레이아웃 것."""
    shape = next(s for s in slide.placeholders if s.placeholder_format.idx == idx)
    if c is not None:
        c.boxes.append((shape.left / PX, shape.top / PX,
                        shape.width / PX, shape.height / PX))
    body = shape.text_frame._txBody
    for old in body.findall(qn("a:p")):
        body.remove(old)
    runs = []
    for i, line in enumerate(text.split("\n")):
        if i:
            runs.append("<a:br/>")
        runs.append(f'<a:r><a:rPr lang="ko-KR" altLang="en-US" dirty="0"/>'
                    f'<a:t>{escape(line)}</a:t></a:r>')
    body.append(etree.fromstring(f'<a:p {NS}>{"".join(runs)}</a:p>'))
    return int(shape.element.find(qn("p:nvSpPr")).find(qn("p:cNvPr")).get("id"))


def slide_cover(prs, layouts):
    slide, c = new_slide(prs, layouts, "표지")
    c.shape("구획 라벨", M, 202, 700, 24, paras=[{
        "t": "SHAPE · 2026 SPRING", "sz": 13.5, "b": True, "c": BLUE,
        "spc": TR_EYEBROW, "ln": 1.2}])
    c.motion.append(ph_text(slide, 0, "사람을 위한\n로봇을 만듭니다", c))
    c.motion.append(ph_text(slide, 1, "서울대학교 휴머노이드·Physical AI 동아리 SHAPE", c))
    c.shape("날짜", 1280 - M - 300, FOOT_Y, 300, 22, still=True, paras=[{
        "t": "2026. 3. 4.", "sz": 11, "b": True, "c": INK300, "al": "r", "ln": 1.2}])
    return slide, c


def slide_howto(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "HOW TO USE", "이 템플릿을 쓰는 법")
    common = [
        "장을 복사해 고칩니다 — 마음에 드는 장을 복사(⌘D · Ctrl+D)하고 글자만 바꾸세요.",
        "색은 고르개 첫 줄만 씁니다 — 파랑·남색·먹으로 충분하고, 쓸 수 있는 색은 마지막 장에 있습니다.",
    ]
    if MODE == "slides":
        lines = [
            "먼저 사본을 만드세요 — 드라이브에 올려 [Google 슬라이드로 열기] 한 뒤 [파일 → 사본 만들기].",
            *common,
            "글꼴은 Noto Sans KR 입니다 — 구글 슬라이드에 이미 있어 깔 것이 없습니다.",
            "움직임은 [보기 → 애니메이션] 에 있습니다 — 몇 개는 다르게 들어올 수 있습니다.",
        ]
    else:
        lines = [
            *common,
            "글꼴은 Pretendard 입니다 — 안 깔려 있으면 자료실의 글꼴 묶음을 받아 설치하세요.",
            "움직임은 이미 들어 있습니다 — 거슬리면 [애니메이션] 탭에서 지우세요.",
        ]
    bullets(c, M, 182, 1060, 350, lines, sz=16, gap=14)
    note_box(c, M, 546, 1120, 52, "발표 자료를 다 만들었으면 이 장은 지우세요.", kind="warn")
    foot(c)
    return slide, c


def slide_contents(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "CONTENTS", "차례")
    items = [
        ("01", "우리는 무엇을 하는 사람들인가", "동아리의 방향과 지난 한 해"),
        ("02", "한 학기 동안 벌어지는 일", "세미나 · 프로젝트 · 공개 시연"),
        ("03", "동아리방과 장비", "301동 109호에 있는 것들"),
        ("04", "들어오는 방법", "지원 절차와 마감일"),
    ]
    for i, (num, title, desc) in enumerate(items):
        x = M + (i % 2) * 580
        y = 214 + (i // 2) * 180
        c.shape("구분선", x, y, 500, 2, fill=LINE_SOFT, still=True)
        c.shape(f"차례 {num}", x, y + 22, 500, 130, paras=[
            {"t": num, "sz": 15, "b": True, "c": BLUE, "spc": TR_EYEBROW, "ln": 1.2, "sa": 12},
            {"t": title, "sz": 22, "b": True, "c": INK900, "spc": TR_CARD, "ln": 1.25, "sa": 8},
            {"t": desc, "sz": 15, "c": INK500, "ln": 1.5}])
    foot(c)
    return slide, c


def slide_section(prs, layouts):
    slide, c = new_slide(prs, layouts, "섹션 표지")
    c.shape("섹션 번호", M, 200, 300, 90, paras=[{
        "t": "01", "sz": 58, "b": True, "c": SKY, "alpha": 0.45,
        "spc": TR_TITLE, "ln": 1.0}])
    c.motion.append(ph_text(slide, 0, "우리는 무엇을 하는 사람들인가", c))
    c.motion.append(ph_text(slide, 1, "만드는 사람이 모여 있는 곳입니다", c))
    return slide, c


def slide_bullets(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "", "직접 만들고, 직접 굴려 봅니다")
    bullets(c, M, 196, 1060, 416, [
        "매주 목요일 세미나 — 부원이 돌아가며 자기 작업을 발표합니다.",
        "학기 프로젝트 — 팀을 꾸려 한 학기에 하나를 끝까지 만듭니다.",
        "공개 시연 — 학기 말에 만든 것을 학교 안에서 굴려 봅니다.",
        "대회 참가 — 매년 두 번, 만든 것을 밖에서 겨뤄 봅니다.",
    ])
    foot(c)
    return slide, c


def slide_statement(prs, layouts):
    slide, c = new_slide(prs, layouts)
    c.shape("구획 라벨", M, 56, CW, 24, paras=[{
        "t": "01. ABOUT", "sz": 13.5, "b": True, "c": BLUE, "spc": TR_EYEBROW, "ln": 1.2}])
    c.shape("강조 막대", M, 210, 76, 8, fill=BLUE, prst="roundRect", radius=4, still=True)
    c.shape("한 줄", M, 248, 1000, 200, paras=[{
        "t": "만들어 보지 않으면\n아무것도 알 수 없습니다",
        "sz": 44, "b": True, "c": INK900, "spc": TR_DISPLAY, "ln": 1.2}])
    c.shape("받침 문장", M, 468, 860, 90, paras=[{
        "t": "그래서 SHAPE 는 배우는 자리보다 만드는 자리를 먼저 만듭니다. "
             "학기마다 팀이 하나씩 무언가를 끝까지 굴려 봅니다.",
        "sz": 18, "c": INK500, "ln": 1.7}])
    foot(c)
    return slide, c


def slide_two_col(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "02. PROGRAM", "두 갈래로 나뉩니다")
    panel(c, M, 206, 540, 356, "스터디",
          "처음 오는 사람을 위한 길입니다. 제어와 기구를 기초부터 함께 보고, "
          "학기 말에 작은 것을 하나 만듭니다.")
    panel(c, 660, 206, 540, 356, "프로젝트",
          "이미 만들어 본 사람을 위한 길입니다. 팀을 꾸려 바로 시작하고, "
          "필요한 장비는 동아리방에서 씁니다.", tone="blue")
    foot(c)
    return slide, c


def slide_cards(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "02. PROGRAM", "한 학기에 세 가지를 합니다")
    card(c, M, 206, 360, 340, "01", "정기 세미나",
         "매주 목요일 저녁, 부원이 돌아가며 자기 작업을 발표합니다.",
         action="일정 보기")
    card(c, 460, 206, 360, 340, "02", "학기 프로젝트",
         "팀을 꾸려 한 학기에 하나를 끝까지 만듭니다.", tone="blue",
         action="지난 결과 보기")
    card(c, 840, 206, 360, 340, "03", "공개 시연",
         "학기 말에 만든 것을 학교 안에서 실제로 굴려 봅니다.", tone="navy",
         action="사진 보기")
    foot(c)
    return slide, c


def slide_numbers(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "03. NUMBERS", "지금의 SHAPE")
    stat(c, M, 226, 360, 200, "98", "활동 부원", unit="명")
    stat(c, 460, 226, 360, 200, "12", "학기 프로젝트", unit="개")
    stat(c, 840, 226, 360, 200, "7", "함께 쓰는 장비", unit="대")
    c.shape("설명", M, 468, 1000, 80, paras=[{
        "t": "2026년 1학기 기준입니다. 부원 수는 매 학기 초에 다시 셉니다.",
        "sz": 15, "c": INK500, "ln": 1.6}])
    foot(c)
    return slide, c


def slide_table(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "04. SCHEDULE", "학기 일정")
    add_table(slide, c, M, 204, 1120, 280,
              ["주차", "내용", "장소", "상태"],
              [["1주", "오리엔테이션과 팀 소개", "301동 109호", "확정"],
               ["3주", "팀 구성과 주제 정하기", "301동 109호", "확정"],
               ["8주", "중간 발표", "301동 109호", "예정"],
               ["14주", "공개 시연", "미정", "조율 중"]],
              [160, 480, 280, 200],
              tints={(1, 3): ST["success"][0], (2, 3): ST["success"][0],
                     (3, 3): ST["info"][0], (4, 3): ST["warn"][0]})
    c.shape("표 설명", M, 512, 1000, 60, paras=[{
        "t": "일정이 바뀌면 사이트의 소식 탭에 먼저 올립니다.",
        "sz": 15, "c": INK500, "ln": 1.6}])
    foot(c)
    return slide, c


def slide_timeline(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "04. SCHEDULE", "한 학기는 이렇게 흘러갑니다")
    rail(c, 140, 372, 960)
    points = [
        ("3월", "모집과 배정", "설명회를 열고 팀을 나눕니다"),
        ("4월", "주제 정하기", "팀마다 만들 것을 정합니다"),
        ("5월", "중간 점검", "굴러가는 데까지 만들어 봅니다"),
        ("6월", "공개 시연", "학교 안에서 실제로 보입니다"),
    ]
    for i, (month, title, desc) in enumerate(points):
        x = 140 + i * 320
        c.shape("점", x - 9, 364, 18, 18, fill=BLUE, prst="ellipse", still=True)
        c.shape(f"월 {month}", x - 110, 306, 220, 34, still=True, paras=[{
            "t": month, "sz": 18, "b": True, "c": BLUE, "al": "c",
            "spc": TR_CARD, "ln": 1.2}])
        c.shape(f"단계 {title}", x - 130, 404, 260, 110, paras=[
            {"t": title, "sz": 18, "b": True, "c": INK900, "al": "c",
             "spc": TR_CARD, "ln": 1.3, "sa": 8},
            {"t": desc, "sz": 14, "c": INK500, "al": "c", "ln": 1.55}])
    foot(c)
    return slide, c


def slide_process(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "05. HOW", "지원부터 배정까지 네 걸음")
    steps = [("01", "지원서", "사이트에서 한 장 씁니다"),
             ("02", "면담", "무엇을 만들고 싶은지 이야기합니다"),
             ("03", "배정", "스터디와 프로젝트 중 하나로"),
             ("04", "시작", "첫 주 세미나부터 함께합니다")]
    for i, (num, title, desc) in enumerate(steps):
        x = M + i * 286
        tone_fill = BLUE if i == 3 else SUBTLE
        c.shape(f"단계 {num}", x, 232, 262, 212, fill=tone_fill, prst="roundRect",
                radius=22, pad=(26, 26, 26, 24), paras=[
                    {"t": num, "sz": 13, "b": True, "spc": TR_EYEBROW, "ln": 1.2, "sa": 14,
                     "c": WHITE if i == 3 else BLUE},
                    {"t": title, "sz": 19, "b": True, "spc": TR_CARD, "ln": 1.25, "sa": 8,
                     "c": WHITE if i == 3 else INK900},
                    {"t": desc, "sz": 14, "ln": 1.6,
                     "c": WHITE if i == 3 else INK500,
                     "alpha": 0.8 if i == 3 else None}])
        if i < 3:
            c.shape("화살표", x + 262, 322, 24, 30, still=True, paras=[{
                "t": "→", "sz": 18, "b": True, "c": INK300, "al": "c", "ln": 1.2}])
    c.shape("마감", M, 462, 1000, 60, paras=[{
        "runs": [("지원 마감 ", {"c": INK500}),
                 ("2026년 3월 8일 밤 12시", {"b": True, "c": INK900})],
        "sz": 17, "ln": 1.6}])
    foot(c)
    return slide, c


def slide_photo_text(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "06. SPACE", "동아리방은 이렇게 생겼습니다")
    photo_slot(c, M, 206, 520, 356)
    c.shape("사진 설명", 660, 206, 540, 360, paras=[
        {"t": "301동 109호", "sz": 22, "b": True, "c": INK900, "spc": TR_CARD,
         "ln": 1.25, "sa": 14},
        {"t": "공과대학 제1공학관 1층입니다. 작업대 여섯 자리와 공용 장비가 있고, "
              "학기 중에는 평일 아침부터 밤까지 열려 있습니다.",
         "sz": 16, "c": INK600, "ln": 1.75, "sa": 20},
        {"t": "들어오는 방법", "sz": 15, "b": True, "c": INK900, "ln": 1.4, "sa": 8},
        {"t": "정문에서 301동까지 셔틀로 10분, 내려서 1층 왼쪽 복도 끝입니다.",
         "sz": 15, "c": INK500, "ln": 1.7}])
    foot(c)
    return slide, c


def slide_photo_full(prs, layouts):
    slide, c = new_slide(prs, layouts)
    photo_slot(c, 0, 0, 1280, 720, "화면을 채우는 사진을 넣으세요", radius=0)
    c.shape("사진 위 설명", M, 430, 660, 176, fill=NAVY, prst="roundRect", radius=22,
            pad=(34, 30, 34, 28), paras=[
                {"t": "2025 공개 시연", "sz": 13, "b": True, "c": SKY,
                 "spc": TR_EYEBROW, "ln": 1.2, "sa": 12},
                {"t": "만든 것을 사람들 앞에서 굴립니다", "sz": 26, "b": True,
                 "c": WHITE, "spc": TR_CARD, "ln": 1.3}])
    foot(c)
    return slide, c


def slide_quote(prs, layouts):
    slide, c = new_slide(prs, layouts)
    c.shape("구획 라벨", M, 56, CW, 24, paras=[{
        "t": "VOICE", "sz": 13.5, "b": True, "c": BLUE, "spc": TR_EYEBROW, "ln": 1.2}])
    c.shape("따옴표", M, 150, 200, 120, still=True, paras=[{
        "t": "“", "sz": 90, "b": True, "c": BLUE, "alpha": 0.18, "ln": 1.0}])
    c.shape("인용", M, 236, 1040, 220, paras=[{
        "t": "처음 만든 것은 두 걸음 걷고 넘어졌습니다.\n그래도 그 두 걸음은 우리가 만든 것이었습니다.",
        "sz": 32, "b": True, "c": INK900, "spc": TR_TITLE, "ln": 1.4}])
    c.shape("말한 사람", M, 490, 700, 60, paras=[{
        "runs": [("김서연", {"b": True, "c": INK900}),
                 (" · 2025년 2학기 보행팀", {"c": INK500})],
        "sz": 16, "ln": 1.5}])
    foot(c)
    return slide, c


def slide_people(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "07. PEOPLE", "이 학기를 함께 굴리는 사람들")
    people = [("회장", "이름을 적으세요", "전체 운영과 대외 협력"),
              ("부회장", "이름을 적으세요", "프로젝트 진행과 장비"),
              ("총무", "이름을 적으세요", "회계와 동아리방 관리"),
              ("홍보", "이름을 적으세요", "소식과 사이트 관리")]
    for i, (role, name, desc) in enumerate(people):
        x = M + i * 290
        photo_slot(c, x + 45, 208, 160, 160, "사진", circle=True)
        c.shape(f"사람 {role}", x, 392, 250, 150, paras=[
            {"t": name, "sz": 19, "b": True, "c": INK900, "al": "c",
             "spc": TR_CARD, "ln": 1.3, "sa": 6},
            {"t": role, "sz": 14, "b": True, "c": BLUE, "al": "c", "ln": 1.4, "sa": 10},
            {"t": desc, "sz": 13, "c": INK500, "al": "c", "ln": 1.6}])
    foot(c)
    return slide, c


def slide_compare(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "08. CHANGE", "무엇을 바꾸려 합니까")
    for x, label, tone, lines, label_kind in (
        (M, "지금", "plain", ["장비를 쓰려면 운영진에게 카톡으로 물어봅니다",
                             "누가 언제 쓰는지 아무도 모릅니다",
                             "겹치면 그 자리에서 양보합니다"], "danger"),
        (660, "앞으로", "blue", ["사이트에서 빈 시간을 보고 바로 잡습니다",
                                "달력 한 장에 모두의 예약이 보입니다",
                                "겹친 신청만 운영진이 봅니다"], "success"),
    ):
        on_blue = tone == "blue"
        c.shape(f"비교 {label}", x, 204, 540, 356, fill=BLUE if on_blue else SUBTLE,
                prst="roundRect", radius=22, pad=(34, 30, 34, 30), paras=(
                    [{"t": label, "sz": 20, "b": True, "spc": TR_CARD, "ln": 1.25,
                      "sa": 20, "c": WHITE if on_blue else INK900}]
                    + [{"t": line, "sz": 16, "ln": 1.6, "sa": 16, "marL": 26,
                        "c": WHITE if on_blue else INK600,
                        "alpha": 0.85 if on_blue else None,
                        "bullet": {"c": WHITE if on_blue else INK400,
                                   "char": "●", "size": 0.65}}
                       for line in lines]))
    foot(c)
    return slide, c


def slide_roadmap(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "09. ROADMAP", "올해 어디까지 갑니다")
    rail(c, 140, 380, 960)
    stops = [("1분기", "팀 정비"), ("2분기", "첫 보행"), ("3분기", "대회 참가"),
             ("4분기", "공개 시연"), ("내년", "다음 기수에 넘기기")]
    for i, (when, what) in enumerate(stops):
        x = 140 + i * 240
        done = i < 2
        c.shape("점", x - 10, 371, 20, 20, prst="ellipse", still=True,
                fill=BLUE if done else WHITE, line=None if done else LINE_STRONG,
                line_w=2)
        c.shape(f"때 {when}", x - 110, 316, 220, 32, still=True, paras=[{
            "t": when, "sz": 15, "b": True, "c": BLUE if done else INK400,
            "al": "c", "spc": TR_CARD, "ln": 1.2}])
        c.shape(f"할 것 {what}", x - 110, 412, 220, 70, paras=[{
            "t": what, "sz": 17, "b": True, "c": INK900 if done else INK500,
            "al": "c", "spc": TR_CARD, "ln": 1.4}])
    note_box(c, M, 528, 1120, 52,
             "칠해진 점은 이미 지난 것입니다. 발표하는 날에 맞춰 옮기세요.", kind="info")
    foot(c)
    return slide, c


def slide_checklist(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "10. SUMMARY", "오늘 정한 것")
    for x, items in ((M, ["3월 8일까지 지원서를 받습니다",
                          "면담은 3월 10일부터 사흘 동안 합니다",
                          "팀은 3월 셋째 주에 나눕니다"]),
                     (660, ["장비 예약은 사이트에서만 받습니다",
                            "세미나 발표 순서는 첫 주에 정합니다",
                            "예산안은 다음 회의에서 확정합니다"])):
        c.shape("체크 목록", x, 200, 540, 300, anchor="ctr", paras=[
            {"t": line, "sz": 17, "c": INK700, "ln": 1.55, "sa": 22, "marL": 32,
             "bullet": {"c": BLUE, "char": "✓", "size": 0.9}}
            for line in items])
    note_box(c, M, 528, 1120, 52,
             "정하지 못한 것은 다음 회의로 넘깁니다 — 예산 배분과 대회 참가 여부.",
             kind="warn")
    foot(c)
    return slide, c


def slide_dark_statement(prs, layouts):
    slide, c = new_slide(prs, layouts)
    c.shape("남색 바탕", 0, 0, 1280, 720, fill=NAVY, still=True)
    c.shape("구획 라벨", M, 200, 700, 24, paras=[{
        "t": "WHAT WE NEED", "sz": 13.5, "b": True, "c": SKY,
        "spc": TR_EYEBROW, "ln": 1.2}])
    c.shape("한 줄", M, 250, 1040, 190, paras=[{
        "t": "지금 필요한 것은\n한 학기를 끝까지 가는 팀입니다",
        "sz": 42, "b": True, "c": WHITE, "spc": TR_DISPLAY, "ln": 1.25}])
    c.shape("받침 문장", M, 464, 900, 80, paras=[{
        "t": "잘하는 사람을 찾는 것이 아니라, 끝까지 남아 있는 사람을 찾습니다.",
        "sz": 18, "c": SKY, "ln": 1.7}])
    foot(c, dark=True)
    return slide, c


def slide_contact(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "CONTACT", "더 알고 싶으면")
    c.shape("연락 설명", M, 210, 500, 260, paras=[
        {"t": "궁금한 것은 아무 때나 물어봐 주세요. 동아리방은 학기 중 평일에 "
              "거의 열려 있고, 사이트의 문의 창구로 보내면 운영진이 함께 봅니다.",
         "sz": 17, "c": INK600, "ln": 1.75}])
    rows = [("동아리방", "서울대학교 301동 109호"),
            ("웹", "www.snu-shape.com"),
            ("문의", "사이트 → 바로가기 → 문의")]
    c.shape("연락 카드", 660, 204, 540, 336, fill=SUBTLE, prst="roundRect", radius=22,
            pad=(34, 32, 34, 30), paras=[
                para for label, value in rows for para in (
                    {"t": label, "sz": 13, "b": True, "c": INK400,
                     "ln": 1.2, "sa": 6},
                    {"t": value, "sz": 19, "b": True, "c": INK900,
                     "spc": TR_CARD, "ln": 1.3, "sa": 22})])
    foot(c)
    return slide, c


def slide_closing(prs, layouts):
    slide, c = new_slide(prs, layouts, "마무리")
    c.motion.append(ph_text(slide, 0, "함께 만들 사람을\n기다립니다", c))
    c.motion.append(ph_text(slide, 1, "www.snu-shape.com · 서울대학교 301동 109호", c))
    c.shape("단추", M, 548, 260, 56, fill=BLUE, prst="roundRect", radius=28,
            anchor="ctr", paras=[{"t": "지원서 쓰러 가기", "sz": 16, "b": True,
                                  "c": WHITE, "al": "c", "ln": 1.2}])
    return slide, c


def slide_palette(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "APPENDIX", "쓸 수 있는 색은 이만큼입니다")
    swatches = [(BLUE, "브랜드 파랑", "#2855F3"), (NAVY, "남색", "#0C245E"),
                (NAVY_MID, "짙은 카드", "#163C91"), (INK900, "먹", "#111111"),
                (INK500, "보조 글자", "#69717F"), (LINE_SOFT, "테두리", "#E2E6EE")]
    for i, (color, label, hexed) in enumerate(swatches):
        x = M + i * 190
        c.shape(f"색 {label}", x, 196, 170, 92, fill=color, prst="roundRect",
                radius=14, line=LINE_SOFT if color in (LINE_SOFT,) else None)
        c.shape(f"색 이름 {label}", x, 298, 170, 50, still=True, paras=[
            {"t": label, "sz": 14, "b": True, "c": INK900, "ln": 1.3, "sa": 4},
            {"t": hexed, "sz": 12, "c": INK400, "ln": 1.3}])
    c.shape("상태색 설명", M, 376, 1120, 30, still=True, paras=[{
        "t": "상태색은 글자색과 배경색이 늘 짝입니다. 표와 배지에만 쓰세요.",
        "sz": 14, "c": INK500, "ln": 1.4}])
    for i, (kind, label) in enumerate(
            [("info", "안내"), ("success", "됨"), ("warn", "조율 중"),
             ("danger", "안 됨"), ("staff", "운영진")]):
        fg, bg = ST[kind]
        x = M + i * 230
        c.shape(f"상태 {label}", x, 420, 200, 92, fill=bg, prst="roundRect",
                radius=14, anchor="ctr", pad=(20, 16, 20, 16), paras=[
                    {"t": label, "sz": 18, "b": True, "c": fg, "al": "c",
                     "ln": 1.3, "sa": 4},
                    {"t": kind, "sz": 12, "b": True, "c": fg, "alpha": 0.7,
                     "al": "c", "ln": 1.3}])
    note_box(c, M, 536, 1120, 52,
             "여기 없는 색은 쓰지 마세요. 강조가 필요하면 파랑 하나로 충분합니다.",
             kind="info")
    foot(c)
    return slide, c


def slide_type(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "APPENDIX", "글자 크기와 자간")
    ladder = [(57, "표지 제목", "사람을 위한 로봇", True, TR_HERO, 110),
              (34, "장 제목", "직접 만들고, 직접 굴려 봅니다", True, TR_TITLE, 74),
              (20, "작은 제목", "동아리방과 장비", True, TR_CARD, 50),
              (18, "본문", "한 장에 메시지 하나만 담습니다.", False, 0.0, 44),
              (15, "설명", "표와 각주에 쓰는 크기입니다.", False, 0.0, 40),
              (13.5, "구획 라벨", "CONTENTS", True, TR_EYEBROW, 36)]
    y = 182
    for size, name, sample, bold, spc, step in ladder:
        c.shape(f"크기 {name}", M, y + 6, 250, 30, still=True, paras=[{
            "t": f"{name} · {size:g}pt", "sz": 12, "b": True, "c": INK400, "ln": 1.3}])
        c.shape(f"보기 {name}", 360, y, 840, step + 10, paras=[{
            "t": sample, "sz": size, "b": bold,
            "c": BLUE if name == "구획 라벨" else INK900, "spc": spc, "ln": 1.15}])
        y += step
    note_box(c, M, 556, 1120, 52,
             "구글 슬라이드에는 자간 기능이 없어 큰 제목이 조금 헐거워 보입니다."
             if MODE == "slides" else
             "본문을 15pt 아래로 내리지 마세요. 뒷자리에서 읽히지 않습니다.",
             kind="info")
    foot(c)
    return slide, c


# ── 기본 장 ────────────────────────────────────────────────────────────────
# 꾸밈이 거의 없는 장들입니다. 어떤 내용에나 맞으므로 가장 많이 쓰이게 됩니다.
# 앞쪽에 모아 두어, 처음 여는 사람이 먼저 만나게 했습니다.

def slide_plain_text(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "", "제목을 적으세요")
    c.shape("본문", M, 200, 920, 330, paras=[
        {"t": "여기에 하고 싶은 말을 문단으로 적습니다. 한 장에 담는 이야기는 하나로 "
              "두고, 길어지면 장을 나누는 편이 읽힙니다.",
         "sz": 18, "c": INK600, "ln": 1.8, "sa": 22},
        {"t": "글머리도 상자도 없는, 가장 밋밋한 장입니다. 무엇을 넣어도 어색하지 "
              "않아서 회의 자료나 보고서에 그대로 쓸 수 있습니다.",
         "sz": 18, "c": INK600, "ln": 1.8}])
    foot(c)
    return slide, c


def slide_plain_two_col(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "", "두 가지를 나란히 놓을 때")
    for x, title, body in (
        (M, "왼쪽 제목", "상자도 색도 없이 글만 두 단으로 나눕니다. 견주는 내용이 "
                       "아니라 그냥 양이 많을 때 쓰기 좋습니다."),
        (700, "오른쪽 제목", "단 사이를 넉넉히 비워 두면 상자를 그리지 않아도 두 덩이로 "
                          "읽힙니다."),
    ):
        c.shape(f"단 {title}", x, 200, 500, 320, paras=[
            {"t": title, "sz": 20, "b": True, "c": INK900, "spc": TR_CARD,
             "ln": 1.3, "sa": 14},
            {"t": body, "sz": 17, "c": INK600, "ln": 1.75}])
    foot(c)
    return slide, c


def slide_plain_blocks(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "", "여러 갈래를 한 장에")
    blocks = [
        ("첫째 갈래", "소제목과 문단을 짝지어 쌓습니다. 셋까지가 한 장에 들어갑니다."),
        ("둘째 갈래", "가는 선 하나로만 나누면 장이 무거워지지 않습니다."),
        ("셋째 갈래", "더 필요하면 장을 나누세요. 넷을 넘기면 글자가 작아집니다."),
    ]
    for i, (title, body) in enumerate(blocks):
        y = 200 + i * 124
        c.shape("구분선", M, y, 1120, 1, fill=LINE_SOFT, still=True)
        c.shape(f"덩이 {title}", M, y + 18, 1000, 92, paras=[
            {"t": title, "sz": 19, "b": True, "c": INK900, "spc": TR_CARD,
             "ln": 1.3, "sa": 8},
            {"t": body, "sz": 16, "c": INK600, "ln": 1.7}])
    foot(c)
    return slide, c


def slide_plain_title(prs, layouts):
    slide, c = new_slide(prs, layouts)
    head(c, "", "제목만 있는 장")
    c.shape("안내", M, 320, 1120, 40, paras=[{
        "t": "여기에 표·그림·글을 직접 넣으세요.", "sz": 16, "c": INK300,
        "al": "c", "ln": 1.4}])
    foot(c)
    return slide, c


def slide_blank(prs, layouts):
    slide, c = new_slide(prs, layouts)
    c.shape("안내", M, 340, 1120, 40, paras=[{
        "t": "빈 장입니다. 이 글을 지우고 쓰세요.", "sz": 14, "c": INK300,
        "al": "c", "ln": 1.4}])
    foot(c)
    return slide, c


SLIDES = [
    slide_cover, slide_howto, slide_contents, slide_section,
    # 기본 — 꾸밈이 거의 없는 장
    slide_plain_text, slide_bullets, slide_plain_two_col, slide_plain_blocks,
    slide_plain_title, slide_blank,
    # 꾸민 장
    slide_statement, slide_two_col, slide_cards, slide_numbers, slide_table,
    slide_timeline, slide_process, slide_photo_text, slide_photo_full,
    slide_quote, slide_people, slide_compare, slide_roadmap, slide_checklist,
    slide_dark_statement, slide_contact, slide_closing, slide_palette, slide_type,
]

# 발표자 노트에 "이 장은 언제 쓰는 것인가" 를 적어 둡니다. 장을 복사해 쓰는
# 사람이 화면 밖에서 읽을 수 있는 유일한 자리입니다.
NOTES = [
    "표지. 큰 제목은 두 줄을 넘기지 마세요. 모눈 배경은 레이아웃에 들어 있어 지워지지 않습니다.",
    "쓰는 법 안내. 발표 자료를 다 만들었으면 이 장은 지우세요.",
    "차례. 항목이 여섯 개를 넘으면 두 장으로 나누세요.",
    "섹션 표지. 이야기가 크게 바뀌는 자리에만 넣습니다. 너무 자주 쓰면 흐름이 끊깁니다.",
    "기본 — 제목과 문단. 꾸밈이 없어 어디에나 맞습니다. 회의 자료는 이 장으로 충분합니다.",
    "기본 — 제목과 글머리. 가장 많이 쓰는 장입니다. 글머리는 다섯 줄을 넘기지 마세요.",
    "기본 — 두 단. 견주는 내용이 아니라 양이 많을 때 씁니다.",
    "기본 — 소제목 여러 개. 셋까지가 한 장에 들어갑니다.",
    "기본 — 제목만. 표나 그림을 직접 붙여 넣을 때 바탕으로 쓰세요.",
    "기본 — 빈 장. 아무것도 정해져 있지 않습니다.",
    "한 줄로 못 박을 때. 이 장에는 다른 것을 넣지 마세요.",
    "두 갈래를 나란히 놓을 때. 파란 쪽이 강조하고 싶은 쪽입니다.",
    "세 가지를 늘어놓을 때. 흰색·파랑·남색 순으로 두면 홈 화면과 같은 리듬이 납니다.",
    "숫자는 셋이 가장 읽기 좋습니다. 넷을 넘기면 표로 바꾸세요.",
    "표. 칸을 늘리려면 표 안에서 [행 삽입] 을 쓰세요. 상태 글자는 색으로 구분합니다.",
    "시간 순서를 보일 때. 점은 네 개까지가 읽힙니다.",
    "차례대로 밟는 절차. 마지막 칸만 파랑으로 두어 도착점을 보입니다.",
    "사진 한 장과 설명. 회색 자리를 지우고 [삽입 → 그림] 으로 넣으세요.",
    "사진으로 화면을 채울 때. 사진 위에 남색 상자를 얹어 글자가 읽히게 합니다.",
    "부원이나 밖에서 들은 말을 그대로 옮길 때.",
    "사람을 소개할 때. 동그란 자리에 사진을 넣습니다.",
    "지금과 앞으로를 견줄 때. 왼쪽이 문제, 오른쪽이 하려는 것입니다.",
    "긴 계획. 칠해진 점이 이미 지난 것입니다.",
    "회의나 발표를 닫으며 정리할 때.",
    "가장 중요한 한마디. 앞뒤로 흰 장이 있어야 힘이 삽니다.",
    "연락처. 사이트 주소와 동아리방은 그대로 두어도 됩니다.",
    "마무리. 단추는 눌러지지 않는 그림이므로, 필요하면 [삽입 → 링크] 를 거세요.",
    "부록 — 쓸 수 있는 색. 발표할 때는 지우고, 만들 때만 보세요.",
    "부록 — 글자 크기. 발표할 때는 지우고, 만들 때만 보세요.",
]


def main() -> None:
    out = out_path()
    prs = Presentation()
    prs.slide_width, prs.slide_height = emu(1280), emu(720)
    prs.core_properties.title = ("SHAPE 발표자료 템플릿 (구글 슬라이드)"
                                if MODE == "slides" else "SHAPE 발표자료 템플릿")
    prs.core_properties.author = "SHAPE"
    prs.core_properties.comments = (
        "서울대학교 로봇 동아리 SHAPE 의 공식 발표자료 템플릿입니다. "
        "www.snu-shape.com 과 같은 색·글자·여백을 씁니다.")

    restyle_theme(prs)
    boxes: list[list[tuple[float, float, float, float]]] = []
    grid = out.parent / "_shape-grid.png"
    write_grid_png(grid)
    try:
        layouts = build_layouts(prs, grid)
        for build, note in zip(SLIDES, NOTES):
            slide, canvas = build(prs, layouts)
            apply_motion(slide, canvas)
            slide.notes_slide.notes_text_frame.text = note
            boxes.append(canvas.boxes)
        drop_thumbnail(prs)
        out.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out))
    finally:
        grid.unlink(missing_ok=True)
    trace = os.environ.get("SHAPE_PPTX_BOXES")
    if trace:
        pathlib.Path(trace).write_text(json.dumps(boxes), encoding="utf-8")
    print(f"만들었습니다 — {out} ({out.stat().st_size:,} 바이트, {len(SLIDES)}장)")
    print(f"자료실 주소는 /downloads/{out.name} 입니다.")


if __name__ == "__main__":
    wanted = [a.lstrip("-") for a in sys.argv[1:] if a.lstrip("-") in VARIANTS] or list(VARIANTS)
    for MODE in wanted:
        FONT = VARIANTS[MODE]["font"]
        main()
