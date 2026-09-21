"""무대 상태기계 — 도메인. 파일도 어댑터도 모른다.

관객 패드·운영자·TV(display)가 서로 다른 시각에 같은 무대를 본다. 이 클래스가 그 무대의 유일한 주인이다.

- 화면 상태(idle · preview · executing · dance)와 그 수명(TTL) — 어느 기기가 조작하든 display 는 서버만 본다
- 동작 실행: 카탈로그·허용목록(패드) 검사, 무대 중 관객 명령 차단, 백엔드 호출. LLM 경로는 제거됐고
  source="llm" 은 항상 거부한다
- dance 스케줄: 미래의 절대 시각을 정해 두고 동작은 서버 Timer 가, 음원은 display 가 각자 맞춘다.
  세대 번호(_dance_gen)로 옛 무대의 늦은 콜백을 무력화한다
- 백엔드 능력(prepare · motion_duration)은 core.ports 의 Protocol 로 묻는다

**의존은 안쪽으로만 흐른다.** core/ 는 adapters 를 import 하지 않는다 — 하드웨어 없이 테스트가 돌아야 한다.
표준 라이브러리와 core.ports 밖의 것은 전부 생성자 인자다(Stage.__init__ 참고).

server.py 의 State(Stage) 가 이 앱의 파일·어댑터를 꽂고, 앱마다 다른 메서드 하나씩(solo 의 set_rc_mode,
group 의 rescan_rc)만 갖는다. 나머지 20개 메서드는 두 앱에서 글자 하나까지 같았다 — 그게 계획서가 말한
"차이는 배선뿐"이다.

이 파일은 로봇 컨테이너에도 배포된다(server.py 가 최상단에서 import 한다). run.sh 의 DEPLOY_FILES 에
core/__init__.py · core/stage.py · core/ports.py 가 있어야 한다.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import deque

from core.ports import SupportsDuration, SupportsPrepare, Transport


class Stage:
    def __init__(self, backend: Transport, *, catalog, load_presets, media_files, clip_seconds,
                 clip_exists, session_log, ready_only=False, access_token=None,
                 pad_allowlist=None, api_allowlist=None):
        """이 클래스는 파일도 어댑터도 모른다 — 필요한 것을 인자로 받는다.

        catalog        (items, by_state) — 동작 카탈로그
        load_presets   () -> {이름: 프리셋}         무대 프리셋. 호출할 때마다 읽는다(/dance 가 저장하면 바뀐다)
        media_files    () -> [파일명]               무대 음원·영상이 실제로 있는 것
        clip_seconds   (state) -> 초 | None         sim 클립 길이. 모르면 None (호출부가 기본값으로 떨어진다)
        clip_exists    (state) -> bool              sim 클립 파일이 있나
        session_log    write(kind, **kw) · text(s)

        값이 아니라 **함수**를 받는 이유: 음원·프리셋·클립은 실행 중에 바뀐다(/dance 저장, 클립 다시
        굽기). 시작할 때 한 번 읽은 값을 들고 있으면 안 된다.
        """
        self.backend = backend
        self._load_presets = load_presets
        self._media_files = media_files
        self._clip_seconds = clip_seconds
        self._clip_exists = clip_exists
        # RC 모드 토글의 복귀 지점. 토글은 self.backend 만 바꾼다.
        self._primary_backend = backend
        self.ready_only = ready_only
        self.items, self.by_state = catalog
        # 음성/LLM 요청 경로는 제거됐다. source="llm" 은 아래 _play() 에서 항상 거부한다.
        self.allowed = set()
        # 관객에게 여는 목록은 api_allowlist 를 넘을 수 없다. **정책에서 온 값**으로 자른다.
        # 예전에는 backend.api_allowlist 속성이 있을 때만 잘랐다. 그래서 RcBackend 는 그 속성을 일부러
        # 갖지 않아야만 올바르게 동작했고(있으면 패드가 조용히 줄어든다), 누가 일관성을 위해 추가하면
        # 사고가 났다. 이제 UI 목록은 백엔드가 무엇을 갖고 있는지와 무관하다 — RC 로 토글해도 목록이
        # 그대로인 것(2026-08-18 사용자 확정)이 구조로 보장된다.
        # None 이면 안 자른다: 정책을 모르는 호출(테스트의 State(MockBackend()) 등)은 옛 동작 그대로다.
        api = set(api_allowlist) if api_allowlist is not None else None
        # 관객용(/pad) 버튼 목록. 카탈로그·api 밖 항목이 오타 하나로 조용히 통과하는 일이 없게
        # 교집합을 취한다.
        self.pad_allowed = set(pad_allowlist or ())
        self.pad_allowed &= set(self.by_state)
        if api is not None:
            self.pad_allowed &= api
        # 패드 그리드 번호 = 목록 순서 (2026-08-18 사용자 확정 스펙).
        # set 은 순서를 잃으므로 원본 순서를 따로 보존해 API 로 내보낸다.
        self.pad_order = [s for s in (pad_allowlist or ()) if s in self.pad_allowed]
        self.session_log = session_log
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
        length = self._clip_seconds(motion) or self.EXEC_IDLE_DEFAULT_SEC
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
        # LLM 경로는 제거됐다. 운영자 버튼은 사람이 누른 것이라 허용한다.
        if source == "llm":
            return self.record(ok=False, motion=motion, ko=info["ko"], reason=reason,
                               source=source, msg="LLM 경로는 현재 운영하지 않습니다")
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
            preset = self._load_presets().get(name)
            if not preset:
                return {"ok": False, "msg": f"프리셋이 없습니다: {name}"}
        name = name or "(직접 설정)"
        motion = preset.get("motion") or ""
        media = preset.get("media") or ""
        if media and media not in self._media_files():
            return {"ok": False, "msg": f"음원 파일이 없습니다: {media}"}
        if motion and motion not in self.by_state:
            return {"ok": False, "msg": f"카탈로그에 없는 동작: {motion}"}
        # 게이트웨이가 준비 안 된 채로 무대를 시작하면 영상만 돌고 로봇은 안 움직인다
        # (SD API Arm 안 올림 등). stop_dance 는 로봇을 안 건드리는 설계라 한 번 시작되면
        # 되돌릴 수 없으므로, 시작 시점에 막는다. mock 은 로봇 미연결 개발용이라 통과.
        if motion:
            gw = self.backend.status().get("gateway")
            if gw not in ("ready", "mock"):
                return {"ok": False, "msg": f"로봇이 명령을 받을 준비가 안 됐습니다 (gateway: {gw})"}
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
            saved = self._load_presets()
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
            if motion and isinstance(self.backend, SupportsPrepare):
                self._dance_prep_timer = threading.Timer(
                    max(0.0, motion_at - time.time() - 1.5),
                    self._prep_dance_motion, (motion, self._dance_gen))
                self._dance_prep_timer.daemon = True
                self._dance_prep_timer.start()
            motion_dur = None
            if motion and isinstance(self.backend, SupportsDuration):
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
        return sorted(s for s in self.by_state if self._clip_exists(s))
