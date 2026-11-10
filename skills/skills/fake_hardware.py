"""In-memory HardwareClient for unit tests. No ROS imports.

Every command is appended to `calls` as (name, *args) so tests can assert what a
skill did. State fields are plain attributes that tests set directly. Nothing
moves over time: the gripper and crusher settle the instant they are commanded.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .hardware import CrusherStatus, Frame, GripperStatus, HardwareClient, Pose2D


class FakeHardware(HardwareClient):

  def __init__(self):
    self.calls: List[tuple] = []
    self.pose: Optional[Pose2D] = Pose2D(0.0, 0.0, 0.0)
    self.frame: Optional[Frame] = None
    self.head: Optional[Tuple[float, float]] = (0.0, 0.0)
    self.eyes = 'neutral'
    self.playing = False
    self.arm: Dict[str, float] = {}
    self.object_in_gripper = False   # what the gripper would close on
    self.gripper_state = GripperStatus(0.0, False)
    self.crusher_safe = True
    self.crusher_state = CrusherStatus(False, '')
    self.cmd = (0.0, 0.0)            # last drive command

  def drive(self, v, w):
    self.calls.append(('drive', v, w))
    self.cmd = (v, w)

  def stop(self):
    self.calls.append(('stop',))
    self.cmd = (0.0, 0.0)

  def odometry(self):
    return self.pose

  def rgbd(self):
    return self.frame

  def move_head(self, pan, tilt):
    self.calls.append(('move_head', pan, tilt))
    self.head = (pan, tilt)

  def head_position(self):
    return self.head

  def set_eyes(self, expression):
    self.calls.append(('set_eyes', expression))
    self.eyes = expression

  def play_audio(self, clip):
    self.calls.append(('play_audio', clip))

  def stop_audio(self):
    self.calls.append(('stop_audio',))
    self.playing = False

  def audio_playing(self):
    return self.playing

  def set_arm(self, joints):
    self.calls.append(('set_arm', dict(joints)))
    self.arm.update(joints)

  def hold_arm(self):
    self.calls.append(('hold_arm',))

  def arm_position(self):
    return dict(self.arm)

  def set_gripper(self, closed):
    self.calls.append(('set_gripper', closed))
    if closed:
      holding = self.object_in_gripper
      self.gripper_state = GripperStatus(0.5 if holding else 1.0, holding)
    else:
      self.gripper_state = GripperStatus(0.0, False)
    return True

  def gripper(self):
    return self.gripper_state

  def run_crusher(self):
    self.calls.append(('run_crusher',))
    if not self.crusher_safe:
      self.crusher_state = CrusherStatus(False, 'refused: unsafe')
      return False, 'refused: unsafe'
    self.crusher_state = CrusherStatus(False, 'complete')
    return True, 'started'

  def stop_crusher(self):
    self.calls.append(('stop_crusher',))

  def crusher(self):
    return self.crusher_state
