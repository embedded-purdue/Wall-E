"""ROS 2 node for the arm and gripper commands: set_arm, set_gripper.

  set_arm(pose)      -> subscribe /arm/cmd (sensor_msgs/JointState; joint angles in rad,
                        names from arm_joint_names; partial messages are fine)
                        publish /arm/state (sensor_msgs/JointState; current commanded angles)
                        call /arm/hold (std_srvs/Trigger) to stop moving where it is
  set_gripper(close) -> call /gripper/set (std_srvs/SetBool; data=true closes, false opens);
                        returns at once, it does not wait for the gripper to finish
                        publish /gripper/state (sensor_msgs/JointState; name 'gripper',
                        position 0.0 open ... 1.0 closed)
                        publish /gripper/holding (std_msgs/Bool, latched; changes only)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool
from std_srvs.srv import SetBool, Trigger

from .arm import arm_specs
from .gripper import MockGripperBackend
from .joints import JointController, MockJointBackend


class ArmNode(Node):
  """Thin ROS wrapper around JointController (arm) and a GripperBackend."""

  def __init__(self):
    super().__init__('arm_node')
    names = list(self.declare_parameter('arm_joint_names', ['']).value)
    specs = arm_specs(
      names,
      list(self.declare_parameter('arm_min', [0.0]).value),
      list(self.declare_parameter('arm_max', [0.0]).value),
      list(self.declare_parameter('arm_max_speed', [0.0]).value),
      list(self.declare_parameter('arm_home', [0.0]).value),
    )
    backend_name = self.declare_parameter('backend', 'mock').value
    rate_hz = self.declare_parameter('control_rate_hz', 50.0).value
    self.declare_parameter('mock_object_present', False)
    close_time = self.declare_parameter('mock_gripper_close_time', 1.0).value

    if backend_name != 'mock':
      raise ValueError(f"unknown backend '{backend_name}'")
    self._arm = JointController(MockJointBackend({s.name: s.home for s in specs}), specs)
    self._gripper = MockGripperBackend(close_time=close_time)

    self._arm_pub = self.create_publisher(JointState, 'arm/state', 10)
    self._gripper_pub = self.create_publisher(JointState, 'gripper/state', 10)
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    self._holding_pub = self.create_publisher(Bool, 'gripper/holding', latched)
    self.create_subscription(JointState, 'arm/cmd', self._on_arm_cmd, 10)
    self.create_service(Trigger, 'arm/hold', self._on_hold)
    self.create_service(SetBool, 'gripper/set', self._on_gripper)
    self._holding = False
    self._holding_pub.publish(Bool(data=False))
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self.get_logger().info(f'arm_node up with {backend_name} backend, joints {names}')

  def _on_arm_cmd(self, msg: JointState) -> None:
    try:
      self._arm.command(dict(zip(msg.name, msg.position)))
    except KeyError as exc:
      self.get_logger().warn(f'/arm/cmd ignored: {exc}')

  def _on_hold(self, request, response):
    self._arm.hold()
    response.success = True
    response.message = 'holding'
    return response

  def _on_gripper(self, request, response):
    self._gripper.set_closed(request.data)
    response.success = True
    response.message = 'closing' if request.data else 'opening'
    return response

  def _on_timer(self) -> None:
    stamp = self.get_clock().now().to_msg()
    positions = self._arm.step()
    arm_msg = JointState()
    arm_msg.header.stamp = stamp
    arm_msg.name = self._arm.names
    arm_msg.position = [positions[name] for name in arm_msg.name]
    self._arm_pub.publish(arm_msg)

    self._gripper.object_present = self.get_parameter('mock_object_present').value
    state = self._gripper.read_state()
    gripper_msg = JointState()
    gripper_msg.header.stamp = stamp
    gripper_msg.name = ['gripper']
    gripper_msg.position = [state.position]
    self._gripper_pub.publish(gripper_msg)
    if state.holding != self._holding:
      self._holding = state.holding
      self._holding_pub.publish(Bool(data=state.holding))


def main(args=None):
  rclpy.init(args=args)
  node = ArmNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node._arm.hold()
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
