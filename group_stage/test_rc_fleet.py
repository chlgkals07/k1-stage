"""RcFleetBackend 테스트 — 가짜 시리얼 4대로 팬아웃·집계·동시성을 검증한다."""

import pathlib
import time
import unittest

import rc_fleet
from rc_backend import RcBackend
from rc_fleet import RcFleetBackend, _short_name
from test_rc_backend import KNOWN_A, KNOWN_B, FakeSerial

HERE = pathlib.Path(__file__).parent
MOTIONS = HERE / "motions.yaml"


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
