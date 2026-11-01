"""ROS 2 node for run_crusher.

  run_crusher() -> call /crusher/run (std_srvs/Trigger). Starts one crush cycle and
                   returns at once: success=false with the reason if the safety
                   check fails, success=true if the cycle started.
                   call /crusher/stop (std_srvs/Trigger) to abort
                   publish /crusher/running (std_msgs/Bool, latched; changes only)
                   publish /crusher/result (std_msgs/String, latched): the outcome of the
                   last request or cycle (refused: ..., running, complete, aborted: ...)

The cycle is aborted if a safety input goes false while it runs.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from .crusher import CrusherController, MockCrusherBackend


class CrusherNode(Node):
  """Thin ROS wrapper around CrusherController."""

  def __init__(self):
    super().__init__('crusher_node')
    backend_name = self.declare_parameter('backend', 'mock').value
    cycle_time = self.declare_parameter('cycle_time', 5.0).value
    rate_hz = self.declare_parameter('check_rate_hz', 20.0).value
    for name in ('mock_chamber_closed', 'mock_lock_engaged', 'mock_contents_ok'):
      self.declare_parameter(name, False)

    if backend_name != 'mock':
      raise ValueError(f"unknown backend '{backend_name}'")
    self._backend = MockCrusherBackend()
    self._controller = CrusherController(self._backend, cycle_time)

    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    self._running_pub = self.create_publisher(Bool, 'crusher/running', latched)
    self._result_pub = self.create_publisher(String, 'crusher/result', latched)
    self.create_service(Trigger, 'crusher/run', self._on_run)
    self.create_service(Trigger, 'crusher/stop', self._on_stop)
    self._running = False
    self._result = ''
    self._publish_state()
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self.get_logger().info(f'crusher_node up with {backend_name} backend (refuses unless safe)')

  def _sync_mock_inputs(self) -> None:
    self._backend.chamber_closed = self.get_parameter('mock_chamber_closed').value
    self._backend.hardware_lock_engaged = self.get_parameter('mock_lock_engaged').value
    self._backend.contents_ok = self.get_parameter('mock_contents_ok').value

  def _publish_state(self) -> None:
    running = self._controller.running
    if running != self._running or not self._result:
      self._running = running
      self._running_pub.publish(Bool(data=running))
    if self._controller.last_result != self._result:
      self._result = self._controller.last_result
      self._result_pub.publish(String(data=self._result))

  def _on_run(self, request, response):
    self._sync_mock_inputs()
    response.success, response.message = self._controller.run()
    if not response.success:
      self.get_logger().warn(f'run_crusher: {response.message}')
    self._publish_state()
    return response

  def _on_stop(self, request, response):
    self._controller.stop()
    response.success = True
    response.message = 'stopped'
    self._publish_state()
    return response

  def _on_timer(self) -> None:
    self._sync_mock_inputs()
    self._controller.step()
    self._publish_state()


def main(args=None):
  rclpy.init(args=args)
  node = CrusherNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node._controller.stop()
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
