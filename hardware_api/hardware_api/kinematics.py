"""Differential-drive kinematics and wheel odometry. No ROS imports."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DriveParams:
  """Physical drive parameters (see config/drive.yaml)."""

  wheel_radius: float  # m
  track_width: float  # m, left-to-right wheel contact distance
  ticks_per_rev: int  # encoder ticks per wheel revolution
  max_wheel_speed: float  # m/s at the wheel rim, hardware maximum


@dataclass(frozen=True)
class Pose2D:
  x: float = 0.0
  y: float = 0.0
  theta: float = 0.0


def twist_to_wheels(v: float, omega: float, track_width: float) -> tuple[float, float]:
  """Body (v m/s, omega rad/s) to (left, right) wheel speeds in m/s."""
  half = track_width / 2.0
  return v - omega * half, v + omega * half


def wheels_to_twist(left: float, right: float, track_width: float) -> tuple[float, float]:
  """(left, right) wheel speeds in m/s to body (v m/s, omega rad/s)."""
  return (left + right) / 2.0, (right - left) / track_width


def ticks_to_distance(ticks: float, params: DriveParams) -> float:
  """Encoder ticks to wheel rim distance in m."""
  return ticks / params.ticks_per_rev * 2.0 * math.pi * params.wheel_radius


def normalize_angle(theta: float) -> float:
  """Wrap an angle to [-pi, pi)."""
  return (theta + math.pi) % (2.0 * math.pi) - math.pi


class OdometryIntegrator:
  """Integrates cumulative encoder ticks into a pose in the odom frame."""

  def __init__(self, params: DriveParams):
    self._params = params
    self._last_ticks = None
    self.pose = Pose2D()

  def reset(self) -> None:
    self._last_ticks = None
    self.pose = Pose2D()

  def update(self, left_ticks: int, right_ticks: int, dt: float) -> tuple[Pose2D, float, float]:
    """Advance from new cumulative ticks; return (pose, v, omega).

    The first call only records the starting ticks, since encoders need not start at zero.
    """
    if self._last_ticks is None:
      self._last_ticks = (left_ticks, right_ticks)
      return self.pose, 0.0, 0.0

    d_left = ticks_to_distance(left_ticks - self._last_ticks[0], self._params)
    d_right = ticks_to_distance(right_ticks - self._last_ticks[1], self._params)
    self._last_ticks = (left_ticks, right_ticks)

    d_center, d_theta = wheels_to_twist(d_left, d_right, self._params.track_width)
    # Midpoint heading integrates arcs more accurately than the start heading.
    mid = self.pose.theta + d_theta / 2.0
    self.pose = Pose2D(
      x=self.pose.x + d_center * math.cos(mid),
      y=self.pose.y + d_center * math.sin(mid),
      theta=normalize_angle(self.pose.theta + d_theta),
    )
    if dt <= 0.0:
      return self.pose, 0.0, 0.0
    return self.pose, d_center / dt, d_theta / dt
