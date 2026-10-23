"""Drive logic between the ROS node and a DriveBackend. No ROS imports."""

import time

from .drive_backend import DriveBackend
from .kinematics import DriveParams, OdometryIntegrator, Pose2D, twist_to_wheels


class DriveController:
  """Turns body velocity commands into wheel commands and tracks odometry."""

  def __init__(self, backend: DriveBackend, params: DriveParams, clock=time.monotonic):
    self._backend = backend
    self._params = params
    self._clock = clock
    self._odometry = OdometryIntegrator(params)
    self._target = (0.0, 0.0)
    self._last_step = None

  def command(self, v: float, omega: float) -> None:
    """Set the body velocity target; applied on the next step()."""
    self._target = twist_to_wheels(v, omega, self._params.track_width)

  def stop(self) -> None:
    """Clear the target and stop the backend immediately."""
    self._target = (0.0, 0.0)
    self._backend.stop()

  def step(self) -> tuple[Pose2D, float, float]:
    """Send the current target to the backend, then return (pose, v, omega)."""
    now = self._clock()
    dt = 0.0 if self._last_step is None else now - self._last_step
    self._last_step = now

    if self._target == (0.0, 0.0):
      self._backend.stop()
    else:
      self._backend.set_wheel_speeds(*self._target)

    left, right = self._backend.read_encoders()
    return self._odometry.update(left, right, dt)
