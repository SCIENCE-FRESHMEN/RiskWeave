#!/usr/bin/env python3
"""Actual ROS pub/sub smoke test; run only in a prepared Humble environment."""
import json
from pathlib import Path
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from riskweave_console.riskweave_replanner import RiskWeaveReplanner


def main():
    rclpy.init(args=['--ros-args', '-p', 'mission_file:=/work/experiments/mission.example.json'])
    planner = RiskWeaveReplanner()
    tester = Node('selective_smoke_tester')
    received = []
    subscription = tester.create_subscription(String, '/riskweave/replanning/decision',
                                             lambda msg: received.append(json.loads(msg.data)), 10)
    publisher = tester.create_publisher(String, '/riskweave/replanning/events', 10)
    executor = SingleThreadedExecutor()
    executor.add_node(planner)
    executor.add_node(tester)
    try:
        deadline = time.monotonic() + 10
        while publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.1)
        for event, expected in [({'id':'start','time':0}, 'replan'),
                                ({'id':'emergency','time':1,'emergency':True}, 'stop')]:
            count = len(received)
            msg = String()
            msg.data = json.dumps(event)
            publisher.publish(msg)
            deadline = time.monotonic() + 10
            while len(received) == count and time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.1)
            assert len(received) > count, 'ROS decision message was not received'
            assert received[-1]['action'] == expected, received[-1]
        report = {'kind':'actual_ros_transport_smoke','passed':True,
                  'events_processed':len(received),'robot_execution_connected':False}
        Path('/output/ros_smoke.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        executor.shutdown()
        planner.destroy_node()
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
