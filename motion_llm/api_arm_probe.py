#!/usr/bin/env python3
"""Publish only an advancing API heartbeat and print K1 mode status changes."""

import time

import rclpy
from ai_sapiens_sim2real.msg import ApiModeHeartbeat, ModeStatus


def main():
    rclpy.init()
    node = rclpy.create_node("k1_api_arm_probe")
    publisher = node.create_publisher(ApiModeHeartbeat, "/ai_sapiens/api_mode_heartbeat", 10)
    last = None

    def on_status(msg):
        nonlocal last
        current = (msg.active_mode, msg.authority, msg.api_mode_heartbeat_valid,
                   msg.api_request_available, msg.last_transition_reason)
        if current != last:
            last = current
            print("mode=%s authority=%s heartbeat=%s request_available=%s reason=%s" % current,
                  flush=True)

    node.create_subscription(ModeStatus, "/ai_sapiens/mode_status", on_status, 10)
    sequence = 0
    try:
        while rclpy.ok():
            msg = ApiModeHeartbeat()
            msg.header.stamp = node.get_clock().now().to_msg()
            msg.sequence = sequence
            sequence = (sequence + 1) & 0xFFFFFFFF
            publisher.publish(msg)
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
