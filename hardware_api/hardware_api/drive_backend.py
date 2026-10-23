"""Abstract drive backend: the only layer that touches motor hardware."""

from abc import ABC, abstractmethod


class DriveBackend(ABC):
  """Wheel-level motor interface. Real, mock and future backends implement this."""

  @abstractmethod
  def set_wheel_speeds(self, left: float, right: float) -> None:
    """Command left/right wheel rim speeds in m/s."""

  @abstractmethod
  def stop(self) -> None:
    """Stop both wheels immediately."""

  @abstractmethod
  def read_encoders(self) -> tuple[int, int]:
    """Return cumulative (left, right) encoder ticks."""
