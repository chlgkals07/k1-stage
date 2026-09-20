import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import server
from server import State

GATEWAY_CONFIG = Path(__file__).parent / "gateway_config.yaml"


class Backend:
    name = "relay"
    api_allowlist = {"MimicWaveHand", "MimicBowNavel", "MimicBadChestpopVer2"}

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
    def test_state_rejects_non_wave_llm_motion(self):
        state = State(Backend(), ready_only=True, llm_allowlist={"MimicWaveHand"})
        self.assertEqual(state.allowed, {"MimicWaveHand"})
        out = state.play("MimicBowNavel", source="llm")
        self.assertFalse(out["ok"])

    def test_stop_bypasses_llm_allowlist_and_is_always_manual(self):
        backend = Backend()
        state = State(backend, ready_only=True, llm_allowlist={"MimicWaveHand"})
        out = state.stop_motion("운영자 정지")
        self.assertTrue(out["ok"])
        self.assertEqual(out["motion"], "ReadyPose")
        # source 는 서버가 강제한다. LLM 이 정지를 호출할 수 있어서는 안 된다.
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

    def test_llm_allowlist_is_subset_of_api_allowlist(self):
        policy = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]
        self.assertTrue(set(policy["llm_allowlist"]) <= set(policy["api_allowlist"]))

    def test_llm_exclusion_boundary(self):
        """LLM 제외 경계 (2026-08-13 사용자 확정): 회전·긴 댄스 일부·미확인·이동은 제외.
        예외로 PushUp/JazzHands 는 desc 게이팅(명시 요청 전용)으로 포함한다."""
        policy = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]
        llm = set(policy["llm_allowlist"])
        for state in ("MimicCrossedArmsTurn", "MimicDanceBasicTurnV1360RLoopFast003A325",
                      "MimicDanceBlindingLights", "MimicDanceClick", "MimicDanceFloss",
                      "MimicShuffleDance",
                      "MimicSnuCheer", "MimicStraykidsThisAndThat", "MimicBow",
                      "MimicBossDustBrushingNew", "MimicBossDustBrushingR001A036",
                      "MimicGuapIntroP2", "MimicGuapVer2"):
            self.assertNotIn(state, llm, state)
        # 검증된 3개 + 명시 요청 전용 2개는 포함
        for state in ("MimicWaveHand", "MimicBowNavel", "MimicBadChestpopVer2",
                      "MimicPushUp", "MimicDanceJazzHands", "MimicCartwheel"):
            self.assertIn(state, llm)
        # 명시 요청 전용은 desc 에 그 조건이 적혀 있어야 한다 — 모델의 유일한 근거다
        _, by_state = server.load_catalog()
        for state in ("MimicPushUp", "MimicDanceJazzHands", "MimicCartwheel"):
            self.assertIn("지목해 요청할 때만", by_state[state]["desc"], state)

    def test_llm_allowlist_only_contains_llm_true_ready_catalog_entries(self):
        """llm_allowlist 에 넣어도 카탈로그가 llm:false/planned 면 enum 에 안 들어간다 —
        그 조합은 조용히 사라지므로 여기서 막는다."""
        _, by_state = server.load_catalog()
        policy = yaml.safe_load(GATEWAY_CONFIG.read_text())["policy"]
        for state in policy["llm_allowlist"]:
            m = by_state[state]
            self.assertTrue(m.get("llm"), f"{state}: llm flag false")
            self.assertEqual(m.get("status", "ready"), "ready", f"{state}: not ready")
            self.assertNotEqual(m.get("safety"), "restricted", state)


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
            "MimicNewRockOut002A487", "MimicGuapVer2"])

    def test_pad_has_no_duplicates(self):
        self.assertEqual(len(self.pad), len(set(self.pad)))

    def test_clips_are_all_known_states(self):
        """클립은 "최종 렌더만" 정책(2026-08-18) — 부분 존재가 정상이다.
        지키는 건 고아 방지뿐: 존재하는 클립은 전부 카탈로그 state 여야 한다."""
        for f in server.CLIPS.glob("*.mp4"):
            self.assertIn(f.stem, self.by_state, f.name)

    def test_pad_entries_are_ready(self):
        """학습·배포가 안 된 동작을 버튼으로 열면 눌렀을 때 실패한다."""
        for state in self.pad:
            self.assertEqual(self.by_state[state].get("status", "ready"), "ready", state)

    def test_restricted_still_never_reaches_llm(self):
        """패드에는 restricted 를 허용했지만 LLM 에는 여전히 안 나간다."""
        restricted = {m["state"] for m in self.items if m.get("safety") == "restricted"}
        self.assertFalse(restricted & set(self.policy["llm_allowlist"]))

    def test_llm_allowlist_unchanged(self):
        self.assertEqual(len(self.policy["llm_allowlist"]), 21)

    def _state(self):
        return State(Backend(), ready_only=True,
                     pad_allowlist=["MimicWaveHand", "MimicBowNavel"],
                     pad_llm_exclude=["MimicCartwheel"])

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
        """오타 하나로 카탈로그 밖 항목이 조용히 통과하지 않는다."""
        st = State(Backend(), ready_only=True, pad_allowlist=["NotARealMotion"])
        self.assertEqual(st.pad_allowed, set())


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
        local = {p.name for p in root.glob("*.py") if not p.name.startswith("test_")}
        source = (root / "server.py").read_text()
        pairs = re.findall(r"^from (\w+) import|^import (\w+)", source, re.M)
        needed = {f"{m}.py" for pair in pairs for m in pair if m and f"{m}.py" in local}
        self.assertTrue(needed, "의존 모듈을 하나도 못 찾았다 — 정규식이 깨졌다")
        self.assertFalse(needed - deploy, f"배포 목록에서 빠짐: {sorted(needed - deploy)}")

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
