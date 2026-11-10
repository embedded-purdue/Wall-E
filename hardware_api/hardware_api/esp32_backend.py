"""Drive backend that talks to the ESP32-S3 over UART (draft v0 message format).

The ESP32 runs electrical's firmware and drives the RoboClaws and the Maestro. We send
tread speeds and servo targets, and read encoders, battery and ultrasonics; see
docs/esp32-protocol.md.

There is one serial port, so every node that talks to the ESP32 must share one
Esp32Link: use Esp32Link.shared(), and run those nodes in one process
(`ros2 run hardware_api esp32_hardware`).
"""

import threading

from .drive_backend import DriveBackend
from .esp32_protocol import (
  READY,
  ProtocolError,
  Reply,
  encode_drive,
  encode_heartbeat,
  encode_read_battery,
  encode_read_encoders,
  encode_read_servo,
  encode_read_ultrasonic,
  encode_servo,
  encode_stop,
  mps_to_rpm,
  parse_battery,
  parse_encoders,
  parse_reply,
  parse_servo,
  parse_ultrasonic,
)
from .kinematics import DriveParams

DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 0.05  # s to wait for each reply


class Esp32Link:
  """Request/reply over a serial-like port (anything with write() and readline())."""

  _shared: dict[str, 'Esp32Link'] = {}
  _shared_lock = threading.Lock()

  def __init__(self, port):
    self._port = port
    self._lock = threading.Lock()  # one request/reply at a time, even from several nodes

  @classmethod
  def shared(cls, device: str, baud: int = DEFAULT_BAUD, timeout: float = DEFAULT_TIMEOUT):
    """The one link for this device in this process; opened on first use."""
    with cls._shared_lock:
      if device not in cls._shared:
        cls._shared[device] = cls.open(device, baud, timeout)
      return cls._shared[device]

  @classmethod
  def open(cls, device: str, baud: int = DEFAULT_BAUD, timeout: float = DEFAULT_TIMEOUT):
    import serial  # pyserial; imported here so tests and the mock backend don't need it

    # dsrdtr/rtscts off and DTR/RTS low so opening the port does not reset the ESP32.
    port = serial.Serial(device, baud, timeout=timeout, dsrdtr=False, rtscts=False)
    port.dtr = False
    port.rts = False
    return cls(port)

  def request(self, line: bytes) -> Reply:
    """Send one command and return its reply, skipping a READY left over from a reboot."""
    with self._lock:
      self._port.write(line)
      reply = parse_reply(self._port.readline())
      if reply.kind == READY:
        reply = parse_reply(self._port.readline())
    if reply.kind == 'ERR':
      raise ProtocolError('ESP32 error: ' + ' '.join(reply.args))
    return reply

  def drive(self, left_rpm: float, right_rpm: float) -> None:
    self._expect_ok(self.request(encode_drive(left_rpm, right_rpm)), 'D')

  def stop(self) -> None:
    self._expect_ok(self.request(encode_stop()), 'S')

  def heartbeat(self) -> None:
    self._expect_ok(self.request(encode_heartbeat()), 'H')

  def read_encoders(self) -> tuple[int, int]:
    return parse_encoders(self.request(encode_read_encoders()))

  def read_battery(self) -> float:
    return parse_battery(self.request(encode_read_battery()))

  def read_ultrasonic(self) -> list[float | None]:
    return parse_ultrasonic(self.request(encode_read_ultrasonic()))

  def set_servo(self, channel: int, pulse_us: float) -> None:
    self._expect_ok(self.request(encode_servo(channel, pulse_us)), 'P')

  def read_servo(self, channel: int) -> float:
    return parse_servo(self.request(encode_read_servo(channel)), channel)

  def close(self) -> None:
    self._port.close()

  @staticmethod
  def _expect_ok(reply: Reply, command: str) -> None:
    if reply.kind != 'OK' or reply.args != (command,):
      raise ProtocolError(f'expected "OK {command}", got {reply}')


class Esp32DriveBackend(DriveBackend):
  """Left tread = first value, right tread = second; positive RPM drives forward."""

  def __init__(self, params: DriveParams, link: Esp32Link):
    self._params = params
    self._link = link

  def set_wheel_speeds(self, left: float, right: float) -> None:
    radius = self._params.wheel_radius
    self._link.drive(mps_to_rpm(left, radius), mps_to_rpm(right, radius))

  def stop(self) -> None:
    self._link.stop()

  def read_encoders(self) -> tuple[int, int]:
    return self._link.read_encoders()
