"""동작 sim 렌더 클립(clips/<state>.mp4)의 길이 = 그 동작이 도는 시간.

로봇은 "동작이 끝났다"를 알려주지 않는다 (RC 경로엔 완료 신호가 아예 없고, Wi-Fi
경로도 무대 화면까지는 안 온다). 그래서 서버가 시간을 추정해야 하는 곳이 두 군데다:

  1. 무대 화면(executing)을 언제 내릴까 — 안 내리면 관객 패드가 TTL(60초)까지 잠긴다
  2. RC 경로에서 다음 명령을 언제 받을까 — rc_list 의 note 에는 길이가 거의 없다

클립은 같은 모션 데이터에서 구운 것이라 길이가 곧 동작 길이다. 카탈로그에 숫자를
베껴 두면 클립을 다시 구울 때마다 어긋나므로(2026-08-18 에 실제로 다시 구웠다),
**파일 자체를 출처로 삼고** 여기서 한 번만 읽어 캐시한다.

표준 라이브러리만 쓴다 — mp4 의 moov/mvhd 박스에서 timescale·duration 을 읽는다.
어떤 이유로든 못 읽으면 None 을 돌려주고, 호출부는 기존 기본값으로 떨어진다.
"""

from __future__ import annotations

import struct
import threading

_CACHE: dict[str, float | None] = {}
_LOCK = threading.Lock()


def _find_box(f, want, end):
    """현재 위치부터 end 까지에서 want 박스를 찾아 (내용 시작, 내용 끝) 을 돌려준다."""
    while f.tell() + 8 <= end:
        head = f.read(8)
        if len(head) < 8:
            return None
        size, kind = struct.unpack(">I4s", head)
        body = f.tell()
        if size == 1:                      # 64비트 확장 크기
            size = struct.unpack(">Q", f.read(8))[0]
            body = f.tell()
            stop = body + size - 16
        elif size == 0:                    # 파일 끝까지
            stop = end
        else:
            stop = body + size - 8
        if stop <= body or stop > end:
            return None
        if kind == want:
            return body, stop
        f.seek(stop)
    return None


def _mp4_duration(path):
    with path.open("rb") as f:
        f.seek(0, 2)
        end = f.tell()
        f.seek(0)
        moov = _find_box(f, b"moov", end)
        if not moov:
            return None
        f.seek(moov[0])
        mvhd = _find_box(f, b"mvhd", moov[1])
        if not mvhd:
            return None
        f.seek(mvhd[0])
        version = f.read(1)[0]
        f.read(3)                          # flags
        if version == 1:
            f.read(16)                     # creation/modification time (64비트)
            timescale = struct.unpack(">I", f.read(4))[0]
            duration = struct.unpack(">Q", f.read(8))[0]
        else:
            f.read(8)                      # creation/modification time (32비트)
            timescale = struct.unpack(">I", f.read(4))[0]
            duration = struct.unpack(">I", f.read(4))[0]
        if not timescale or not duration:
            return None
        return round(duration / timescale, 2)


def clip_duration(clips_dir, state):
    """<state>.mp4 의 길이(초). 파일이 없거나 못 읽으면 None."""
    if not state:
        return None
    with _LOCK:
        if state in _CACHE:
            return _CACHE[state]
    value = None
    try:
        path = clips_dir / f"{state}.mp4"
        if path.is_file():
            value = _mp4_duration(path)
    except (OSError, ValueError, struct.error, IndexError):
        value = None
    with _LOCK:
        _CACHE[state] = value
    return value
