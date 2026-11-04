"""Run the structured decision preview beside an existing ROS system."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('mission_file', description='Absolute path to a structured mission JSON'),
        DeclareLaunchArgument('policy', default_value='selective', choices=['fixed', 'event', 'selective']),
        Node(package='riskweave_console', executable='riskweave_replanner', name='riskweave_replanner',
             parameters=[{'mission_file': LaunchConfiguration('mission_file'),
                          'policy': LaunchConfiguration('policy')}], output='screen'),
    ])
