"""Launch mock_skills_node with config/mock_skills.yaml (no hardware or hardware_api needed)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
  config = PathJoinSubstitution([FindPackageShare('skills'), 'config', 'mock_skills.yaml'])
  return LaunchDescription([
    DeclareLaunchArgument('params_file', default_value=config, description='mock_skills_node parameter file'),
    Node(
      package='skills',
      executable='mock_skills_node',
      name='mock_skills_node',
      output='screen',
      parameters=[LaunchConfiguration('params_file')],
    ),
  ])
