#!/usr/bin/env python3
"""K1 무대 운영 서버 — 버튼(preview→실행) · display 무대 화면 · dance 싱크.

  아이패드(/pad) ──버튼──> 이 서버 ──> Transport(mock/robot/relay/rc/fleet) ──> 로봇
  TV(/display)   ──폴링──> stage 상태 (idle/preview/executing/dance)

음성·LLM 경로는 제거됐다. `source="llm"` 요청은 안전하게 거부한다.

표준 라이브러리 + pyyaml 만 쓴다.
  python3 app.py                       # solo 모드, http 8000 (mock)
  python3 app.py --https               # https 8443
  python3 app.py --mode fleet --mock   # 라디오 플릿 모드, 라디오 없이
"""

from __future__ import annotations

import argparse
import http.cookies
import json
import mimetypes
import os
import secrets
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from runtime import clip_len
from runtime.robot_backend import RobotBackend
from runtime.relay_backend import RelayBackend
from runtime.rc_backend import RcBackend
from runtime.rc_fleet import RcFleetBackend
from runtime.session_log import SessionLog
from core.ports import SupportsDiscovery, Transport
from core.stage import Stage

HERE = Path(__file__).parent
# 앱은 하나고 모드가 둘이다. 모드가 정하는 것은 (1) 어느 데이터를 읽나 — 카탈로그·정책은 로봇의
# RC 다이얼 덤프가 달라 config/<모드>/ 에 따로 있다 — (2) 어느 화면을 여나 (3) 기본 포트·테마·백엔드.
# 새 모드는 이 표에 한 줄과 config/<모드>/ 폴더를 더하는 것으로 시작한다.
MODES = {
    "solo": {   # 로봇 1대, Wi-Fi(relay)/유선 RC. 관객 패드가 있다
        "landing": "/pad", "theme": "shape", "port": 8000, "port_https": 8443,
        "pages": {"/operator": "operator.html", "/display": "display.html",
                  "/pad": "pad.html", "/dance": "dance.html"},
    },
    "fleet": {  # 라디오 여러 대로 군무. 관객 패드가 없고 운영자가 기본 화면이다
        "landing": "/operator", "theme": "shape-gym", "port": 19000, "port_https": 19000,
        "pages": {"/operator": "operator.html", "/display": "display.html",
                  "/dance": "dance.html"},
    },
}
DEFAULT_MODE = "solo"
CONFIG = HERE / "config" / DEFAULT_MODE      # select_mode() 가 main() 에서 바꾼다
CATALOG = CONFIG / "motions.yaml"
GATEWAY_CONFIG = CONFIG / "gateway_config.yaml"


def select_mode(name):
    """모드가 읽을 데이터와 화면 표를 정한다. main() 의 첫 일이고, 테스트는 기본(solo)으로 돌린다."""
    global CONFIG, CATALOG, GATEWAY_CONFIG
    CONFIG = HERE / "config" / name
    CATALOG = CONFIG / "motions.yaml"
    GATEWAY_CONFIG = CONFIG / "gateway_config.yaml"
    Handler.mode = name
CERT = HERE / ".cert.pem"
KEY = HERE / ".key.pem"
# 동작 sim 렌더 클립. tools/render_motion.py 가 굽고 /display 가 튼다.
CLIPS = HERE / "clips"
# /dance 가 재생할 음원·영상. media/ 에 파일만 넣으면 목록에 뜬다.
MEDIA = HERE / "media"
# 화면은 전부 web/ 에 있다. themes/<이름>/ 이 관객 화면의 디자인 자산을 들고 있고,
# 활성 테마는 --theme 로 고른다.
WEB = HERE / "web"
THEMES = WEB / "themes"

MEDIA_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".mp4", ".webm", ".mov"}
# 행사별 설정은 config/venues/<이름>/ 에 있다 — 두 앱이 같이 쓴다.
#   venue.yaml   사람이 쓴다: 이번 행사의 패드 12칸(pad_grid)·메모
#   presets.json 서버가 쓴다: /dance 프리셋 = 동작-음원 짝 + 싱크 오프셋
# 오프셋은 코드가 아니라 그 장소의 물리량이다. 재보정한 값이 다음 행사의 출발점이 되도록
# 폴더째 커밋한다. 정책(gateway_config.yaml)과 카탈로그(motions.yaml)는 로봇에 평평하게
# 배포되는 파일이라 앱 폴더에 그대로 둔다.
VENUES = HERE / "config" / "venues"
DEFAULT_VENUE = "20260922-bank"
PRESETS = VENUES / DEFAULT_VENUE / "presets.json"   # main() 이 --venue 로 바꾼다


def _catalog():
    """공유 검증 코드(core/catalog.py). 앱 폴더의 core 링크로 보인다.

    로봇 컨테이너에는 core/stage.py · core/ports.py 만 간다 — catalog.py 는 안 간다. 로봇(--robot)은
    UI 가 없어 venue 를 안 쓰기 때문이다. 그래서 최상단 import 가 아니라 쓰는 자리에서 늦게 불러온다.
    최상단에 두면 로봇에서 server.py 가 import 에러로 안 뜬다 (배포 목록이 어긋났을 때 실제로 두 번
    났던 사고와 같은 모양이다).
    """
    from core import catalog
    return catalog


def load_venue(name=DEFAULT_VENUE):
    return _catalog().load_venue(VENUES / name)


def check_venue(name, gateway_config, *, require_media):
    """부팅 전 검증. FATAL 이 하나라도 있으면 기동을 거부한다.

    무대에서 발견하던 걸 노트북에서 발견하게 하는 것이 목적이다. tools/preflight.py 와
    같은 함수를 쓴다 — 두 벌이면 preflight 는 통과하는데 부팅은 실패하는 날이 온다.
    """
    cat = _catalog()
    try:
        venue = cat.load_venue(VENUES / name)
    except cat.VenueError as exc:
        sys.exit(f"\n  venue '{name}' 를 못 읽었다: {exc}\n")
    problems = cat.validate(yaml.safe_load(CATALOG.read_text()), gateway_config["policy"],
                            venue, clips_dir=CLIPS, media_dir=MEDIA,
                            require_media=require_media)
    fatal = [p for p in problems if p.level == cat.FATAL]
    warn = [p for p in problems if p.level != cat.FATAL]
    for p in fatal:
        print(f"  {p}")
    # WARN 이 스무 줄씩 쏟아지면 진짜 문제가 묻힌다. 개발 PC 는 클립·음원이 없어 늘 그렇다.
    for p in warn[:5]:
        print(f"  {p}")
    if len(warn) > 5:
        print(f"  WARN   … 외 {len(warn) - 5}건 — tools/preflight.py --venue {name} 로 전체를 본다")
    if fatal:
        sys.exit(f"\n  venue '{name}' 에 FATAL {len(fatal)}건 — 기동하지 않는다. "
                 f"(tools/preflight.py --venue {name} 로 전체 목록을 본다)\n")
    return venue

# ───────────────────────────────────────────────────────────── 카탈로그

def media_files():
    if not MEDIA.is_dir():
        return []
    return sorted(p.name for p in MEDIA.iterdir()
                  if p.is_file() and p.suffix.lower() in MEDIA_EXT)


_PRESET_LOCK = threading.Lock()


def load_presets():
    try:
        return json.loads(PRESETS.read_text())
    except (OSError, ValueError):
        return {}


def save_preset(name, preset):
    """preset dict 저장, None 이면 삭제. 갱신된 전체 프리셋을 돌려준다."""
    with _PRESET_LOCK:
        presets = load_presets()
        if preset is None:
            presets.pop(name, None)
        else:
            # /dance 보정 화면은 숫자·파일 필드만 보낸다. 무대 화면 표기용 title/credit 과
            # 영상 길이 media_len_sec 이 빠져 있으면 기존 값을 유지한다 — 안 그러면
            # 오프셋 한 번 저장에 제목·출처가 조용히 사라지고(개소식 당일 보정 시나리오),
            # 길이가 사라지면 무대 자동 종료가 기본 60초로 떨어져 84초짜리 응원 무대가
            # 곡 중간에 끊긴다 (2026-08-18 리뷰에서 재현).
            old = presets.get(name) or {}
            preset = dict(preset)
            for key in ("title", "credit", "media_len_sec"):
                if not preset.get(key) and old.get(key):
                    preset[key] = old[key]
            presets[name] = preset
        tmp = PRESETS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(presets, ensure_ascii=False, indent=2))
        tmp.replace(PRESETS)
        return presets


def load_catalog():
    doc = yaml.safe_load(CATALOG.read_text())
    items = list(doc.get("motions") or []) + list(doc.get("control_states") or [])
    return items, {m["state"]: m for m in items}


# ───────────────────────────────────────────────────────────── 백엔드

class MockBackend:
    """1단계. 로봇 없이 선택만 기록한다."""
    name = "mock"

    def submit(self, motion, source, reason):
        return {"ok": True, "status": "recorded", "motion": motion,
                "request_id": None, "msg": "기록됨 (로봇 미연결)"}

    def stop_motion(self, source, reason=""):
        return {"ok": True, "status": "recorded", "motion": "Velocity",
                "request_id": None, "msg": "정지 기록됨 (로봇 미연결)"}

    def status(self):
        return {"gateway": "mock", "robot": None, "current_request": None,
                "stop_state": "Velocity", "stop_available": True,
                "last_event": {"status": "mock", "msg": "로봇 미연결"}}

    def stop(self):
        pass


# ───────────────────────────────────────────────────────────── 상태

class State(Stage):
    """이 앱의 State — core.Stage 에 파일 경로·로더·어댑터를 꽂는 배선.

    도메인(무대 상태기계 · dance 스케줄 · 허용목록 교집합)은 core/stage.py 에 있고 여기엔 없다.
    이 클래스가 하는 일은 둘뿐이다: (1) 이 앱의 것(CLIPS · MEDIA · PRESETS · SessionLog)을 Stage 의
    인자로 꽂고, (2) 이 앱에만 있는 메서드를 갖는다.

    꽂을 때 값이 아니라 **함수**를 넘긴다 — 테스트가 server.MEDIA 같은 모듈 수준 이름을 바꿔 끼우고,
    /dance 는 실행 중에 프리셋을 저장한다. 시작할 때 한 번 읽은 값을 들고 있으면 안 된다.
    """

    def __init__(self, backend: Transport, ready_only=False, access_token=None,
                 session_log=None, pad_allowlist=None, api_allowlist=None):
        super().__init__(
            backend,
            catalog=load_catalog(),
            load_presets=lambda: load_presets(),
            media_files=lambda: media_files(),
            clip_seconds=lambda motion: clip_len.clip_duration(CLIPS, motion),
            clip_exists=lambda state: (CLIPS / f"{state}.mp4").is_file(),
            session_log=session_log or SessionLog(None, enabled=False),
            ready_only=ready_only, access_token=access_token,
            pad_allowlist=pad_allowlist, api_allowlist=api_allowlist)

    def set_rc_mode(self, on):
        """명령 경로 전환: on=True 면 유선 RC(ELRS), off 면 원래 백엔드 복귀.

        RC 백엔드는 켤 때마다 새로 만든다 — RcSerial 은 close 후 재사용이 안 되고,
        연결 진단(ping)을 이 시점에 해야 실패 원인을 운영자에게 보여줄 수 있다.
        UI·allowlist·무대는 그대로다: 다이얼에 없는 동작은 실행 시점에만 거부된다.
        """
        with self.lock:
            if on:
                if self.backend.name == "rc":
                    return {"ok": True, "backend": "rc", "msg": "이미 RC 모드입니다"}
                rc = RcBackend(CATALOG, GATEWAY_CONFIG, clips_dir=CLIPS)
                ok, msg = rc.connect_check()
                if not ok:
                    rc.stop()
                    return {"ok": False, "backend": self.backend.name, "msg": msg}
                self.backend = rc
                self.session_log.write("backend_switch", backend="rc")
                return {"ok": True, "backend": "rc", "msg": msg}
            if self.backend.name == "rc":
                self.backend.stop()  # 시리얼 포트 해제
                self.backend = self._primary_backend
                self.session_log.write("backend_switch", backend=self.backend.name)
            return {"ok": True, "backend": self.backend.name,
                    "msg": f"기본 경로({self.backend.name}) 복귀"}

    def rescan_rc(self):
        """USB 재탐색 — 지금 꽂혀 있는 Pocket 전부와 다시 연결한다 (fleet 모드)."""
        with self.lock:
            if not isinstance(self.backend, SupportsDiscovery):
                return {"ok": True, "backend": self.backend.name,
                        "msg": f"{self.backend.name} 백엔드 (재탐색 대상 아님)"}
            units = self.backend.rescan()
            ok, msg = self.backend.connect_check()
            self.session_log.write("rc_rescan", ok=ok, units=units, msg=msg)
            return {"ok": ok, "backend": self.backend.name, "msg": msg}


# ───────────────────────────────────────────────────────────── HTTP

class Handler(BaseHTTPRequestHandler):
    state: State = None  # main 에서 주입
    theme: str = "shape"  # 활성 테마 이름 (main 에서 주입)
    mode: str = DEFAULT_MODE  # select_mode() 가 주입 — 화면 표와 기본 화면이 여기서 갈린다
    # HTTP/1.1 이라야 relay 가 연결을 재사용한다 (무선 링크에서 핸드셰이크 반복을 줄인다).
    # _send() 가 항상 Content-Length 를 보내므로 keep-alive 가 안전하다.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 접근 로그는 끄고, 동작 선택만 보여준다

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        if not self.state.access_token:
            return True
        try:
            cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            return cookie.get("k1_gateway") and cookie["k1_gateway"].value == self.state.access_token
        except (http.cookies.CookieError, KeyError):
            return False

    def _send_clip(self, name):
        """동작 sim 클립 mp4. Range 요청(206)을 지원한다.

        Safari 는 Range 를 못 하는 video 를 아예 재생하지 않는다. 모니터가 아이패드일
        수도 있고 9MB 짜리 클립도 있어 탐색이 필요하다.

        파일명을 경로로 쓰지 않고 **카탈로그 state 이름과 대조**한다. 이름이 목록에
        없으면 파일을 열지도 않으므로 `../` 류 경로 탈출이 원천 차단된다.
        """
        if name not in self.state.by_state:
            return self._send(404, {"error": "not found"})
        clip = CLIPS / f"{name}.mp4"
        if not clip.is_file():
            return self._send(404, {"error": "clip not found"})
        return self._send_range(clip, "video/mp4", "public, max-age=3600")

    def _send_web(self, name):
        """저장소 루트 web/ 의 공유 프론트 파일 (base.css · tool.css · themes/).

        /theme/ 는 활성 테마 안만 보고, 이쪽은 실제 경로 그대로다. 테마가 다른 테마를
        @import 로 물려받을 때(shape-gym → shape) 쓰는 길이기도 하다.
        """
        if not name or name.startswith("/") or ".." in name:
            return self._send(404, {"error": "not found"})
        hit = (WEB / name).resolve()
        if not hit.is_file() or WEB.resolve() not in hit.parents:
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(hit.name)[0] or "application/octet-stream"
        return self._send_range(hit, ctype, "public, max-age=3600")

    def _send_theme(self, name):
        """활성 테마의 자산. 확장자 없이 오면 <name>.* 를 찾는다.

        대기 이미지는 테마마다 포맷이 달라(jpg/png) 페이지가 확장자를 알 수 없다.
        페이지는 늘 /theme/idle 로 요청하고 서버가 실제 파일을 고른다 — 그래서
        테마를 바꿔도 HTML 을 고칠 일이 없다.
        """
        if not name or "/" in name or ".." in name:
            return self._send(404, {"error": "not found"})
        folder = THEMES / self.theme
        hit = folder / name
        if not hit.is_file():
            found = sorted(folder.glob(name + ".*"))
            if not found:
                return self._send(404, {"error": f"theme asset not found: {name}"})
            hit = found[0]
        ctype = mimetypes.guess_type(hit.name)[0] or "application/octet-stream"
        return self._send_range(hit, ctype, "public, max-age=3600")

    def _send_media(self, name):
        """/dance 의 음원·영상. 파일명을 media/ 목록과 대조해 경로 탈출을 막는다."""
        if name not in media_files():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return self._send_range(MEDIA / name, ctype)

    # 아래 QuietServer 가 연결 끊김 예외를 조용히 넘긴다. 정의는 '실행' 구역에 있다.

    def _send_range(self, path, ctype, cache=None):
        """Range 요청(206) 지원 파일 응답. Safari 는 Range 없는 video 를 안 튼다."""
        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            first, _, last = rng[6:].partition("-")
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else size - 1
                else:                       # bytes=-500 → 마지막 500 바이트
                    start = max(0, size - int(last))
            except ValueError:
                start, end = 0, size - 1
            else:
                end = min(end, size - 1)
                if start > end:             # 범위가 파일 밖이면 416
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if cache:
            # 클립은 배포 전까지 안 바뀐다. 모니터가 매번 39MB 를 다시 받지 않게 한다.
            self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command == "HEAD":
            return
        remaining = end - start + 1
        try:
            with path.open("rb") as f:
                f.seek(start)
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # 브라우저가 전송 중에 끊는 것은 정상이다 — 영상 탐색, 클립 전환, 탭 닫기가
            # 전부 여기로 온다. /display 는 새 동작이 오면 재생 중인 클립을 갈아치우므로
            # 설계상 매번 일어난다. 잡지 않으면 운영자 터미널이 traceback 으로 뒤덮여
            # 진짜 오류가 묻힌다.
            pass

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path == "/":
            # 음성 폰 화면 제거(2026-08-18). 옛 북마크는 그 모드의 기본 화면으로 보낸다
            # (solo 는 관객 패드, fleet 은 운영자).
            query = urllib.parse.urlsplit(self.path).query
            self.send_response(302)
            self.send_header("Location", MODES[self.mode]["landing"] + (f"?{query}" if query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        pages = MODES[self.mode]["pages"]
        if path in pages:
            headers = None
            if self.state.access_token:
                supplied = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
                if supplied:
                    if not secrets.compare_digest(supplied, self.state.access_token):
                        return self._send(403, {"error": "invalid gateway token"})
                    headers = {"Set-Cookie": f"k1_gateway={self.state.access_token}; Path=/; Secure; HttpOnly; SameSite=Strict"}
                elif not self._authorized():
                    return self._send(403, {"error": "gateway authorization required"})
            return self._send(200, (WEB / pages[path]).read_bytes(),
                              "text/html; charset=utf-8", headers)
        if not self._authorized():
            return self._send(403, {"error": "gateway authorization required"})
        if path.startswith("/web/"):
            return self._send_web(path[len("/web/"):])
        if path.startswith("/theme/"):
            return self._send_theme(path[len("/theme/"):])
        if path.startswith("/clips/"):
            return self._send_clip(path[len("/clips/"):].removesuffix(".mp4"))
        if path == "/media":
            return self._send(200, {"files": media_files()})
        if path.startswith("/media/"):
            return self._send_media(urllib.parse.unquote(path[len("/media/"):]))
        if path == "/dance/presets":
            return self._send(200, {"presets": load_presets()})
        if path == "/motions":
            st = self.state
            return self._send(200, {
                "all": st.items,
                "llm_allowed": sorted(st.allowed),
                "pad_allowed": st.pad_order,   # 정렬 금지 — 순서가 그리드 스펙이다
                # /dance 가 고를 수 있는 무대 동작 = 이 행사의 프리셋이 쓰는 동작. 프리셋이 아직 없는
                # 새 행사면 패드 동작으로 시작한다. (예전엔 dance.html 에 3개가 박혀 있었고, 앱마다 달랐다)
                "dance_motions": sorted({p.get("motion") for p in load_presets().values()
                                         if p.get("motion")}) or st.pad_order,
                "clips": st.clip_states(),
                "backend": st.backend.name,
            })
        if path == "/log":
            # 락 안에서는 복사만 한다. 락을 쥔 채 느린 클라이언트에 전송하면
            # 그 동안 /motion·/stop 까지 전부 멈춘다 (리뷰 지적).
            with self.state.lock:
                entries = list(self.state.log)
            return self._send(200, {"log": entries})
        if path == "/conversation":
            return self._send(200, self.state.conversation_view())
        if path == "/status":
            return self._send(200, {**self.state.status(), "mode": self.mode})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if not self._authorized():
            return self._send(403, {"error": "gateway authorization required"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            # 끊긴 Wi-Fi 로 잘린 본문이 오면 예외가 그대로 올라가 응답 없이 연결이 끊기고
            # 운영자 터미널이 traceback 으로 덮인다. 400 으로 답하고 넘어간다.
            return self._send(400, {"ok": False, "error": "본문이 JSON 이 아닙니다"})

        if path == "/motion":
            out = self.state.play(payload.get("motion", ""),
                                  payload.get("reason", ""),
                                  payload.get("source", "llm"),
                                  payload.get("turn_id"))
            mark = "OK    " if out["ok"] else "REJECT"
            extra = f"   ← {out['reason']}" if out.get("reason") else ""
            plan = " *미학습" if out.get("status") == "planned" else ""
            print(f"  {out['t']}  {mark} [{out['source']:6s}] "
                  f"{out['ko']}{plan} ({out['motion']}) [{out.get('gateway_status', '')}]{extra}")
            if not out["ok"]:
                print(f"           {out['msg']}")
            return self._send(200, out)

        if path == "/conversation/clear":
            self.state.clear_conversation()
            return self._send(200, {"ok": True})

        if path == "/rc/mode" and self.mode == "solo":
            out = self.state.set_rc_mode(bool(payload.get("on")))
            print(f"  RC모드 {'ON 시도' if payload.get('on') else 'OFF'} → "
                  f"{out['backend']}  {out['msg']}")
            return self._send(200 if out["ok"] else 400, out)

        if path == "/rc/rescan" and self.mode == "fleet":
            out = self.state.rescan_rc()
            print(f"  RC 재탐색 → {out['msg']}")
            return self._send(200 if out["ok"] else 400, out)

        if path == "/stop":
            # source 는 서버가 강제한다. 클라이언트가 llm 을 주장할 수 없게 한다.
            out = self.state.stop_motion(payload.get("reason", ""))
            mark = "STOP  " if out["ok"] else "REJECT"
            print(f"  {out['t']}  {mark} [stop  ] {out['ko']} ({out['motion']}) "
                  f"[{out.get('gateway_status', '')}]")
            if not out["ok"]:
                print(f"           {out['msg']}")
            return self._send(200, out)

        if path == "/dance/presets":
            name = payload.get("name")
            preset = payload.get("preset")
            if not isinstance(name, str) or not name.strip():
                return self._send(400, {"error": "name 이 필요합니다"})
            if preset is not None and not isinstance(preset, dict):
                return self._send(400, {"error": "preset 은 객체 또는 null"})
            if preset is not None:
                # 저장 시점에 숫자 필드를 걸러야 쇼 시작 순간에 터지지 않는다 (리뷰).
                for key in ("offset_ms", "seek", "volume"):
                    if key in preset and preset[key] is not None:
                        try:
                            float(preset[key])
                        except (TypeError, ValueError):
                            return self._send(400, {"error": f"{key} 는 숫자여야 합니다"})
            return self._send(200, {"ok": True,
                                    "presets": save_preset(name.strip(), preset)})

        if path == "/stage":
            # display 상태 전환. executing/dance 는 이 경로로 못 만든다 —
            # 각각 /motion 성공과 /dance/start 만이 만든다.
            stage = payload.get("stage")
            st = self.state
            # 무대(dance) 진행 중에는 패드가 stage 를 못 건드린다 (2026-08-18 사용자
            # 확정). 관객 탭 하나가 진행 중인 무대를 소리 없이 죽이던 경로다 — 무대는
            # /dance/stop(운영자)과 영상 종료만이 내릴 수 있다. 실행 중에는 새 preview
            # 만 막는다 (idle 은 패드의 완료 복귀라 허용).
            current = st.effective_stage()
            if current == "dance" and stage in {"idle", "preview"}:
                return self._send(409, {"ok": False, "error": "무대 진행 중"})
            if current == "executing" and stage == "preview":
                return self._send(409, {"ok": False, "error": "동작 실행 중"})
            # listening/thinking 은 음성 제거(2026-08-18)와 함께 폐기됐다.
            if stage == "idle":
                st.set_stage(stage)
                return self._send(200, {"ok": True, "stage": stage})
            if stage == "preview":
                motion = payload.get("motion") or ""
                info = st.by_state.get(motion)
                if (not info or motion not in st.pad_allowed
                        or not (CLIPS / f"{motion}.mp4").is_file()):
                    return self._send(400, {"ok": False,
                                            "error": "preview 할 수 없는 동작"})
                st.set_stage("preview", {"motion": motion, "ko": info["ko"]})
                return self._send(200, {"ok": True, "stage": "preview",
                                        "motion": motion, "ko": info["ko"]})
            return self._send(400, {"ok": False, "error": f"허용되지 않은 stage: {stage}"})

        if path == "/dance/start":
            preset = payload.get("preset")
            if preset is not None and not isinstance(preset, dict):
                return self._send(400, {"ok": False, "msg": "preset 은 객체여야 합니다"})
            out = self.state.start_dance(payload.get("name") or None, preset)
            print(f"  DANCE {'시작' if out['ok'] else '거부'}  "
                  f"{payload.get('name') or '(직접 설정)'}  {out.get('msg', '')}")
            return self._send(200 if out["ok"] else 400, out)

        if path == "/dance/stop":
            out = self.state.stop_dance(payload.get("reason", "무대 정지"))
            print("  DANCE 정지")
            return self._send(200, out)

        return self._send(404, {"error": "not found"})


# ───────────────────────────────────────────────────────────── 실행

class QuietServer(ThreadingHTTPServer):
    """클라이언트가 끊어서 나는 예외는 조용히 넘긴다.

    영상 탐색, 클립 전환, 탭 닫기가 전부 연결 끊김으로 온다. /display 는 새 동작이
    오면 재생 중인 클립을 갈아치우므로 **설계상 매번** 일어난다. 기본 동작대로 두면
    운영자 터미널이 traceback 으로 뒤덮여 진짜 오류가 묻힌다.

    TLS 라 끊김이 두 모양으로 온다 — 쓰다가 나는 BrokenPipe/ConnectionReset 과,
    keep-alive 연결에서 다음 요청을 읽으려다 나는 ssl.SSLError(UNEXPECTED_EOF).
    그 밖의 예외는 그대로 올려서 진짜 문제를 놓치지 않는다.
    """

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return
        if isinstance(exc, ssl.SSLError) and "EOF" in str(exc).upper():
            return
        super().handle_error(request, client_address)


def ensure_cert():
    if CERT.exists() and KEY.exists():
        return True
    try:
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(KEY), "-out", str(CERT), "-days", "365",
             "-subj", "/CN=k1-stage"],
            check=True, capture_output=True)
        print(f"  자체 서명 인증서 생성됨: {CERT.name}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ! 인증서 생성 실패: {e}")
        return False


def local_ips():
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout
        return [ip for ip in out.split() if ":" not in ip and not ip.startswith("172.")]
    except Exception:  # noqa: BLE001
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default=DEFAULT_MODE, choices=sorted(MODES),
                    help="solo: 로봇 1대(Wi-Fi/RC) · fleet: 라디오 여러 대 군무 (기본: solo)")
    ap.add_argument("--port", type=int, default=0,
                    help="기본: solo http 8000 / https 8443, fleet 19000")
    ap.add_argument("--https", action="store_true", help="자체 서명 HTTPS 로 서빙")
    ap.add_argument("--robot", action="store_true", help="[solo] RobotBackend 사용 (로봇 안에서)")
    ap.add_argument("--relay", metavar="URL",
                    help="PC relay 모드. 예: https://192.168.60.1:8443")
    ap.add_argument("--relay-token", default=os.environ.get("K1_RELAY_TOKEN", ""),
                    help="로봇 gateway token (기본: K1_RELAY_TOKEN)")
    ap.add_argument("--rc", action="store_true",
                    help="[solo] RcBackend 사용 — 유선 RC(ELRS) 경로로 명령 전송")
    ap.add_argument("--mock", action="store_true",
                    help="로봇·라디오 없이 UI/무대 흐름만 확인 (기록만 하는 가짜 백엔드). solo 는 기본이 mock")
    ap.add_argument("--gateway-token", default=os.environ.get("K1_GATEWAY_TOKEN", ""),
                    help="이 gateway의 고정 token (기본: K1_GATEWAY_TOKEN 또는 랜덤)")
    ap.add_argument("--ready-only", action="store_true",
                    help="학습 끝난 동작만 LLM 에 노출 (로봇 연결 시)")
    ap.add_argument("--log-dir", default=str(HERE / "logs"),
                    help="turn 단위 JSONL 세션 로그 위치 (기본: logs/)")
    ap.add_argument("--no-log", action="store_true", help="세션 로그를 끈다")
    ap.add_argument("--venue", default=DEFAULT_VENUE,
                    help="행사 설정 (config/venues/ 의 폴더명). 패드 12칸과 프리셋이 여기서 온다")
    ap.add_argument("--theme", default=None,
                    help="관객 화면 디자인 테마 (web/themes/ 의 폴더명). 기본은 모드가 정한다")
    ap.add_argument("--no-transcripts", action="store_true",
                    help="발화 원문 대신 길이만 기록 (행사장 프라이버시 모드)")
    args = ap.parse_args()
    mode = MODES[args.mode]
    select_mode(args.mode)
    if args.mode == "fleet" and (args.robot or args.relay or args.rc):
        ap.error("--robot / --relay / --rc 는 solo 모드 전용입니다 (fleet 은 라디오 전부에 직접 쏩니다)")
    if sum(map(bool, (args.robot, args.relay, args.rc))) > 1:
        ap.error("--robot / --relay / --rc 는 동시에 사용할 수 없습니다")
    if (args.robot or args.relay or args.rc) and not args.https:
        ap.error("--robot/--relay/--rc 는 토큰 cookie 보호를 위해 --https 와 함께 실행해야 합니다")
    if args.relay and not args.relay_token:
        ap.error("--relay 는 --relay-token 또는 K1_RELAY_TOKEN 이 필요합니다")

    port = args.port or (mode["port_https"] if args.https else mode["port"])
    gateway_config = yaml.safe_load(GATEWAY_CONFIG.read_text())
    if args.robot:
        backend = RobotBackend(GATEWAY_CONFIG)
    elif args.relay:
        policy = gateway_config["policy"]
        backend = RelayBackend(args.relay, args.relay_token, policy["api_allowlist"],
                               policy.get("relay_timeout_sec", 2.0))
    elif args.rc:
        backend = RcBackend(CATALOG, GATEWAY_CONFIG, clips_dir=CLIPS)
    elif args.mode == "fleet" and not args.mock:
        backend = RcFleetBackend(CATALOG, clips_dir=CLIPS)
    else:
        backend = MockBackend()
    if args.robot:
        backend.start()
    venue = None
    if not args.robot:   # 로봇은 UI 가 없다 — venue 도 검증도 필요 없다
        # 음원은 저작권물이라 저장소에 없다. mock 은 화면만 보는 개발 실행이라 없어도 뜬다.
        venue = check_venue(args.venue, gateway_config,
                            require_media=not isinstance(backend, MockBackend))
        global PRESETS
        PRESETS = venue["dir"] / "presets.json"
    session_log = SessionLog(args.log_dir, transcripts=not args.no_transcripts,
                             enabled=not args.no_log)
    Handler.state = State(
        backend,
        # 실제 통신 경로(로봇·relay·RC·라디오 플릿)면 학습 끝난 동작만 연다. mock 은 전부 보인다.
        ready_only=args.ready_only or not isinstance(backend, MockBackend),
        access_token=args.gateway_token or None,
        api_allowlist=gateway_config["policy"]["api_allowlist"],
        pad_allowlist=venue["pad_grid"] if venue else None,
        session_log=session_log,
    )
    Handler.theme = args.theme or mode["theme"]
    st = Handler.state
    started_at = time.monotonic()
    session_log.write("session_start", backend=backend.name,
                      ready_only=st.ready_only, pad=sorted(st.pad_allowed))
    if session_log.enabled:
        print(f"  세션 로그  {session_log.path}"
              + ("  [전사 원문 제외]" if args.no_transcripts else ""))

    httpd = QuietServer(("0.0.0.0", port), Handler)
    scheme = "http"
    if args.https and ensure_cert():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT, KEY)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    print()
    n_ready = sum(1 for m in st.items if m.get("status", "ready") == "ready")
    print(f"  카탈로그 {len(st.items)}개 (학습완료 {n_ready} / 예정 {len(st.items)-n_ready})")
    print(f"  패드 버튼 {len(st.pad_allowed)}개 · 백엔드 {st.backend.name}")
    print()
    print(f"  PC   {scheme}://localhost:{port}")
    for ip in local_ips():
        print(f"  폰   {scheme}://{ip}:{port}")
    if not args.https:
        print("  (폰에서 마이크를 쓰려면 --https 로 다시 실행하세요)")
    if st.access_token:
        print(f"  제어 URL  {scheme}://<robot-ip>:{port}/?token={st.access_token}")
    print("\n  선택된 동작이 아래에 찍힙니다. Ctrl-C 로 종료.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  종료\n")
    finally:
        session_log.write("session_end",
                          uptime_sec=round(time.monotonic() - started_at, 1))
        session_log.close()
        st.backend.stop()


if __name__ == "__main__":
    main()
