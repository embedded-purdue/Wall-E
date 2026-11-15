"""The channel map: which ESP32 port drives which part of the robot, plus the tweakable
action values (limits, directions, speeds). All real values live in config/esp32.yaml.
No ROS imports.

A port that starts with TBD_ is a placeholder. Placeholders work against the fake ESP32
but are refused for real hardware (see Esp32Config.problems).
"""
import math
from dataclasses import dataclass, field

from esp32_protocol import check_token

KINDS = ('motor', 'servo', 'din', 'dout', 'range')
PLACEHOLDER_PREFIX = 'TBD_'


@dataclass(frozen=True)
class Device:
  """One thing on the ESP32. Only the fields for its kind matter."""
  name: str
  kind: str                  # motor | servo | din (digital input) | dout | range (HC-SR04P)
  port: str                  # token the ESP32 firmware understands
  invert: bool = False       # flip direction (motor/servo) or logic level (din)
  # motor
  max_permille: int = 600    # speed cap, 1000 = full speed. 600 = the team's 60% limit
  ticks_per_rev: int = 2000  # encoder ticks per OUTPUT shaft revolution
  # servo, and joint limits for motors under GOTO. Degrees, in the ESP32's own frame.
  min_deg: float = -90.0
  max_deg: float = 90.0
  center_deg: float = 0.0    # the angle that counts as "0" for the mechanism

  def __post_init__(self):
    if self.kind not in KINDS:
      raise ValueError(f'{self.name}: kind must be one of {KINDS}, got {self.kind!r}')
    check_token(self.port)
    if not 0 < self.max_permille <= 1000:
      raise ValueError(f'{self.name}: max_permille must be in (0, 1000]')
    if self.ticks_per_rev <= 0:
      raise ValueError(f'{self.name}: ticks_per_rev must be > 0')
    if not self.min_deg < self.max_deg:
      raise ValueError(f'{self.name}: min_deg must be < max_deg')

  @property
  def is_placeholder(self) -> bool:
    return self.port.startswith(PLACEHOLDER_PREFIX)

  def wire_permille(self, permille: float) -> int:
    """Wanted speed (+ = the mechanism's forward) -> capped, direction-corrected wire value."""
    value = max(-self.max_permille, min(self.max_permille, round(permille)))
    return -value if self.invert else value

  def wire_degrees(self, degrees: float) -> float:
    """Wanted angle from center (the mechanism's own direction) -> absolute angle to send."""
    sign = -1.0 if self.invert else 1.0
    return max(self.min_deg, min(self.max_deg, self.center_deg + sign * degrees))

  def from_wire_degrees(self, wire: float) -> float:
    """Inverse of wire_degrees (without the clamp)."""
    return (-1.0 if self.invert else 1.0) * (wire - self.center_deg)


@dataclass(frozen=True)
class LinkSettings:
  serial_port: str = '/dev/ttyACM0'  # USB: /dev/ttyACM0 or /dev/ttyUSB0. Jetson header UART: /dev/ttyTHS1
  baud: int = 921600                 # must match the firmware (ignored by native USB serial)
  reply_timeout: float = 0.1         # s to wait for each reply
  retries: int = 2                   # resends after a lost or garbled reply
  watchdog_timeout: float = 0.5      # s; must match the firmware


@dataclass(frozen=True)
class Esp32Config:
  link: LinkSettings = field(default_factory=LinkSettings)
  devices: dict = field(default_factory=dict)   # name -> Device

  def device(self, name: str, kind: str = None) -> Device:
    if name not in self.devices:
      raise KeyError(f"unknown device '{name}'; known: {sorted(self.devices)}")
    device = self.devices[name]
    if kind is not None and device.kind != kind:
      raise ValueError(f"device '{name}' is a {device.kind}, expected {kind}")
    return device

  def problems(self, hardware: bool) -> list[str]:
    """Things to fix before use. With hardware=True, unassigned TBD_ ports are problems."""
    found = []
    by_port = {}
    for device in self.devices.values():
      by_port.setdefault(device.port, []).append(device.name)
    for port, names in by_port.items():
      if len(names) > 1:
        found.append(f"port {port} is used by more than one device: {', '.join(names)}")
    if hardware:
      todo = [d.name for d in self.devices.values() if d.is_placeholder]
      if todo:
        found.append(f"placeholder ports still unassigned: {', '.join(todo)}")
    return found


def from_dict(data: dict) -> Esp32Config:
  try:
    link = LinkSettings(**(data.get('esp32') or {}))
    devices = {name: Device(name=name, **fields) for name, fields in (data.get('devices') or {}).items()}
  except TypeError as exc:   # an unknown or misspelled field
    raise ValueError(f'bad esp32 config: {exc}') from exc
  for value in (link.reply_timeout, link.watchdog_timeout):
    if not (math.isfinite(value) and value > 0):
      raise ValueError('reply_timeout and watchdog_timeout must be > 0')
  return Esp32Config(link, devices)


def load_config(path: str) -> Esp32Config:
  import yaml  # PyYAML ships with ROS 2; imported here so the rest works without it
  with open(path, encoding='utf-8') as handle:
    return from_dict(yaml.safe_load(handle) or {})
