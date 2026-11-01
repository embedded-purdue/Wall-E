"""Gripper backend interface and a mock gripper. No ROS imports."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GripperState:
  closed_command: bool  # what was last commanded
  position: float       # 0.0 fully open ... 1.0 fully closed
  holding: bool         # closed on an object (stopped by it, not fully closed)


class GripperBackend(ABC):
  """Gripper interface. Real and mock backends implement this."""

  @abstractmethod
  def set_closed(self, closed: bool) -> None:
    """Start closing (True) or opening (False). Returns without waiting."""

  @abstractmethod
  def read_state(self) -> GripperState:
    """Return the current gripper state."""


class MockGripperBackend(GripperBackend):
  """Gripper that closes at a fixed speed and is stopped by an object if one is present.

  Set object_present to simulate an object between the fingers. Closing then
  stops at object_fraction and holding is True; with nothing there it closes
  fully and holding is False.
  """

  def __init__(self, close_time: float = 1.0, object_fraction: float = 0.5, clock=time.monotonic):
    if close_time <= 0.0:
      raise ValueError('close_time must be > 0')
    if not 0.0 < object_fraction < 1.0:
      raise ValueError('object_fraction must be in (0, 1)')
    self.object_present = False
    self._close_time = close_time
    self._object_fraction = object_fraction
    self._clock = clock
    self._last = clock()
    self._closed = False
    self._position = 0.0

  def _advance(self) -> None:
    now = self._clock()
    step = max(0.0, now - self._last) / self._close_time
    self._last = now
    if self._closed:
      limit = self._object_fraction if self.object_present else 1.0
      if self._position < limit:
        self._position = min(limit, self._position + step)
    else:
      self._position = max(0.0, self._position - step)

  def set_closed(self, closed: bool) -> None:
    self._advance()
    self._closed = closed

  def read_state(self) -> GripperState:
    self._advance()
    holding = (self._closed and self.object_present
               and abs(self._position - self._object_fraction) < 1e-9)
    return GripperState(self._closed, self._position, holding)
