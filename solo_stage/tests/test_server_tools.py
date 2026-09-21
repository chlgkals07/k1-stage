import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import server
from server import State

GATEWAY_CONFIG = Path(__file__).parent.parent / "gateway_config.yaml"


class Backend:
    name = "relay"

    def status(self):
        return {}

    def __init__(self):
        self.stop_calls = []

    def submit(self, motion, source, reason):
        return {"ok": True, "status": "queued", "motion": motion,
                "request_id": "x", "msg": "queued"}

    def stop_motion(self, source, reason=""):
        self.stop_calls.append((source, reason))
        return {"ok": True, "status": "queued", "motion": "ReadyPose",
                "request_id": "s", "msg": "정지 요청 대기"}

    def stop(self):
        pass


class ServerToolsTest(unittest.TestCase):
    def test_llm_source_is_disabled(self):
        state = State(Backend(), ready_only=True)
        out = state.play("MimicBowNavel", source="llm")
        self.assertFalse(out["ok"])
        self.assertIn("운영하지", out["msg"])

    def test_stop_is_always_manual(self):
        backend = Backend()
        state = State(backend, ready_only=True)
        out = state.stop_motion("운영자 정지")
        self.assertTrue(out["ok"])
        self.assertEqual(out["motion"], "ReadyPose")
        # source 는 서버가 강제한다.
        self.assertEqual(backend.stop_calls, [("manual", "운영자 정지")])
        self.assertEqual(out["source"], "stop")

    def test_every_api_allowlist_state_exists_in_catalog(self):
        """allowlist 에만 있고 카탈로그에 없으면 운영자 버튼이 조용히 사라진다.

        operator.html 이 `catalog.filter(m => allowed.has(m.state))` 로 버튼을 만들고
        State.play() 도 카탈로그에 없는 state 를 거부하므로, 둘이 어긋나면 실행이 안 된다.
        """
        _, by_state = server.load_catalog()
        policy = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]
        missing = [s for s in policy["api_allowlist"] if s not in by_state]
        self.assertEqual(missing, [], f"카탈로그에 없는 allowlist 항목: {missing}")

    def test_api_allowlist_has_no_duplicates(self):
        """중복은 조용히 지나가지만 카운트·UI 를 흐린다 (2026-08-13 에 실제로 있었다)."""
        api = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]["api_allowlist"]
        self.assertEqual(len(api), len(set(api)),
                         [s for s in set(api) if api.count(s) > 1])

    def test_every_api_motion_has_a_category(self):
        """카테고리가 없으면 운영자 화면에서 '분류 없음' 으로 밀린다."""
        _, by_state = server.load_catalog()
        api = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]["api_allowlist"]
        missing = [s for s in api if not by_state[s].get("category")]
        self.assertEqual(missing, [], f"category 누락: {missing}")

class PadAllowlistTest(unittest.TestCase):
    """관객용 아이패드(/pad) — 세 번째 허용목록.

    운영자 버튼(source=manual)은 사람이 누른 것이라 통과시키지만, 관객이 누르는
    화면은 그 사람이 운영자가 아니므로 목록을 강제해야 한다.
    """

    @classmethod
    def setUpClass(cls):
        cls.policy = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]
        cls.pad = server.load_venue()["pad_grid"]
        cls.items, cls.by_state = server.load_catalog()

    def test_pad_is_subset_of_api_and_catalog(self):
        api = set(self.policy["api_allowlist"])
        self.assertTrue(set(self.pad) <= api, set(self.pad) - api)
        unknown = set(self.pad) - set(self.by_state)
        self.assertFalse(unknown, f"카탈로그에 없는 항목: {unknown}")

    def test_pad_is_the_final_twelve_in_order(self):
        """2026-08-18 사용자 최종 확정 12개. 순서 = 패드 그리드 번호라 순서도 스펙이다."""
        self.assertEqual(self.pad, [
            "MimicBowNavel", "MimicShadowBoxing", "MimicDanceJazzHands", "MimicWaveHand",
            "MimicBowCourtly", "MimicNewMacarena001A545", "MimicNewKnightlyBowR001A429",
            "MimicSquat", "MimicChefsKiss", "MimicPushUp",
            "MimicNewRockOut002A487", "MimicBadChestpopVer2"])

    def test_pad_has_no_duplicates(self):
        self.assertEqual(len(self.pad), len(set(self.pad)))

    def test_clips_are_all_known_states(self):
        """클립은 "최종 렌더만" 정책(2026-08-18) — 부분 존재가 정상이다.
        지키는 건 고아 방지뿐: 존재하는 클립은 전부 카탈로그 state 여야 한다."""
        for f in server.CLIPS.glob("*.mp4"):
            self.assertIn(f.stem, self.by_state, f.name)

    def _state(self):
        return State(Backend(), ready_only=True,
                     pad_allowlist=["MimicWaveHand", "MimicBowNavel"])

    def test_pad_source_rejects_motion_outside_pad_list(self):
        out = self._state().play("MimicBadChestpopVer2", source="pad")
        self.assertFalse(out["ok"])
        self.assertIn("관객", out["msg"])

    def test_pad_source_allows_motion_inside_pad_list(self):
        self.assertTrue(self._state().play("MimicWaveHand", source="pad")["ok"])

    def test_manual_source_is_not_limited_by_pad_list(self):
        """운영자 경로는 불변이다. pad 목록이 운영자를 막으면 안 된다."""
        self.assertTrue(self._state().play("MimicBadChestpopVer2", source="manual")["ok"])

    def test_pad_list_intersects_api_allowlist(self):
        """오타 하나로 카탈로그 밖 항목이 조용히 통과하지 않는다. api_allowlist 밖 항목도 마찬가지다.

        api_allowlist 는 백엔드의 속성이 아니라 정책에서 State 로 직접 들어온다."""
        st = State(Backend(), ready_only=True, pad_allowlist=["NotARealMotion"])
        self.assertEqual(st.pad_allowed, set())
        st = State(Backend(), ready_only=True, pad_allowlist=["MimicWaveHand", "MimicBowNavel"],
                   api_allowlist=["MimicWaveHand"])
        self.assertEqual(st.pad_allowed, {"MimicWaveHand"})


# PadSessionTest 는 음성 세션과 함께 제거됨 (2026-08-18)


class DeployListTest(unittest.TestCase):
    """로봇 배포 목록이 server.py 의 의존을 다 덮는지.

    2026-08-13 에 relay_backend.py 가 목록에 없어 로봇 gateway 가 아예 뜨지 않았다.
    py_compile 은 import 를 실행하지 않아 못 잡는다. 여기서 목록으로 잡는다.
    """

    def test_deploy_list_covers_imports(self):
        import re
        root = GATEWAY_CONFIG.parent
        deploy = set(re.search(r"DEPLOY_FILES=\((.*?)\)",
                               (root / "run.sh").read_text(), re.S).group(1).split())
        needed = {p.relative_to(root).as_posix() for p in (root / "runtime").glob("*.py")}
        self.assertTrue(needed, "runtime 실행 모듈을 하나도 못 찾았다")
        self.assertFalse(needed - deploy, f"배포 목록에서 빠짐: {sorted(needed - deploy)}")

    def test_deploy_list_covers_core_imports_transitively(self):
        """`from core.stage import …` 는 위 정규식(`from (\\w+) import`)에 안 걸린다 — 점 앞에서 끊긴다.
        그래서 core/stage.py 를 배포 목록에서 빼도 위 테스트는 초록이었다 (변이로 확인). 로봇에서
        server.py 가 import 에러로 안 뜨는, 이 저장소에서 두 번 실제로 났던 그 사고다.

        core 는 앱 폴더의 링크로 보이고(../core), 로봇에는 core/ 가 진짜 디렉터리로 간다.
        core/stage.py 가 다시 core.ports 를 import 하므로 **전이적으로** 따라간다.
        """
        import re
        root = GATEWAY_CONFIG.parent
        deploy = set(re.search(r"DEPLOY_FILES=\((.*?)\)",
                               (root / "run.sh").read_text(), re.S).group(1).split())
        top_level = re.compile(r"^from core\.(\w+) import", re.M)   # 들여쓴 늦은 import 는 제외
        todo = [m for m in top_level.findall((root / "server.py").read_text())]
        self.assertTrue(todo, "server.py 가 core 를 하나도 import 하지 않는다 — 정규식이 깨졌거나 구조가 바뀌었다")
        needed, seen = {"core/__init__.py"}, set()
        while todo:
            mod = todo.pop()
            if mod in seen:
                continue
            seen.add(mod)
            needed.add(f"core/{mod}.py")
            todo += top_level.findall((root / "core" / f"{mod}.py").read_text())
        self.assertFalse(needed - deploy, f"배포 목록에서 빠짐: {sorted(needed - deploy)}")
        self.assertIn("stage", seen)     # 이 테스트가 실제로 stage 를 봤다
        self.assertIn("ports", seen)     # 그리고 stage 가 끌어오는 ports 까지 따라갔다

    def test_deploy_list_files_exist(self):
        root = GATEWAY_CONFIG.parent
        import re
        deploy = re.search(r"DEPLOY_FILES=\((.*?)\)",
                           (root / "run.sh").read_text(), re.S).group(1).split()
        for name in deploy:
            self.assertTrue((root / name).is_file(), name)


class PadOrderTest(unittest.TestCase):
    def test_state_preserves_pad_grid_order(self):
        """그리드 번호 = 목록 순서 스펙. sorted() 가 끼어들면 배치가 뒤섞인다 (실제 발생)."""
        grid = server.load_venue()["pad_grid"]
        st = State(server.MockBackend(), pad_allowlist=grid)
        self.assertEqual(st.pad_order, grid)
