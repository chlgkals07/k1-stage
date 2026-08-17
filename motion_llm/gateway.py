"""Robot-independent policy and lifecycle core for K1 motion requests."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, replace


COMPLETION_MODES = {"Damping", "ReadyPose", "Velocity"}


@dataclass(frozen=True)
class RobotSnapshot:
    active_mode: str = ""
    authority: str = ""
    heartbeat_valid: bool = False
    request_available: bool = False
    last_transition_reason: str = ""
    received_at: float = 0.0


@dataclass
class MotionRequest:
    request_id: str
    motion: str
    source: str
    reason: str
    submitted_at: float
    phase: str = "queued"
    dispatched_at: float | None = None
    accepted_at: float | None = None
    executing_at: float | None = None
    is_stop: bool = False


class Gateway:
    """Thread-safe execution policy. ROS transport is supplied by RobotBackend."""

    def __init__(self, api_allowlist, entry_timeout_sec=5.0, status_timeout_sec=1.0,
                 stop_state="ReadyPose", cooldowns=None):
        self.api_allowlist = set(api_allowlist)
        self.entry_timeout_sec = entry_timeout_sec
        self.status_timeout_sec = status_timeout_sec
        self.stop_state = stop_state
        # motion -> seconds. 값이 없으면 0 이라 기존 동작과 같다.
        self.cooldowns = dict(cooldowns or {})
        self._lock = threading.RLock()
        self._snapshot: RobotSnapshot | None = None
        self._robot_modes: set[str] = set()
        self._current: MotionRequest | None = None
        self._finished_at: dict[str, float] = {}
        self._last_event = {"status": "offline", "msg": "로봇 상태를 기다리는 중"}

    def set_robot_modes(self, modes):
        with self._lock:
            self._robot_modes = set(modes)

    def update_status(self, snapshot: RobotSnapshot):
        now = time.monotonic()
        snapshot = replace(snapshot, received_at=now)
        with self._lock:
            self._snapshot = snapshot
            current = self._current
            if not current:
                return
            if snapshot.authority != "API" or not snapshot.heartbeat_valid:
                self._finish_locked("rejected", "API Arm 또는 heartbeat가 해제되었습니다")
                return
            if current.phase == "accepted" and snapshot.active_mode == current.motion:
                current.phase = "executing"
                current.executing_at = now
                self._last_event = self._event_locked(current, "실행 중")
            elif current.phase == "executing" and snapshot.active_mode in COMPLETION_MODES:
                self._finish_locked("completed", f"{snapshot.active_mode} 상태로 복귀")

    def submit(self, motion, source, reason=""):
        now = time.monotonic()
        with self._lock:
            ready, message = self._ready_locked()
            if not ready:
                return self._result_locked(False, "rejected", message, motion)
            if motion not in self.api_allowlist:
                return self._result_locked(False, "rejected", "이 동작은 API 허용 목록에 없습니다", motion)
            if motion not in self._robot_modes:
                return self._result_locked(False, "rejected", "현재 로봇에 배포되지 않은 동작입니다", motion)
            if self._current:
                return self._result_locked(False, "rejected", "로봇이 이미 동작을 실행 중입니다", motion)
            remaining = self._cooldown_remaining_locked(motion, now)
            if remaining > 0:
                return self._result_locked(
                    False, "rejected", f"이 동작은 {remaining:.0f}초 뒤에 다시 쓸 수 있습니다", motion)
            self._current = MotionRequest(uuid.uuid4().hex, motion, source, reason, now)
            self._last_event = self._event_locked(self._current, "API 실행 대기")
            return self._result_locked(True, "queued", "API 실행 대기", motion, self._current.request_id)

    def stop_motion(self, source, reason=""):
        """Preempt whatever is running and command the robot back to ``stop_state``.

        정지는 안전 기능이라 allowlist, busy, cooldown 검사를 모두 우회한다.
        ``_ready_locked`` 과 달리 ``request_available`` 도 요구하지 않는다 — Mimic 실행 중
        이 플래그가 내려가는지 아직 실물로 확인되지 않았고, 내려간다면 정지가 거부되어
        기능 자체가 무의미해지기 때문이다.
        """
        now = time.monotonic()
        with self._lock:
            ready, message = self._stop_ready_locked()
            if not ready:
                return self._result_locked(False, "rejected", message, self.stop_state)
            if self._current:
                self._finish_locked("interrupted", "운영자가 동작을 중단했습니다")
            self._current = MotionRequest(uuid.uuid4().hex, self.stop_state, source, reason,
                                          now, is_stop=True)
            self._last_event = self._event_locked(self._current, "정지 요청 대기")
            return self._result_locked(True, "queued", "정지 요청 대기", self.stop_state,
                                       self._current.request_id)

    def next_dispatch(self):
        """Return one queued request exactly once; called by the ROS timer."""
        with self._lock:
            if not self._current or self._current.phase != "queued":
                return None
            ready, message = self._ready_locked()
            if not ready:
                self._finish_locked("rejected", message)
                return None
            self._current.phase = "dispatching"
            self._current.dispatched_at = time.monotonic()
            return MotionRequest(**asdict(self._current))

    def service_result(self, request_id, success, message):
        with self._lock:
            if not self._current or self._current.request_id != request_id:
                return
            if success:
                self._current.phase = "accepted"
                self._current.accepted_at = time.monotonic()
                self._last_event = self._event_locked(self._current, message or "로봇이 요청을 수락했습니다")
            else:
                self._finish_locked("rejected", message or "로봇이 요청을 거부했습니다")

    def tick(self):
        with self._lock:
            current = self._current
            if current and current.phase in {"dispatching", "accepted"}:
                # accepted_at 을 먼저 본다. dispatched_at 우선이면 ROS 수락이 느릴 때
                # 수락된 요청까지 오거부하고 단일 요청 불변식이 깨진다 (리뷰 지적).
                started = current.accepted_at or current.dispatched_at or current.submitted_at
                if time.monotonic() - started > self.entry_timeout_sec:
                    self._finish_locked("rejected", "동작 상태 진입 시간이 초과되었습니다")

    def status(self):
        with self._lock:
            snapshot = asdict(self._snapshot) if self._snapshot else None
            return {
                "gateway": self._gateway_state_locked(),
                "robot": snapshot,
                "robot_modes_loaded": bool(self._robot_modes),
                "api_allowlist": sorted(self.api_allowlist),
                "stop_state": self.stop_state,
                "stop_available": self._stop_ready_locked()[0],
                "current_request": asdict(self._current) if self._current else None,
                "last_event": dict(self._last_event),
            }

    def _api_live_locked(self):
        """정지와 일반 요청이 공통으로 요구하는 최소 조건."""
        if not self._snapshot:
            return False, "로봇 상태를 아직 받지 못했습니다"
        if time.monotonic() - self._snapshot.received_at > self.status_timeout_sec:
            return False, "로봇 상태 연결이 끊겼습니다"
        if self._snapshot.authority != "API":
            return False, "SD API Arm이 켜져 있지 않습니다"
        if not self._snapshot.heartbeat_valid:
            return False, "API heartbeat 준비 중입니다"
        return True, "ready"

    def _ready_locked(self):
        ok, message = self._api_live_locked()
        if not ok:
            return ok, message
        if not self._snapshot.request_available:
            return False, "현재 로봇 상태에서는 요청을 받을 수 없습니다"
        if not self._robot_modes:
            return False, "로봇 동작 목록을 불러오는 중입니다"
        return True, "ready"

    def _stop_ready_locked(self):
        ok, message = self._api_live_locked()
        if not ok:
            return ok, message
        # 목록을 아직 못 받았으면 막지 않는다. 정지는 시도할 수 있어야 하고,
        # 이름이 틀렸다면 ROS service 가 거부한다.
        if self._robot_modes and self.stop_state not in self._robot_modes:
            return False, f"로봇에 {self.stop_state} 상태가 없습니다"
        return True, "ready"

    def _cooldown_remaining_locked(self, motion, now):
        window = self.cooldowns.get(motion, 0)
        if not window:
            return 0.0
        finished = self._finished_at.get(motion)
        if finished is None:
            return 0.0
        return max(0.0, window - (now - finished))

    def _gateway_state_locked(self):
        if self._current:
            return "stopping" if self._current.is_stop else self._current.phase
        ready, _ = self._ready_locked()
        if ready:
            return "ready"
        if not self._snapshot or time.monotonic() - self._snapshot.received_at > self.status_timeout_sec:
            return "offline"
        if self._snapshot.heartbeat_valid:
            return "api_warming"
        return "manual"

    def _finish_locked(self, status, message):
        if self._current:
            # 실제로 로봇에서 돈 동작만 cooldown 을 시작한다. 거부된 요청은 대상이 아니고,
            # 정지 요청(ReadyPose) 자체에도 대기시간을 두지 않는다.
            # "실제로 돈" 판정에 phase 도 본다: 큐에서 정지로 끊긴(발사 전) 요청은
            # 로봇이 움직인 적이 없으므로 cooldown 대상이 아니다 (리뷰 지적).
            if (status in {"completed", "interrupted"} and not self._current.is_stop
                    and (self._current.dispatched_at or self._current.accepted_at
                         or self._current.executing_at)):
                self._finished_at[self._current.motion] = time.monotonic()
            self._last_event = self._event_locked(self._current, message, status)
        else:
            self._last_event = {"status": status, "msg": message}
        self._current = None

    def _event_locked(self, request, message, status=None):
        return {
            "request_id": request.request_id,
            "motion": request.motion,
            "status": status or request.phase,
            "msg": message,
        }

    def _result_locked(self, ok, status, msg, motion, request_id=None):
        return {"ok": ok, "status": status, "msg": msg, "motion": motion,
                "request_id": request_id}
