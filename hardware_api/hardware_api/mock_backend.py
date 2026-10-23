"""Hardware-free drive backend with simulated encoders."""

import math
import time

from .drive_backend import DriveBackend
from .kinematics import DriveParams


class MockDriveBackend(DriveBackend):
  """Ideal wheels: commanded speeds apply instantly and encoders count exactly."""

  def __init__(self, params: DriveParams, clock=time.monotonic):
    self._ticks_per_m = params.ticks_per_rev / (2.0 * math.pi * params.wheel_radius)
    self._clock = clock
    self._last = clock()
    self._speeds = (0.0, 0.0)
    self._ticks = [0.0, 0.0]

  def _advance(self) -> None:
    now = self._clock()
    dt = now - self._last
    self._last = now
    self._ticks[0] += self._speeds[0] * dt * self._ticks_per_m
    self._ticks[1] += self._speeds[1] * dt * self._ticks_per_m

  def set_wheel_speeds(self, left: float, right: float) -> None:
    self._advance()
    self._speeds = (left, right)

  def stop(self) -> None:
    self._advance()
    self._speeds = (0.0, 0.0)

  def read_encoders(self) -> tuple[int, int]:
    self._advance()
    return round(self._ticks[0]), round(self._ticks[1])
