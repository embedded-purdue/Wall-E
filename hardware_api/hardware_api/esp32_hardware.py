"""Run every node that talks to the ESP32 in one process, sharing one serial link.

There is only one UART to the ESP32, so drive_node, head_eyes_node, arm_node and
sensors_node cannot each open it from their own process. This runs them together;
each still reads its own section of the params file, e.g.:

  ros2 run hardware_api esp32_hardware --ros-args --params-file config/esp32.yaml

(or `ros2 launch hardware_api esp32.launch.py`). Audio, camera and crusher are not on
the ESP32 and run separately.
"""

import rclpy
from rclpy.executors import SingleThreadedExecutor

from .arm_node import ArmNode
from .drive_node import DriveNode
from .head_eyes_node import HeadEyesNode
from .sensors_node import SensorsNode


def main(args=None):
  rclpy.init(args=args)
  nodes = []
  executor = SingleThreadedExecutor()
  try:
    for make in (DriveNode, HeadEyesNode, ArmNode, SensorsNode):
      node = make()
      nodes.append(node)
      executor.add_node(node)
    executor.spin()
  except KeyboardInterrupt:
    pass
  finally:
    for node in nodes:
      if isinstance(node, DriveNode):
        node.shutdown()  # send stop before letting go of the link
      node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
