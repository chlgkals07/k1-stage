import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from server import Handler, MockBackend, State


TOKEN = "ui-test-token"


class UiHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state = State(MockBackend())
        state.access_token = TOKEN
        Handler.state = state
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = "http://127.0.0.1:" + str(cls.httpd.server_port)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, cookie=None):
        headers = {"Cookie": cookie} if cookie else {}
        request = urllib.request.Request(self.base_url + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.headers, exc.read()
            finally:
                exc.close()

    def test_token_mints_cookie_then_cookie_opens_operator(self):
        status, headers, body = self.request("/pad?token=" + TOKEN)
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        status, _, body = self.request("/operator", cookie)
        self.assertEqual(status, 200)
        self.assertIn("K1 운영자 화면".encode(), body)
        self.assertIn(b'id="modeBadge"', body)

    def test_operator_rejects_missing_or_bad_token(self):
        self.assertEqual(self.request("/operator")[0], 403)
        self.assertEqual(self.request("/operator?token=bad")[0], 403)

    def post(self, path, payload, cookie=None):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        request = urllib.request.Request(self.base_url + path, method="POST",
                                         data=json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, None
            finally:
                exc.close()

    def get_json(self, path, cookie=None):
        status, _, body = self.request(path, cookie)
        return status, json.loads(body)

    def test_stop_requires_authorization(self):
        self.assertEqual(self.post("/stop", {"reason": "x"})[0], 403)

    def test_stop_button_present_and_reachable_with_cookie(self):
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        _, _, page = self.request("/operator", cookie)
        self.assertIn(b'id="stopBtn"', page)

        status, out = self.post("/stop", {"reason": "테스트", "source": "llm"}, cookie)
        self.assertEqual(status, 200)
        self.assertTrue(out["ok"])
        # 클라이언트가 source: llm 을 주장해도 서버가 무시한다.
        self.assertEqual(out["source"], "stop")

    def test_root_redirects_to_pad(self):
        """음성 폰 화면 제거(2026-08-18) — 옛 북마크는 관객 화면으로 보낸다."""
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=2)
        conn.request("GET", "/?token=" + TOKEN)
        resp = conn.getresponse()
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "/pad?token=" + TOKEN)
        conn.close()

    def test_display_page_requires_token(self):
        self.assertEqual(self.request("/display")[0], 403)
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, page = self.request("/display", cookie)
        self.assertEqual(status, 200)
        # 무대 화면의 6개 상태 레이어 + 오디오 잠금 오버레이가 전부 있어야 한다
        for layer in (b'layer-idle', b'layer-preview', b'layer-executing',
                      b'layer-dance', b'layer-unlock'):
            self.assertIn(layer, page)
        # 실행 시 클립 재재생은 없다 — preview 에서 본 것을 또 틀면 "실행 안 됨"으로
        # 보인다 (현장 리허설). 이 회귀를 페이지 내용으로 잡는다.
        self.assertNotIn(b"lastMotionRev = data.motion_rev", page)

    def test_pad_page_requires_token(self):
        self.assertEqual(self.request("/pad")[0], 403)
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, page = self.request("/pad", cookie)
        self.assertEqual(status, 200)
        self.assertIn(b'id="goBtn"', page)   # preview 실행 버튼 (talk 은 음성과 함께 제거됨)

    def test_pad_page_has_no_operator_surface(self):
        """관객 화면에 정지·로그·상태카드가 새어 들어가지 않는다."""
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        page = self.request("/pad", cookie)[2]
        for leak in (b'id="stopBtn"', b'id="log"', b'id="cards"'):
            self.assertNotIn(leak, page)

    def test_pad_page_has_no_voice_code(self):
        """음성 전면 제거(2026-08-18) — WebRTC·마이크·세션 발급이 있으면 회귀다."""
        page = self.request("/pad", self.cookie())[2]
        for voice in (b"getUserMedia", b"RTCPeerConnection", b"'/session'",
                      b"output_text", b"postStage('listening'"):
            self.assertNotIn(voice, page, voice)

    def test_stage_listening_is_rejected(self):
        """listening/thinking 은 음성과 함께 폐기 — 서버가 400 을 내야 한다."""
        status, _ = self.post("/stage", {"stage": "listening"}, self.cookie())
        self.assertEqual(status, 400)

    def test_display_has_no_voice_stage_branch(self):
        page = self.request("/display", self.cookie())[2]
        self.assertNotIn(b"showLayer('listening')", page)

    def test_motions_endpoint_exposes_pad_allowlist(self):
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        body = json.loads(self.request("/motions", cookie)[2])
        self.assertIn("pad_allowed", body)
        self.assertIsInstance(body["pad_allowed"], list)

    def test_motions_endpoint_lists_clips(self):
        """모니터는 이 목록을 보고 재생 여부를 정한다. 실제 파일과 일치해야 한다."""
        _, headers, _ = self.request("/?token=" + TOKEN)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        body = json.loads(self.request("/motions", cookie)[2])
        from server import CLIPS
        for state in body["clips"]:
            self.assertTrue((CLIPS / f"{state}.mp4").is_file(), state)
        self.assertEqual(sorted(body["clips"]),
                         sorted(p.stem for p in CLIPS.glob("*.mp4")))

    # ── 동작 sim 클립 서빙: 경로 탈출 차단과 Range 지원이 핵심이다 ──

    def cookie(self):
        _, headers, _ = self.request("/?token=" + TOKEN)
        return headers["Set-Cookie"].split(";", 1)[0]

    def any_clip(self):
        """클립은 부분 존재가 정상 — 디스크에 실재하는 것으로 검증한다."""
        from server import CLIPS
        clips = sorted(CLIPS.glob("*.mp4"))
        self.assertTrue(clips, "클립이 하나도 없다 — 이 테스트군은 최소 1개를 전제한다")
        return clips[0].stem

    def test_clip_is_served_with_range_support(self):
        status, headers, body = self.request(f"/clips/{self.any_clip()}.mp4", self.cookie())
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "video/mp4")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertTrue(len(body) > 0)

    def test_range_request_returns_partial_content(self):
        """Safari 는 Range 를 못 하는 video 를 아예 재생하지 않는다."""
        request = urllib.request.Request(
            self.base_url + f"/clips/{self.any_clip()}.mp4",
            headers={"Cookie": self.cookie(), "Range": "bytes=0-99"})
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(len(response.read()), 100)
            self.assertTrue(response.headers["Content-Range"].startswith("bytes 0-99/"))

    def test_unknown_state_is_404(self):
        self.assertEqual(self.request("/clips/NotAMotion.mp4", self.cookie())[0], 404)

    def test_path_traversal_is_blocked(self):
        """카탈로그 이름과 대조하므로 파일 밖으로 나갈 수 없다."""
        for attack in ("/clips/../server.py", "/clips/..%2Fserver.py",
                       "/clips/../../etc/passwd"):
            self.assertEqual(self.request(attack, self.cookie())[0], 404, attack)

    def test_clip_requires_token(self):
        self.assertEqual(self.request(f"/clips/{self.any_clip()}.mp4")[0], 403)

    def test_conversation_clear_resets_stage_and_motion(self):
        """/event 자막은 제거됐다. clear 는 무대 리셋만 한다."""
        cookie = self.cookie()
        self.post("/motion", {"motion": "MimicWaveHand", "source": "manual"}, cookie)
        self.post("/conversation/clear", {}, cookie)
        _, body = self.get_json("/conversation", cookie)
        self.assertEqual(body["current_motion"], "")
        self.assertEqual(body["stage"], "idle")
        self.assertNotIn("lines", body)

    def test_event_route_is_gone(self):
        self.assertEqual(self.post("/event", {"kind": "user_transcript",
                                              "text": "x"}, self.cookie())[0], 404)

    def test_ui_config_is_gone(self):
        """음성 설정 API 는 음성과 함께 제거됐다 (2026-08-18)."""
        self.assertEqual(self.request("/ui-config", self.cookie())[0], 404)




class MotionRevTest(unittest.TestCase):
    """모니터가 "동작이 시작됐다"를 알아채는 신호.

    rev 는 자막 delta 에도 오르므로 쓸 수 없다. motion_rev 는 동작이 실제로
    나갈 때만 오른다.
    """

    def setUp(self):
        self.state = State(MockBackend())

    def test_motion_rev_rises_only_on_successful_motion(self):
        before = self.state.motion_rev
        self.state.play("MimicWaveHand", source="manual")
        self.assertEqual(self.state.motion_rev, before + 1)
        self.assertEqual(self.state.current_motion_state, "MimicWaveHand")

    def test_conversation_updates_do_not_move_motion_rev(self):
        self.state.play("MimicWaveHand", source="manual")
        before = self.state.motion_rev
        self.state.set_stage("preview", {"motion": "MimicWaveHand"})  # 화면 갱신 사례
        self.assertEqual(self.state.motion_rev, before)

    def test_rejected_motion_does_not_move_motion_rev(self):
        before = self.state.motion_rev
        out = self.state.play("NotAMotion", source="manual")
        self.assertFalse(out["ok"])
        self.assertEqual(self.state.motion_rev, before)

    def test_same_motion_twice_moves_motion_rev(self):
        """같은 버튼을 두 번 누르면 두 번째도 재생돼야 한다."""
        self.state.play("MimicWaveHand", source="manual")
        first = self.state.motion_rev
        self.state.play("MimicWaveHand", source="manual")
        self.assertEqual(self.state.motion_rev, first + 1)

    def test_clear_keeps_motion_rev(self):
        """되돌리면 모니터가 새 동작으로 오해해 끝난 클립을 다시 튼다."""
        self.state.play("MimicWaveHand", source="manual")
        before = self.state.motion_rev
        self.state.clear_conversation()
        self.assertEqual(self.state.motion_rev, before)
        self.assertEqual(self.state.conversation_view()["current_motion_state"], "")


if __name__ == "__main__":
    unittest.main()
