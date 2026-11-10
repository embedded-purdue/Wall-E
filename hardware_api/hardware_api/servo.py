"""Servo backends that move Maestro servos through the ESP32. No ROS imports.

Hobby servos are commanded by pulse width in microseconds (us). Each joint gets a
ServoChannel that maps its angle range (the JointSpec limits) linearly onto a pulse
range that electrical measured as safe for that servo. Channel numbers and pulse
ranges are PLACEHOLDERS until electrical fills in the channel map in
docs/esp32-protocol.md.
"""

from dataclasses import dataclass

from .esp32_backend import Esp32Link
from .gripper import GripperBackend, GripperState
from .joints import JointBackend, JointSpec


@dataclass(frozen=True)
class ServoChannel:
  """One servo on the Maestro: channel number and the pulse widths for the joint's min/max angle."""

  channel: int
  min_us: float   # pulse width at the joint's min_angle
  max_us: float   # pulse width at the joint's max_angle (may be < min_us if the servo is mounted reversed)

  def __post_init__(self):
    if self.channel < 0:
      raise ValueError('channel must be >= 0')
    if self.min_us <= 0 or self.max_us <= 0 or self.min_us == self.max_us:
      raise ValueError(f'channel {self.channel}: min_us and max_us must be positive and different')

  def to_us(self, angle: float, spec: JointSpec) -> float:
    angle = spec.clamp(angle)
    fraction = (angle - spec.min_angle) / (spec.max_angle - spec.min_angle)
    return self.min_us + fraction * (self.max_us - self.min_us)

  def to_angle(self, pulse_us: float, spec: JointSpec) -> float:
    fraction = (pulse_us - self.min_us) / (self.max_us - self.min_us)
    return spec.clamp(spec.min_angle + fraction * (spec.max_angle - spec.min_angle))


class Esp32ServoJointBackend(JointBackend):
  """JointBackend for servo joints (head, eyes) on the Maestro.

  Only sends a servo message when a joint's pulse width actually changes, so the
  50 Hz control loop does not flood the serial link while the head is still.
  """

  def __init__(self, link: Esp32Link, specs: list[JointSpec], channels: dict[str, ServoChannel],
               min_change_us: float = 1.0):
    missing = [spec.name for spec in specs if spec.name not in channels]
    if missing:
      raise ValueError(f'no servo channel for joint(s) {missing}')
    self._link = link
    self._specs = {spec.name: spec for spec in specs}
    self._channels = channels
    self._min_change_us = min_change_us
    self._sent_us: dict[str, float] = {}
    self._positions = {spec.name: spec.home for spec in specs}

  def set_positions(self, positions: dict[str, float]) -> None:
    for name, angle in positions.items():
      spec, channel = self._specs[name], self._channels[name]
      pulse = channel.to_us(angle, spec)
      last = self._sent_us.get(name)
      if last is None or abs(pulse - last) >= self._min_change_us:
        self._link.set_servo(channel.channel, pulse)
        self._sent_us[name] = pulse
      self._positions[name] = spec.clamp(angle)

  def read_positions(self) -> dict[str, float]:
    # Plain hobby servos report no real position; the Maestro returns the pulse it is sending,
    # which is the last commanded angle.
    return dict(self._positions)


class Esp32ServoGripperBackend(GripperBackend):
  """Gripper on one Maestro servo: open_us and closed_us pulse widths.

  A plain servo cannot tell us whether it closed on something, so `holding` is
  always False here. TODO(electrical): add a sensor (servo current, a switch in the
  fingers, or a feedback servo) so grab() can check it is holding something.
  """

  def __init__(self, link: Esp32Link, channel: int, open_us: float, closed_us: float):
    self._link = link
    self._channel = ServoChannel(channel, open_us, closed_us)
    self._spec = JointSpec('gripper', 0.0, 1.0, 1.0)  # 0 open .. 1 closed
    self._closed = False

  def set_closed(self, closed: bool) -> None:
    self._link.set_servo(self._channel.channel, self._channel.to_us(1.0 if closed else 0.0, self._spec))
    self._closed = closed

  def read_state(self) -> GripperState:
    position = self._channel.to_angle(self._link.read_servo(self._channel.channel), self._spec)
    return GripperState(self._closed, position, holding=False)
