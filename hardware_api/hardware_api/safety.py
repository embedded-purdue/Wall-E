"""Software speed cap and command watchdog. No ROS imports.

These never rely on hardware limits being configured.
"""

import math
import time

from .kinematics import twist_to_wheels


def _clamp(value: float, limit: float) -> float:
  return max(-limit, min(limit, value))


class SpeedLimiter:
  """Caps commands at cap_fraction of the hardware maximum wheel speed."""

  def __init__(self, track_width: float, max_wheel_speed: float, cap_fraction: float = 0.6):
    if not 0.0 < cap_fraction <= 1.0:
      raise ValueError(f'cap_fraction must be in (0, 1], got {cap_fraction}')
    self._track_width = track_width
    self.max_wheel_speed = max_wheel_speed * cap_fraction
    self.max_v = self.max_wheel_speed
    self.max_omega = 2.0 * self.max_wheel_speed / track_width

  def limit(self, v: float, omega: float) -> tuple[float, float]:
    """Return capped (left, right) wheel speeds in m/s; non-finite input gives (0, 0).

    v and omega are clamped first, then both wheels are scaled by the same factor
    so the turning curve is preserved.
    """
    if not (math.isfinite(v) and math.isfinite(omega)):
      return 0.0, 0.0
    left, right = twist_to_wheels(
      _clamp(v, self.max_v), _clamp(omega, self.max_omega), self._track_width)
    peak = max(abs(left), abs(right))
    if peak > self.max_wheel_speed:
      scale = self.max_wheel_speed / peak
      left, right = left * scale, right * scale
    return left, right


class Watchdog:
  """Expires when not fed within timeout seconds. Starts expired."""

  def __init__(self, timeout: float, clock=time.monotonic):
    if timeout <= 0.0:
      raise ValueError(f'timeout must be > 0, got {timeout}')
    self._timeout = timeout
    self._clock = clock
    self._last_feed = None

  def feed(self) -> None:
    self._last_feed = self._clock()

  def expire(self) -> None:
    """Force the expired state until the next feed()."""
    self._last_feed = None

  def expired(self) -> bool:
    return self._last_feed is None or self._clock() - self._last_feed > self._timeout
