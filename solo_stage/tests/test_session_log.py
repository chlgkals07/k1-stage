import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import Handler, MockBackend, State
from runtime.session_log import SessionLog

TOKEN = "log-test-token"


def read_records(log):
    log.close()
    return [json.loads(line) for line in Path(log.path).read_text().splitlines()]


class SessionLogTest(unittest.TestCase):
    def test_roundtrip_and_sequence(self):
        with tempfile.TemporaryDirectory() as d:
            log = SessionLog(d)
            log.write("session_start", backend="mock")
            log.write("user_transcript", turn_id=1, text=log.text("안녕"))
            records = read_records(log)
        self.assertEqual([r["kind"] for r in records], ["session_start", "user_transcript"])
        self.assertEqual([r["seq"] for r in records], [1, 2])
        self.assertEqual(records[1]["text"], "안녕")

    def test_no_transcripts_hides_utterance_text(self):
        """행사장 프라이버시 모드: 원문 대신 길이만 남아야 한다."""
        with tempfile.TemporaryDirectory() as d:
            log = SessionLog(d, transcripts=False)
            log.write("user_transcript", turn_id=1, text=log.text("안녕하세요"))
            records = read_records(log)
        self.assertNotIn("안녕하세요", json.dumps(records, ensure_ascii=False))
        self.assertEqual(records[0]["text"], "<5자>")

    def test_disabled_log_writes_nothing(self):
        log = SessionLog(None, enabled=False)
        log.write("session_start")  # 예외 없이 무시돼야 한다
        log.close()
        self.assertIsNone(log.path)


# EventEndpointTest 는 /event 라우트와 함께 제거됨 (음성 전면 삭제 2026-08-18)


if __name__ == "__main__":
    unittest.main()
