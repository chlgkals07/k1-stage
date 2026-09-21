"""core.stage.Stage — 파일도 HTTP 도 서버도 없이.

이 파일이 6단계의 보상이다. State 가 server.py 에 있을 때는 무대 시나리오 하나를 시험하려면 임시 디렉터리,
프리셋 JSON, 음원 파일, 가짜 mp4 가 필요했다(test_dance · test_motion_duration). Stage 는 그것들을 인자로
받으므로 여기서는 람다 몇 개면 된다. 그래서 빠르고, 빠르면 더 많이 쓰게 된다.

실행: 저장소 루트에서  python3 -m unittest discover -s tests -t .
"""

import ast
import copy
import unittest
from pathlib import Path

from core import stage as stage_module
from core.stage import Stage

ROOT = Path(__file__).resolve().parent.parent

CATALOG_ITEMS = [
    {"state": "MimicA", "ko": "에이", "safety": "safe", "llm": True},
    {"state": "MimicB", "ko": "비", "safety": "safe", "llm": True},
    {"state": "MimicSecret", "ko": "비공개", "safety": "restricted", "llm": True},
    {"state": "Velocity", "ko": "보행 대기", "safety": "safe"},
]
BY_STATE = {m["state"]: m for m in CATALOG_ITEMS}


class NullLog:
    def __init__(self):
        self.events = []

    def write(self, kind, **kw):
        self.events.append((kind, kw))

    def text(self, s):
        return s


class FakeTransport:
    """Transport 모양의 가짜. 무엇이 불렸는지만 기록한다."""
    name = "fake"

    def __init__(self):
        self.submitted = []
        self.stopped = []

    def submit(self, motion, source, reason):
        self.submitted.append((motion, source))
        return {"ok": True, "status": "queued", "motion": motion, "request_id": "1", "msg": "ok"}

    def stop_motion(self, source, reason=""):
        self.stopped.append(source)
        return {"ok": True, "status": "queued", "motion": "Velocity", "request_id": None, "msg": "stop"}

    def status(self):
        return {"gateway": "ready"}       # 준비된 백엔드. 준비 안 된 경우는 아래 NotReady 가 시험한다

    def stop(self):
        pass


def make(*, presets=None, media=("a.mp4",), clips=None, backend=None, **kw):
    clips = {} if clips is None else clips
    stage = Stage(
        backend or FakeTransport(),
        catalog=(CATALOG_ITEMS, BY_STATE),
        # 진짜 load_presets() 는 JSON 파일을 읽어 **매번 새 dict** 를 만든다. 같은 객체를 돌려주는 가짜는
        # 현실보다 관대해서, 시작할 때 한 번 읽어 둔 스냅샷도 테스트가 제자리에서 바꾼 값을 보게 된다.
        load_presets=lambda: copy.deepcopy(presets) if presets is not None else {},
        media_files=lambda: list(media),
        clip_seconds=lambda s: clips.get(s),
        clip_exists=lambda s: s in clips,
        session_log=NullLog(), **kw)
    return stage


class StageCase(unittest.TestCase):
    def build(self, **kw):
        stage = make(**kw)
        self.addCleanup(self.cancel_timers, stage)
        return stage

    @staticmethod
    def cancel_timers(stage):
        for t in (stage._dance_timer, stage._dance_prep_timer, stage._dance_autostop_timer,
                  stage._exec_idle_timer):
            if t:
                t.cancel()


class DependencyRuleTest(unittest.TestCase):
    def test_core_imports_nothing_but_the_standard_library_and_its_own_ports(self):
        """의존은 안쪽으로만 흐른다. core 가 어댑터·서버·파일 라이브러리를 알면 하드웨어 없이 못 돈다."""
        for name in ("stage.py", "ports.py"):
            tree = ast.parse((ROOT / "core" / name).read_text())
            mods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    mods.add(node.module.split(".")[0] if node.module != "core.ports" else "core.ports")
            with self.subTest(name):
                self.assertLessEqual(mods, {"__future__", "typing", "secrets", "threading", "time",
                                            "collections", "core.ports"}, mods)


class PlayTest(StageCase):
    def test_a_successful_motion_becomes_executing_and_arms_the_unlock_timer(self):
        st = self.build(clips={"MimicA": 4.0})
        out = st.play("MimicA", source="manual")
        self.assertTrue(out["ok"], out)
        self.assertEqual(st.stage, "executing")
        # 클립 길이는 주입된 clip_seconds 가 준다 — fake_mp4 도 static/clips 도 없다
        self.assertAlmostEqual(st._exec_idle_timer.interval, 4.0 + Stage.EXEC_IDLE_MARGIN_SEC)

    def test_a_motion_without_a_clip_uses_the_default_length(self):
        st = self.build()
        st.play("MimicA", source="manual")
        self.assertAlmostEqual(st._exec_idle_timer.interval,
                               Stage.EXEC_IDLE_DEFAULT_SEC + Stage.EXEC_IDLE_MARGIN_SEC)

    def test_unknown_motion_is_rejected_and_the_screen_stays(self):
        st = self.build()
        out = st.play("MimicNope", source="manual")
        self.assertFalse(out["ok"])
        self.assertEqual(st.stage, "idle")
        self.assertEqual(st.backend.submitted, [])

    def test_the_audience_cannot_press_outside_the_pad_list(self):
        st = self.build(pad_allowlist=["MimicA", "MimicB"], api_allowlist=["MimicA"])
        self.assertEqual(st.pad_order, ["MimicA"])
        self.assertTrue(st.play("MimicA", source="pad")["ok"])
        rejected = st.play("MimicB", source="pad")     # 목록엔 있지만 api_allowlist 밖
        self.assertFalse(rejected["ok"])
        self.assertIn("관객", rejected["msg"])
        self.assertEqual(st.backend.submitted, [("MimicA", "pad")])

    def test_the_audience_is_refused_during_a_dance_but_the_dance_itself_still_fires(self):
        """패드도 스스로 잠그지만 그건 1초 폴링 뒤에야 반영된다. 무대 시작 직후 눌린 탭이 안무 대신 다른
        동작을 내지 않도록 서버가 막는다 (2026-08-18 리뷰). 무대가 쏘는 동작은 source=manual 이라 통과한다."""
        st = self.build(pad_allowlist=["MimicA"],
                        presets={"p": {"motion": "MimicB", "media": "a.mp4", "offset_ms": 0, "media_len_sec": 5}})
        self.assertTrue(st.start_dance("p")["ok"])
        refused = st.play("MimicA", source="pad")
        self.assertFalse(refused["ok"])
        self.assertIn("무대 진행 중", refused["msg"])
        self.assertEqual(st.backend.submitted, [])
        self.assertTrue(st.play("MimicB", source="manual")["ok"])     # 무대 자신의 발사
        self.assertEqual(st.stage, "dance")                           # 무대 화면은 유지된다

    def test_restricted_never_reaches_the_llm(self):
        st = self.build(ready_only=False)
        self.assertNotIn("MimicSecret", st.allowed)
        self.assertFalse(st.play("MimicSecret", source="llm")["ok"])

    def test_an_operator_stop_during_a_dance_takes_the_dance_down_but_calls_the_robot_once(self):
        st = self.build(presets={"p": {"motion": "MimicA", "media": "a.mp4", "offset_ms": 0,
                                       "media_len_sec": 5}})
        self.assertTrue(st.start_dance("p")["ok"])
        st.stop_motion("정지")
        self.assertEqual(st.stage, "idle")
        self.assertEqual(st.backend.stopped, ["manual"])


class StartDanceTest(StageCase):
    PRESET = {"motion": "MimicA", "media": "a.mp4", "offset_ms": -1500, "media_len_sec": 12}

    def test_negative_offset_puts_the_media_first(self):
        st = self.build(presets={"p": self.PRESET})
        out = st.start_dance("p")
        self.assertTrue(out["ok"], out)
        self.assertAlmostEqual(out["motion_at"] - out["media_at"], 1.5, places=2)
        self.assertEqual(st.stage, "dance")

    def test_presets_are_read_at_call_time_not_at_construction(self):
        """/dance 는 실행 중에 프리셋을 저장한다. 시작할 때 한 번 읽은 값을 들고 있으면 새 오프셋이 안 먹는다."""
        presets = {"p": dict(self.PRESET, offset_ms=-1000)}
        st = self.build(presets=presets)
        self.assertAlmostEqual(st.start_dance("p")["motion_at"] - st.stage_data["media_at"], 1.0, places=2)
        presets["p"] = dict(self.PRESET, offset_ms=-2500)             # 저장 버튼
        out = st.start_dance("p")
        self.assertAlmostEqual(out["motion_at"] - out["media_at"], 2.5, places=2)

    def test_missing_media_and_unknown_preset_and_unknown_motion_are_refused(self):
        st = self.build(presets={"nomedia": dict(self.PRESET, media="gone.mp4"),
                                 "nomotion": dict(self.PRESET, motion="MimicNope")})
        for name, needle in (("nomedia", "음원"), ("nomotion", "카탈로그"), ("nope", "프리셋")):
            with self.subTest(name):
                out = st.start_dance(name)
                self.assertFalse(out["ok"])
                self.assertIn(needle, out["msg"])
        self.assertEqual(st.stage, "idle")

    def test_a_bad_number_refuses_before_any_timer_is_armed(self):
        """숫자 필드는 타이머를 걸기 전에 전부 파싱한다. 먼저 걸면 "시작 실패"로 보이는데 2초 뒤 로봇만
        움직인다 (리뷰 지적). 그때 실제로 아무 타이머도 없어야 한다."""
        st = self.build(presets={"bad": dict(self.PRESET, offset_ms="abc")})
        out = st.start_dance("bad")
        self.assertFalse(out["ok"])
        self.assertIsNone(st._dance_timer)
        self.assertIsNone(st._dance_autostop_timer)
        self.assertEqual((st.stage, st._dance_gen), ("idle", 0))

    def test_starting_a_second_dance_invalidates_the_first_ones_late_callback(self):
        st = self.build(presets={"a": self.PRESET, "b": dict(self.PRESET, motion="MimicB")})
        st.start_dance("a")
        old = st._dance_gen
        st.start_dance("b")
        st._fire_dance_motion("MimicA", old)              # A 의 늦은 콜백
        self.assertEqual(st.backend.submitted, [])
        st._fire_dance_motion("MimicB", st._dance_gen)
        self.assertEqual(st.backend.submitted, [("MimicB", "manual")])

    def test_a_dance_is_refused_when_the_gateway_is_not_ready(self):
        """SD API Arm 을 안 올린 채 무대를 누르면 영상만 돌고 로봇은 안 움직인다(2026-09-20 실제로 겪음).
        stop_dance 는 로봇을 안 건드리는 설계라 한 번 시작되면 되돌릴 수 없으므로 시작 시점에 막는다."""
        class NotReady(FakeTransport):
            def status(self):
                return {"gateway": "offline"}
        st = self.build(presets={"p": self.PRESET}, backend=NotReady())
        out = st.start_dance("p")
        self.assertFalse(out["ok"])
        self.assertIn("준비", out["msg"])
        self.assertIsNone(st._dance_timer)
        self.assertEqual(st.stage, "idle")

    def test_the_gateway_check_is_skipped_for_mock_and_for_a_dance_without_a_motion(self):
        class Named(FakeTransport):
            def __init__(self, gateway):
                super().__init__()
                self._gw = gateway

            def status(self):
                return {"gateway": self._gw}
        mock = self.build(presets={"p": self.PRESET}, backend=Named("mock"))
        self.assertTrue(mock.start_dance("p")["ok"])                       # 로봇 미연결 개발용은 통과
        audio_only = self.build(backend=Named("offline"))
        out = audio_only.start_dance(preset={"motion": "", "media": "a.mp4", "media_len_sec": 5})
        self.assertTrue(out["ok"], out)                                     # 동작이 없으면 로봇 상태와 무관

    def test_stop_dance_never_touches_the_robot(self):
        st = self.build(presets={"p": self.PRESET})
        st.start_dance("p")
        st.stop_dance()
        self.assertEqual(st.backend.stopped, [])
        self.assertEqual(st.stage, "idle")


class StageLifetimeTest(StageCase):
    def test_a_stage_that_outlives_its_ttl_falls_back_to_idle(self):
        st = self.build()
        st.set_stage("preview", {"motion": "MimicA"})
        st.stage_set_at -= Stage.STAGE_TTL["preview"] + 1     # 패드가 죽어서 아무도 idle 을 안 보냈다
        self.assertEqual(st.effective_stage(), "idle")

    def test_a_fresh_stage_is_kept(self):
        st = self.build()
        st.set_stage("preview")
        self.assertEqual(st.effective_stage(), "preview")

    def test_clip_states_asks_the_injected_lookup_and_only_knows_the_catalog(self):
        st = self.build(clips={"MimicA": 4.0, "NotInCatalog": 9.0})
        self.assertEqual(st.clip_states(), ["MimicA"])


class ProtectedTest(StageCase):
    def test_paths_that_move_the_robot_get_a_token_and_a_mock_does_not(self):
        class Named(FakeTransport):
            def __init__(self, name):
                super().__init__()
                self.name = name
        for name, protected in (("robot", True), ("relay", True), ("rc", True), ("mock", False)):
            with self.subTest(name):
                st = self.build(backend=Named(name))
                self.assertEqual(bool(st.access_token), protected)


if __name__ == "__main__":
    unittest.main()
