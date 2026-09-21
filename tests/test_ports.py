"""ports — 백엔드 계약과 그 위에서 State 가 하는 일.

세 가지를 지킨다.

1. **적합성**: 백엔드가 Transport 모양을 갖고, 메서드 시그니처가 State 의 호출 방식과 맞는다.
   isinstance 는 이름의 존재만 보므로(hasattr 와 같은 강도) 시그니처는 여기서 따로 본다.
2. **능력 표**: 어느 백엔드가 어느 선택 능력을 가졌는지 못박는다. 예전엔 State 가 hasattr 로 물었고
   지금은 isinstance 다 — 같은 답이어야 한다. 백엔드가 능력을 슬쩍 얻거나 잃으면 무대 동작이 바뀐다
   (예: prepare 를 얻으면 갑자기 PREP 타이머가 걸린다).
3. **지뢰 제거**: UI 목록(패드·LLM)은 백엔드가 무엇을 갖든 같다. 예전엔 backend.api_allowlist 속성이
   있을 때만 State 가 교집합해서, RcBackend 는 그 속성이 **없어야만** 올바르게 동작했다.

하드웨어·네트워크에는 손대지 않는다.
"""

import inspect
import unittest
from pathlib import Path

import yaml

import app
from core.ports import MotionResult, SupportsDiscovery, SupportsDuration, SupportsPrepare, Transport
from runtime.rc_backend import RcBackend
from tests.test_rc_backend import FakeSerial
from runtime.relay_backend import RelayBackend
from runtime.robot_backend import RobotBackend

POLICY = yaml.safe_load(app.GATEWAY_CONFIG.read_text())["policy"]
GRID = app.load_venue()["pad_grid"]

# (prepare, duration, discovery) — 어느 백엔드가 어느 선택 능력을 가졌나
CAPS_EXPECTED = {
    "mock":  (False, False, False),
    "relay": (False, False, False),
    "robot": (False, False, False),
    "rc":    (True,  True,  False),     # connect_check 는 있지만 rescan 이 없다 — 단일 라디오라 재탐색할 게 없다
}


def backends():
    """{이름: 인스턴스}"""
    return {
        "mock": app.MockBackend(),
        "relay": RelayBackend("https://127.0.0.1:1", "token", POLICY["api_allowlist"]),
        "robot": RobotBackend(app.GATEWAY_CONFIG),
        "rc": RcBackend(app.CATALOG, serial=FakeSerial()),
    }


def params(fn):
    return list(inspect.signature(fn).parameters)


class ConformanceTest(unittest.TestCase):
    def test_every_backend_is_a_transport(self):
        for label, b in backends().items():
            with self.subTest(label):
                self.assertIsInstance(b, Transport)

    def test_the_methods_state_calls_have_the_shape_state_calls_them_with(self):
        """State 는 submit(motion, source, reason) 을 위치 인자로, stop_motion(source, reason) 을 부른다.
        이름이나 순서가 바뀌면 isinstance 는 통과하는데 무대에서 TypeError 가 난다."""
        for label, b in backends().items():
            with self.subTest(label):
                self.assertEqual(params(b.submit), ["motion", "source", "reason"])
                self.assertEqual(params(b.stop_motion), ["source", "reason"])
                self.assertEqual(inspect.signature(b.stop_motion).parameters["reason"].default, "")
                self.assertEqual(params(b.status), [])
                self.assertEqual(params(b.stop), [])

    def test_optional_capabilities_have_the_shape_state_calls_them_with(self):
        for label, b in backends().items():
            with self.subTest(label):
                if isinstance(b, SupportsPrepare):
                    self.assertEqual(params(b.prepare), ["motion"])
                if isinstance(b, SupportsDuration):
                    self.assertEqual(params(b.motion_duration), ["motion"])
                if isinstance(b, SupportsDiscovery):
                    self.assertEqual(params(b.rescan), [])
                    self.assertEqual(params(b.connect_check), [])

    def test_stop_motion_results_carry_what_motion_result_says(self):
        """MotionResult 는 타입 힌트라 런타임엔 안 검사된다. 문서가 실제를 말하는지만 본다.
        (하드웨어 없이 부를 수 있는 백엔드만: mock · rc 는 가짜 시리얼이다.)"""
        self.assertEqual(set(MotionResult.__required_keys__), {"ok", "msg"})
        for label in ("mock", "rc"):
            with self.subTest(label):
                out = backends()[label].stop_motion("test")
                self.assertTrue(MotionResult.__required_keys__ <= set(out), out)


class CapabilityMatrixTest(unittest.TestCase):
    def test_capabilities_are_pinned(self):
        got = {label: (isinstance(b, SupportsPrepare), isinstance(b, SupportsDuration),
                       isinstance(b, SupportsDiscovery)) for label, b in backends().items()}
        self.assertEqual(got, CAPS_EXPECTED)

    def test_isinstance_answers_exactly_what_hasattr_used_to(self):
        """리팩터의 핵심 주장: hasattr → isinstance 는 이 백엔드들에서 답이 같다."""
        for label, b in backends().items():
            with self.subTest(label):
                self.assertEqual(isinstance(b, SupportsPrepare), hasattr(b, "prepare"))
                self.assertEqual(isinstance(b, SupportsDuration), hasattr(b, "motion_duration"))
                self.assertEqual(isinstance(b, SupportsDiscovery),
                                 hasattr(b, "rescan") and hasattr(b, "connect_check"))


class ProtocolDefinitionTest(unittest.TestCase):
    """Protocol 이 무엇을 요구하는지 그 자체를 못박는다.

    백엔드들이 모양을 갖는지(ConformanceTest)와 별개다 — 정의에서 멤버 하나가 빠져도 지금 백엔드들은
    여전히 통과한다. 그러면 나중에 그 멤버 없이 만든 백엔드가 isinstance 를 통과하고, 실패는 State 가
    그 멤버를 부르는 시점(예: 종료 때의 backend.stop())에 무대 위에서 난다.
    """

    @staticmethod
    def fake(**members):
        """지정한 멤버만 가진 객체."""
        return type("Fake", (), members)()

    def test_transport_requires_every_member_state_uses(self):
        every = {"name": "x", "submit": lambda *a: {}, "stop_motion": lambda *a: {},
                 "status": lambda: {}, "stop": lambda: None}
        self.assertIsInstance(self.fake(**every), Transport)
        for missing in every:
            with self.subTest(missing):
                partial = {k: v for k, v in every.items() if k != missing}
                self.assertNotIsInstance(self.fake(**partial), Transport)

    def test_discovery_needs_both_halves(self):
        """rescan 만 있거나 connect_check 만 있으면 재탐색 대상이 아니다. solo 의 RcBackend 는
        connect_check 만 있어서(단일 라디오) 대상이 아니고, 이것이 그 경계다."""
        self.assertIsInstance(self.fake(rescan=lambda: [], connect_check=lambda: (True, "")), SupportsDiscovery)
        self.assertNotIsInstance(self.fake(rescan=lambda: []), SupportsDiscovery)
        self.assertNotIsInstance(self.fake(connect_check=lambda: (True, "")), SupportsDiscovery)

    def test_the_other_capabilities_are_one_method_each(self):
        self.assertIsInstance(self.fake(prepare=lambda m: True), SupportsPrepare)
        self.assertNotIsInstance(self.fake(), SupportsPrepare)
        self.assertIsInstance(self.fake(motion_duration=lambda m: None), SupportsDuration)
        self.assertNotIsInstance(self.fake(), SupportsDuration)


class UiListsDoNotDependOnTheBackendTest(unittest.TestCase):
    """지뢰 제거. 관객 패드 목록은 정책과 venue 에서만 온다."""

    def state(self, backend):
        return app.State(backend, ready_only=True, pad_allowlist=GRID,
                            api_allowlist=POLICY["api_allowlist"])

    def test_lists_are_identical_whatever_the_backend_is(self):
        """RC 로 토글해도 패드 12개가 그대로여야 한다 (2026-08-18 사용자 확정)."""
        base = self.state(app.MockBackend())
        self.assertEqual(len(base.pad_order), 12)
        for label, b in backends().items():
            with self.subTest(label):
                st = self.state(b)
                self.assertEqual(st.pad_order, base.pad_order)
                self.assertEqual(st.pad_allowed, base.pad_allowed)
                self.assertEqual(st.allowed, base.allowed)

    def test_a_backend_api_allowlist_attribute_is_ignored(self):
        """예전엔 이 속성이 State 의 목록을 잘랐다 — 그래서 누가 일관성을 위해 RcBackend 에 추가하면
        관객 패드가 조용히 줄어들었다. 이제 백엔드가 뭐라고 하든 목록은 그대로다."""
        class Lying(app.MockBackend):
            api_allowlist = {"MimicSquat"}

        self.assertEqual(self.state(Lying()).pad_order, self.state(app.MockBackend()).pad_order)
        self.assertEqual(self.state(Lying()).allowed, self.state(app.MockBackend()).allowed)

    def test_the_policy_still_caps_the_lists(self):
        """자르는 일은 그대로다. 출처가 백엔드가 아니라 정책이 됐을 뿐이다."""
        st = app.State(app.MockBackend(), pad_allowlist=["MimicBowNavel", "MimicSquat"],
                          api_allowlist=["MimicBowNavel"])
        self.assertEqual((st.pad_order, st.pad_allowed), (["MimicBowNavel"], {"MimicBowNavel"}))
        st = app.State(app.MockBackend(), api_allowlist=["MimicBowNavel"])
        self.assertTrue(st.allowed <= {"MimicBowNavel"})

    def test_without_a_policy_nothing_is_capped(self):
        """정책을 모르는 호출(State(MockBackend()) 를 쓰는 옛 테스트들)은 옛 동작 그대로다."""
        st = app.State(app.MockBackend(), pad_allowlist=["MimicBowNavel", "MimicSquat"])
        self.assertEqual(st.pad_order, ["MimicBowNavel", "MimicSquat"])

    def test_a_pad_item_outside_the_api_allowlist_cannot_be_pressed_by_the_audience(self):
        """교집합이 실제로 관객 경로를 막는다: 목록에서 빠지는 것이 아니라 요청이 거부된다."""
        st = app.State(app.MockBackend(), pad_allowlist=["MimicBowNavel", "MimicSquat"],
                          api_allowlist=["MimicBowNavel"])
        self.assertTrue(st.play("MimicBowNavel", source="pad")["ok"])
        out = st.play("MimicSquat", source="pad")
        self.assertFalse(out["ok"])
        self.assertIn("관객", out["msg"])


class Capable(app.MockBackend):
    """prepare 와 motion_duration 을 가진 백엔드 (RC 계열의 모양)."""

    def __init__(self, duration=None):
        self.duration = duration
        self.prepared = []

    def prepare(self, motion):
        self.prepared.append(motion)
        return True

    def motion_duration(self, motion):
        return self.duration


class StartDanceUsesCapabilitiesTest(unittest.TestCase):
    """능력을 가진 백엔드만 PREP 타이머를 받고, 동작 길이가 자동 종료를 늘린다."""

    PRESET = {"motion": "MimicWaveHand", "media": "", "offset_ms": 0, "media_len_sec": 10}

    def start(self, backend):
        st = app.State(backend)
        out = st.start_dance(preset=dict(self.PRESET))
        self.assertTrue(out["ok"], out)
        self.addCleanup(st.stop_dance)
        return st

    def test_a_backend_with_prepare_gets_a_prep_timer(self):
        self.assertIsNotNone(self.start(Capable())._dance_prep_timer)

    def test_a_backend_without_prepare_does_not(self):
        self.assertIsNone(self.start(app.MockBackend())._dance_prep_timer)

    def test_a_longer_motion_extends_the_autostop(self):
        base = self.start(app.MockBackend())._dance_autostop_timer.interval
        longer = self.start(Capable(duration=40.0))._dance_autostop_timer.interval
        self.assertAlmostEqual(longer - base, 40.0 - 10.0, delta=0.2)   # max(40, 10) 대 max(0, 10)

    def test_an_unknown_or_shorter_motion_does_not_shrink_it(self):
        """영상·동작 중 긴 쪽 기준이다. 모르면(None) 영상 길이로 떨어진다."""
        base = self.start(app.MockBackend())._dance_autostop_timer.interval
        for dur in (None, 3.0):
            with self.subTest(dur):
                st = self.start(Capable(duration=dur))
                self.assertAlmostEqual(st._dance_autostop_timer.interval, base, delta=0.2)


if __name__ == "__main__":
    unittest.main()
