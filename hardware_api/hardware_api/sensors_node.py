"""ROS 2 node for battery and ultrasonic readings.

  battery      -> publish /battery (sensor_msgs/BatteryState; voltage, percentage 0..1)
  ultrasonics  -> publish /ultrasonic/<name> (sensor_msgs/Range; meters, +inf = no echo)

Used by the BT team's battery_sufficient and near checks.
"""

import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState, Range

from .esp32_backend import Esp32Link
from .esp32_protocol import ProtocolError
from .sensors import Esp32SensorsBackend, MockSensorsBackend, battery_fraction


class SensorsNode(Node):

  def __init__(self):
    super().__init__('sensors_node')
    backend_name = self.declare_parameter('backend', 'mock').value
    rate_hz = self.declare_parameter('rate_hz', 5.0).value
    self._names = list(self.declare_parameter('ultrasonic_names', ['front']).value)
    self._frames = list(self.declare_parameter('ultrasonic_frames', ['ultrasonic_front']).value)
    if len(self._frames) != len(self._names):
      raise ValueError('ultrasonic_frames must have one entry per ultrasonic_names')
    self._min_range = self.declare_parameter('ultrasonic_min_range', 0.02).value
    self._max_range = self.declare_parameter('ultrasonic_max_range', 4.0).value
    self._fov = self.declare_parameter('ultrasonic_fov', 0.26).value  # rad, about 15 degrees
    # TODO(electrical): real pack limits. Placeholders for a 20 V (5S Li-ion) drill pack.
    self._empty_volts = self.declare_parameter('battery_empty_volts', 15.0).value
    self._full_volts = self.declare_parameter('battery_full_volts', 20.5).value

    if backend_name == 'mock':
      self._backend = MockSensorsBackend(
        self.declare_parameter('mock_battery_volts', 20.0).value,
        list(self.declare_parameter('mock_distances', [1.5]).value),
      )
    elif backend_name == 'esp32':
      port = self.declare_parameter('esp32_port', '').value
      if not port:
        raise ValueError('backend esp32 needs esp32_port')
      baud = self.declare_parameter('esp32_baud', 115200).value
      self._backend = Esp32SensorsBackend(Esp32Link.shared(port, baud))
    else:
      raise ValueError(f"unknown backend '{backend_name}'")

    self._battery_pub = self.create_publisher(BatteryState, 'battery', 10)
    self._range_pubs = [self.create_publisher(Range, f'ultrasonic/{name}', 10) for name in self._names]
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self.get_logger().info(f'sensors_node up with {backend_name} backend, ultrasonics {self._names}')

  def _on_timer(self) -> None:
    stamp = self.get_clock().now().to_msg()
    try:
      volts = self._backend.read_battery()
      distances = self._backend.read_ultrasonic()
    except ProtocolError as exc:
      self.get_logger().error(f'ESP32 link error: {exc}', throttle_duration_sec=1.0)
      return

    battery = BatteryState()
    battery.header.stamp = stamp
    battery.voltage = float(volts)
    battery.percentage = battery_fraction(volts, self._empty_volts, self._full_volts)
    battery.present = True
    self._battery_pub.publish(battery)

    if len(distances) != len(self._names):
      self.get_logger().warn(
        f'got {len(distances)} ultrasonic readings for {len(self._names)} sensors', throttle_duration_sec=5.0)
    for pub, frame, distance in zip(self._range_pubs, self._frames, distances):
      msg = Range()
      msg.header.stamp = stamp
      msg.header.frame_id = frame
      msg.radiation_type = Range.ULTRASOUND
      msg.field_of_view = float(self._fov)
      msg.min_range = float(self._min_range)
      msg.max_range = float(self._max_range)
      msg.range = math.inf if distance is None else float(distance)
      pub.publish(msg)


def main(args=None):
  rclpy.init(args=args)
  node = SensorsNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
