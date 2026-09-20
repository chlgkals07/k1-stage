"""HTTPS relay transport from the PC gateway to the robot gateway.

무선 링크 전용이라(유선 폴백 없음) 연결을 재사용한다. urllib 은 요청마다 TCP+TLS
핸드셰이크를 새로 하는데, /status 가 1초마다 폴링되므로 불안정한 Wi-Fi 에서
실패 확률이 누적된다. 2026-08-13 실기에서 실제로 `No route to host` 가 나왔다.

재시도는 **연결 계열 실패에만** 적용한다. 로봇이 내린 거부는 재시도하지 않는다 —
같은 동작이 두 번 실행될 수 있다.
"""

from __future__ import annotations

import http.client
import json
import ssl
import threading
from urllib.parse import urlsplit


class RelayError(RuntimeError):
    """로봇이 응답은 했지만 오류를 돌려준 경우 (재시도 대상 아님)."""


class RelayBackend:
    """Forward status and motion requests to the robot-local gateway."""

    name = "relay"

    def __init__(self, base_url, access_token, api_allowlist, timeout_sec=2.0):
        parts = urlsplit(base_url)
        self.host = parts.hostname
        self.port = parts.port or 443
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.api_allowlist = set(api_allowlist)
        self.timeout_sec = timeout_sec
        self._ssl_context = ssl._create_unverified_context()
        self._lock = threading.Lock()
        self._conn = None

    def submit(self, motion, source, reason):
        if motion not in self.api_allowlist:
            return self._rejected(motion, "PC relay 허용 목록에 없는 동작입니다")
        try:
            out = self._request("POST", "/motion", {
                "motion": motion, "source": source, "reason": reason,
            }, retries=1)
            # 로봇 쪽 server.py 응답은 status=카탈로그 학습상태, gateway_status=실제
            # 게이트웨이 단계다. PC 쪽 State 는 status 를 단계로 기록하므로 여기서
            # 매핑해 주지 않으면 로그·UI 에 'ready/planned' 가 단계로 찍힌다 (리뷰).
            if isinstance(out, dict) and "gateway_status" in out:
                out = {**out, "status": out["gateway_status"]}
            return out
        except ConnectionError as exc:
            return self._rejected(motion, f"로봇 연결 끊김: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._rejected(motion, f"로봇 gateway 오류: {exc}")

    def stop_motion(self, source, reason=""):
        """정지는 allowlist 를 거치지 않고 그대로 로봇 gateway 로 넘긴다."""
        try:
            return self._request("POST", "/stop", {"source": source, "reason": reason},
                                 retries=1)
        except ConnectionError as exc:
            return self._rejected("", f"로봇 연결 끊김: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._rejected("", f"로봇 gateway 오류: {exc}")

    def status(self):
        # 1초마다 폴링되므로 재시도하지 않는다. 실패하면 다음 폴링이 곧 온다.
        try:
            return self._request("GET", "/status", retries=0)
        except Exception as exc:  # noqa: BLE001
            return {
                "gateway": "offline", "robot": None, "current_request": None,
                "last_event": {"status": "offline", "msg": f"로봇 gateway 연결 실패: {exc}"},
            }

    def stop(self):
        with self._lock:
            self._close_locked()

    # ── 내부 ────────────────────────────────────────────────────────
    def _request(self, method, path, payload=None, retries=1):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json",
                   "Cookie": f"k1_gateway={self.access_token}"}
        with self._lock:
            last = None
            for attempt in range(retries + 1):
                sent = False
                try:
                    if self._conn is None:
                        self._conn = http.client.HTTPSConnection(
                            self.host, self.port, timeout=self.timeout_sec,
                            context=self._ssl_context)
                    self._conn.request(method, path, body=data, headers=headers)
                    # 요청 본문이 나간 뒤부터는 재전송하면 안 된다. 응답만 못 받은
                    # 것일 수 있고, /motion 을 다시 보내면 같은 동작이 두 번 실행된다
                    # (리뷰 지적 — timeout 도 OSError 라 기존 코드는 재시도했다).
                    sent = True
                    response = self._conn.getresponse()
                    body = response.read()
                    if response.status >= 400:
                        # 로봇이 응답은 했다. 연결은 살려두고 재시도하지 않는다.
                        raise RelayError(
                            f"HTTP {response.status}: {body[:200].decode(errors='replace')}")
                    return json.loads(body)
                except (OSError, http.client.HTTPException) as exc:
                    # 끊긴 연결일 수 있다. 버리고 다음 시도에서 새로 만든다.
                    self._close_locked()
                    last = exc
                    if sent:
                        # 본문 전달 후의 실패: 로봇이 이미 받았을 수 있다 → 재시도 금지.
                        raise ConnectionError(f"응답 미수신 (재시도 안 함): {exc}") from exc
            raise ConnectionError(str(last))

    def _close_locked(self):
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._conn = None

    @staticmethod
    def _rejected(motion, message):
        return {"ok": False, "status": "rejected", "motion": motion,
                "request_id": None, "msg": message}
