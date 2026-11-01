"""Can-crusher cycle logic with a safety interlock. No ROS imports.

run() refuses unless every safety input is true, and a running cycle is aborted
the moment any input goes false or cannot be read. This is a software check on
top of the physical lock; it never replaces it.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CrusherSafety:
  chamber_closed: bool        # chamber door/lid is shut
  hardware_lock_engaged: bool # the physical lock is engaged
  contents_ok: bool           # nothing but the item is inside

  def problems(self) -> list[str]:
    """Names of the inputs that are not safe; empty if the crusher may run."""
    return [name for name, ok in (
      ('chamber_closed', self.chamber_closed),
      ('hardware_lock_engaged', self.hardware_lock_engaged),
      ('contents_ok', self.contents_ok),
    ) if not ok]


class CrusherBackend(ABC):
  """Crusher motor and safety sensors. Real and mock backends implement this."""

  @abstractmethod
  def read_safety(self) -> CrusherSafety:
    """Read the safety inputs now."""

  @abstractmethod
  def start(self) -> None:
    """Start the crusher motor."""

  @abstractmethod
  def stop(self) -> None:
    """Stop the crusher motor immediately."""


class MockCrusherBackend(CrusherBackend):
  """Hardware-free crusher. Every safety input starts False, so it refuses by default."""

  def __init__(self):
    self.chamber_closed = False
    self.hardware_lock_engaged = False
    self.contents_ok = False
    self.running = False

  def read_safety(self) -> CrusherSafety:
    return CrusherSafety(self.chamber_closed, self.hardware_lock_engaged, self.contents_ok)

  def start(self) -> None:
    self.running = True

  def stop(self) -> None:
    self.running = False


class CrusherController:
  """Runs one crush cycle at a time: starts only when safe, aborts when not."""

  def __init__(self, backend: CrusherBackend, cycle_time: float = 5.0, clock=time.monotonic):
    if cycle_time <= 0.0:
      raise ValueError('cycle_time must be > 0')
    self._backend = backend
    self._cycle_time = cycle_time
    self._clock = clock
    self._started = None
    self.last_result = 'idle'

  @property
  def running(self) -> bool:
    return self._started is not None

  def _safety_problems(self) -> list[str]:
    try:
      return self._backend.read_safety().problems()
    except Exception:  # an unreadable sensor is treated as unsafe
      return ['safety_read_failed']

  def run(self) -> tuple[bool, str]:
    """Start one cycle. Returns (started, message); a refusal never touches the motor."""
    if self.running:
      return False, 'refused: already running'
    problems = self._safety_problems()
    if problems:
      self.last_result = f"refused: {', '.join(problems)}"
      return False, self.last_result
    self._backend.start()
    self._started = self._clock()
    self.last_result = 'running'
    return True, 'crush cycle started'

  def stop(self) -> None:
    """Abort any cycle and stop the motor."""
    self._backend.stop()
    if self.running:
      self._started = None
      self.last_result = 'aborted: stop requested'

  def step(self) -> bool:
    """Check safety and the cycle timer; returns True while a cycle is running."""
    if not self.running:
      return False
    problems = self._safety_problems()
    if problems:
      self._backend.stop()
      self._started = None
      self.last_result = f"aborted: {', '.join(problems)}"
    elif self._clock() - self._started >= self._cycle_time:
      self._backend.stop()
      self._started = None
      self.last_result = 'complete'
    return self.running
