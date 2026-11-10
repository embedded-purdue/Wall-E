"""ROS 2 node for the audio commands: play_audio, get_audio.

  play_audio(clip) -> subscribe /audio/play (std_msgs/String; clip name or file path)
                      call /audio/stop (std_srvs/Trigger) to cut playback
                      publish /audio/playing (std_msgs/Bool, latched; changes only)
  get_audio()      -> publish /audio/mic (std_msgs/UInt8MultiArray): raw PCM,
                      signed 16-bit little-endian, mono, sample_rate Hz, one
                      chunk_ms chunk per message
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String, UInt8MultiArray
from std_srvs.srv import Trigger

from .audio import AudioController, MockAudioBackend


class AudioNode(Node):
  """Thin ROS wrapper around AudioController."""

  def __init__(self):
    super().__init__('audio_node')
    backend_name = self.declare_parameter('backend', 'mock').value
    sample_rate = self.declare_parameter('sample_rate', 16000).value
    chunk_ms = self.declare_parameter('chunk_ms', 20).value
    self._mic_enabled = self.declare_parameter('mic_enabled', True).value
    self._clip_duration = self.declare_parameter('mock_clip_duration', 1.0).value

    self._controller = AudioController(self._make_backend(backend_name), sample_rate, chunk_ms)
    self._mic_pub = self.create_publisher(UInt8MultiArray, 'audio/mic', 10)
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    self._playing_pub = self.create_publisher(Bool, 'audio/playing', latched)
    self.create_subscription(String, 'audio/play', self._on_play, 10)
    self.create_service(Trigger, 'audio/stop', self._on_stop)
    self.create_timer(chunk_ms / 1000.0, self._on_timer)
    self._playing = False
    self._playing_pub.publish(Bool(data=False))
    self.get_logger().info(f'audio_node up with {backend_name} backend')

  def _make_backend(self, name: str):
    if name == 'mock':
      return MockAudioBackend(clip_duration=self._clip_duration)
    raise ValueError(f"unknown backend '{name}'")

  def _on_play(self, msg: String) -> None:
    accepted, message = self._controller.play(msg.data)
    if not accepted:
      self.get_logger().warn(f"play_audio rejected '{msg.data}': {message}")

  def _on_stop(self, request, response):
    self._controller.stop()
    response.success = True
    response.message = 'stopped'
    return response

  def _on_timer(self) -> None:
    playing = self._controller.playing()
    if playing != self._playing:
      self._playing = playing
      self._playing_pub.publish(Bool(data=playing))
    if self._mic_enabled:
      self._mic_pub.publish(UInt8MultiArray(data=list(self._controller.read_chunk())))


def main(args=None):
  rclpy.init(args=args)
  node = AudioNode()
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
