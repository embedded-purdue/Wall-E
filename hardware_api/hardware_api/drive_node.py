"""ROS 2 node for the driving commands: drive, stop, get_odometry.

  drive(v, omega)  -> subscribe /cmd_vel (geometry_msgs/Twist; linear.x, angular.z)
  stop()           -> service /hardware/stop (std_srvs/Trigger)
  get_odometry()   -> publish /odom (nav_msgs/Odometry)
"""

import math

import rclpy
from geometry_msgs.msg import Quaternion, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_srvs.srv import Trigger

from .controller import DriveController
from .kinematics import DriveParams
from .mock_backend import MockDriveBackend


def _yaw_to_quaternion(yaw: float) -> Quaternion:
  return Quaternion(z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))


class DriveNode(Node):
  """Thin ROS wrapper around DriveController."""

  def __init__(self):
    super().__init__('drive_node')
    # Zero defaults force these to come from config/drive.yaml.
    self._params = DriveParams(
      wheel_radius=self.declare_parameter('wheel_radius', 0.0).value,
      track_width=self.declare_parameter('track_width', 0.0).value,
      ticks_per_rev=self.declare_parameter('ticks_per_rev', 0).value,
      max_wheel_speed=self.declare_parameter('max_wheel_speed', 0.0).value,
    )
    for name, value in vars(self._params).items():
      if value <= 0:
        raise ValueError(f'parameter {name} must be > 0 (set it in config/drive.yaml)')
    backend_name = self.declare_parameter('backend', 'mock').value
    rate_hz = self.declare_parameter('control_rate_hz', 50.0).value
    self._odom_frame = self.declare_parameter('odom_frame', 'odom').value
    self._base_frame = self.declare_parameter('base_frame', 'base_link').value

    self._controller = DriveController(
      self._make_backend(backend_name), self._params, clock=self._now)

    self._odom_pub = self.create_publisher(Odometry, 'odom', 10)
    self.create_subscription(Twist, 'cmd_vel', self._on_cmd_vel, 10)
    self.create_service(Trigger, 'hardware/stop', self._on_stop)
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self.get_logger().info(f'drive_node up with {backend_name} backend')

  def _make_backend(self, name: str):
    if name == 'mock':
      return MockDriveBackend(self._params)
    raise ValueError(f"unknown backend '{name}'")

  def _now(self) -> float:
    return self.get_clock().now().nanoseconds * 1e-9

  def _on_cmd_vel(self, msg: Twist) -> None:
    self._controller.command(msg.linear.x, msg.angular.z)

  def _on_stop(self, request, response):
    self._controller.stop()
    response.success = True
    response.message = 'stopped'
    return response

  def _on_timer(self) -> None:
    pose, v, omega = self._controller.step()
    msg = Odometry()
    msg.header.stamp = self.get_clock().now().to_msg()
    msg.header.frame_id = self._odom_frame
    msg.child_frame_id = self._base_frame
    msg.pose.pose.position.x = pose.x
    msg.pose.pose.position.y = pose.y
    msg.pose.pose.orientation = _yaw_to_quaternion(pose.theta)
    msg.twist.twist.linear.x = v
    msg.twist.twist.angular.z = omega
    self._odom_pub.publish(msg)

  def shutdown(self) -> None:
    self._controller.stop()


def main(args=None):
  rclpy.init(args=args)
  node = DriveNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.shutdown()
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
