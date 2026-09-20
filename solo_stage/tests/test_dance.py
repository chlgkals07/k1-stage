"""/dance — 동작과 음원/영상을 시간차 맞춰 같이 출발시키는 화면.

Range 는 iOS Safari 가 음원을 재생하기 위한 전제라서 반드시 확인한다.
프리셋은 서버 JSON 파일이라 저장-불러오기-삭제 왕복을 확인한다.
"""

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server
from server import Handler, MockBackend, State

TOKEN = "dance-test-token"
BLOB = bytes(range(256)) * 8      # 2048 바이트
_MEDIA_TMPDIR = None
_ORIG_MEDIA = None


def setUpModule():
    """저작권 미디어 없이도 모든 dance 테스트를 실제 운영 파일과 격리해 실행한다."""
    global _MEDIA_TMPDIR, _ORIG_MEDIA
    _MEDIA_TMPDIR = tempfile.TemporaryDirectory()
    _ORIG_MEDIA = server.MEDIA
    server.MEDIA = Path(_MEDIA_TMPDIR.name)
    for name in ("응원단 fade_out.mp4", "straykids.mp4", "bad.mp4"):
        (server.MEDIA / name).touch()


def tearDownModule():
    global _MEDIA_TMPDIR
    server.MEDIA = _ORIG_MEDIA
    _MEDIA_TMPDIR.cleanup()
    _MEDIA_TMPDIR = None


class DanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.track = server.MEDIA / "_test_track.mp3"
        cls.track.write_bytes(BLOB)
        # 실제 프리셋 파일을 건드리지 않는다.
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.orig_presets = server.PRESETS
        server.PRESETS = Path(cls.tmpdir.name) / "presets.json"
        state = State(MockBackend())
        state.access_token = TOKEN
        Handler.state = state
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = "http://127.0.0.1:" + str(cls.httpd.server_port)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.track.unlink(missing_ok=True)
        server.PRESETS = cls.orig_presets
        cls.tmpdir.cleanup()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, cookie=None, headers=None, data=None):
        head = dict(headers or {})
        if cookie:
            head["Cookie"] = cookie
        if data is not None:
            head["Content-Type"] = "application/json"
            data = json.dumps(data).encode()
        req = urllib.request.Request(self.base_url + path, headers=head, data=data)
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.headers, exc.read()
            finally:
                exc.close()

    def cookie(self):
        _, headers, _ = self.request("/?token=" + TOKEN)
        return headers["Set-Cookie"].split(";", 1)[0]

    # ── 화면 ──────────────────────────────────────────────────────
    def test_dance_page_requires_token_and_has_controls(self):
        self.assertEqual(self.request("/dance")[0], 403)
        self.assertEqual(self.request("/dance?token=bad")[0], 403)
        status, _, page = self.request("/dance", self.cookie())
        self.assertEqual(status, 200)
        for needed in (b'id="offset"', b'id="player"', b'id="startBtn"',
                       b'id="stopBtn"', b'id="presetSave"', b'id="presetLoad"'):
            self.assertIn(needed, page)

    def test_page_asks_for_manual_source(self):
        """댄스 화면은 사람이 누르는 버튼이다. LLM allowlist 를 타면 안 된다."""
        _, _, page = self.request("/dance", self.cookie())
        self.assertIn(b"source:'manual'", page.replace(b" ", b""))

    # ── 미디어 ────────────────────────────────────────────────────
    def test_media_listing(self):
        status, _, body = self.request("/media", self.cookie())
        self.assertEqual(status, 200)
        self.assertIn("_test_track.mp3", json.loads(body)["files"])

    def test_full_get_advertises_range_support(self):
        status, headers, body = self.request("/media/_test_track.mp3", self.cookie())
        self.assertEqual(status, 200)
        self.assertEqual(body, BLOB)
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["Content-Type"], "audio/mpeg")

    def test_range_requests(self):
        cookie = self.cookie()
        cases = {
            "bytes=0-99": (BLOB[:100], "bytes 0-99/2048"),
            "bytes=100-": (BLOB[100:], "bytes 100-2047/2048"),
            "bytes=-50": (BLOB[-50:], "bytes 1998-2047/2048"),
            "bytes=0-99999": (BLOB, "bytes 0-2047/2048"),   # 끝을 넘겨도 잘라서 준다
        }
        for rng, (expect, content_range) in cases.items():
            with self.subTest(rng=rng):
                status, headers, body = self.request(
                    "/media/_test_track.mp3", cookie, {"Range": rng})
                self.assertEqual(status, 206)
                self.assertEqual(body, expect)
                self.assertEqual(headers["Content-Range"], content_range)

    def test_range_past_end_is_416(self):
        status, headers, _ = self.request(
            "/media/_test_track.mp3", self.cookie(), {"Range": "bytes=9999-"})
        self.assertEqual(status, 416)
        self.assertEqual(headers["Content-Range"], "bytes */2048")

    def test_unknown_and_traversal_paths_are_404(self):
        cookie = self.cookie()
        for path in ("/media/nope.mp3", "/media/..%2Fserver.py", "/media/server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, cookie)[0], 404)

    def test_media_requires_authorization(self):
        self.assertEqual(self.request("/media")[0], 403)
        self.assertEqual(self.request("/media/_test_track.mp3")[0], 403)

    # ── 프리셋 ────────────────────────────────────────────────────
    def test_preset_roundtrip(self):
        cookie = self.cookie()
        preset = {"motion": "MimicSnuCheer", "media": "_test_track.mp3",
                  "clip": "MimicSnuCheer", "seek": 1.5, "offset_ms": 350, "volume": 80}
        status, _, body = self.request("/dance/presets", cookie,
                                       data={"name": "t1", "preset": preset})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["presets"]["t1"], preset)
        # 다시 GET 해도 (파일에서) 그대로 나온다
        _, _, body = self.request("/dance/presets", cookie)
        self.assertEqual(json.loads(body)["presets"]["t1"], preset)
        # null 로 삭제
        status, _, body = self.request("/dance/presets", cookie,
                                       data={"name": "t1", "preset": None})
        self.assertEqual(status, 200)
        self.assertNotIn("t1", json.loads(body)["presets"])

    def test_preset_bad_requests(self):
        cookie = self.cookie()
        for payload in ({"preset": {}}, {"name": "", "preset": {}},
                        {"name": "x", "preset": "not-a-dict"}):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.request("/dance/presets", cookie, data=payload)[0], 400)

    def test_presets_require_authorization(self):
        self.assertEqual(self.request("/dance/presets")[0], 403)
        self.assertEqual(
            self.request("/dance/presets", data={"name": "x", "preset": {}})[0], 403)




class StageTest(unittest.TestCase):
    """display 무대 상태 기계. executing/dance 는 /stage 로 못 만든다."""

    def setUp(self):
        import yaml
        cfg = yaml.safe_load((Path(__file__).parent.parent / "gateway_config.yaml").read_text())
        self.state = server.State(server.MockBackend(),
                                  pad_allowlist=cfg["policy"]["pad_allowlist"])

    def test_view_exposes_stage_and_server_clock(self):
        v = self.state.conversation_view()
        self.assertEqual(v["stage"], "idle")
        self.assertIn("stage_rev", v)
        self.assertAlmostEqual(v["server_now"], time.time(), delta=2)

    def test_successful_motion_becomes_executing(self):
        self.state.set_stage("preview", {"motion": "MimicWaveHand", "ko": "손 흔들기"})
        self.state.play("MimicWaveHand", source="pad")
        v = self.state.conversation_view()
        self.assertEqual(v["stage"], "executing")
        self.assertEqual(v["stage_data"]["motion"], "MimicWaveHand")

    def test_rejected_motion_keeps_stage(self):
        self.state.set_stage("preview", {"motion": "MimicWaveHand", "ko": "손 흔들기"})
        self.state.play("MimicCartwheel", source="pad")   # pad 목록 밖 → 거부
        self.assertEqual(self.state.conversation_view()["stage"], "preview")

    def test_stage_expires_to_idle(self):
        """패드가 죽어도 display 가 preview 에 영원히 갇히지 않는다."""
        self.state.set_stage("preview", {"motion": "MimicWaveHand"})
        self.state.stage_set_at = time.time() - 121
        self.assertEqual(self.state.conversation_view()["stage"], "idle")

    def test_clear_conversation_resets_stage(self):
        self.state.set_stage("listening")
        self.state.clear_conversation()
        self.assertEqual(self.state.conversation_view()["stage"], "idle")


class DanceScheduleTest(unittest.TestCase):
    """폴링 지연과 무관하게 절대 시각으로 싱크를 맞춘다."""

    def setUp(self):
        self.state = server.State(server.MockBackend())

    def tearDown(self):
        if self.state._dance_timer:
            self.state._dance_timer.cancel()

    def test_negative_offset_means_media_first(self):
        out = self.state.start_dance("snucheer-api")     # offset -1500ms (2026-08-18 실측 고정)
        self.assertTrue(out["ok"])
        self.assertAlmostEqual(out["motion_at"] - out["media_at"], 1.5, places=2)
        self.assertGreater(out["media_at"], time.time() + 1.5)   # 리드타임
        v = self.state.conversation_view()
        self.assertEqual(v["stage"], "dance")
        self.assertEqual(v["stage_data"]["media"], "응원단 fade_out.mp4")

    def test_stop_cancels_timer_and_returns_idle(self):
        self.state.start_dance("snucheer-api")
        self.state.stop_dance()
        self.assertIsNone(self.state._dance_timer)
        self.assertEqual(self.state.conversation_view()["stage"], "idle")

    def test_unknown_preset_rejected(self):
        self.assertFalse(self.state.start_dance("nope")["ok"])

    def test_dance_motion_does_not_flip_stage_to_executing(self):
        """무대 중 동작 실행은 무대 화면을 유지해야 한다."""
        self.state.start_dance("snucheer-api")
        self.state.play("MimicWaveHand", source="manual")
        self.assertEqual(self.state.conversation_view()["stage"], "dance")

    def test_start_dance_blocked_when_gateway_not_ready(self):
        """SD API Arm 안 올린 채로 무대를 누르면 영상만 돌고 로봇은 안 움직이던 사고
        (2026-09-20) — 게이트웨이가 준비되지 않았으면 무대 자체를 시작하지 않는다."""
        class NotReadyBackend(server.MockBackend):
            def status(self):
                return {"gateway": "offline"}
        state = server.State(NotReadyBackend())
        out = state.start_dance("snucheer-api")
        self.assertFalse(out["ok"])
        self.assertIsNone(state._dance_timer)

    def test_start_dance_without_motion_ignores_gateway(self):
        """음원만 보정하는 inline preset(동작 없음)은 로봇 상태와 무관하게 통과해야 한다."""
        class NotReadyBackend(server.MockBackend):
            def status(self):
                return {"gateway": "offline"}
        state = server.State(NotReadyBackend())
        out = state.start_dance(preset={"motion": "", "media": ""})
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()


class DanceProtectionTest(unittest.TestCase):
    """2026-08-18 리뷰 수정: 무대는 패드 터치로 죽지 않고, 로봇은 ReadyPose 로 선점되지 않는다."""

    def setUp(self):
        import yaml
        cfg = yaml.safe_load((Path(__file__).parent.parent / "gateway_config.yaml").read_text())
        self.backend = MockBackend()
        self.backend.stop_calls = []
        real_stop = self.backend.stop_motion
        def counting_stop(source, reason=""):
            self.backend.stop_calls.append((source, reason))
            return real_stop(source, reason)
        self.backend.stop_motion = counting_stop
        self.state = server.State(self.backend,
                                  pad_allowlist=cfg["policy"]["pad_allowlist"])
        server.Handler.state = self.state

    def tearDown(self):
        if self.state._dance_timer:
            self.state._dance_timer.cancel()

    def test_stop_dance_never_touches_the_robot(self):
        """영상이 안무보다 짧아 먼저 끝나도 로봇이 관객 앞에서 끊기면 안 된다."""
        self.state.start_dance("straykids-api")
        out = self.state.stop_dance()
        self.assertTrue(out["ok"])
        self.assertEqual(self.backend.stop_calls, [],
                         "dance 경로가 로봇 정지를 호출했다 — ReadyPose 선점 금지 위반")
        self.assertEqual(self.state.conversation_view()["stage"], "idle")
        self.assertIsNone(self.state._dance_timer)

    def test_effective_stage_helper(self):
        self.state.start_dance("straykids-api")
        self.assertEqual(self.state.effective_stage(), "dance")
        self.state.stop_dance()
        self.assertEqual(self.state.effective_stage(), "idle")


class DanceGenerationTest(unittest.TestCase):
    """A 재생 중 B 시작: A 의 늦은 타이머 콜백이 B 무대에 A 동작을 쏘면 안 된다."""

    def setUp(self):
        self.backend = MockBackend()
        self.fired = []
        real = self.backend.submit
        def counting(motion, source, reason):
            self.fired.append(motion)
            return real(motion, source, reason)
        self.backend.submit = counting
        self.state = server.State(self.backend)

    def tearDown(self):
        if self.state._dance_timer:
            self.state._dance_timer.cancel()

    def test_stale_generation_callback_is_dropped(self):
        self.state.start_dance("snucheer-api")          # A (gen 1)
        old_gen = self.state._dance_gen
        self.state.start_dance("straykids-api")         # B (gen 2) — A 타이머는 cancel 됐지만
        # cancel 을 비껴간 A 콜백이 늦게 도착했다고 가정
        self.state._fire_dance_motion("MimicNewSnuCheerHeadShort", old_gen)
        self.assertNotIn("MimicNewSnuCheerHeadShort", self.fired,
                         "옛 세대 콜백이 B 무대에 A 동작을 쐈다")
        # 현재 세대 콜백은 정상 발사된다
        self.state._fire_dance_motion("MimicStraykidsThisAndThat", self.state._dance_gen)
        self.assertIn("MimicStraykidsThisAndThat", self.fired)

    def test_stop_invalidates_inflight_callback(self):
        self.state.start_dance("snucheer-api")
        gen = self.state._dance_gen
        self.state.stop_dance()
        self.state._fire_dance_motion("MimicNewSnuCheerHeadShort", gen)
        self.assertEqual(self.fired, [], "정지 후 늦은 콜백이 동작을 쐈다")


class DanceCaptionTest(unittest.TestCase):
    """무대 자막: 공식 명칭(중앙) + 출처(하단). 약칭은 무대에 쓰지 않는다."""

    def test_stage_data_carries_title_and_credit(self):
        state = State(MockBackend())
        out = state.start_dance(preset={"motion": "MimicWaveHand", "media": "",
                                        "title": "관악을 보아라", "credit": "서울대학교 응원단"})
        self.assertTrue(out["ok"])
        sd = state.conversation_view()["stage_data"]
        self.assertEqual(sd["title"], "관악을 보아라")
        self.assertEqual(sd["credit"], "서울대학교 응원단")
        state.stop_dance()

    def test_title_never_falls_back_to_nickname(self):
        """자막을 못 찾으면 비운다. 동작 약칭("체스트팝 v2")은 무대에 띄우지 않는다.

        2026-08-18 사용자 확정 규칙. 예전에는 여기서 카탈로그 한글명으로 떨어져,
        /dance 화면에서 음원 없이 시작하면 무대 TV 에 약칭이 그대로 떴다.
        """
        state = State(MockBackend())
        state.start_dance(preset={"motion": "MimicWaveHand", "media": ""})
        sd = state.conversation_view()["stage_data"]
        self.assertEqual(sd["title"], "")
        self.assertNotEqual(sd["title"], state.by_state["MimicWaveHand"]["ko"])
        state.stop_dance()

    def test_saving_offset_does_not_wipe_caption(self):
        """/dance 보정 화면은 숫자·파일 필드만 보낸다. 제목·출처가 날아가면 안 된다."""
        import server
        original = server.PRESETS
        with tempfile.TemporaryDirectory() as tmp:
            server.PRESETS = Path(tmp) / "presets.json"
            try:
                server.save_preset("x", {"motion": "MimicWaveHand", "media": "",
                                         "title": "ATEEZ - Bad", "credit": "ATEEZ 'Bad' 안무 영상"})
                after = server.save_preset("x", {"motion": "MimicWaveHand", "media": "",
                                                 "offset_ms": 250})
                self.assertEqual(after["x"]["title"], "ATEEZ - Bad")
                self.assertEqual(after["x"]["credit"], "ATEEZ 'Bad' 안무 영상")
                self.assertEqual(after["x"]["offset_ms"], 250)
            finally:
                server.PRESETS = original

    def test_inline_preset_without_caption_borrows_from_saved(self):
        """/dance 보정 화면은 자막 없는 inline preset 을 보낸다.

        같은 음원 파일의 저장본에서 제목·출처를 끌어와야 한다. 안 하면 무대에
        동작 약칭("체스트팝 v2")이 뜬다 — 현장에서 실제로 그렇게 떴다.
        """
        import server
        media = (server.media_files() or [None])[0]
        if not media:
            self.skipTest("media 파일이 없다")
        original = server.PRESETS
        with tempfile.TemporaryDirectory() as tmp:
            server.PRESETS = Path(tmp) / "p.json"
            try:
                server.save_preset("x", {"motion": "MimicWaveHand", "media": media,
                                         "title": "ATEEZ - Bad", "credit": "ATEEZ 'Bad' 안무 영상"})
                state = State(MockBackend())
                state.start_dance(preset={"motion": "MimicWaveHand", "media": media,
                                          "offset_ms": 0})
                sd = state.conversation_view()["stage_data"]
                self.assertEqual(sd["title"], "ATEEZ - Bad")
                self.assertEqual(sd["credit"], "ATEEZ 'Bad' 안무 영상")
                state.stop_dance()
            finally:
                server.PRESETS = original
