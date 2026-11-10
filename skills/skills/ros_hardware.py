"""HardwareClient over the hardware_api ROS 2 topics and services.

Works the same against the real robot and the simulator, since both speak the
interfaces in hardware_api/README.md. Construct it inside a skills node that is
spun by a MultiThreadedExecutor: blocking calls (run_crusher, set_gripper, stop)
wait on service futures, which only complete if another thread is spinning.
"""

from __future__ import annotations

import math
import threading
from typing import Dict, Optional, Tuple

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import CameraInfo, Image, JointState
from std_msgs.msg import Bool, String
from std_srvs.srv import SetBool, Trigger

from .hardware import CrusherStatus, Frame, GripperStatus, HardwareClient, Pose2D

HEAD_JOINTS = ('head_pan', 'head_tilt')


def _yaw(q) -> float:
  return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class RosHardware(HardwareClient):

  def __init__(self, node: Node, service_timeout_s: float = 2.0):
    self._node = node
    self._timeout = service_timeout_s
    self._lock = threading.Lock()
    group = ReentrantCallbackGroup()
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

    self._pose: Optional[Pose2D] = None
    self._color: Optional[Image] = None
    self._depth: Optional[Image] = None
    self._info: Optional[CameraInfo] = None
    self._head: Optional[Tuple[float, float]] = None
    self._arm: Dict[str, float] = {}
    self._gripper_pos: Optional[float] = None
    self._holding = False
    self._playing = False
    self._crusher = CrusherStatus(False, '')

    self._cmd_vel = node.create_publisher(Twist, 'cmd_vel', 10)
    self._head_cmd = node.create_publisher(JointState, 'head/cmd', 10)
    self._eyes = node.create_publisher(String, 'eyes/expression', 10)
    self._audio = node.create_publisher(String, 'audio/play', 10)
    self._arm_cmd = node.create_publisher(JointState, 'arm/cmd', 10)

    sub = node.create_subscription
    sub(Odometry, 'odom', self._on_odom, 10, callback_group=group)
    sub(Image, 'camera/color/image_raw', self._on_color, 5, callback_group=group)
    sub(Image, 'camera/depth/image_raw', self._on_depth, 5, callback_group=group)
    sub(CameraInfo, 'camera/color/camera_info', self._on_info, 5, callback_group=group)
    sub(JointState, 'head/state', self._on_head, 10, callback_group=group)
    sub(JointState, 'arm/state', self._on_arm, 10, callback_group=group)
    sub(JointState, 'gripper/state', self._on_gripper, 10, callback_group=group)
    sub(Bool, 'gripper/holding', self._on_holding, latched, callback_group=group)
    sub(Bool, 'audio/playing', self._on_playing, latched, callback_group=group)
    sub(Bool, 'crusher/running', self._on_crusher_running, latched, callback_group=group)
    sub(String, 'crusher/result', self._on_crusher_result, latched, callback_group=group)

    client = node.create_client
    self._stop = client(Trigger, 'hardware/stop', callback_group=group)
    self._audio_stop = client(Trigger, 'audio/stop', callback_group=group)
    self._arm_hold = client(Trigger, 'arm/hold', callback_group=group)
    self._gripper_set = client(SetBool, 'gripper/set', callback_group=group)
    self._crusher_run = client(Trigger, 'crusher/run', callback_group=group)
    self._crusher_stop = client(Trigger, 'crusher/stop', callback_group=group)

  # Subscriptions

  def _on_odom(self, msg):
    p = msg.pose.pose
    with self._lock:
      self._pose = Pose2D(p.position.x, p.position.y, _yaw(p.orientation))

  def _on_color(self, msg):
    with self._lock:
      self._color = msg

  def _on_depth(self, msg):
    with self._lock:
      self._depth = msg

  def _on_info(self, msg):
    with self._lock:
      self._info = msg

  def _on_head(self, msg):
    pos = dict(zip(msg.name, msg.position))
    if all(j in pos for j in HEAD_JOINTS):
      with self._lock:
        self._head = (pos['head_pan'], pos['head_tilt'])

  def _on_arm(self, msg):
    with self._lock:
      self._arm = dict(zip(msg.name, msg.position))

  def _on_gripper(self, msg):
    if msg.position:
      with self._lock:
        self._gripper_pos = msg.position[0]

  def _on_holding(self, msg):
    with self._lock:
      self._holding = msg.data

  def _on_playing(self, msg):
    with self._lock:
      self._playing = msg.data

  def _on_crusher_running(self, msg):
    with self._lock:
      self._crusher = CrusherStatus(msg.data, self._crusher.result)

  def _on_crusher_result(self, msg):
    with self._lock:
      self._crusher = CrusherStatus(self._crusher.running, msg.data)

  # Service helper

  def _call(self, client, request) -> Tuple[bool, str]:
    if not client.wait_for_service(timeout_sec=self._timeout):
      return False, f'{client.srv_name} not available'
    done = threading.Event()
    future = client.call_async(request)
    future.add_done_callback(lambda _: done.set())
    if not done.wait(self._timeout) or future.result() is None:
      return False, f'{client.srv_name} did not answer'
    result = future.result()
    return result.success, result.message

  # HardwareClient

  def drive(self, v, w):
    msg = Twist()
    msg.linear.x = float(v)
    msg.angular.z = float(w)
    self._cmd_vel.publish(msg)

  def stop(self):
    self._cmd_vel.publish(Twist())  # zero first, in case the service is slow
    ok, message = self._call(self._stop, Trigger.Request())
    if not ok:
      self._node.get_logger().error(f'stop failed: {message}')

  def odometry(self):
    with self._lock:
      return self._pose

  def rgbd(self):
    with self._lock:
      color, depth, info = self._color, self._depth, self._info
    if color is None or depth is None or info is None:
      return None
    if (color.header.stamp != depth.header.stamp
        or (color.width, color.height) != (depth.width, depth.height)
        or color.encoding != 'rgb8' or depth.encoding != '32FC1' or depth.is_bigendian):
      return None  # mid-update or unexpected format; caller retries next frame
    k = info.k
    return Frame(color.width, color.height, bytes(color.data), bytes(depth.data),
                 fx=k[0], fy=k[4], cx=k[2], cy=k[5], frame_id=color.header.frame_id)

  def move_head(self, pan, tilt):
    msg = JointState()
    msg.name = list(HEAD_JOINTS)
    msg.position = [float(pan), float(tilt)]
    self._head_cmd.publish(msg)

  def head_position(self):
    with self._lock:
      return self._head

  def set_eyes(self, expression):
    self._eyes.publish(String(data=expression))

  def play_audio(self, clip):
    with self._lock:
      self._playing = True  # until /audio/playing says otherwise
    self._audio.publish(String(data=clip))

  def stop_audio(self):
    self._call(self._audio_stop, Trigger.Request())

  def audio_playing(self):
    with self._lock:
      return self._playing

  def set_arm(self, joints):
    msg = JointState()
    msg.name = list(joints)
    msg.position = [float(joints[n]) for n in msg.name]
    self._arm_cmd.publish(msg)

  def hold_arm(self):
    self._call(self._arm_hold, Trigger.Request())

  def arm_position(self):
    with self._lock:
      return dict(self._arm)

  def set_gripper(self, closed):
    request = SetBool.Request()
    request.data = bool(closed)
    ok, message = self._call(self._gripper_set, request)
    if not ok:
      self._node.get_logger().error(f'set_gripper failed: {message}')
    return ok

  def gripper(self):
    with self._lock:
      if self._gripper_pos is None:
        return None
      return GripperStatus(self._gripper_pos, self._holding)

  def run_crusher(self):
    return self._call(self._crusher_run, Trigger.Request())

  def stop_crusher(self):
    self._call(self._crusher_stop, Trigger.Request())

  def crusher(self):
    with self._lock:
      return self._crusher
