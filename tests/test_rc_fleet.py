"""RcFleetBackend 테스트 — 가짜 시리얼 4대로 팬아웃·집계·동시성을 검증한다."""

import pathlib
import time
import unittest

from runtime import rc_fleet
from runtime.rc_backend import RcBackend, load_rc_map
from runtime.rc_fleet import RcFleetBackend, _short_name
from tests.test_rc_backend import FakeSerial

HERE = pathlib.Path(__file__).parent.parent
# 플릿 모드는 자기 카탈로그·다이얼 덤프를 쓴다(config/fleet/) — solo 의 것과 다르다.
MOTIONS = HERE / "config" / "fleet" / "motions.yaml"
# 2026-08-18 로봇 백업 k1_config 기준 앵커
KNOWN_A = "MimicNewWelcoming001A142"   # 뱅크 A, code 200 → slot 1
KNOWN_B = "MimicSnuCheer"              # 뱅크 B, code 203 → slot 4
KNOWN_B_SLOT = 4
KNOWN_NOTE_DUR = "MimicNewMacarena001A545"   # note "29.5s..."


class StampedSerial(FakeSerial):
    """run/fire 시각을 기록해 팬아웃 동시성을 잰다."""

    def run(self, slot, bank="A"):
        self.calls.append(("run_at", time.monotonic()))
        return super().run(slot, bank)

    def fire(self):
        self.calls.append(("fire_at", time.monotonic()))
        return super().fire()


def make_fleet(n=4, fail_names=(), serial_cls=FakeSerial):
    orig = rc_fleet.discover_ports
    rc_fleet.discover_ports = lambda: []
    try:
        fleet = RcFleetBackend(MOTIONS)
    finally:
        rc_fleet.discover_ports = orig
    for i in range(n):
        unit_name = f"rc-U{i + 1}"
        fleet.units[unit_name] = RcBackend(
            MOTIONS, serial=serial_cls(fail=unit_name in fail_names))
    return fleet


class TestFleet(unittest.TestCase):
    def test_short_name(self):
        self.assertEqual(
            _short_name("/dev/serial/by-id/usb-OpenTX_Radiomaster_Pocket_"
                        "Serial_Port_00000000001B-if00"), "rc-1B")

    def test_submit_fans_out_to_all(self):
        fleet = make_fleet(4)
        res = fleet.submit(KNOWN_A, "manual", "군무")
        self.assertTrue(res["ok"])
        self.assertIn("4/4대 발사", res["msg"])
        for unit in fleet.units.values():
            self.assertIn(("run", 1, "A"), unit.serial.calls)

    def test_partial_failure_reported(self):
        fleet = make_fleet(4, fail_names={"rc-U2"})
        res = fleet.submit(KNOWN_A, "manual", "")
        self.assertTrue(res["ok"])
        self.assertIn("3/4대 발사", res["msg"])
        self.assertIn("rc-U2", res["msg"])

    def test_all_fail_rejected(self):
        fleet = make_fleet(2, fail_names={"rc-U1", "rc-U2"})
        res = fleet.submit(KNOWN_A, "manual", "")
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "rejected")

    def test_no_units(self):
        fleet = make_fleet(0)
        res = fleet.submit(KNOWN_A, "manual", "")
        self.assertFalse(res["ok"])
        self.assertIn("라디오", res["msg"])
        self.assertEqual(fleet.status()["gateway"], "offline")

    def test_prepare_then_submit_fires_everywhere(self):
        fleet = make_fleet(3)
        self.assertTrue(fleet.prepare(KNOWN_B))
        res = fleet.submit(KNOWN_B, "manual", "dance")
        self.assertTrue(res["ok"])
        for unit in fleet.units.values():
            self.assertIn(("fire",), unit.serial.calls)

    def test_busy_blocks_second_command(self):
        fleet = make_fleet(2)
        self.assertTrue(fleet.submit(KNOWN_A, "manual", "")["ok"])
        res = fleet.submit(KNOWN_B, "manual", "")
        self.assertFalse(res["ok"])  # 대별 busy → 전 대 거부

    def test_stop_fans_out(self):
        fleet = make_fleet(3)
        fleet.submit(KNOWN_A, "manual", "")
        res = fleet.stop_motion("manual")
        self.assertTrue(res["ok"])
        self.assertIn("3/3대 정지", res["msg"])
        self.assertEqual(res["motion"], "Velocity")  # 정지 = locomotion 복귀
        for unit in fleet.units.values():
            self.assertIn(("vel",), unit.serial.calls)

    def test_motion_duration_is_max(self):
        fleet = make_fleet(2)
        single = RcBackend(MOTIONS, serial=FakeSerial())
        self.assertEqual(fleet.motion_duration(KNOWN_B),
                         single.motion_duration(KNOWN_B))

    def test_status_shape(self):
        fleet = make_fleet(3)
        st = fleet.status()
        self.assertEqual(st["gateway"], "ready")
        self.assertEqual(st["robot"]["total"], 3)
        self.assertEqual(st["robot"]["ready"], 3)
        self.assertEqual(len(st["robot"]["fleet"]), 3)
        for key in ("current_request", "stop_state", "stop_available", "last_event"):
            self.assertIn(key, st)

    def test_fanout_simultaneity(self):
        fleet = make_fleet(4, serial_cls=StampedSerial)
        fleet.submit(KNOWN_A, "manual", "")
        stamps = []
        for unit in fleet.units.values():
            stamps += [c[1] for c in unit.serial.calls if c[0] == "run_at"]
        self.assertEqual(len(stamps), 4)
        spread_ms = (max(stamps) - min(stamps)) * 1000
        self.assertLess(spread_ms, 50, f"발사 시차 {spread_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()


class FleetDialTest(unittest.TestCase):
    """플릿 모드의 다이얼 덤프(config/fleet/motions.yaml)가 solo 것과 다르다는 사실을 못박는다."""

    def test_known_slots(self):
        mapping, _ = load_rc_map(MOTIONS)
        self.assertEqual((mapping[KNOWN_A]["bank"], mapping[KNOWN_A]["slot"]), ("A", 1))
        self.assertEqual((mapping[KNOWN_B]["bank"], mapping[KNOWN_B]["slot"]), ("B", KNOWN_B_SLOT))

    def test_duration_from_note_and_cooldown(self):
        mapping, cooldowns = load_rc_map(MOTIONS)
        self.assertAlmostEqual(mapping[KNOWN_NOTE_DUR]["duration_sec"], 29.5)
        self.assertEqual(cooldowns.get("MimicBadChestpopVer2"), 8.0)


class FleetTlmTimeoutTest(unittest.TestCase):
    def test_a_fleet_waits_less_for_telemetry_than_a_single_radio(self):
        """1.5s(단일)와 0.6s(플릿)는 통일하지 않고 모드가 고른다. 통일하면 둘 중 하나의 실측이 사라진다."""
        from runtime.rc_serial import RcSerial, TLM_TIMEOUT_S
        self.assertEqual(RcSerial.__init__.__defaults__[-1], TLM_TIMEOUT_S)
        self.assertEqual(TLM_TIMEOUT_S, 1.5)
        self.assertEqual(rc_fleet.FLEET_TLM_TIMEOUT_S, 0.6)

    def test_fleet_units_are_built_with_the_fleet_timeout(self):
        made = []

        class Recorder(FakeSerial):
            def __init__(self, port_pattern=None, tlm_timeout_s=None):
                super().__init__()
                made.append((port_pattern, tlm_timeout_s))

        orig = (rc_fleet.discover_ports, rc_fleet.RcSerial)
        rc_fleet.discover_ports = lambda: ["/dev/serial/by-path/pci-0:usb-0:1.2:1.0"]
        rc_fleet.RcSerial = Recorder
        try:
            RcFleetBackend(MOTIONS)
        finally:
            rc_fleet.discover_ports, rc_fleet.RcSerial = orig
        self.assertEqual(made, [("/dev/serial/by-path/pci-0:usb-0:1.2:1.0", 0.6)])
