"""Jetson <-> ESP32 message format (draft v0, see docs/esp32-protocol.md). No ROS imports.

One ASCII line per message, ending in '\n'. The Jetson sends a command and the ESP32
answers with exactly one line.

  Jetson -> ESP32            ESP32 -> Jetson
  D <left_rpm> <right_rpm>   OK D           set tread speeds (closed loop), wheel RPM
  S                          OK S           stop all motors
  H                          OK H           heartbeat, nothing else to say
  E                          E <left> <right>   cumulative encoder counts
  B                          B <volts>      battery voltage
  U                          U <m> [<m> ...]  ultrasonic distances in meters (-1 = no echo)
  P <channel> <us>           OK P           move Maestro servo channel to a pulse width (us)
  Q <channel>                Q <channel> <us>   Maestro's current pulse width for that channel
  (any)                      ERR <reason>   command refused or not understood
  (on boot)                  READY          sent once, motors stopped
"""

import math
from dataclasses import dataclass

READY = 'READY'


class ProtocolError(Exception):
  """The ESP32 sent something we did not expect, or reported ERR."""


@dataclass(frozen=True)
class Reply:
  kind: str  # 'OK', 'E', 'B', 'ERR' or 'READY'
  args: tuple[str, ...] = ()


def encode_drive(left_rpm: float, right_rpm: float) -> bytes:
  if not (math.isfinite(left_rpm) and math.isfinite(right_rpm)):
    raise ValueError('drive RPM must be finite')
  return f'D {left_rpm:.2f} {right_rpm:.2f}\n'.encode('ascii')


def encode_stop() -> bytes:
  return b'S\n'


def encode_heartbeat() -> bytes:
  return b'H\n'


def encode_read_encoders() -> bytes:
  return b'E\n'


def encode_read_battery() -> bytes:
  return b'B\n'


def encode_read_ultrasonic() -> bytes:
  return b'U\n'


def encode_servo(channel: int, pulse_us: float) -> bytes:
  if channel < 0 or not math.isfinite(pulse_us) or pulse_us <= 0:
    raise ValueError(f'bad servo command: channel {channel}, {pulse_us} us')
  return f'P {int(channel)} {round(pulse_us)}\n'.encode('ascii')


def encode_read_servo(channel: int) -> bytes:
  if channel < 0:
    raise ValueError(f'bad servo channel {channel}')
  return f'Q {int(channel)}\n'.encode('ascii')


def parse_reply(line: bytes) -> Reply:
  """Split one line from the ESP32 into a Reply. Raises ProtocolError on junk."""
  try:
    text = line.decode('ascii').strip()
  except UnicodeDecodeError as exc:
    raise ProtocolError(f'non-ASCII reply: {line!r}') from exc
  if not text:
    raise ProtocolError('empty reply (timed out?)')
  kind, *args = text.split()
  if kind not in ('OK', 'E', 'B', 'U', 'Q', 'ERR', READY):
    raise ProtocolError(f'unknown reply: {text!r}')
  return Reply(kind, tuple(args))


def parse_encoders(reply: Reply) -> tuple[int, int]:
  if reply.kind != 'E' or len(reply.args) != 2:
    raise ProtocolError(f'expected "E <left> <right>", got {reply}')
  try:
    return int(reply.args[0]), int(reply.args[1])
  except ValueError as exc:
    raise ProtocolError(f'bad encoder counts: {reply.args}') from exc


def parse_battery(reply: Reply) -> float:
  if reply.kind != 'B' or len(reply.args) != 1:
    raise ProtocolError(f'expected "B <volts>", got {reply}')
  try:
    return float(reply.args[0])
  except ValueError as exc:
    raise ProtocolError(f'bad battery voltage: {reply.args}') from exc


def parse_ultrasonic(reply: Reply) -> list[float | None]:
  """Distances in meters, one per sensor; None where the sensor got no echo (-1)."""
  if reply.kind != 'U' or not reply.args:
    raise ProtocolError(f'expected "U <m> ...", got {reply}')
  try:
    values = [float(arg) for arg in reply.args]
  except ValueError as exc:
    raise ProtocolError(f'bad ultrasonic distances: {reply.args}') from exc
  return [None if v < 0 else v for v in values]


def parse_servo(reply: Reply, channel: int) -> float:
  if reply.kind != 'Q' or len(reply.args) != 2:
    raise ProtocolError(f'expected "Q <channel> <us>", got {reply}')
  try:
    got_channel, pulse = int(reply.args[0]), float(reply.args[1])
  except ValueError as exc:
    raise ProtocolError(f'bad servo reply: {reply.args}') from exc
  if got_channel != channel:
    raise ProtocolError(f'asked for servo {channel}, got {got_channel}')
  return pulse


def mps_to_rpm(speed: float, wheel_radius: float) -> float:
  """Wheel rim speed in m/s to wheel RPM."""
  return speed / (2.0 * math.pi * wheel_radius) * 60.0
