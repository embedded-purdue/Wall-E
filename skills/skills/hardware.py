"""The hardware API (Layer 2) as the skills see it. No ROS imports.

Skills call a HardwareClient and never touch topics or services directly, so the
same skill code runs against the robot, the simulator (RosHardware for both) and
FakeHardware in unit tests.

Timing rules that come from hardware_api (see hardware_api/README.md):
  - drive() must be called at 10 Hz or faster while moving, or the drive
    watchdog stops the robot. It is a single publish, not a latched command.
  - set_gripper() returns at once. Poll gripper() until it settles.
  - run_crusher() returns when the cycle starts. Poll crusher() for the outcome.
  - play_audio() returns at once. Poll audio_playing() to know when it ends.
"""

from __future__ import annotations

import math
import sys
from abc import ABC, abstractmethod
from array import array
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Pose2D:
  """Robot pose in the odom frame (m, m, rad)."""
  x: float
  y: float
  yaw: float


@dataclass(frozen=True)
class Frame:
  """Latest color + depth pair with the color camera's pinhole intrinsics.

  Color is rgb8, depth is float32 meters aligned to color (NaN = no reading),
  both row-major, matching get_rgbd() in hardware_api.
  """
  width: int
  height: int
  color: bytes
  depth: bytes
  fx: float
  fy: float
  cx: float
  cy: float
  frame_id: str = 'camera_link'

  def depth_at(self, x: int, y: int) -> float:
    """Depth in meters at pixel (x, y); NaN if there is no reading."""
    if not (0 <= x < self.width and 0 <= y < self.height):
      raise IndexError(f'pixel ({x}, {y}) is outside {self.width}x{self.height}')
    values = array('f')
    values.frombytes(self.depth[(y * self.width + x) * 4:(y * self.width + x + 1) * 4])
    if sys.byteorder == 'big':
      values.byteswap()
    return values[0]

  def deproject(self, x: float, y: float, depth: float) -> Tuple[float, float, float]:
    """Pixel + depth -> 3D point in the camera optical frame (x right, y down, z forward)."""
    if not math.isfinite(depth):
      raise ValueError('depth must be finite')
    return ((x - self.cx) * depth / self.fx, (y - self.cy) * depth / self.fy, depth)


@dataclass(frozen=True)
class GripperStatus:
  position: float  # 0.0 open ... 1.0 closed
  holding: bool    # stopped by an object


@dataclass(frozen=True)
class CrusherStatus:
  running: bool
  result: str      # last /crusher/result: refused: ..., running, complete, aborted: ...


class HardwareClient(ABC):
  """Every Layer 2 command the skills use. get_audio() is left out: only NLP reads the mic."""

  # Driving
  @abstractmethod
  def drive(self, v: float, w: float) -> None:
    """Forward speed (m/s) and turn rate (rad/s). Call at >= 10 Hz while moving."""

  @abstractmethod
  def stop(self) -> None:
    """Stop all driving immediately."""

  @abstractmethod
  def odometry(self) -> Optional[Pose2D]:
    """Latest pose in odom, or None if none has arrived yet."""

  # Perception
  @abstractmethod
  def rgbd(self) -> Optional[Frame]:
    """Latest color + depth frame, or None if none has arrived yet."""

  # Head, eyes, audio
  @abstractmethod
  def move_head(self, pan: float, tilt: float) -> None:
    """Point the head (rad). hardware_api clamps to the joint limits."""

  @abstractmethod
  def head_position(self) -> Optional[Tuple[float, float]]:
    """Current (pan, tilt) in rad, or None if unknown."""

  @abstractmethod
  def set_eyes(self, expression: str) -> None:
    """Show an eye expression (neutral, happy, sad, surprised, curious, confused, sleepy)."""

  @abstractmethod
  def play_audio(self, clip: str) -> None:
    """Start playing a clip name or path. Returns at once."""

  @abstractmethod
  def stop_audio(self) -> None:
    """Cut playback."""

  @abstractmethod
  def audio_playing(self) -> bool:
    """True while a clip is playing."""

  # Arm, gripper, crusher
  @abstractmethod
  def set_arm(self, joints: Dict[str, float]) -> None:
    """Move arm joints to angles (rad). Partial dicts are fine."""

  @abstractmethod
  def hold_arm(self) -> None:
    """Stop the arm where it is."""

  @abstractmethod
  def arm_position(self) -> Dict[str, float]:
    """Current commanded joint angles; empty if unknown."""

  @abstractmethod
  def set_gripper(self, closed: bool) -> bool:
    """Start closing (True) or opening (False). Returns False if the call failed."""

  @abstractmethod
  def gripper(self) -> Optional[GripperStatus]:
    """Latest gripper state, or None if unknown."""

  @abstractmethod
  def run_crusher(self) -> Tuple[bool, str]:
    """Start one crush cycle. (False, reason) if the safety check refuses it."""

  @abstractmethod
  def stop_crusher(self) -> None:
    """Abort a running cycle."""

  @abstractmethod
  def crusher(self) -> CrusherStatus:
    """Latest crusher state."""
