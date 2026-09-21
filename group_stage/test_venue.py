"""서버가 venue 를 제대로 물고 있는지 — 부팅 거부, 프리셋 위치, 로봇 배포 안전성.

검증 로직 자체(무엇이 FATAL 인가)는 저장소 루트 tests/test_catalog.py 가 본다.
여기서는 그 함수를 server.py 가 올바른 자리에서 부르는지만 본다.
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import server

HERE = Path(server.__file__).parent
# group 은 --mock 이 없으면 실제 라디오를 찾는다. solo 는 인자 없이 mock 이다.
EXTRA_ARGS = ("--mock",)


def gateway_config():
    return yaml.safe_load((HERE / "gateway_config.yaml").read_text())


class BootCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = server.VENUES
        server.VENUES = Path(self.tmp.name)

    def tearDown(self):
        server.VENUES = self.orig
        self.tmp.cleanup()

    def venue(self, name, pad_grid):
        d = Path(self.tmp.name) / name
        d.mkdir()
        (d / "venue.yaml").write_text("name: t\npad_grid: " + json.dumps(pad_grid) + "\n")
        return d

    def boot(self, name, **kw):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            try:
                return server.check_venue(name, gateway_config(), **kw), out.getvalue()
            except SystemExit as exc:
                return exc, out.getvalue()

    def test_fatal_venue_refuses_to_boot(self):
        """무대에서 발견하던 걸 노트북에서 발견한다. 기동 자체를 거부해야 한다."""
        self.venue("bad", ["MimicNotARealMotion"])
        result, printed = self.boot("bad", require_media=False)
        self.assertIsInstance(result, SystemExit)
        self.assertIn("FATAL", printed)
        self.assertIn("기동하지 않는다", str(result))

    def test_unreadable_venue_refuses_to_boot(self):
        result, _ = self.boot("does-not-exist", require_media=False)
        self.assertIsInstance(result, SystemExit)

    def test_valid_venue_boots_and_returns_its_pad_grid(self):
        grid = [m for m in gateway_config()["policy"]["api_allowlist"]
                if m.startswith("Mimic")][:12]
        self.venue("ok", grid)
        venue, _ = self.boot("ok", require_media=False)
        self.assertEqual(venue["pad_grid"], grid)

    def test_warnings_are_capped_so_real_problems_stay_visible(self):
        """개발 PC 는 클립·음원이 없어 WARN 이 늘 스무 줄쯤 나온다. 다 찍으면 진짜 문제가 묻힌다."""
        self.venue("noisy", [m for m in gateway_config()["policy"]["api_allowlist"]
                             if m.startswith("Mimic")][:12])
        _, printed = self.boot("noisy", require_media=False)
        self.assertLessEqual(printed.count("WARN"), 6)   # 5건 + 요약 한 줄

    def test_default_venue_boots_without_media(self):
        """mock 개발 실행은 음원이 없어도 떠야 한다. 없으면 아무도 화면을 못 본다."""
        server.VENUES = self.orig
        venue, _ = self.boot(server.DEFAULT_VENUE, require_media=False)
        self.assertNotIsInstance(venue, SystemExit)
        self.assertEqual(len(venue["pad_grid"]), 12)


class PresetLocationTest(unittest.TestCase):
    def test_default_presets_live_in_the_default_venue(self):
        self.assertEqual(server.PRESETS, server.VENUES / server.DEFAULT_VENUE / "presets.json")
        self.assertTrue(server.PRESETS.is_file())

    def test_presets_are_not_kept_in_the_app_folder_anymore(self):
        """앱 폴더에 사본이 남으면 두 앱이 서로 다른 오프셋을 들고 무대에 나간다 (8/31 의 그 병)."""
        self.assertFalse((HERE / "dance_presets.json").exists())


class RobotDeployTest(unittest.TestCase):
    def test_server_imports_only_the_core_modules_the_robot_receives(self):
        """로봇에는 core/stage.py · core/ports.py 가 간다(State 의 부모와 그 계약). core/catalog.py 는 안 간다.

        로봇(--robot)은 UI 가 없어 venue 를 안 쓴다. 그래서 catalog 는 최상단이 아니라 쓰는 자리에서
        늦게 불러온다 — 최상단에서 import 하면 로봇에서 server.py 가 import 에러로 안 뜬다.
        배포 목록이 어긋났을 때 실제로 두 번 났던 사고와 같은 모양이다.
        (배포 목록이 이 임포트를 다 덮는지는 test_server_tools 가 본다.)
        """
        source = (HERE / "server.py").read_text()
        self.assertNotRegex(source, r"(?m)^from core import|^import core\b")   # 패키지 통째 import 금지
        top_level_core = set(re.findall(r"(?m)^from core\.(\w+) import", source))
        self.assertEqual(top_level_core - {"catalog"}, top_level_core)          # catalog 는 최상단 금지
        self.assertTrue({"stage", "ports"} <= top_level_core, top_level_core)
        self.assertIn("def _catalog", source)   # 늦은 import 가 실제로 그 자리에 있다



class MainBootTest(unittest.TestCase):
    """main() 을 실제로 끝까지 태운다 — 네트워크 서버만 가짜로 바꾸고 나머지는 전부 진짜다.

    이 테스트가 없을 때 실제로 있었던 일: group 에 없는 `args.robot` 을 solo 에서 복사해 와서
    group 이 부팅할 때마다 AttributeError 로 죽었는데, 테스트 108건이 전부 초록이었다.
    main() 을 부르는 테스트가 하나도 없었기 때문이다.
    """

    class _NoNetwork:
        def __init__(self, *a, **kw):
            self.socket = None

        def serve_forever(self):
            raise KeyboardInterrupt   # main() 이 정상 종료 경로로 빠진다

        def server_close(self):
            pass

    def run_main(self, *argv):
        orig = (sys.argv, server.QuietServer, server.PRESETS)
        sys.argv = ["server.py", "--port", "0", "--no-log", *EXTRA_ARGS, *argv]
        server.QuietServer = self._NoNetwork
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                server.main()
            return out.getvalue()
        finally:
            sys.argv, server.QuietServer, server.PRESETS = orig

    def test_boots_with_the_default_venue(self):
        printed = self.run_main()
        self.assertIn("패드 버튼 12개", printed)

    def test_presets_follow_the_chosen_venue(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "mine"
            d.mkdir()
            grid = [m for m in gateway_config()["policy"]["api_allowlist"] if m.startswith("Mimic")][:12]
            (d / "venue.yaml").write_text("pad_grid: " + json.dumps(grid) + "\n")
            orig = server.VENUES
            server.VENUES = Path(tmp)
            try:
                sys_argv = ["server.py", "--port", "0", "--no-log", *EXTRA_ARGS, "--venue", "mine"]
                orig_argv, orig_srv, orig_presets = sys.argv, server.QuietServer, server.PRESETS
                sys.argv, server.QuietServer = sys_argv, self._NoNetwork
                with contextlib.redirect_stdout(io.StringIO()):
                    server.main()
                self.assertEqual(server.PRESETS, d / "presets.json")
            finally:
                sys.argv, server.QuietServer, server.PRESETS = orig_argv, orig_srv, orig_presets
                server.VENUES = orig

    def test_unknown_venue_stops_the_boot(self):
        with self.assertRaises(SystemExit):
            self.run_main("--venue", "no-such-venue")


if __name__ == "__main__":
    unittest.main()
