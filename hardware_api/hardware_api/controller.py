"""Drive logic between the ROS node and a DriveBackend. No ROS imports."""

import time

from .drive_backend import DriveBackend
from .kinematics import DriveParams, OdometryIntegrator, Pose2D
from .safety import SpeedLimiter, Watchdog


class DriveController:
  """Turns body velocity commands into capped wheel commands and tracks odometry.

  Safety: every command passes the speed cap; the target is dropped if no command
  arrives within watchdog_timeout; stop() reaches the backend immediately.
  """

  def __init__(
    self,
    backend: DriveBackend,
    params: DriveParams,
    cap_fraction: float = 0.6,
    watchdog_timeout: float = 0.5,
    clock=time.monotonic,
    on_timeout=None,
  ):
    self._backend = backend
    self._clock = clock
    self._on_timeout = on_timeout
    self._limiter = SpeedLimiter(params.track_width, params.max_wheel_speed, cap_fraction)
    self._watchdog = Watchdog(watchdog_timeout, clock)
    self._odometry = OdometryIntegrator(params)
    self._target = (0.0, 0.0)
    self._last_step = None

  def command(self, v: float, omega: float) -> None:
    """Set the body velocity target; applied on the next step()."""
    self._target = self._limiter.limit(v, omega)
    self._watchdog.feed()

  def stop(self) -> None:
    """Clear the target and stop the backend immediately."""
    self._watchdog.expire()
    self._target = (0.0, 0.0)
    self._backend.stop()

  def step(self) -> tuple[Pose2D, float, float]:
    """Send the current target to the backend, then return (pose, v, omega)."""
    now = self._clock()
    dt = 0.0 if self._last_step is None else now - self._last_step
    self._last_step = now

    if self._watchdog.expired() and self._target != (0.0, 0.0):
      self._target = (0.0, 0.0)
      if self._on_timeout is not None:
        self._on_timeout()

    if self._target == (0.0, 0.0):
      self._backend.stop()
    else:
      self._backend.set_wheel_speeds(*self._target)

    left, right = self._backend.read_encoders()
    return self._odometry.update(left, right, dt)
