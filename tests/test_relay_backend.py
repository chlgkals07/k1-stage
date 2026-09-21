import json
import unittest
from unittest.mock import MagicMock, patch

from runtime.relay_backend import RelayBackend


def fake_response(body, status=200):
    r = MagicMock()
    r.status = status
    r.read.return_value = json.dumps(body).encode() if isinstance(body, dict) else body
    return r


class RelayBackendTest(unittest.TestCase):
    def setUp(self):
        self.backend = RelayBackend(
            "https://192.168.50.1:8443", "secret", {"MimicWaveHand"}
        )

    def make_conn(self, *responses):
        """getresponse 가 순서대로 반환/예외를 내는 가짜 연결."""
        conn = MagicMock()
        conn.getresponse.side_effect = responses
        return conn

    @patch("http.client.HTTPSConnection")
    def test_status_forwards_gateway_cookie(self, ctor):
        ctor.return_value = self.make_conn(fake_response({"gateway": "ready"}))
        out = self.backend.status()
        self.assertEqual(out["gateway"], "ready")
        _, kwargs = ctor.return_value.request.call_args
        self.assertEqual(kwargs["headers"]["Cookie"], "k1_gateway=secret")

    @patch("http.client.HTTPSConnection")
    def test_motion_is_forwarded(self, ctor):
        ctor.return_value = self.make_conn(fake_response({
            "ok": True, "status": "queued", "motion": "MimicWaveHand",
            "request_id": "abc", "msg": "API 실행 대기",
        }))
        out = self.backend.submit("MimicWaveHand", "manual", "hello")
        self.assertTrue(out["ok"])
        args, kwargs = ctor.return_value.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/motion")
        self.assertEqual(json.loads(kwargs["body"])["motion"], "MimicWaveHand")

    @patch("http.client.HTTPSConnection")
    def test_connection_reused_across_requests(self, ctor):
        """무선 링크에서 핸드셰이크 반복을 줄이는 것이 목적이다."""
        ctor.return_value = self.make_conn(
            fake_response({"gateway": "ready"}), fake_response({"gateway": "ready"}))
        self.backend.status()
        self.backend.status()
        self.assertEqual(ctor.call_count, 1, "연결이 재생성되면 안 된다")

    @patch("http.client.HTTPSConnection")
    def test_connect_failure_is_retried_once(self, ctor):
        """전송 전(연결) 실패는 안전하다 — 새로 맺어 한 번 재시도한다.

        연결 실패(No route to host)는 request() 즉 전송 단계에서 난다.
        """
        conn = self.make_conn(
            fake_response({"ok": True, "status": "queued", "motion": "MimicWaveHand",
                           "request_id": "x", "msg": "queued"}))
        conn.request.side_effect = [OSError("No route to host"), None]
        ctor.return_value = conn
        out = self.backend.submit("MimicWaveHand", "manual", "")
        self.assertTrue(out["ok"], out)
        self.assertEqual(ctor.call_count, 2, "재연결이 있어야 한다")

    @patch("http.client.HTTPSConnection")
    def test_timeout_after_send_is_not_retried(self, ctor):
        """본문이 나간 뒤의 실패는 재시도하면 안 된다 — 로봇이 이미 받았을 수 있고,
        재전송하면 같은 동작이 두 번 실행된다 (무선 순단의 실제 위험)."""
        ctor.return_value = self.make_conn(TimeoutError("timed out"))
        out = self.backend.submit("MimicWaveHand", "manual", "")
        self.assertFalse(out["ok"])
        self.assertIn("재시도 안 함", out["msg"])
        self.assertEqual(ctor.return_value.request.call_count, 1,
                         "본문 전달 후에는 재전송이 없어야 한다")

    @patch("http.client.HTTPSConnection")
    def test_robot_rejection_is_not_retried(self, ctor):
        """로봇이 응답한 오류는 재시도하지 않는다 — 같은 동작이 두 번 실행될 수 있다."""
        ctor.return_value = self.make_conn(fake_response(b"nope", status=403))
        out = self.backend.submit("MimicWaveHand", "manual", "")
        self.assertFalse(out["ok"])
        self.assertEqual(ctor.return_value.request.call_count, 1, "재시도하면 안 된다")
        self.assertIn("오류", out["msg"])

    @patch("http.client.HTTPSConnection")
    def test_persistent_failure_reports_disconnect(self, ctor):
        ctor.return_value = self.make_conn(
            OSError("No route to host"), OSError("No route to host"))
        out = self.backend.submit("MimicWaveHand", "manual", "")
        self.assertFalse(out["ok"])
        self.assertIn("연결 끊김", out["msg"])

    @patch("http.client.HTTPSConnection")
    def test_status_does_not_retry(self, ctor):
        """1초마다 폴링되므로 실패는 다음 폴링에 맡긴다."""
        ctor.return_value = self.make_conn(OSError("down"))
        out = self.backend.status()
        self.assertEqual(out["gateway"], "offline")
        self.assertEqual(ctor.return_value.request.call_count, 1)

    @patch("http.client.HTTPSConnection")
    def test_stop_is_forwarded_and_bypasses_local_allowlist(self, ctor):
        ctor.return_value = self.make_conn(fake_response({
            "ok": True, "status": "queued", "motion": "ReadyPose",
            "request_id": "s1", "msg": "정지 요청 대기",
        }))
        out = self.backend.stop_motion("manual", "운영자 정지")
        self.assertTrue(out["ok"])
        args, _ = ctor.return_value.request.call_args
        self.assertEqual(args[1], "/stop")

    @patch("http.client.HTTPSConnection")
    def test_local_allowlist_rejects_without_network(self, ctor):
        out = self.backend.submit("MimicWalk", "manual", "")
        self.assertFalse(out["ok"])
        ctor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
