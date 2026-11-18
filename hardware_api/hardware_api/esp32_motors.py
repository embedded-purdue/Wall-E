"""Arm motor and crusher backends that go through the ESP32. No ROS imports.

The arm joints and the crusher are DC motors on RoboClaws behind the ESP32. Arm motion
is planned on the Jetson (JointController slews toward the target), so the ESP32 only
gets simple per-step position targets: `A <counts> ...`, one absolute encoder count per
arm motor, which the RoboClaw's position PID holds. The crusher is on/off at a capped
duty (`C <percent>`), and the switch inputs come back with `I`.

Counts per radian and the arm motor order are PLACEHOLDERS until electrical and
mechanical confirm them (docs/esp32-protocol.md, "Arm and crusher").
"""

from .crusher import CrusherBackend, CrusherSafety
from .esp32_backend import Esp32Link
from .esp32_protocol import ProtocolError
from .joints import JointBackend, JointSpec


class Esp32ArmJointBackend(JointBackend):
  """JointBackend for the arm motors. Joint i is motor i in the `A`/`J` messages.

  angle = home + counts / counts_per_rad, so the encoders read 0 with the arm at its home
  pose (the firmware zeroes them at boot). A negative counts_per_rad flips a motor's
  direction. Only sends `A` when some target moved by at least min_change_counts, so a
  still arm does not flood the serial link at 50 Hz.
  """

  def __init__(self, link: Esp32Link, specs: list[JointSpec], counts_per_rad: list[float],
               min_change_counts: int = 1):
    if len(counts_per_rad) != len(specs):
      raise ValueError(f'{len(counts_per_rad)} counts_per_rad values for {len(specs)} arm joints')
    if any(c == 0 for c in counts_per_rad):
      raise ValueError('counts_per_rad must be non-zero')
    self._link = link
    self._specs = list(specs)
    self._cpr = list(counts_per_rad)
    self._min_change = min_change_counts
    self._targets = [spec.home for spec in specs]
    self._sent: list[int] | None = None

  def _to_counts(self, i: int, angle: float) -> int:
    spec = self._specs[i]
    return round((spec.clamp(angle) - spec.home) * self._cpr[i])

  def set_positions(self, positions: dict[str, float]) -> None:
    names = [spec.name for spec in self._specs]
    for name, angle in positions.items():
      self._targets[names.index(name)] = angle
    counts = [self._to_counts(i, a) for i, a in enumerate(self._targets)]
    if self._sent is None or any(abs(c - s) >= self._min_change for c, s in zip(counts, self._sent)):
      self._link.set_arm(counts)
      self._sent = counts

  def read_positions(self) -> dict[str, float]:
    counts = self._link.read_arm()
    if len(counts) != len(self._specs):
      raise ProtocolError(f'ESP32 sent {len(counts)} arm counts, expected {len(self._specs)}')
    return {spec.name: spec.home + c / cpr for spec, c, cpr in zip(self._specs, counts, self._cpr)}


class Esp32CrusherBackend(CrusherBackend):
  """Crusher motor (`C`) plus the three safety switches (`I`).

  A link failure raises, and CrusherController treats an unreadable sensor as unsafe, so
  a dead link refuses to start and aborts a running cycle. The firmware also refuses to
  start the crusher unless its switches are closed, and stops it on silence.
  """

  def __init__(self, link: Esp32Link, duty_percent: float = 60.0):
    if not 0.0 < duty_percent <= 100.0:
      raise ValueError('crusher duty_percent must be in (0, 100]')
    self._link = link
    self._duty = duty_percent

  def read_safety(self) -> CrusherSafety:
    inputs = self._link.read_inputs()
    return CrusherSafety(inputs['chamber_closed'], inputs['lock_engaged'], inputs['contents_ok'])

  def start(self) -> None:
    self._link.set_crusher(self._duty)

  def stop(self) -> None:
    self._link.set_crusher(0.0)
