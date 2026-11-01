"""Joint-level actuator interface shared by head, eyes and arm. No ROS imports.

Angles are radians. Limits and the slew (speed) limit are enforced here in
software; they never rely on the servo or motor controller being configured.
"""

import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class JointSpec:
  """Limits for one joint. max_speed is a software slew limit in rad/s."""

  name: str
  min_angle: float
  max_angle: float
  max_speed: float
  home: float = 0.0

  def __post_init__(self):
    if not self.min_angle < self.max_angle:
      raise ValueError(f'{self.name}: min_angle must be < max_angle')
    if self.max_speed <= 0.0:
      raise ValueError(f'{self.name}: max_speed must be > 0')
    if not self.min_angle <= self.home <= self.max_angle:
      raise ValueError(f'{self.name}: home must be within [min_angle, max_angle]')

  def clamp(self, angle: float) -> float:
    return max(self.min_angle, min(self.max_angle, angle))


class JointBackend(ABC):
  """Joint-level interface. Real (Maestro, motor driver) and mock backends implement this."""

  @abstractmethod
  def set_positions(self, positions: dict[str, float]) -> None:
    """Command joint angles in radians, keyed by joint name."""

  @abstractmethod
  def read_positions(self) -> dict[str, float]:
    """Return the best-known joint angles in radians, keyed by joint name."""


class MockJointBackend(JointBackend):
  """Hardware-free backend: commanded angles are reported back exactly."""

  def __init__(self, homes: dict[str, float]):
    self._positions = dict(homes)

  def set_positions(self, positions: dict[str, float]) -> None:
    self._positions.update(positions)

  def read_positions(self) -> dict[str, float]:
    return dict(self._positions)


class JointController:
  """Clamps targets to joint limits and slews toward them at a capped speed.

  command() sets targets; step() moves the commanded position toward the targets
  by at most max_speed * dt and sends it to the backend. Joints start at home.
  """

  def __init__(self, backend: JointBackend, specs: list[JointSpec], clock=time.monotonic):
    if not specs:
      raise ValueError('at least one joint is required')
    names = [spec.name for spec in specs]
    if len(set(names)) != len(names):
      raise ValueError('duplicate joint names')
    self._backend = backend
    self._specs = {spec.name: spec for spec in specs}
    self._clock = clock
    self._targets = {spec.name: spec.home for spec in specs}
    self._commanded = dict(self._targets)
    self._last_step = None

  @property
  def names(self) -> list[str]:
    return list(self._specs)

  def command(self, targets: dict[str, float]) -> dict[str, float]:
    """Set joint targets and return the applied (clamped) targets for every joint.

    An unknown joint name raises KeyError and nothing is applied. Non-finite
    angles are ignored (that joint keeps its previous target).
    """
    unknown = [name for name in targets if name not in self._specs]
    if unknown:
      raise KeyError(f'unknown joint(s): {unknown}')
    for name, angle in targets.items():
      if math.isfinite(angle):
        self._targets[name] = self._specs[name].clamp(angle)
    return dict(self._targets)

  def hold(self) -> None:
    """Stop moving: make the current commanded position the target."""
    self._targets = dict(self._commanded)

  def step(self) -> dict[str, float]:
    """Advance toward the targets, send the result to the backend and return it."""
    now = self._clock()
    dt = 0.0 if self._last_step is None else max(0.0, now - self._last_step)
    self._last_step = now
    for name, target in self._targets.items():
      limit = self._specs[name].max_speed * dt
      delta = target - self._commanded[name]
      self._commanded[name] += max(-limit, min(limit, delta))
    self._backend.set_positions(dict(self._commanded))
    return dict(self._commanded)

  def targets(self) -> dict[str, float]:
    return dict(self._targets)

  def at_target(self, tolerance: float = 1e-3) -> bool:
    return all(abs(self._targets[n] - self._commanded[n]) <= tolerance for n in self._targets)
