"""ROS 2 node for the driving commands: drive, stop, get_odometry."""

import rclpy
from rclpy.node import Node


class DriveNode(Node):
  """Placeholder; interfaces are added in later commits."""

  def __init__(self):
    super().__init__('drive_node')


def main(args=None):
  rclpy.init(args=args)
  node = DriveNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
