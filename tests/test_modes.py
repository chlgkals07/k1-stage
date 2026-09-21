"""app.py 의 두 모드(solo · fleet)가 갈리는 곳과 갈리면 안 되는 곳.

앱은 하나다. 모드가 정하는 것은 어느 데이터를 읽나 · 어느 화면을 여나 · 기본 포트·테마·백엔드 뿐이다.
안전 코어(정지 경로 · api_allowlist 게이트 · 인증 · 부팅 검증)는 모드와 무관해야 하고, 그래서
같은 시나리오를 두 모드에 보내 같은 답이 나오는지를 여기서 본다.
"""

import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

import app
from core import catalog
from tests.test_rc_fleet import make_fleet

ROOT = Path(__file__).parent.parent
TOKEN = "modes-test-token"


class ModeTableTest(unittest.TestCase):
    def test_every_mode_has_its_data_and_its_pages(self):
        for name, mode in app.MODES.items():
            with self.subTest(name):
                self.assertTrue((ROOT / "config" / name / "motions.yaml").is_file())
                self.assertTrue((ROOT / "config" / name / "gateway_config.yaml").is_file())
                self.assertIn(mode["landing"], mode["pages"])
                self.assertIn("/operator", mode["pages"])   # 정지는 운영자 화면에 있다 — 어느 모드든 있어야 한다
                for page in mode["pages"].values():
                    self.assertTrue((app.WEB / page).is_file(), page)
                self.assertTrue((app.THEMES / mode["theme"]).is_dir())

    def test_the_audience_pad_exists_only_in_solo(self):
        self.assertIn("/pad", app.MODES["solo"]["pages"])
        self.assertNotIn("/pad", app.MODES["fleet"]["pages"])

    def test_every_mode_passes_the_default_venue_without_fatal(self):
        """fleet 의 카탈로그(139)·정책(79)이 solo 의 것(16/14)과 달라도, 기본 venue 의 패드 12칸은 둘 다 덮는다."""
        venue = catalog.load_venue(app.VENUES / app.DEFAULT_VENUE)
        for name in app.MODES:
            with self.subTest(name):
                cfg = ROOT / "config" / name
                problems = catalog.validate(yaml.safe_load((cfg / "motions.yaml").read_text()),
                                            yaml.safe_load((cfg / "gateway_config.yaml").read_text())["policy"],
                                            venue, require_media=False)
                self.assertEqual([str(p) for p in problems if p.level == catalog.FATAL], [])


def run_main(*argv):
    """main() 을 끝까지 태운다(서버만 가짜). 끝나면 solo 로 되돌린다 — 모듈 전역이 바뀌므로."""
    class NoNetwork:
        def __init__(self, *a, **kw):
            self.socket = None

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass
    orig = (sys.argv, app.QuietServer, app.PRESETS, app.Handler.state, app.Handler.theme)
    sys.argv = ["app.py", "--port", "0", "--no-log", *argv]
    app.QuietServer = NoNetwork
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            app.main()
        return out.getvalue(), (app.Handler.mode, app.Handler.theme, app.CATALOG)
    finally:
        sys.argv, app.QuietServer, app.PRESETS, app.Handler.state, app.Handler.theme = orig
        app.select_mode("solo")


class BootTest(unittest.TestCase):
    def test_solo_is_the_default_and_uses_its_own_data(self):
        _, (mode, theme, cat) = run_main()
        self.assertEqual((mode, theme), ("solo", "shape"))
        self.assertEqual(cat, ROOT / "config" / "solo" / "motions.yaml")

    def test_fleet_boots_with_its_own_data_and_theme(self):
        printed, (mode, theme, cat) = run_main("--mode", "fleet", "--mock")
        self.assertEqual((mode, theme), ("fleet", "shape-gym"))
        self.assertEqual(cat, ROOT / "config" / "fleet" / "motions.yaml")
        self.assertIn("패드 버튼 12개", printed)

    def test_the_theme_flag_still_overrides_the_mode_default(self):
        _, (_, theme, _) = run_main("--mode", "fleet", "--mock", "--theme", "shape")
        self.assertEqual(theme, "shape")

    def test_fleet_refuses_the_solo_only_backends(self):
        for flag in (["--robot", "--https"], ["--rc", "--https"]):
            with self.subTest(flag), self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    run_main("--mode", "fleet", *flag)

    def test_leaving_fleet_restores_solo_for_everything_that_follows(self):
        run_main("--mode", "fleet", "--mock")
        self.assertEqual(app.Handler.mode, "solo")
        self.assertEqual(app.CATALOG, ROOT / "config" / "solo" / "motions.yaml")


class HttpBase:
    mode = None

    @classmethod
    def setUpClass(cls):
        app.select_mode(cls.mode)
        state = app.State(app.MockBackend(), pad_allowlist=app.load_venue()["pad_grid"])
        state.access_token = TOKEN
        cls.orig_state = app.Handler.state
        app.Handler.state = state
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        app.Handler.state = cls.orig_state
        app.select_mode("solo")

    def call(self, method, path, body=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)

        def send(url, cookie=None):
            req = urllib.request.Request(url, method=method,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json",
                                                  **({"Cookie": cookie} if cookie else {})})
            try:
                with opener.open(req, timeout=5) as r:
                    return r.status, dict(r.headers), r.read()
            except urllib.error.HTTPError as e:
                return e.code, dict(e.headers), e.read()
        if path == "/":     # 인증 전 진입점: 토큰을 쿼리로 준다
            return send(f"{self.base}/?token={TOKEN}")
        # 인증은 쿠키다 — 운영자 화면을 토큰과 함께 열면 서버가 준다
        with urllib.request.urlopen(f"{self.base}/operator?token={TOKEN}", timeout=5) as r:
            cookie = r.headers["Set-Cookie"].split(";", 1)[0]
        return send(self.base + path, cookie)


class SoloHttpTest(HttpBase, unittest.TestCase):
    mode = "solo"

    def test_root_goes_to_the_audience_pad(self):
        status, headers, _ = self.call("GET", "/")
        self.assertEqual((status, headers["Location"].split("?")[0]), (302, "/pad"))

    def test_status_says_which_mode_this_is(self):
        status, _, body = self.call("GET", "/status")
        self.assertEqual(json.loads(body)["mode"], "solo")

    def test_rc_toggle_exists_and_rescan_does_not(self):
        self.assertEqual(self.call("POST", "/rc/mode", {"on": False})[0], 200)
        self.assertEqual(self.call("POST", "/rc/rescan", {})[0], 404)


    def test_dance_motions_come_from_the_venue_presets(self):
        """dance.html 에 박혀 있던 무대 3종을 서버가 준다 — 행사가 바뀌면 프리셋과 함께 바뀐다."""
        motions = json.loads(self.call("GET", "/motions")[2])["dance_motions"]
        presets = json.loads((app.PRESETS).read_text())
        self.assertEqual(motions, sorted({p["motion"] for p in presets.values()}))
        self.assertEqual(len(motions), 3)

    def test_dance_motions_fall_back_to_the_pad_when_a_venue_has_no_presets(self):
        orig = app.PRESETS
        with tempfile.TemporaryDirectory() as tmp:
            app.PRESETS = Path(tmp) / "presets.json"     # 없는 파일 = 프리셋 없음
            try:
                motions = json.loads(self.call("GET", "/motions")[2])["dance_motions"]
            finally:
                app.PRESETS = orig
        self.assertEqual(len(motions), 12)
        self.assertEqual(motions, app.Handler.state.pad_order)


class FleetHttpTest(HttpBase, unittest.TestCase):
    mode = "fleet"

    def test_root_goes_to_the_operator(self):
        status, headers, _ = self.call("GET", "/")
        self.assertEqual((status, headers["Location"].split("?")[0]), (302, "/operator"))

    def test_there_is_no_audience_pad(self):
        self.assertEqual(self.call("GET", "/pad")[0], 404)
        self.assertEqual(self.call("GET", "/operator")[0], 200)

    def test_status_says_which_mode_this_is(self):
        self.assertEqual(json.loads(self.call("GET", "/status")[2])["mode"], "fleet")

    def test_rescan_exists_and_the_rc_toggle_does_not(self):
        self.assertEqual(self.call("POST", "/rc/mode", {"on": True})[0], 404)
        status, _, body = self.call("POST", "/rc/rescan", {})
        self.assertEqual(status, 200)
        self.assertIn("재탐색 대상 아님", json.loads(body)["msg"])   # mock 은 재탐색할 게 없다


class RescanUsesDiscoveryTest(unittest.TestCase):
    """/rc/rescan 은 재탐색 능력이 있는 백엔드에서만 재탐색한다."""

    def test_a_backend_without_discovery_is_not_rescanned(self):
        out = app.State(app.MockBackend()).rescan_rc()
        self.assertTrue(out["ok"])
        self.assertIn("재탐색 대상 아님", out["msg"])

    def test_a_fleet_is_rescanned(self):
        calls = []
        fleet = make_fleet(2)
        fleet.rescan = lambda: calls.append("rescan") or []
        out = app.State(fleet).rescan_rc()
        self.assertEqual(calls, ["rescan"])
        self.assertEqual(out["backend"], "rc")

    def test_an_empty_fleet_fails_with_guidance(self):
        from runtime import rc_fleet
        orig = rc_fleet.discover_ports
        rc_fleet.discover_ports = lambda: []
        try:
            out = app.State(rc_fleet.RcFleetBackend(ROOT / "config" / "fleet" / "motions.yaml")).rescan_rc()
        finally:
            rc_fleet.discover_ports = orig
        self.assertFalse(out["ok"])
        self.assertIn("Pocket", out["msg"])


class SafetyCoreIsTheSameInEveryModeTest(unittest.TestCase):
    """모드는 화면과 데이터를 바꾸지 안전 코어를 바꾸지 않는다."""

    def test_stop_and_the_llm_rejection_answer_identically(self):
        answers = {}
        for name in app.MODES:
            app.select_mode(name)
            try:
                st = app.State(app.MockBackend(), ready_only=False)
                stop = st.stop_motion("test")
                llm = st.play("MimicWaveHand", "r", "llm")
                answers[name] = ({k: stop[k] for k in ("ok", "motion", "status")},
                                 {k: llm[k] for k in ("ok", "msg")})
            finally:
                app.select_mode("solo")
        self.assertEqual(answers["solo"], answers["fleet"])
        self.assertFalse(answers["solo"][1]["ok"])


if __name__ == "__main__":
    unittest.main()
