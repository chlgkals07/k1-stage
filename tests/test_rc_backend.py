"""RcBackend 단위 테스트 — 시리얼은 가짜, rc_list 는 실제 motions.yaml 을 쓴다."""

import pathlib
import time
import unittest

from runtime import rc_backend
from runtime.rc_backend import RcBackend, load_rc_map

HERE = pathlib.Path(__file__).parent.parent
MOTIONS = HERE / "config" / "solo" / "motions.yaml"

# 이번 무대 RC 배포 목표 앵커. 최신 로봇 selector 백업으로 실기 전에 대조한다.
KNOWN_A = "MimicBowNavel"               # 뱅크 A, code 200 → slot 1
KNOWN_B = "MimicNewSnuCheerHeadShort"   # 뱅크 B, code 202 → slot 3
KNOWN_B_SLOT = 3
NOT_ON_DIAL = "MimicBillyJean"


class FakeSerial:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.last_error = ""

    def _res(self):
        return {"ok": not self.fail, "msg": "가짜 실패" if self.fail else ""}

    def ping(self):
        self.calls.append(("ping",))
        return self._res()

    def run(self, slot, bank="A"):
        self.calls.append(("run", slot, bank))
        return self._res()

    def prep(self, slot, bank):
        self.calls.append(("prep", slot, bank))
        return self._res()

    def fire(self):
        self.calls.append(("fire",))
        return self._res()

    def stop_pulse(self):
        self.calls.append(("stop",))
        return self._res()

    def vel(self):
        self.calls.append(("vel",))
        return self._res()

    def tlm(self):
        return {"ok": True, "lq": "99", "rssi": "-40"}

    def close(self):
        self.calls.append(("close",))


def make_backend(fail=False):
    return RcBackend(MOTIONS, serial=FakeSerial(fail=fail))


class TestRcMap(unittest.TestCase):
    def test_known_slots(self):
        mapping, cooldowns = load_rc_map(MOTIONS)
        self.assertEqual(mapping[KNOWN_A]["bank"], "A")
        self.assertEqual(mapping[KNOWN_A]["slot"], 1)
        self.assertEqual(mapping[KNOWN_B]["bank"], "B")
        self.assertEqual(mapping[KNOWN_B]["slot"], KNOWN_B_SLOT)

    def test_default_duration_without_clip_or_note(self):
        mapping, _ = load_rc_map(MOTIONS)
        self.assertEqual(mapping[KNOWN_A]["duration_sec"],
                         rc_backend.DEFAULT_DURATION_SEC)

    def test_cooldowns_loaded(self):
        _, cooldowns = load_rc_map(MOTIONS)
        self.assertEqual(cooldowns, {})


class TestRcBackend(unittest.TestCase):
    def test_submit_known_motion(self):
        b = make_backend()
        res = b.submit(KNOWN_A, "manual", "test")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "queued")
        self.assertEqual(b.serial.calls, [("run", 1, "A")])
        self.assertTrue(res["request_id"].startswith("rc-"))

    def test_submit_unknown_rejected(self):
        b = make_backend()
        res = b.submit(NOT_ON_DIAL, "manual", "test")  # 카탈로그엔 있지만 다이얼엔 없음
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(b.serial.calls, [])

    def test_busy_blocks_second_submit(self):
        b = make_backend()
        self.assertTrue(b.submit(KNOWN_A, "manual", "")["ok"])
        res = b.submit(KNOWN_B, "manual", "")
        self.assertFalse(res["ok"])
        self.assertIn("실행 중", res["msg"])
        # 완료 추정 시각이 지나면 다시 허용
        b._busy_until = time.monotonic() - 1
        self.assertTrue(b.submit(KNOWN_B, "manual", "")["ok"])

    def test_cooldown(self):
        b = make_backend()
        b._cooldowns[KNOWN_A] = 5.0
        self.assertTrue(b.submit(KNOWN_A, "manual", "")["ok"])
        b._busy_until = time.monotonic() - 1
        res = b.submit(KNOWN_A, "manual", "")
        self.assertFalse(res["ok"])
        self.assertIn("cooldown", res["msg"])

    def test_prepare_then_submit_fires(self):
        b = make_backend()
        self.assertTrue(b.prepare(KNOWN_B))
        res = b.submit(KNOWN_B, "manual", "dance")
        self.assertTrue(res["ok"])
        self.assertEqual(b.serial.calls, [("prep", KNOWN_B_SLOT, "B"), ("fire",)])

    def test_prepare_then_submit_other_runs(self):
        b = make_backend()
        self.assertTrue(b.prepare(KNOWN_B))
        res = b.submit(KNOWN_A, "manual", "")
        self.assertTrue(res["ok"])
        self.assertEqual(b.serial.calls[-1], ("run", 1, "A"))

    def test_expired_prep_falls_back_to_run(self):
        b = make_backend()
        self.assertTrue(b.prepare(KNOWN_B))
        b._prepared = (KNOWN_B, time.monotonic() - 1)  # 만료
        b.submit(KNOWN_B, "manual", "")
        self.assertEqual(b.serial.calls[-1], ("run", KNOWN_B_SLOT, "B"))

    def test_serial_failure_rejected(self):
        b = make_backend(fail=True)
        res = b.submit(KNOWN_A, "manual", "")
        self.assertFalse(res["ok"])
        # 실패한 발사는 busy 를 잡지 않는다
        self.assertEqual(b._busy_left(), 0.0)

    def test_stop_motion_clears_busy(self):
        b = make_backend()
        b.submit(KNOWN_A, "manual", "")
        res = b.stop_motion("manual")
        self.assertTrue(res["ok"])
        # 정지는 locomotion(Velocity) 복귀다 — ReadyPose 는 균형 없는 고정 자세
        self.assertEqual(res["motion"], "Velocity")
        self.assertEqual(b._busy_left(), 0.0)
        self.assertIn(("vel",), b.serial.calls)

    def test_status_shape(self):
        b = make_backend()
        st = b.status()
        for key in ("gateway", "robot", "current_request", "stop_state",
                    "stop_available", "last_event"):
            self.assertIn(key, st)
        # UI(canSubmit)가 아는 라벨로 보고해야 실행 버튼이 잠기지 않는다
        self.assertEqual(st["gateway"], "ready")
        self.assertEqual(st["stop_state"], "Velocity")

    def test_obs_verification(self):
        from runtime.rc_backend import _model_us, _parse_obs, _verify_obs
        entry = {"slot": 1, "bank": "A"}
        # 정상 관측: slot1 A → ch11=988, ch5=988, code 4 유지
        line = "OK RUN 1 ch5=988 ch6=2012 ch7=2012 ch11=988"
        verdict, ok = _verify_obs(entry, _parse_obs(line))
        self.assertTrue(ok, verdict)
        # 다이얼 값이 어긋난 관측 → 불일치 판정
        bad = "OK RUN 1 ch5=988 ch6=2012 ch7=2012 ch11=1100"
        verdict, ok = _verify_obs(entry, _parse_obs(bad))
        self.assertFalse(ok)
        self.assertIn("불일치", verdict)
        # 관측값 없는 구버전 응답은 실패로 치지 않는다
        verdict, ok = _verify_obs(entry, _parse_obs("OK RUN 1"))
        self.assertTrue(ok)
        self.assertEqual(_model_us(-100), 988)
        self.assertEqual(_model_us(100), 2012)

    def test_connect_check(self):
        ok, msg = make_backend().connect_check()
        self.assertTrue(ok)
        bad = make_backend(fail=True)
        ok, msg = bad.connect_check()
        self.assertFalse(ok)
        self.assertTrue(msg)


class TestServerIntegration(unittest.TestCase):
    def test_state_pad_allowed_with_rc_backend(self):
        import yaml
        import app
        b = make_backend()
        cfg = yaml.safe_load(open(HERE / "config" / "solo" / "gateway_config.yaml"))
        pad_list = app.load_venue()["pad_grid"]
        st = app.State(b, ready_only=True, pad_allowlist=pad_list)
        # UI 동일성: RC 백엔드여도 패드 목록은 primary 와 동일 (12개 그대로)
        self.assertEqual(st.pad_allowed, set(pad_list) & set(st.by_state))
        self.assertEqual(len(st.pad_allowed), len(pad_list))

    def test_set_rc_mode_toggle(self):
        import app

        made = []
        real_rc_backend = app.RcBackend

        def factory(*a, **k):
            b = RcBackend(MOTIONS, serial=FakeSerial())
            made.append(b)
            return b

        st = app.State(app.MockBackend())
        app.RcBackend = factory
        try:
            out = st.set_rc_mode(True)
            self.assertTrue(out["ok"], out)
            self.assertEqual(st.backend.name, "rc")
            self.assertEqual(st.status()["backend"], "rc")
            # 실행이 RC 로 가는지
            res = st.backend.submit(KNOWN_A, "manual", "")
            self.assertTrue(res["ok"])
            # 복귀
            out = st.set_rc_mode(False)
            self.assertTrue(out["ok"])
            self.assertEqual(st.backend.name, "mock")
            self.assertIn(("close",), made[0].serial.calls)  # 포트 해제됨
        finally:
            app.RcBackend = real_rc_backend

    def test_set_rc_mode_connect_failure_keeps_backend(self):
        import app
        real_rc_backend = app.RcBackend
        app.RcBackend = lambda *a, **k: RcBackend(MOTIONS, serial=FakeSerial(fail=True))
        st = app.State(app.MockBackend())
        try:
            out = st.set_rc_mode(True)
            self.assertFalse(out["ok"])
            self.assertTrue(out["msg"])
            self.assertEqual(st.backend.name, "mock")  # 실패 시 백엔드 불변
        finally:
            app.RcBackend = real_rc_backend

    def test_dance_autostop_without_display(self):
        # display 종료 신호가 없어도 추정 길이 + 여유 뒤 무대가 스스로 내려간다
        import app

        class DurBackend:
            name = "rc"

            def submit(self, motion, source, reason):
                return {"ok": True, "status": "queued", "motion": motion,
                        "request_id": "rc-1", "msg": ""}

            def motion_duration(self, motion):
                return 0.2

            def stop_motion(self, source, reason=""):
                return {"ok": True, "status": "queued", "motion": "ReadyPose",
                        "request_id": None, "msg": ""}

            def status(self):
                return {"gateway": "ready"}

            def stop(self):
                pass

        st = app.State(DurBackend())
        old = (app.State.DANCE_LEAD_SEC, app.State.DANCE_AUTOSTOP_MARGIN_SEC)
        app.State.DANCE_LEAD_SEC = 0.2
        app.State.DANCE_AUTOSTOP_MARGIN_SEC = 0.2
        try:
            res = st.start_dance(preset={"motion": KNOWN_B, "media": "",
                                         "offset_ms": 0, "seek": 0, "volume": 100})
            self.assertTrue(res["ok"], res)
            self.assertEqual(st.effective_stage(), "dance")
            time.sleep(1.2)  # lead 0.2 + duration 0.2 + margin 0.2 + 여유
            self.assertEqual(st.effective_stage(), "idle")
        finally:
            (app.State.DANCE_LEAD_SEC,
             app.State.DANCE_AUTOSTOP_MARGIN_SEC) = old
            st.stop_dance()

    def test_dance_prep_hook_fires_before_motion(self):
        import app
        events = []

        class HookBackend:
            name = "rc"

            def submit(self, motion, source, reason):
                events.append(("submit", motion, time.monotonic()))
                return {"ok": True, "status": "queued", "motion": motion,
                        "request_id": "rc-1", "msg": ""}

            def prepare(self, motion):
                events.append(("prepare", motion, time.monotonic()))
                return True

            def stop_motion(self, source, reason=""):
                return {"ok": True, "status": "queued", "motion": "ReadyPose",
                        "request_id": None, "msg": ""}

            def status(self):
                return {"gateway": "ready"}

            def stop(self):
                pass

        st = app.State(HookBackend())
        old_lead = app.State.DANCE_LEAD_SEC
        app.State.DANCE_LEAD_SEC = 0.3  # prep 지연 = max(0, 0.3-1.5) = 즉시
        try:
            res = st.start_dance(preset={
                "motion": KNOWN_B, "media": "", "offset_ms": 0,
                "seek": 0, "volume": 100})
            self.assertTrue(res["ok"], res)
            time.sleep(0.8)
        finally:
            app.State.DANCE_LEAD_SEC = old_lead
            st.stop_dance()
        kinds = [e[0] for e in events]
        self.assertEqual(kinds, ["prepare", "submit"])
        self.assertEqual(events[0][1], KNOWN_B)


if __name__ == "__main__":
    unittest.main()
