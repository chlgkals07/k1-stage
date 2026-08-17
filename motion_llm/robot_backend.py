"""ROS 2 transport for the K1 motion gateway.

This module is deliberately imported only for ``server.py --robot`` so mock
and unit-test workflows do not need a ROS installation.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import yaml

from gateway import Gateway, RobotSnapshot


def _load_cooldowns(catalog_path: Path):
    """motions.yaml 의 ``cooldown_sec`` 만 뽑는다. 값이 없는 모션은 대기시간 0 이다."""
    try:
        doc = yaml.safe_load(catalog_path.read_text())
    except OSError:
        return {}
    items = list(doc.get("motions") or []) + list(doc.get("control_states") or [])
    return {m["state"]: m["cooldown_sec"] for m in items if m.get("cooldown_sec")}


class RobotBackend:
    name = "robot"

    def __init__(self, config_path: Path):
        config = yaml.safe_load(config_path.read_text())
        self.config = config
        policy = config["policy"]
        self.gateway = Gateway(policy["api_allowlist"], policy["entry_timeout_sec"],
                               policy.get("status_timeout_sec", 1.0),
                               stop_state=policy.get("stop_state", "ReadyPose"),
                               cooldowns=_load_cooldowns(config_path.parent / "motions.yaml"))
        self._ros = None
        self._node = None
        self._thread = None
        self._running = False
        self._sequence = 0
        self._list_requested = False

    @property
    def api_allowlist(self):
        return set(self.gateway.api_allowlist)

    def start(self):
        try:
            import rclpy
            from rclpy.node import Node
            from ai_sapiens_sim2real.msg import ApiModeHeartbeat, ModeStatus
            from ai_sapiens_sim2real.srv import ListModes, RequestModeByName
        except ImportError as exc:
            raise RuntimeError("--robot 은 ai_sapiens ROS 환경에서 실행해야 합니다") from exc

        self._ros = rclpy
        rclpy.init(args=None)
        self._node = Node("k1_motion_gateway")
        ros = self.config["ros"]
        self._heartbeat_type = ApiModeHeartbeat
        self._request_type = RequestModeByName
        self._list_type = ListModes
        self._heartbeat_pub = self._node.create_publisher(ApiModeHeartbeat, ros["heartbeat_topic"], 10)
        self._node.create_subscription(ModeStatus, ros["status_topic"], self._on_status, 10)
        self._request_client = self._node.create_client(RequestModeByName, ros["request_service"])
        self._list_client = self._node.create_client(ListModes, ros["list_modes_service"])
        self._node.create_timer(1.0 / ros["heartbeat_hz"], self._publish_heartbeat)
        self._node.create_timer(0.05, self._tick)
        self._running = True
        self._thread = threading.Thread(target=rclpy.spin, args=(self._node,), daemon=True,
                                        name="k1-motion-gateway-ros")
        self._thread.start()

    def play(self, motion, info):
        return self.gateway.submit(motion, info.get("source", "unknown"), info.get("reason", ""))

    def submit(self, motion, source, reason):
        return self.gateway.submit(motion, source, reason)

    def stop_motion(self, source, reason=""):
        return self.gateway.stop_motion(source, reason)

    def status(self):
        return self.gateway.status()

    def stop(self):
        self._running = False
        if self._node:
            self._node.destroy_node()
        if self._ros:
            self._ros.shutdown()
        if self._thread:
            self._thread.join(timeout=2)

    def _publish_heartbeat(self):
        msg = self._heartbeat_type()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.sequence = self._sequence
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        self._heartbeat_pub.publish(msg)

    def _on_status(self, msg):
        self.gateway.update_status(RobotSnapshot(
            active_mode=msg.active_mode,
            authority=msg.authority,
            heartbeat_valid=bool(msg.api_mode_heartbeat_valid),
            request_available=bool(msg.api_request_available),
            last_transition_reason=msg.last_transition_reason,
            received_at=time.monotonic(),
        ))

    def _tick(self):
        self.gateway.tick()
        if not self._list_requested and self._list_client.service_is_ready():
            self._list_requested = True
            future = self._list_client.call_async(self._request_type_to_list_request())
            future.add_done_callback(self._on_list_modes)
        request = self.gateway.next_dispatch()
        if request:
            if not self._request_client.service_is_ready():
                self.gateway.service_result(request.request_id, False, "모션 서비스가 준비되지 않았습니다")
                return
            ros_request = self._request_type.Request()
            ros_request.mode_name = request.motion
            future = self._request_client.call_async(ros_request)
            future.add_done_callback(lambda f, request_id=request.request_id: self._on_request_result(request_id, f))

    def _request_type_to_list_request(self):
        # ListModes has an empty request; constructing from the client service type
        # avoids importing a second type into the dispatch path.
        return self._list_type.Request()

    def _on_list_modes(self, future):
        try:
            response = future.result()
            if not response.success:
                raise RuntimeError(response.message or "list_modes 거부")
            modes = response.available_modes or response.modes
            self.gateway.set_robot_modes(modes)
        except Exception as exc:  # noqa: BLE001
            self._node.get_logger().error(f"list_modes 실패: {exc}")
            self._list_requested = False

    def _on_request_result(self, request_id, future):
        try:
            response = future.result()
            self.gateway.service_result(request_id, bool(response.success), response.message)
        except Exception as exc:  # noqa: BLE001
            self.gateway.service_result(request_id, False, f"ROS service 예외: {exc}")
