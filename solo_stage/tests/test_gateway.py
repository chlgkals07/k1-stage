import time
import unittest

from runtime.gateway import Gateway, RobotSnapshot


def ready_snapshot(active="Velocity"):
    return RobotSnapshot(active_mode=active, authority="API", heartbeat_valid=True,
                         request_available=True, received_at=1.0)


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway({"MimicWaveHand"}, entry_timeout_sec=5)
        # Velocity/ReadyPose 는 로봇에 실재하는 control state 다. allowlist 에는 넣지 않는다.
        self.gateway.set_robot_modes({"MimicWaveHand", "Velocity", "ReadyPose"})

    def test_rejects_without_api_arm(self):
        self.gateway.update_status(RobotSnapshot(authority="MANUAL"))
        out = self.gateway.submit("MimicWaveHand", "manual")
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "rejected")

    def test_lifecycle_and_single_request(self):
        self.gateway.update_status(ready_snapshot())
        queued = self.gateway.submit("MimicWaveHand", "manual")
        self.assertTrue(queued["ok"])
        request = self.gateway.next_dispatch()
        self.assertEqual(request.motion, "MimicWaveHand")
        self.assertFalse(self.gateway.submit("MimicWaveHand", "manual")["ok"])
        self.gateway.service_result(request.request_id, True, "accepted")
        self.gateway.update_status(ready_snapshot("MimicWaveHand"))
        self.assertEqual(self.gateway.status()["gateway"], "executing")
        self.gateway.update_status(ready_snapshot("Velocity"))
        self.assertEqual(self.gateway.status()["gateway"], "ready")
        repeated = self.gateway.submit("MimicWaveHand", "manual")
        self.assertTrue(repeated["ok"])

    def test_rejects_unknown_robot_mode(self):
        self.gateway.update_status(ready_snapshot())
        out = self.gateway.submit("MimicBowNavel", "manual")
        self.assertFalse(out["ok"])
        self.assertIn("허용", out["msg"])

    def _start_motion(self):
        """WaveHand 를 executing 까지 진행시킨다."""
        self.gateway.update_status(ready_snapshot())
        self.gateway.submit("MimicWaveHand", "manual")
        request = self.gateway.next_dispatch()
        self.gateway.service_result(request.request_id, True, "accepted")
        self.gateway.update_status(ready_snapshot("MimicWaveHand"))
        self.assertEqual(self.gateway.status()["gateway"], "executing")
        return request

    def test_stop_preempts_running_motion(self):
        self._start_motion()
        out = self.gateway.stop_motion("manual", "운영자 정지")
        self.assertTrue(out["ok"])
        self.assertEqual(out["motion"], "Velocity")
        self.assertEqual(self.gateway.status()["gateway"], "stopping")
        # 선점된 요청은 interrupted 로 끝나고, 정지 요청이 locomotion 을 향한다.
        request = self.gateway.next_dispatch()
        self.assertEqual(request.motion, "Velocity")
        self.assertTrue(request.is_stop)

    def test_stop_passes_when_request_unavailable(self):
        """Mimic 실행 중 api_request_available 이 내려가도 정지는 통과해야 한다."""
        self.gateway.update_status(RobotSnapshot(
            active_mode="MimicWaveHand", authority="API", heartbeat_valid=True,
            request_available=False, received_at=1.0))
        self.assertFalse(self.gateway.submit("MimicWaveHand", "manual")["ok"])
        self.assertTrue(self.gateway.stop_motion("manual")["ok"])

    def test_stop_requires_api_authority(self):
        self.gateway.update_status(RobotSnapshot(authority="MANUAL"))
        out = self.gateway.stop_motion("manual")
        self.assertFalse(out["ok"])

    def test_stop_when_idle_is_allowed(self):
        self.gateway.update_status(ready_snapshot())
        self.assertTrue(self.gateway.stop_motion("manual")["ok"])

    def test_stop_rejected_when_robot_lacks_stop_state(self):
        self.gateway.set_robot_modes({"MimicWaveHand"})  # Velocity 없음
        self.gateway.update_status(ready_snapshot())
        out = self.gateway.stop_motion("manual")
        self.assertFalse(out["ok"])
        self.assertIn("Velocity", out["msg"])

    def test_stop_goes_to_locomotion_not_ready_pose(self):
        """정지는 균형 정책(Velocity)으로 보낸다 — ReadyPose 는 균형 없는 고정 자세다."""
        self.gateway.update_status(ready_snapshot("MimicWaveHand"))
        self.assertEqual(self.gateway.stop_motion("manual")["motion"], "Velocity")
        self.assertEqual(self.gateway.status()["stop_state"], "Velocity")

    def test_stop_from_damping_uses_entry_state(self):
        """Damping 에서만 예외 — 상태기계상 ReadyPose 말고는 나갈 길이 없다."""
        self.gateway.update_status(ready_snapshot("Damping"))
        self.assertEqual(self.gateway.stop_motion("manual")["motion"], "ReadyPose")
        # 로봇 상태를 아직 못 받았을 때(부팅 직후)도 진입부터 되게 한다.
        fresh = Gateway({"MimicWaveHand"})
        self.assertEqual(fresh._stop_target_locked(), "ReadyPose")

    def test_stop_attempted_before_mode_list_loads(self):
        gateway = Gateway({"MimicWaveHand"})  # set_robot_modes 호출 전
        gateway.update_status(ready_snapshot())
        self.assertFalse(gateway.submit("MimicWaveHand", "manual")["ok"])
        self.assertTrue(gateway.stop_motion("manual")["ok"])

    def test_cooldown_blocks_then_expires(self):
        gateway = Gateway({"MimicWaveHand"}, cooldowns={"MimicWaveHand": 0.05})
        gateway.set_robot_modes({"MimicWaveHand", "Velocity", "ReadyPose"})
        gateway.update_status(ready_snapshot())
        request = gateway.submit("MimicWaveHand", "manual")
        gateway.next_dispatch()
        gateway.service_result(request["request_id"], True, "accepted")
        gateway.update_status(ready_snapshot("MimicWaveHand"))
        gateway.update_status(ready_snapshot("Velocity"))  # completed
        blocked = gateway.submit("MimicWaveHand", "manual")
        self.assertFalse(blocked["ok"])
        self.assertIn("초 뒤에", blocked["msg"])
        time.sleep(0.06)
        gateway.update_status(ready_snapshot("Velocity"))
        self.assertTrue(gateway.submit("MimicWaveHand", "manual")["ok"])

    def test_cooldown_does_not_block_stop(self):
        gateway = Gateway({"MimicWaveHand"}, cooldowns={"MimicWaveHand": 60})
        gateway.set_robot_modes({"MimicWaveHand", "Velocity", "ReadyPose"})
        gateway.update_status(ready_snapshot())
        request = gateway.submit("MimicWaveHand", "manual")
        gateway.next_dispatch()
        gateway.service_result(request["request_id"], True, "accepted")
        gateway.update_status(ready_snapshot("MimicWaveHand"))
        gateway.stop_motion("manual")  # interrupted -> cooldown 시작
        gateway.update_status(ready_snapshot("ReadyPose"))
        gateway.update_status(ready_snapshot("ReadyPose"))
        self.assertFalse(gateway.submit("MimicWaveHand", "manual")["ok"])
        self.assertTrue(gateway.stop_motion("manual")["ok"])

    def test_motion_without_cooldown_repeats_immediately(self):
        """기존 검증된 행동: 인사류는 완료 직후 재실행할 수 있어야 한다."""
        self.gateway.update_status(ready_snapshot())
        request = self.gateway.submit("MimicWaveHand", "manual")
        self.gateway.next_dispatch()
        self.gateway.service_result(request["request_id"], True, "accepted")
        self.gateway.update_status(ready_snapshot("MimicWaveHand"))
        self.gateway.update_status(ready_snapshot("Velocity"))
        self.assertTrue(self.gateway.submit("MimicWaveHand", "manual")["ok"])

    def test_stale_robot_status_becomes_offline(self):
        gateway = Gateway({"MimicWaveHand"}, status_timeout_sec=0.01)
        gateway.set_robot_modes({"MimicWaveHand"})
        gateway.update_status(ready_snapshot())
        time.sleep(0.02)
        self.assertEqual(gateway.status()["gateway"], "offline")


if __name__ == "__main__":
    unittest.main()
