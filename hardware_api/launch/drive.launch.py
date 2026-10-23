"""Launch drive_node with config/drive.yaml (mock backend by default)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
  config = PathJoinSubstitution([FindPackageShare('hardware_api'), 'config', 'drive.yaml'])
  return LaunchDescription([
    DeclareLaunchArgument('backend', default_value='mock', description='Drive backend (mock)'),
    Node(
      package='hardware_api',
      executable='drive_node',
      name='drive_node',
      output='screen',
      parameters=[config, {'backend': LaunchConfiguration('backend')}],
    ),
  ])
