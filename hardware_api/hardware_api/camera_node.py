"""ROS 2 node for get_rgbd.

  get_rgbd() -> subscribe the latest pair, both stamped with the same time:
    /camera/color/image_raw   (sensor_msgs/Image, rgb8)
    /camera/depth/image_raw   (sensor_msgs/Image, 32FC1, meters, NaN = no reading)
    /camera/color/camera_info (sensor_msgs/CameraInfo, ideal pinhole from hfov)
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image

from .camera import MockCameraBackend, RGBDFrame, pinhole_intrinsics


class CameraNode(Node):
  """Thin ROS wrapper around a CameraBackend."""

  def __init__(self):
    super().__init__('camera_node')
    backend_name = self.declare_parameter('backend', 'mock').value
    width = self.declare_parameter('width', 320).value
    height = self.declare_parameter('height', 240).value
    rate_hz = self.declare_parameter('frame_rate_hz', 15.0).value
    hfov = self.declare_parameter('hfov', 1.2).value
    self._frame_id = self.declare_parameter('frame_id', 'camera_link').value
    mock_depth = self.declare_parameter('mock_depth_m', 2.0).value
    mock_object = self.declare_parameter('mock_object_depth_m', 0.0).value  # 0 = no object

    if backend_name == 'mock':
      self._backend = MockCameraBackend(
        width, height, mock_depth, mock_object if mock_object > 0.0 else None)
    else:
      raise ValueError(f"unknown backend '{backend_name}'")
    self._fx, self._fy, self._cx, self._cy = pinhole_intrinsics(width, height, hfov)

    self._color_pub = self.create_publisher(Image, 'camera/color/image_raw', 5)
    self._depth_pub = self.create_publisher(Image, 'camera/depth/image_raw', 5)
    self._info_pub = self.create_publisher(CameraInfo, 'camera/color/camera_info', 5)
    self.create_timer(1.0 / rate_hz, self._on_timer)
    self.get_logger().info(f'camera_node up with {backend_name} backend')

  def _image(self, frame: RGBDFrame, stamp, encoding: str, bytes_per_pixel: int, data: bytes):
    msg = Image()
    msg.header.stamp = stamp
    msg.header.frame_id = self._frame_id
    msg.height = frame.height
    msg.width = frame.width
    msg.encoding = encoding
    msg.is_bigendian = 0
    msg.step = frame.width * bytes_per_pixel
    msg.data = data
    return msg

  def _on_timer(self) -> None:
    frame = self._backend.read()
    stamp = self.get_clock().now().to_msg()
    self._color_pub.publish(self._image(frame, stamp, 'rgb8', 3, frame.color))
    self._depth_pub.publish(self._image(frame, stamp, '32FC1', 4, frame.depth))

    info = CameraInfo()
    info.header.stamp = stamp
    info.header.frame_id = self._frame_id
    info.width = frame.width
    info.height = frame.height
    info.distortion_model = 'plumb_bob'
    info.d = [0.0] * 5
    info.k = [self._fx, 0.0, self._cx, 0.0, self._fy, self._cy, 0.0, 0.0, 1.0]
    info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    info.p = [self._fx, 0.0, self._cx, 0.0, 0.0, self._fy, self._cy, 0.0, 0.0, 0.0, 1.0, 0.0]
    self._info_pub.publish(info)


def main(args=None):
  rclpy.init(args=args)
  node = CameraNode()
  try:
    rclpy.spin(node)
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
