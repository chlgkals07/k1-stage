#!/usr/bin/env python3
"""K1 무대 운영 서버 — 버튼(preview→실행) · display 무대 화면 · dance 싱크.

  아이패드(/pad) ──버튼──> 이 서버 ──> MotionBackend(mock/robot/relay) ──> 로봇
  TV(/display)   ──폴링──> stage 상태 (idle/preview/executing/dance)

음성·LLM 경로는 2026-08-18 에 제거했다. 재개발은 voice-llm-dev 브랜치에서 한다
(`docs/voice/`). 이 파일에 남은 llm_allowlist·source=="llm" 검사는 그때 쓸 구조다.

표준 라이브러리 + pyyaml 만 쓴다.
  python3 server.py            # http 8000 (mock)
  python3 server.py --https    # https 8443
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
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

import clip_len
from robot_backend import RobotBackend
from relay_backend import RelayBackend
from rc_backend import RcBackend
from session_log import SessionLog

HERE = Path(__file__).parent
CATALOG = HERE / "motions.yaml"
CERT = HERE / ".cert.pem"
KEY = HERE / ".key.pem"
# 동작 sim 렌더 클립. tools/render_motion.py 가 굽고 /display 가 튼다.
CLIPS = HERE / "static" / "clips"
# /dance 가 재생할 음원·영상. media/ 에 파일만 넣으면 목록에 뜬다.
MEDIA = HERE / "media"
# 공유 프론트. 저장소 루트의 web/ 를 두 앱이 함께 쓴다 (한 벌만 유지).
# themes/<이름>/ 이 관객 화면의 디자인 자산을 들고 있고, 활성 테마는 --theme 로 고른다.
WEB = HERE.parent / "web"
THEMES = WEB / "themes"
# 관객 화면(display · pad)은 두 앱이 web/ 한 벌을 같이 쓴다. 운영자 화면
# (operator · dance)은 아직 앱마다 다르다 — operator 는 RC 토글과 플릿 재탐색으로
# 갈리고, dance 는 프리셋 유실 수정이 group 에만 있다(main 에서 포팅할 것).
# 여기 목록이 비면 static/ 이 사라지고 화면 넷이 전부 web/ 에 있게 된다.
SHARED_PAGES = {"display.html", "pad.html"}


def page_dir(page):
    return WEB if page in SHARED_PAGES else HERE / "static"

MEDIA_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".mp4", ".webm", ".mov"}
# /dance 프리셋: 동작-음원 짝 + 싱크 오프셋. 서버 파일이라 어느 기기에서 열어도 같다.
PRESETS = HERE / "dance_presets.json"

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


def llm_motions(items, ready_only=False):
    """LLM 에게 노출할 것만. restricted 는 llm 플래그와 무관하게 제외한다.

    ready_only=True 면 학습이 끝난 것(status: ready)만 남긴다. 로봇에 붙일 때 쓴다.
    status 가 없으면 ready 로 본다.
    """
    out = [m for m in items if m.get("llm") and m.get("safety") != "restricted"]
    if ready_only:
        out = [m for m in out if m.get("status", "ready") == "ready"]
    return out


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

class State:
    def __init__(self, backend, ready_only=False, access_token=None, llm_allowlist=None,
                 session_log=None, pad_allowlist=None, pad_llm_exclude=None):
        self.backend = backend
        # RC 모드 토글의 복귀 지점. 토글은 self.backend 만 바꾼다.
        self._primary_backend = backend
        self.ready_only = ready_only
        self.items, self.by_state = load_catalog()
        self.allowed = {m["state"] for m in llm_motions(self.items, ready_only)}
        if hasattr(backend, "api_allowlist"):
            self.allowed &= backend.api_allowlist
        if llm_allowlist is not None:
            self.allowed &= set(llm_allowlist)
        # 관객용(/pad) 버튼 목록. self.allowed 와 같은 방식으로 교집합을 취해
        # 카탈로그·api 밖 항목이 오타 하나로 조용히 통과하는 일이 없게 한다.
        self.pad_allowed = set(pad_allowlist or ())
        self.pad_allowed &= set(self.by_state)
        if hasattr(backend, "api_allowlist"):
            self.pad_allowed &= backend.api_allowlist
        # 패드 그리드 번호 = 목록 순서 (2026-08-18 사용자 확정 스펙).
        # set 은 순서를 잃으므로 원본 순서를 따로 보존해 API 로 내보낸다.
        self.pad_order = [s for s in (pad_allowlist or ()) if s in self.pad_allowed]
        self.pad_llm_exclude = set(pad_llm_exclude or ())
        self.session_log = session_log or SessionLog(None, enabled=False)
        self.log = deque(maxlen=200)
        # display(무대 화면)가 폴링으로 읽는 현재 동작. 자막 버퍼는 음성과 함께 제거됨.
        self.current_motion = ""
        # 클립 파일은 영문 state 로 찾는다. 화면에 쓰는 한글 이름과 별개로 들고 있어야 한다.
        self.current_motion_state = ""
        self.rev = 0
        # rev 는 자막 delta 에도 오르므로 "동작이 시작됐다"를 구분할 수 없다.
        # motion_rev 는 동작이 실제로 나갈 때만 오른다. 같은 동작을 연달아 눌러도
        # 값이 바뀌므로 모니터가 클립을 다시 튼다.
        self.motion_rev = 0
        # display(무대 화면)가 보여줄 상태. 어느 기기가 조작하든 display 는 서버만 본다.
        # idle | listening | thinking | preview | executing | dance
        self.stage = "idle"
        self.stage_data = {}
        self.stage_set_at = time.time()
        self.stage_rev = 0
        self._dance_timer = None
        # RC 백엔드 전용: 발사 1.5s 전에 다이얼·게이트를 미리 잡는 PREP 타이머
        self._dance_prep_timer = None
        # display 가 없을 때의 무대 자동 종료 fallback (추정 길이 + 여유 뒤)
        self._dance_autostop_timer = None
        # executing 화면을 동작 길이만큼 지나면 스스로 내리는 타이머
        self._exec_idle_timer = None
        # 무대 세대 번호. Timer.cancel() 은 이미 시작된 콜백을 못 멈추므로, 콜백이
        # "내가 걸렸던 그 무대가 아직 유효한가"를 이 번호로 확인한다. stage=='dance'
        # 검사만으로는 부족하다 — A 재생 중 B 를 시작하면 A 의 늦은 콜백이 B 가 만든
        # dance 를 보고 통과해 B 음악에 A 동작이 나간다 (리뷰 지적).
        self._dance_gen = 0
        self.lock = threading.Lock()
        # rc 도 실제 로봇을 움직인다. 빠져 있어서 `--rc` 단독 기동 시 토큰 없이
        # 누구나 /motion 을 쏠 수 있었다 (main() 은 --https 를 강제하면서 인증만 빠졌다).
        protected = backend.name in {"robot", "relay", "rc"}
        self.access_token = (access_token or secrets.token_urlsafe(32)) if protected else None

    def clear_conversation(self):
        """무대 리셋. (자막 버퍼는 음성 제거 2026-08-18 와 함께 사라졌다)"""
        with self.lock:
            self.current_motion = ""
            self.current_motion_state = ""
            self.rev += 1
            # motion_rev 는 되돌리지 않는다. 모니터가 "새 동작"으로 오해해 이미 끝난
            # 클립을 다시 트는 것을 막는다.
            self._set_stage_locked("idle")

    # 패드가 죽거나 이벤트를 놓쳐도 display 가 한 상태에 영원히 갇히지 않게,
    # 상태마다 수명을 두고 읽는 시점에 만료를 계산한다 (타이머 없음).
    STAGE_TTL = {"listening": 30.0, "thinking": 30.0, "preview": 120.0,
                 "executing": 60.0, "dance": 480.0}

    def _set_stage_locked(self, stage, data=None):
        self.stage = stage
        self.stage_data = dict(data or {})
        self.stage_set_at = time.time()
        self.stage_rev += 1
        self.rev += 1

    def set_stage(self, stage, data=None):
        with self.lock:
            self._set_stage_locked(stage, data)

    def _effective_stage_locked(self):
        ttl = self.STAGE_TTL.get(self.stage)
        if ttl and time.time() - self.stage_set_at > ttl:
            self._set_stage_locked("idle")
        return self.stage

    def conversation_view(self):
        with self.lock:
            stage = self._effective_stage_locked()
            return {"current_motion": self.current_motion,
                    "current_motion_state": self.current_motion_state,
                    "motion_rev": self.motion_rev, "rev": self.rev,
                    "stage": stage, "stage_data": dict(self.stage_data),
                    "stage_rev": self.stage_rev,
                    # dance 싱크의 시계 기준. display 가 자기 시계와의 차이를 재서
                    # media_at(절대 시각)에 맞춰 재생을 예약한다.
                    "server_now": time.time()}

    def record(self, **kw):
        kw["t"] = time.strftime("%H:%M:%S")
        with self.lock:
            self.log.appendleft(kw)
        return kw

    def play(self, motion, reason="", source="llm", turn_id=None):
        out = self._play(motion, reason, source)
        # persona 튜닝의 근거: 어떤 발화(turn_id)에서 어떤 동작이 나갔나/거부됐나.
        record = dict(turn_id=turn_id, motion=motion, source=source,
                      reason=self.session_log.text(reason), ok=out["ok"],
                      msg=out["msg"], gateway_status=out.get("gateway_status"))
        if not out["ok"]:
            # 2026-08-13 에 "허용되지 않은 동작" 거부가 났는데 로그만으로 원인을 못 밝혔다.
            # 거부 시점의 판정 근거를 함께 남긴다.
            record.update(allowed_count=len(self.allowed),
                          in_allowed=motion in self.allowed,
                          backend=self.backend.name)
        else:
            with self.lock:
                self.current_motion = out.get("ko") or motion
                self.current_motion_state = motion
                self.motion_rev += 1
                self.rev += 1
                # 동작이 실제로 나갈 때만 executing 이 된다. /stage 로는 못 만든다.
                # dance 중의 동작 실행(서버 스케줄)은 무대 화면을 유지한다.
                if self.stage != "dance":
                    self._set_stage_locked("executing",
                                           {"motion": motion, "ko": self.current_motion})
                    self._arm_exec_idle_locked(motion)
        self.session_log.write("motion_request", **record)
        return out

    # executing 화면을 스스로 내리기까지의 여유. 클립 길이(=동작 길이) + 이만큼.
    EXEC_IDLE_MARGIN_SEC = 3.0
    EXEC_IDLE_DEFAULT_SEC = 12.0

    def _arm_exec_idle_locked(self, motion):
        """동작이 끝날 즈음 무대 화면을 스스로 idle 로 되돌린다.

        idle 복귀를 패드만 책임지고 있어서, 운영자가 수동으로 동작을 실행하면
        아무도 idle 을 보내지 않아 TTL(60초)까지 **관객 패드 전체가 잠기고**
        display 는 "로봇이 동작 중입니다"에 머물렀다 (2026-08-18 리허설에서 재현).
        패드가 보내는 idle 이 먼저 오면 stage_rev 가 달라져 이 타이머는 무시된다.
        """
        if self._exec_idle_timer:
            self._exec_idle_timer.cancel()
        length = clip_len.clip_duration(CLIPS, motion) or self.EXEC_IDLE_DEFAULT_SEC
        rev = self.stage_rev
        self._exec_idle_timer = threading.Timer(
            length + self.EXEC_IDLE_MARGIN_SEC, self._exec_idle, (rev,))
        self._exec_idle_timer.daemon = True
        self._exec_idle_timer.start()

    def _exec_idle(self, rev):
        with self.lock:
            # 그 사이 화면이 바뀌었으면(패드가 idle 을 보냈거나 무대가 시작됐거나)
            # 남의 화면을 내리지 않는다.
            if self.stage_rev != rev or self.stage != "executing":
                return
            self._set_stage_locked("idle")

    def _play(self, motion, reason, source):
        info = self.by_state.get(motion)
        if info is None:
            return self.record(ok=False, motion=motion, ko="?", reason=reason,
                               source=source, msg="카탈로그에 없는 동작")
        # LLM 경로만 화이트리스트를 강제한다. 운영자 버튼은 사람이 누른 것이라 허용.
        if source == "llm" and motion not in self.allowed:
            return self.record(ok=False, motion=motion, ko=info["ko"], reason=reason,
                               source=source, msg="LLM 에게 허용되지 않은 동작")
        # 관객용 아이패드도 사람이 누르는 것이지만 그 사람이 운영자가 아니다.
        if source == "pad" and motion not in self.pad_allowed:
            return self.record(ok=False, motion=motion, ko=info["ko"], reason=reason,
                               source=source, msg="관객 화면에 허용되지 않은 동작")
        # 무대 중에는 관객 명령을 서버가 막는다. 패드도 스스로 잠그지만 그건 1초 폴링
        # 뒤에야 반영돼, 무대 시작 직후 눌린 탭이 그 창으로 새어 들어와 안무 대신
        # 다른 동작이 나갈 수 있다 (2026-08-18 리뷰에서 재현).
        if source == "pad" and self.effective_stage() == "dance":
            return self.record(ok=False, motion=motion, ko=info["ko"], reason=reason,
                               source=source, msg="무대 진행 중입니다")
        out = self.backend.submit(motion, source, reason)
        return self.record(ok=out["ok"], motion=motion, ko=info["ko"], reason=reason,
                           source=source, safety=info.get("safety"),
                           status=info.get("status", "ready"), msg=out["msg"],
                           gateway_status=out.get("status"), request_id=out.get("request_id"))

    def stop_motion(self, reason=""):
        """운영자 정지. allowlist 를 거치지 않고 실행 중이든 아니든 항상 시도한다.

        무대 예약(dance)은 정지 **전에** 무력화한다. 안 그러면 빨간 정지를 누른
        1~3.5초 뒤에 예약돼 있던 안무가 그대로 발사된다 — 운영자는 이미 멈췄다고
        믿고 있다 (2026-08-18 리뷰에서 mock 재현). 무대 화면도 같이 내린다.
        """
        if self.effective_stage() == "dance":
            self.stop_dance("운영자 정지")
        out = self.backend.stop_motion("manual", reason)
        motion = out.get("motion") or ""
        info = self.by_state.get(motion) or {}
        return self.record(ok=out["ok"], motion=motion, ko=info.get("ko", "정지"),
                           reason=reason, source="stop", safety=info.get("safety"),
                           status=info.get("status", "ready"), msg=out["msg"],
                           gateway_status=out.get("status"), request_id=out.get("request_id"))

    def status(self):
        out = self.backend.status()
        out["backend"] = self.backend.name
        return out

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
                rc = RcBackend(HERE / "motions.yaml", HERE / "gateway_config.yaml")
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

    # ── dance: display(TV) 재생 + 서버 스케줄 ──────────────────────
    # 폴링 지연(±300ms)이 매번 달라 "명령 보고 즉시 재생"은 싱크가 안 맞는다.
    # 미래의 절대 시각(base = now + 리드타임)을 정해 두고, 동작은 서버 Timer 가,
    # 음원은 display 가 server_now 와의 시계차로 각자 그 시각에 맞춘다.
    DANCE_LEAD_SEC = 2.0
    # 무대 자동 종료 fallback: display 가 영상 종료를 알려주지 못하는 상황(창을 안
    # 열었거나 죽음)에서 "무대 실행중"이 TTL(8분)까지 걸려 있지 않게, max(영상 실측
    # 길이, 로봇 동작 추정 길이) + 여유가 지나면 서버가 스스로 무대를 내린다.
    # display 의 정상 종료가 먼저 오면 세대 번호 불일치로 이 타이머는 무시된다.
    DANCE_AUTOSTOP_MARGIN_SEC = 5.0
    DANCE_AUTOSTOP_DEFAULT_SEC = 60.0

    def start_dance(self, name=None, preset=None):
        """저장된 프리셋 이름 또는 inline preset(보정 중인 현재 값)으로 무대를 시작한다."""
        if preset is None:
            preset = load_presets().get(name)
            if not preset:
                return {"ok": False, "msg": f"프리셋이 없습니다: {name}"}
        name = name or "(직접 설정)"
        motion = preset.get("motion") or ""
        media = preset.get("media") or ""
        if media and media not in media_files():
            return {"ok": False, "msg": f"음원 파일이 없습니다: {media}"}
        if motion and motion not in self.by_state:
            return {"ok": False, "msg": f"카탈로그에 없는 동작: {motion}"}
        # 숫자 필드는 타이머를 걸기 **전에** 전부 파싱한다. 타이머를 먼저 걸면 파싱
        # 오류 시 "시작 실패"로 보이는데 2초 뒤 로봇만 움직인다 (리뷰 지적).
        try:
            offset = float(preset.get("offset_ms") or 0) / 1000.0
            seek = float(preset.get("seek") or 0)
            volume = float(preset.get("volume", 100))
        except (TypeError, ValueError) as exc:
            return {"ok": False, "msg": f"프리셋 숫자 필드가 잘못됐습니다: {exc}"}
        base = time.time() + self.DANCE_LEAD_SEC
        # 오프셋 부호는 기존 /dance 페이지와 같다: + 면 로봇 먼저, − 면 음원 먼저.
        motion_at = base if offset >= 0 else base - offset
        media_at = base + offset if offset >= 0 else base
        info = self.by_state.get(motion) or {}
        # /dance 보정 화면은 숫자·파일 필드만 담은 inline preset 을 보낸다 — 자막이 없다.
        # 저장된 프리셋에서 같은 이름으로, 없으면 같은 음원 파일로 찾아 채운다. 이걸 안 하면
        # 무대에 동작 약칭("체스트팝 v2")이 떠서 공식 명칭 규칙이 깨진다 (2026-08-18).
        title, credit = preset.get("title"), preset.get("credit")
        media_len_sec = preset.get("media_len_sec")
        if not (title and credit and media_len_sec):
            saved = load_presets()
            src = saved.get(name) or next(
                (p for p in saved.values() if media and p.get("media") == media), {})
            title = title or src.get("title")
            credit = credit or src.get("credit")
            # 길이도 같이 복구한다 — 없으면 자동 종료가 기본 60초로 떨어져 긴 무대가 끊긴다
            media_len_sec = media_len_sec or src.get("media_len_sec")
        with self.lock:
            if self._dance_timer:
                self._dance_timer.cancel()
            if self._dance_prep_timer:
                self._dance_prep_timer.cancel()
                self._dance_prep_timer = None
            if self._dance_autostop_timer:
                self._dance_autostop_timer.cancel()
                self._dance_autostop_timer = None
            self._dance_gen += 1
            self._dance_timer = threading.Timer(
                max(0.0, motion_at - time.time()),
                self._fire_dance_motion, (motion, self._dance_gen))
            self._dance_timer.daemon = True
            self._dance_timer.start()
            # RC 백엔드는 발사 엣지 지터를 줄이려고 1.5s 전에 PREP(code 0, 무해)를 건다.
            # 실패해도 발사는 RUN 으로 폴백되므로 best-effort 다.
            if motion and hasattr(self.backend, "prepare"):
                self._dance_prep_timer = threading.Timer(
                    max(0.0, motion_at - time.time() - 1.5),
                    self._prep_dance_motion, (motion, self._dance_gen))
                self._dance_prep_timer.daemon = True
                self._dance_prep_timer.start()
            motion_dur = None
            if motion and hasattr(self.backend, "motion_duration"):
                motion_dur = self.backend.motion_duration(motion)
            media_len = None
            try:
                media_len = float(media_len_sec or 0) or None
            except (TypeError, ValueError):
                media_len = None
            # 영상·동작 중 긴 쪽 기준 (둘 다 모르면 기본값)
            duration = max(motion_dur or 0.0, media_len or 0.0) \
                or self.DANCE_AUTOSTOP_DEFAULT_SEC
            self._dance_autostop_timer = threading.Timer(
                max(0.0, motion_at - time.time()) + duration + self.DANCE_AUTOSTOP_MARGIN_SEC,
                self._auto_stop_dance, (self._dance_gen,))
            self._dance_autostop_timer.daemon = True
            self._dance_autostop_timer.start()
            self._set_stage_locked("dance", {
                "name": name, "motion": motion, "ko": info.get("ko", motion),
                # 무대 화면 자막: title 은 공식 명칭(중앙 큰 글씨), credit 은 출처(하단 작게).
                # 못 찾으면 **빈 값**이다 — 동작 약칭("체스트팝 v2")을 무대에 띄우지
                # 않는다는 규칙이 폴백보다 우선한다 (2026-08-18 사용자 확정).
                "title": title or "",
                "credit": credit or "",
                "media": media, "media_at": media_at,
                "seek": seek, "volume": volume})
        # 보정값 유실 방지: 무대를 시작할 때마다 오프셋을 세션 로그에 남긴다
        # (2026-08-18 배드 오프셋을 저장 안 해 잃어버린 사건의 재발 방지)
        self.session_log.write("dance_start", name=name, motion=motion, media=media,
                               offset_ms=round(offset * 1000.0), seek=seek, volume=volume)
        return {"ok": True, "motion": motion, "media": media,
                "motion_at": motion_at, "media_at": media_at}

    def _fire_dance_motion(self, motion, gen):
        # Timer.cancel() 은 이미 시작된 콜백을 못 멈춘다. 세대 번호가 다르면 그 사이
        # 새 무대가 시작됐거나 정지된 것이므로 발사하지 않는다 — stage 검사만으로는
        # "B 무대에 A 동작" 을 못 막는다.
        with self.lock:
            if gen != self._dance_gen or self.stage != "dance":
                return
        if motion:
            self.play(motion, reason="dance 무대", source="manual")

    def _prep_dance_motion(self, motion, gen):
        with self.lock:
            if gen != self._dance_gen or self.stage != "dance":
                return
        try:
            self.backend.prepare(motion)
        except Exception as exc:  # PREP 는 best-effort — 발사는 RUN 으로 폴백된다
            print(f"[rc] PREP 실패(무시): {exc}", flush=True)

    def _auto_stop_dance(self, gen):
        with self.lock:
            if gen != self._dance_gen or self.stage != "dance":
                return
        print("  DANCE 자동 종료 (추정 시간 경과 — display 종료 신호 없음)")
        self.stop_dance("무대 자동 종료 (추정 시간 경과)")

    def stop_dance(self, reason="무대 정지"):
        """무대(영상·예약)만 내린다. **로봇은 절대 건드리지 않는다.**

        2026-08-18 사용자 확정: dance 경로에서 ReadyPose 선점 금지 — 진행 중인
        동작은 끝까지 마치고 locomotion 으로 스스로 복귀한다. 영상이 안무보다
        짧아 먼저 끝나도(자동 종료 경로) 로봇이 관객 앞에서 뚝 끊기지 않는다.
        즉시 중단이 필요하면 운영자 빨간 정지 버튼 또는 RC/E-stop 을 쓴다.
        """
        with self.lock:
            if self._dance_timer:
                self._dance_timer.cancel()
                self._dance_timer = None
            if self._dance_prep_timer:
                self._dance_prep_timer.cancel()
                self._dance_prep_timer = None
            if self._dance_autostop_timer:
                self._dance_autostop_timer.cancel()
                self._dance_autostop_timer = None
            # 이미 시작된(cancel 이 못 잡은) 콜백도 세대 불일치로 무력화한다.
            self._dance_gen += 1
            self._set_stage_locked("idle")
        return {"ok": True, "msg": "무대 종료 — 로봇 동작은 그대로 마칩니다"}

    def effective_stage(self):
        with self.lock:
            return self._effective_stage_locked()

    def clip_states(self):
        """클립 mp4 가 실재하는 state 목록.

        모니터가 재생 전에 있는지 알아야 헛되이 404 를 때리지 않는다.
        카탈로그에 있는 이름만 본다 — 파일명을 그대로 믿지 않는다.
        """
        return sorted(s for s in self.by_state if (CLIPS / f"{s}.mp4").is_file())


# ───────────────────────────────────────────────────────────── HTTP

class Handler(BaseHTTPRequestHandler):
    state: State = None  # main 에서 주입
    theme: str = "shape"  # 활성 테마 이름 (main 에서 주입)
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
            # 음성 폰 화면 제거(2026-08-18). 옛 북마크는 관객 화면으로 보낸다.
            # 페이지 원본은 archive/index_voice_20260818.html.
            query = urllib.parse.urlsplit(self.path).query
            self.send_response(302)
            self.send_header("Location", "/pad" + (f"?{query}" if query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in {"/operator", "/display", "/pad", "/dance"}:
            headers = None
            if self.state.access_token:
                supplied = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
                if supplied:
                    if not secrets.compare_digest(supplied, self.state.access_token):
                        return self._send(403, {"error": "invalid gateway token"})
                    headers = {"Set-Cookie": f"k1_gateway={self.state.access_token}; Path=/; Secure; HttpOnly; SameSite=Strict"}
                elif not self._authorized():
                    return self._send(403, {"error": "gateway authorization required"})
            page = {"/operator": "operator.html", "/display": "display.html",
                    "/pad": "pad.html", "/dance": "dance.html"}.get(path, "pad.html")
            return self._send(200, (page_dir(page) / page).read_bytes(),
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
            return self._send(200, self.state.status())
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

        if path == "/rc/mode":
            out = self.state.set_rc_mode(bool(payload.get("on")))
            print(f"  RC모드 {'ON 시도' if payload.get('on') else 'OFF'} → "
                  f"{out['backend']}  {out['msg']}")
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
             "-subj", "/CN=k1-solo-stage"],
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
    ap.add_argument("--port", type=int, default=0, help="기본: http 8000 / https 8443")
    ap.add_argument("--https", action="store_true", help="폰에서 마이크를 쓰려면 필요")
    ap.add_argument("--robot", action="store_true", help="RobotBackend 사용 (2단계)")
    ap.add_argument("--relay", metavar="URL",
                    help="PC relay 모드. 예: https://192.168.60.1:8443")
    ap.add_argument("--relay-token", default=os.environ.get("K1_RELAY_TOKEN", ""),
                    help="로봇 gateway token (기본: K1_RELAY_TOKEN)")
    ap.add_argument("--rc", action="store_true",
                    help="RcBackend 사용 — 유선 RC(ELRS) 경로로 명령 전송")
    ap.add_argument("--gateway-token", default=os.environ.get("K1_GATEWAY_TOKEN", ""),
                    help="이 gateway의 고정 token (기본: K1_GATEWAY_TOKEN 또는 랜덤)")
    ap.add_argument("--ready-only", action="store_true",
                    help="학습 끝난 동작만 LLM 에 노출 (로봇 연결 시)")
    ap.add_argument("--log-dir", default=str(HERE / "logs"),
                    help="turn 단위 JSONL 세션 로그 위치 (기본: logs/)")
    ap.add_argument("--no-log", action="store_true", help="세션 로그를 끈다")
    ap.add_argument("--theme", default="shape",
                    help="관객 화면 디자인 테마 (web/themes/ 의 폴더명)")
    ap.add_argument("--no-transcripts", action="store_true",
                    help="발화 원문 대신 길이만 기록 (행사장 프라이버시 모드)")
    args = ap.parse_args()
    if sum(map(bool, (args.robot, args.relay, args.rc))) > 1:
        ap.error("--robot / --relay / --rc 는 동시에 사용할 수 없습니다")
    if (args.robot or args.relay or args.rc) and not args.https:
        ap.error("--robot/--relay/--rc 는 토큰 cookie 보호를 위해 --https 와 함께 실행해야 합니다")
    if args.relay and not args.relay_token:
        ap.error("--relay 는 --relay-token 또는 K1_RELAY_TOKEN 이 필요합니다")

    port = args.port or (8443 if args.https else 8000)
    gateway_config = yaml.safe_load((HERE / "gateway_config.yaml").read_text())
    if args.robot:
        backend = RobotBackend(HERE / "gateway_config.yaml")
    elif args.relay:
        policy = gateway_config["policy"]
        backend = RelayBackend(args.relay, args.relay_token, policy["api_allowlist"],
                               policy.get("relay_timeout_sec", 2.0))
    elif args.rc:
        backend = RcBackend(HERE / "motions.yaml", HERE / "gateway_config.yaml")
    else:
        backend = MockBackend()
    if args.robot:
        backend.start()
    session_log = SessionLog(args.log_dir, transcripts=not args.no_transcripts,
                             enabled=not args.no_log)
    Handler.state = State(
        backend,
        ready_only=args.ready_only or args.robot or bool(args.relay) or args.rc,
        access_token=args.gateway_token or None,
        llm_allowlist=gateway_config["policy"].get("llm_allowlist"),
        pad_allowlist=gateway_config["policy"].get("pad_allowlist"),
        pad_llm_exclude=gateway_config["policy"].get("pad_llm_exclude"),
        session_log=session_log,
    )
    Handler.theme = args.theme
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
