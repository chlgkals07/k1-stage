"""동작 길이 → 관객 패드가 잠겨 있는 시간. STATUS §4 수정 6·7 이 실제로 지켜지는지.

- 서버(`_exec_idle`): 동작이 나가면 화면을 executing 으로 두고 (클립 길이 + 3초) 뒤에 idle 로 내린다.
  이게 없으면 운영자가 수동 실행할 때마다 패드가 TTL 60초까지 잠긴다 (2026-08-18 리허설).
- RC(`motion_duration`): 클립 길이 + 2초. 이게 없으면 4초짜리 손인사에도 30초 잠긴다.

둘 다 clip_len 을 읽는데, 지금까지 이 경로를 검사하는 테스트가 하나도 없었다. 실제 클립이
저장소에 없어서였다. test_clip_len.fake_mp4 로 만든 클립과 합성 다이얼을 쓰므로 운영
파일에 기대지 않는다.
"""

import tempfile
import unittest
from pathlib import Path

from runtime import clip_len
import app
from runtime.rc_backend import BUSY_MARGIN_SEC, DEFAULT_DURATION_SEC, RcBackend
from tests.test_clip_len import fake_mp4

# ch11 = 1000 + 20 * (slot - 1). slot 1..20. 이 다이얼은 이 파일이 스스로 만든다.
SYNTHETIC_MOTIONS = """\
motions:
  - {state: MimicPlain,   ko: 기본,   category: performance, safety: safe}
  - {state: MimicNoted,   ko: 명시,   category: performance, safety: safe}
  - {state: MimicOffDial, ko: 밖,     category: performance, safety: safe}
rc_list:
  select: {bank: CH5, slot: CH11}
  banks:
    A:
      ch5: 1000
      input_code: 4
      slots:
        - {slot: 200, ch11: 1000, state: MimicPlain}
        - {slot: 201, ch11: 1020, state: MimicNoted, note: "이 동작은 12.5s 정도"}
    B: {ch5: 2000, input_code: 5, slots: []}
"""


class FakeSerial:
    last_error = ""

    def close(self):
        pass


class RcMotionDurationTest(unittest.TestCase):
    def setUp(self):
        clip_len._CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "motions.yaml").write_text(SYNTHETIC_MOTIONS, encoding="utf-8")
        self.clips = root / "clips"     # RcBackend 는 clips_dir 를 안 받으면 motions.yaml 옆 clips/ 에서 찾는다
        self.clips.mkdir(parents=True)
        self.backend = RcBackend(root / "motions.yaml", serial=FakeSerial())

    def tearDown(self):
        clip_len._CACHE.clear()
        self.tmp.cleanup()

    def clip(self, state, seconds):
        (self.clips / f"{state}.mp4").write_bytes(fake_mp4(seconds))

    def test_clip_length_plus_margin_replaces_the_default(self):
        """4초 클립이면 30초가 아니라 4 + 여백. 관객 패드가 30초 멈추던 것이 이것이다."""
        self.clip("MimicPlain", 4.0)
        self.assertEqual(self.backend.motion_duration("MimicPlain"), 4.0 + BUSY_MARGIN_SEC)

    def test_note_on_the_dial_beats_the_clip(self):
        self.clip("MimicNoted", 4.0)
        self.assertEqual(self.backend.motion_duration("MimicNoted"), 12.5)

    def test_no_clip_falls_back_to_the_default(self):
        self.assertEqual(self.backend.motion_duration("MimicPlain"), DEFAULT_DURATION_SEC)

    def test_unreadable_clip_falls_back_to_the_default(self):
        (self.clips / "MimicPlain.mp4").write_bytes(b"not an mp4")
        self.assertEqual(self.backend.motion_duration("MimicPlain"), DEFAULT_DURATION_SEC)

    def test_motion_not_on_the_dial_has_no_duration(self):
        """다이얼에 없는 동작. State 는 None 을 "길이를 모른다"로 받아 기본값을 쓴다."""
        self.clip("MimicOffDial", 4.0)
        self.assertIsNone(self.backend.motion_duration("MimicOffDial"))
        self.assertIsNone(self.backend.motion_duration("MimicNeverHeardOf"))


class ExecIdleTest(unittest.TestCase):
    def setUp(self):
        clip_len._CACHE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.orig_clips = app.CLIPS
        app.CLIPS = Path(self.tmp.name)
        self.state = app.State(app.MockBackend())

    def tearDown(self):
        if self.state._exec_idle_timer:
            self.state._exec_idle_timer.cancel()
        app.CLIPS = self.orig_clips
        clip_len._CACHE.clear()
        self.tmp.cleanup()

    def play(self, motion="MimicWaveHand"):
        out = self.state.play(motion, source="manual")
        self.assertTrue(out["ok"], out)

    def test_pad_unlocks_after_clip_length_plus_margin(self):
        (app.CLIPS / "MimicWaveHand.mp4").write_bytes(fake_mp4(4.0))
        self.play()
        self.assertEqual(self.state.stage, "executing")
        self.assertAlmostEqual(self.state._exec_idle_timer.interval,
                               4.0 + app.State.EXEC_IDLE_MARGIN_SEC)

    def test_no_clip_uses_the_default_length(self):
        self.play()
        self.assertAlmostEqual(self.state._exec_idle_timer.interval,
                               app.State.EXEC_IDLE_DEFAULT_SEC + app.State.EXEC_IDLE_MARGIN_SEC)

    def test_the_timer_puts_the_screen_back_to_idle(self):
        self.play()
        self.state._exec_idle(self.state.stage_rev)
        self.assertEqual(self.state.stage, "idle")

    def test_a_stale_timer_does_not_take_down_someone_elses_screen(self):
        """패드가 idle 을 먼저 보냈거나 다음 동작이 시작됐으면 옛 타이머는 무시된다."""
        self.play("MimicWaveHand")
        old_rev = self.state.stage_rev
        self.play("MimicBowNavel")                       # 다음 동작이 화면을 가져갔다
        self.assertNotEqual(self.state.stage_rev, old_rev)
        self.state._exec_idle(old_rev)
        self.assertEqual(self.state.stage, "executing")

    def test_during_a_dance_no_timer_is_armed(self):
        """무대 중의 동작 실행은 무대 화면을 유지한다 — idle 로 내리는 타이머가 걸리면 안 된다."""
        with self.state.lock:
            self.state._set_stage_locked("dance", {"name": "x"})
        self.play()
        self.assertEqual(self.state.stage, "dance")
        self.assertIsNone(self.state._exec_idle_timer)

    def test_a_rejected_motion_arms_nothing(self):
        out = self.state.play("MimicNoSuchMotion", source="manual")
        self.assertFalse(out["ok"])
        self.assertIsNone(self.state._exec_idle_timer)
        self.assertEqual(self.state.stage, "idle")


if __name__ == "__main__":
    unittest.main()
