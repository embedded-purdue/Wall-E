"""Real robot: drive, head/eyes, gripper and sensors through the ESP32, in one process.

  ros2 launch hardware_api esp32.launch.py
  ros2 launch hardware_api esp32.launch.py params_file:=/path/to/my_esp32.yaml
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
  config = PathJoinSubstitution([FindPackageShare('hardware_api'), 'config', 'esp32.yaml'])
  return LaunchDescription([
    DeclareLaunchArgument('params_file', default_value=config, description='ESP32 node parameter file'),
    Node(
      package='hardware_api',
      executable='esp32_hardware',
      output='screen',
      parameters=[LaunchConfiguration('params_file')],
    ),
  ])
