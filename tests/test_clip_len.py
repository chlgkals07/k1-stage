"""clip_len — sim 클립 mp4 의 길이 = 그 동작이 도는 시간.

이 모듈은 관객 패드가 잠겨 있는 시간을 정한다 (STATUS §4 수정 6·7: 60초+ → 8초, 30초 → 4초).
그런데 지금까지 이걸 검사하는 테스트가 하나도 없었다 — 실제 클립(39MB)이 저장소에 없어서다.
그래서 clip_len 이 읽는 최소한의 mp4(ftyp + moov/mvhd)를 코드로 만든다. 100바이트면 된다.

`fake_mp4` 는 다른 테스트 파일도 가져다 쓴다 (from test_clip_len import fake_mp4).
"""

import struct
import tempfile
import unittest
from pathlib import Path

from runtime import clip_len


def _box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def fake_mp4(seconds, timescale=1000, version=0, moov_last=False):
    """clip_len 이 읽을 수 있는 최소 mp4. moov/mvhd 의 timescale·duration 만 진짜다.

    version=1 은 64비트 시간 필드(긴 영상용)이고, moov_last 는 mdat 뒤에 moov 를 둔다 —
    카메라·일부 인코더가 그렇게 쓰므로 박스 건너뛰기까지 같이 시험된다.
    """
    duration = round(seconds * timescale)
    if version == 1:
        mvhd = struct.pack(">B3xQQIQ", 1, 0, 0, timescale, duration)
    else:
        mvhd = struct.pack(">B3xIIII", 0, 0, 0, timescale, duration)
    mvhd += b"\0" * 80          # rate·volume·matrix… — clip_len 은 읽지 않는다
    ftyp = _box(b"ftyp", b"isom\0\0\0\0isom")
    moov = _box(b"moov", _box(b"mvhd", mvhd))
    mdat = _box(b"mdat", b"\xaa" * 1000)
    return ftyp + (mdat + moov if moov_last else moov + mdat)


def _hidden_moov(seconds=4.0):
    """크기 7 로 거짓말하는 박스 헤더 마지막 1바이트 자리에서 시작하는 진짜 moov."""
    mvhd = _box(b"mvhd", struct.pack(">B3xIIII", 0, 0, 0, 1000, round(seconds * 1000)) + b"\0" * 80)
    hidden_size = struct.pack(">I", 8 + len(mvhd))          # 첫 바이트는 0 이다
    return struct.pack(">I", 7) + b"fre" + hidden_size[:1] + hidden_size[1:] + b"moov" + mvhd


class ClipLenTest(unittest.TestCase):
    def setUp(self):
        # 캐시가 state 이름만 키로 삼는다 — 테스트끼리 서로의 값을 물려받지 않게 비운다.
        clip_len._CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        clip_len._CACHE.clear()
        self.tmp.cleanup()

    def put(self, state, data):
        (self.dir / f"{state}.mp4").write_bytes(data)

    def test_reads_duration_in_seconds(self):
        self.put("A", fake_mp4(4.0))
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 4.0)

    def test_uses_timescale_not_milliseconds(self):
        """실제 인코더는 timescale 을 90000 등으로 쓴다. 1000 으로 가정하면 길이가 90배 틀어진다."""
        self.put("A", fake_mp4(3.98, timescale=90000))
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 3.98)

    def test_64bit_mvhd_version_1(self):
        self.put("A", fake_mp4(29.5, version=1))
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 29.5)

    def test_moov_after_mdat_is_found(self):
        self.put("A", fake_mp4(8.25, moov_last=True))
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 8.25)

    def test_unreadable_inputs_give_none_never_raise(self):
        """못 읽으면 None 이고 호출부가 기본값(12초·30초)으로 떨어진다. 예외로 새면 무대가 죽는다."""
        cases = {
            "empty": b"",
            "garbage": b"not an mp4 at all" * 20,
            "no_moov": _box(b"ftyp", b"isom\0\0\0\0isom") + _box(b"mdat", b"\0" * 100),
            "no_mvhd": _box(b"ftyp", b"isom\0\0\0\0isom") + _box(b"moov", _box(b"trak", b"\0" * 20)),
            "zero_duration": fake_mp4(0.0),
            "truncated": fake_mp4(4.0)[:30],
            "box_size_past_end": struct.pack(">I4s", 9999, b"moov") + b"\0" * 20,
            # 아래 둘은 명시적 검사를 지나 struct.error / IndexError 까지 가는 입력이다. 앞의 것들은
            # 전부 그 앞에서 None 이 돼서, except 를 좁혀도 테스트가 모르고 통과했다 (변이 테스트로 확인).
            # moov 가 파일보다 크다고 주장하지만 mvhd 는 온전하다. 크기 검증이 없으면 이걸 읽어
            # 4.0 을 돌려준다 — 잘린 파일의 길이를 믿게 된다 (변이 테스트로 확인).
            "moov_claims_more_than_file": (lambda d: d[:20] + struct.pack(">I", 5000) + d[24:])(fake_mp4(4.0)),
            "box_size_under_header": struct.pack(">I4s", 4, b"free") + fake_mp4(4.0),
            # 크기 7 짜리 박스의 다음 위치는 헤더 마지막 1바이트다. 검증이 없으면 거기서 다시 읽어
            # 그 뒤에 숨긴 진짜 moov 를 파싱한다. 깨진 헤더에서 길이를 끌어내면 안 된다.
            "box_size_under_header_hides_a_moov": _hidden_moov(),
            "mvhd_shorter_than_header": _box(b"moov", _box(b"mvhd", b"\x00")),
            "mvhd_empty": _box(b"moov", _box(b"mvhd", b"")),
        }
        for name, data in cases.items():
            with self.subTest(name):
                clip_len._CACHE.clear()
                self.put("X", data)
                self.assertIsNone(clip_len.clip_duration(self.dir, "X"))

    def test_missing_file_and_empty_state_give_none(self):
        self.assertIsNone(clip_len.clip_duration(self.dir, "NoSuchClip"))
        self.assertIsNone(clip_len.clip_duration(self.dir, ""))
        self.assertIsNone(clip_len.clip_duration(self.dir, None))

    def test_result_is_cached_for_the_life_of_the_process(self):
        """지금 동작의 기록이지 요구사항이 아니다. 나중에 바뀌면 이 테스트를 고쳐도 된다.

        한 번 읽은 값은 파일이 바뀌어도 그대로이고, **못 읽어서 None 이 된 것도 캐시된다**.
        그래서 클립이 없을 때 한 번 조회되면 나중에 구워 넣어도 서버를 재시작하기 전까지
        반영되지 않는다. (STATUS §4 는 "다시 구우면 자동 반영"이라고 적었지만 재시작이 필요하다.)
        """
        self.assertIsNone(clip_len.clip_duration(self.dir, "A"))      # 없음 → None 이 캐시된다
        self.put("A", fake_mp4(4.0))
        self.assertIsNone(clip_len.clip_duration(self.dir, "A"))      # 파일이 생겨도 여전히 None
        clip_len._CACHE.clear()                                       # 재시작에 해당
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 4.0)
        self.put("A", fake_mp4(9.0))
        self.assertEqual(clip_len.clip_duration(self.dir, "A"), 4.0)  # 바뀌어도 옛 값


class FakeMp4SelfTest(unittest.TestCase):
    def test_fake_mp4_is_tiny(self):
        """저장소에 바이너리가 필요 없다는 전제 — 코드로 만든 클립이 작아야 한다."""
        self.assertLess(len(fake_mp4(4.0)), 1500)


if __name__ == "__main__":
    unittest.main()
