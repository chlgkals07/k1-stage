"""RcSerial 테스트 — pty 루프백으로 가짜 K1PC 응답기를 세운다."""

import os
import pty
import re
import threading
import unittest

from runtime.rc_serial import RcSerial


class FakeRadio(threading.Thread):
    """pty master 쪽에서 K1PC.lua v2 프로토콜을 흉내 낸다."""

    def __init__(self, master_fd):
        super().__init__(daemon=True)
        self.fd = master_fd
        self.prepared = False
        self.silent = False   # True 면 PING 외 무응답 (타임아웃 테스트)
        self._buf = b""
        self.stopped = False

    def _reply(self, text):
        os.write(self.fd, (text + "\n").encode())

    def run(self):
        while not self.stopped:
            try:
                chunk = os.read(self.fd, 256)
            except OSError:
                return
            if not chunk:
                return
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                self.handle(line.decode().strip())

    def handle(self, line):
        if line == "PING":
            self._reply("PONG")
            return
        if self.silent:
            return
        m = re.match(r"RUN (\d+)\s*([AB]?)", line)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:
                self._reply(f"OK RUN {n}")
            else:
                self._reply("ERR ARG")
            return
        m = re.match(r"PREP (\d+) ([AB])", line)
        if m:
            self.prepared = True
            self._reply("OK PREP")
            return
        if line == "FIRE":
            if self.prepared:
                self.prepared = False
                self._reply("OK FIRE")
            else:
                self._reply("ERR NOPREP")
            return
        if line == "STOP":
            self._reply("OK STOP")
            return
        if line == "DAMP":
            self._reply("OK DAMP")
            return
        if line == "TLM":
            self._reply("TLM st=IDLE lq=97 rssi=-42")
            return
        if line == "CHK":
            self._reply("CHK ch5=988 ch6=1500 ch7=2012 ch11=1009")
            return
        self._reply("ERR CMD")


class TestRcSerial(unittest.TestCase):
    def setUp(self):
        self.master, self.slave_keeper = pty.openpty()
        self.slave_path = os.ttyname(self.slave_keeper)
        # slave fd 를 하나 살려 둬야 master 가 EOF 를 보지 않는다 —
        # 닫으면 FakeRadio 의 os.read 가 즉시 EOF 로 끝난다.
        self.radio = FakeRadio(self.master)
        self.radio.start()
        self.rc = RcSerial(port_pattern=self.slave_path)

    def tearDown(self):
        self.rc.close()
        self.radio.stopped = True
        # macOS에서는 다른 스레드가 read 중인 master를 먼저 닫으면 close가 멈출 수 있다.
        # 마지막 slave를 닫아 read를 깨운 뒤 스레드 종료를 확인하고 master를 닫는다.
        try:
            os.close(self.slave_keeper)
        except OSError:
            pass
        self.radio.join(timeout=1)
        try:
            os.close(self.master)
        except OSError:
            pass

    def test_ping(self):
        self.assertTrue(self.rc.ping()["ok"])

    def test_run_ok(self):
        res = self.rc.run(3, "B")
        self.assertTrue(res["ok"], res)
        self.assertIn("OK RUN 3", res["line"])

    def test_run_rejected(self):
        res = self.rc.run(99)
        self.assertFalse(res["ok"])
        self.assertIn("거부", res["msg"])

    def test_prep_fire_roundtrip(self):
        self.assertTrue(self.rc.prep(2, "B")["ok"])
        self.assertTrue(self.rc.fire()["ok"])

    def test_fire_without_prep(self):
        res = self.rc.fire()
        self.assertFalse(res["ok"])

    def test_stop_damp(self):
        self.assertTrue(self.rc.stop_pulse()["ok"])
        self.assertTrue(self.rc.damp()["ok"])

    def test_tlm_parsed(self):
        res = self.rc.tlm()
        self.assertTrue(res["ok"])
        self.assertEqual(res["lq"], "97")
        self.assertEqual(res["rssi"], "-42")

    def test_chk_parsed(self):
        res = self.rc.chk()
        self.assertTrue(res["ok"])
        self.assertEqual(res["ch11"], "1009")
        self.assertEqual(res["ch5"], "988")

    def test_timeout_returns_error(self):
        self.radio.silent = True
        res = self.rc._command("RUN 3 A", ("OK RUN",), timeout_s=0.5)
        self.assertFalse(res["ok"])
        self.assertIn("시간 초과", res["msg"])

    def test_missing_port(self):
        rc = RcSerial(port_pattern="/dev/does-not-exist-*")
        try:
            res = rc.ping()
            self.assertFalse(res["ok"])
            self.assertIn("포트", res["msg"])
        finally:
            rc.close()


if __name__ == "__main__":
    unittest.main()
