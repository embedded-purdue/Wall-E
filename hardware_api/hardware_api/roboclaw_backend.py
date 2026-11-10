"""RoboClaw drive backend. STUB: not implemented until wiring is decided.

Per electrical's notes: packet serial, address 0x80, 38400 baud.
Open questions (see docs/drive-open-questions.md):
  - Is the RoboClaw driven from the Jetson directly or through the ESP32?
  - Are the encoders wired to the RoboClaw or the ESP32?
"""

from .drive_backend import DriveBackend
from .kinematics import DriveParams

DEFAULT_ADDRESS = 0x80
DEFAULT_BAUD = 38400


class RoboClawBackend(DriveBackend):
  """One RoboClaw driving the left (M1) and right (M2) drive motors. Stub only."""

  def __init__(
    self,
    params: DriveParams,
    port: str,
    address: int = DEFAULT_ADDRESS,
    baud: int = DEFAULT_BAUD,
  ):
    # TODO: open the serial port once the Jetson/ESP32 link is decided.
    # TODO: confirm the RoboClaw serial timeout is enabled so motors stop if we go silent.
    self._params = params
    self._port = port
    self._address = address
    self._baud = baud

  def set_wheel_speeds(self, left: float, right: float) -> None:
    # TODO: convert m/s to encoder counts/s and send a closed-loop speed command.
    # TODO: confirm M1/M2 to left/right mapping and motor direction signs.
    raise NotImplementedError('RoboClawBackend.set_wheel_speeds: wiring not decided')

  def stop(self) -> None:
    # TODO: command zero speed on both motors.
    raise NotImplementedError('RoboClawBackend.stop: wiring not decided')

  def read_encoders(self) -> tuple[int, int]:
    # TODO: read both encoders here only if they are wired to the RoboClaw.
    raise NotImplementedError('RoboClawBackend.read_encoders: encoder wiring not decided')
