"""Opt-in ROS decision preview for structured, externally supervised missions.

Never publishes to the robot execution topic. Stop/interrupt acknowledgements
and synchronized manipulation remain the responsibility of the robot supervisor.
"""
import json
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from .selective import Scheduler


class RiskWeaveReplanner(Node):
    def __init__(self):
        super().__init__('riskweave_replanner')
        self.declare_parameter('mission_file', '')
        self.declare_parameter('policy', 'selective')
        mission_path = Path(self.get_parameter('mission_file').value).expanduser()
        with mission_path.open(encoding='utf-8') as stream:
            mission = json.load(stream)
        self.scheduler = Scheduler.from_dict(mission, self.get_parameter('policy').value)
        self.decision_pub = self.create_publisher(String, '/riskweave/replanning/decision', 10)
        self.preview_pub = self.create_publisher(String, '/riskweave/replanning/proposed_tasks_json', 10)
        self.event_sub = self.create_subscription(String, '/riskweave/replanning/events', self.on_event, 10)
        self.get_logger().info('Structured replanning preview ready; robot execution is not connected.')

    def on_event(self, message):
        try:
            decision = self.scheduler.step(json.loads(message.data))
        except (ValueError, KeyError, TypeError) as exc:
            self.get_logger().error(f'Rejected structured event: {exc}')
            return
        output = String()
        output.data = json.dumps(decision, ensure_ascii=False, allow_nan=False)
        self.decision_pub.publish(output)
        preview = String()
        preview.data = json.dumps(self.scheduler.proposed_robot_tasks(), ensure_ascii=False)
        self.preview_pub.publish(preview)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = RiskWeaveReplanner()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
