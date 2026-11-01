"""ROS 2 node for the head and eye commands: move_head, set_eyes.

  move_head(pan, tilt) -> subscribe /head/cmd (sensor_msgs/JointState; names head_pan, head_tilt, rad)
                          publish /head/state (sensor_msgs/JointState; current commanded angles)
  set_eyes(expression) -> subscribe /eyes/expression (std_msgs/String; see expressions.py)
                          publish /eyes/state (std_msgs/String; last applied expression, latched)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import JointState
from std_msgs.msg import String

from .expressions import LEFT_EYE, RIGHT_EYE, eye_targets
from .joints import JointController, JointSpec, MockJointBackend

HEAD_JOINTS = ('head_pan', 'head_tilt')


class HeadEyesNode(Node):
  """Thin ROS wrapper around JointController for the head and eye servos."""

  def __init__(self):
    super().__init__('head_eyes_node')
    head_speed = self.declare_parameter('head_max_speed', 2.0).value
    eye_speed = self.declare_parameter('eye_max_speed', 6.0).value
    specs = [
      JointSpec(
        'head_pan',
        self.declare_parameter('head_pan_min', -1.2).value,
        self.declare_parameter('head_pan_max', 1.2).value,
        head_speed),
      JointSpec(
        'head_tilt',
        self.declare_parameter('head_tilt_min', -0.5).value,
        self.declare_parameter('head_tilt_max', 0.5).value,
        head_speed),
    ]
    eye_min = self.declare_parameter('eye_min', -0.5).value
    eye_max = self.declare_parameter('eye_max', 0.5).value
    specs += [JointSpec(name, eye_min, eye_max, eye_speed) for name in (LEFT_EYE, RIGHT_EYE)]

    backend_name = self.declare_parameter('backend', 'mock').value
    rate_hz = self.declare_parameter('control_rate_hz', 50.0).value
    self._expression = self.declare_parameter('default_expression', 'neutral').value.strip().lower()

    self._controller = JointController(self._make_backend(backend_name, specs), specs)
    self._controller.command(eye_targets(self._expression))

    self._head_pub = self.create_publisher(JointState, 'head/state', 10)
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    self._eyes_pub = self.create_publisher(String, 'eyes/state', latched)
    self.create_subscription(JointState, 'head/cmd', self._on_head_cmd, 10)
    self.create_subscription(String, 'eyes/expression', self._on_expression, 10)
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self._publish_expression()
    self.get_logger().info(f'head_eyes_node up with {backend_name} backend')

  def _make_backend(self, name: str, specs: list[JointSpec]):
    if name == 'mock':
      return MockJointBackend({spec.name: spec.home for spec in specs})
    raise ValueError(f"unknown backend '{name}'")

  def _on_head_cmd(self, msg: JointState) -> None:
    targets = {n: p for n, p in zip(msg.name, msg.position) if n in HEAD_JOINTS}
    if not targets:
      self.get_logger().warn(f'/head/cmd needs joint names from {HEAD_JOINTS}; ignored')
      return
    self._controller.command(targets)

  def _on_expression(self, msg: String) -> None:
    try:
      targets = eye_targets(msg.data)
    except KeyError as exc:
      self.get_logger().warn(str(exc))
      return
    self._controller.command(targets)
    self._expression = msg.data.strip().lower()
    self._publish_expression()

  def _publish_expression(self) -> None:
    self._eyes_pub.publish(String(data=self._expression))

  def _on_timer(self) -> None:
    positions = self._controller.step()
    msg = JointState()
    msg.header.stamp = self.get_clock().now().to_msg()
    msg.name = list(HEAD_JOINTS)
    msg.position = [positions[name] for name in HEAD_JOINTS]
    self._head_pub.publish(msg)


def main(args=None):
  rclpy.init(args=args)
  node = HeadEyesNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
