"""Drive backend that talks to the ESP32-S3 over UART (draft v0 message format).

The ESP32 runs electrical's firmware and drives the RoboClaws. We send tread speeds
and read encoder counts; see docs/esp32-protocol.md.
"""

from .drive_backend import DriveBackend
from .esp32_protocol import (
  READY,
  ProtocolError,
  Reply,
  encode_drive,
  encode_heartbeat,
  encode_read_battery,
  encode_read_encoders,
  encode_stop,
  mps_to_rpm,
  parse_battery,
  parse_encoders,
  parse_reply,
)
from .kinematics import DriveParams

DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 0.05  # s to wait for each reply


class Esp32Link:
  """Request/reply over a serial-like port (anything with write() and readline())."""

  def __init__(self, port):
    self._port = port

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
