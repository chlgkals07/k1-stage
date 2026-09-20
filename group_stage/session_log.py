"""Turn-level JSONL session log for persona tuning.

목적: "어떤 발화에서 어떤 동작이 나갔나/거부됐나"를 turn_id 로 묶어 남긴다.
세션이 끝난 뒤 이 파일을 보고 PERSONA 와 카탈로그 desc 를 고친다.

- 쓰기는 queue + 데몬 스레드로 분리한다. 호출자(HTTP 핸들러)가 디스크를 기다리지 않는다.
- transcripts=False 면 발화 원문 대신 길이만 남긴다 (행사장 방문객 프라이버시 모드).
- 토큰·API key 는 어떤 경로로도 기록하지 않는다.
"""

from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from pathlib import Path

# 클라이언트(/event)가 보낼 수 있는 kind. 이 밖은 서버가 거부한다.
CLIENT_KINDS = {"user_transcript", "assistant_transcript"}


class SessionLog:
    def __init__(self, log_dir, transcripts=True, enabled=True):
        self.enabled = enabled
        self.transcripts = transcripts
        self.path = None
        self._queue: queue.Queue | None = None
        self._seq = 0
        self._lock = threading.Lock()
        if not enabled:
            return
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = log_dir / f"{stamp}-{secrets.token_hex(3)}.jsonl"
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._writer, daemon=True,
                                        name="k1-session-log")
        self._thread.start()

    def text(self, s):
        """전사 원문 또는 (프라이버시 모드에서) 길이 표시만."""
        s = "" if s is None else str(s)
        return s if self.transcripts else f"<{len(s)}자>"

    def write(self, kind, **fields):
        if not self.enabled:
            return
        with self._lock:
            self._seq += 1
            seq = self._seq
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "seq": seq, "kind": kind}
        record.update(fields)
        self._queue.put(record)

    def close(self):
        if not self.enabled:
            return
        self._queue.put(None)
        self._thread.join(timeout=3)

    def _writer(self):
        # 한 스레드만 파일을 만진다. 열어둔 채 flush 로 이어 쓴다.
        with open(self.path, "a", encoding="utf-8") as f:
            while True:
                record = self._queue.get()
                if record is None:
                    return
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
