"""Launch the head/eyes, audio, camera, arm/gripper and crusher nodes (mock backends by default).

Drive is launched separately with drive.launch.py.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

NODES = ('head_eyes_node', 'audio_node', 'camera_node', 'arm_node', 'crusher_node')


def generate_launch_description():
  config = PathJoinSubstitution([FindPackageShare('hardware_api'), 'config', 'peripherals.yaml'])
  return LaunchDescription([
    DeclareLaunchArgument('params_file', default_value=config, description='peripheral node parameter file'),
    *[
      Node(
        package='hardware_api',
        executable=name,
        name=name,
        output='screen',
        parameters=[LaunchConfiguration('params_file')],
      )
      for name in NODES
    ],
  ])
