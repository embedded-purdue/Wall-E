"""ROS 2 node for run_crusher.

  run_crusher() -> call /crusher/run (std_srvs/Trigger). Starts one crush cycle and
                   returns at once: success=false with the reason if the safety
                   check fails, success=true if the cycle started.
                   call /crusher/stop (std_srvs/Trigger) to abort
                   publish /crusher/running (std_msgs/Bool, latched; changes only)
                   publish /crusher/result (std_msgs/String, latched): the outcome of the
                   last request or cycle (refused: ..., running, complete, aborted: ...)

The cycle is aborted if a safety input goes false while it runs. With backend esp32 the
crusher motor and its switches are on the ESP32, so this node must run in the same
process as the other ESP32 nodes (esp32_hardware).
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from .crusher import CrusherController, MockCrusherBackend
from .esp32_backend import Esp32Link
from .esp32_motors import Esp32CrusherBackend
from .esp32_protocol import ProtocolError


class CrusherNode(Node):
  """Thin ROS wrapper around CrusherController."""

  def __init__(self):
    super().__init__('crusher_node')
    backend_name = self.declare_parameter('backend', 'mock').value
    cycle_time = self.declare_parameter('cycle_time', 5.0).value
    rate_hz = self.declare_parameter('check_rate_hz', 20.0).value
    for name in ('mock_chamber_closed', 'mock_lock_engaged', 'mock_contents_ok'):
      self.declare_parameter(name, False)

    if backend_name == 'mock':
      self._backend = MockCrusherBackend()
    elif backend_name == 'esp32':
      port = self.declare_parameter('esp32_port', '').value
      if not port:
        raise ValueError('backend esp32 needs esp32_port')
      baud = self.declare_parameter('esp32_baud', 115200).value
      duty = self.declare_parameter('crusher_duty_percent', 60.0).value
      self._backend = Esp32CrusherBackend(Esp32Link.shared(port, baud), duty)
    else:
      raise ValueError(f"unknown backend '{backend_name}'")
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
    if not isinstance(self._backend, MockCrusherBackend):
      return
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
    try:
      response.success, response.message = self._controller.run()
    except ProtocolError as exc:  # e.g. the firmware's own interlock said no (ERR interlock)
      response.success, response.message = False, f'refused by ESP32: {exc}'
    if not response.success:
      self.get_logger().warn(f'run_crusher: {response.message}')
    self._publish_state()
    return response

  def _on_stop(self, request, response):
    try:
      self._controller.stop()
    except ProtocolError as exc:
      response.success = False
      response.message = f'stop failed: {exc}'
      return response
    response.success = True
    response.message = 'stopped'
    self._publish_state()
    return response

  def _on_timer(self) -> None:
    self._sync_mock_inputs()
    try:
      self._controller.step()
    except ProtocolError as exc:  # stop did not get through; the next tick tries again
      self.get_logger().error(f'ESP32 link error (crusher): {exc}', throttle_duration_sec=1.0)
    self._publish_state()


  def shutdown(self) -> None:
    self._controller.stop()


def main(args=None):
  rclpy.init(args=args)
  node = CrusherNode()
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
