"""Backends that carry the hardware_api backend interfaces over the ESP32 link.

Each takes an Esp32Link and an Esp32Config, so changing a port, direction, limit or speed
cap is a config/esp32.yaml edit, not a code change. No ROS imports.
"""
import math

from crusher import CrusherBackend, CrusherSafety
from drive_backend import DriveBackend
from gripper import GripperBackend, GripperState
from joints import JointBackend


class Esp32DriveBackend(DriveBackend):
  """Two tread motors. Speeds are m/s; the wire carries permille of max_wheel_speed."""

  def __init__(self, link, config, max_wheel_speed: float,
               left: str = 'tread_left', right: str = 'tread_right'):
    if max_wheel_speed <= 0:
      raise ValueError('max_wheel_speed must be > 0')
    self._link = link
    self._max = max_wheel_speed
    self._left = config.device(left, 'motor')
    self._right = config.device(right, 'motor')

  def set_wheel_speeds(self, left: float, right: float) -> None:
    self._link.motors({
      self._left.port: self._left.wire_permille(left / self._max * 1000.0),
      self._right.port: self._right.wire_permille(right / self._max * 1000.0),
    })

  def stop(self) -> None:
    self._link.stop([self._left.port, self._right.port])

  def read_encoders(self) -> tuple[int, int]:
    left, right = self._link.encoders([self._left.port, self._right.port])
    return (-left if self._left.invert else left), (-right if self._right.invert else right)


class Esp32JointBackend(JointBackend):
  """Servos (SRV) and encoder-equipped motors (GOTO) addressed by joint name in radians.

  The joint name is the device name in esp32.yaml. Only joints whose angle changed by more
  than epsilon_deg are sent, which keeps a 50 Hz control loop from flooding the serial line.
  """

  def __init__(self, link, config, joints, epsilon_deg: float = 0.5):
    self._link = link
    self._devices = {name: config.device(name) for name in joints}
    for name, device in self._devices.items():
      if device.kind not in ('servo', 'motor'):
        raise ValueError(f"joint '{name}' is a {device.kind}; joints must be servo or motor")
    self._epsilon = epsilon_deg
    self._sent: dict = {}   # joint -> last absolute degrees sent

  def set_positions(self, positions: dict) -> None:
    unknown = [name for name in positions if name not in self._devices]
    if unknown:
      raise KeyError(f'unknown joint(s): {unknown}')
    servos, gotos, pending = {}, {}, {}
    for name, radians in positions.items():
      device = self._devices[name]
      wire = device.wire_degrees(math.degrees(radians))
      if name in self._sent and abs(wire - self._sent[name]) < self._epsilon:
        continue
      pending[name] = wire
      if device.kind == 'servo':
        servos[device.port] = wire
      else:
        gotos[device.port] = (wire, device.max_permille)
    if servos:
      self._link.servos(servos)
    if gotos:
      self._link.goto(gotos)
    self._sent.update(pending)   # only after the ESP32 accepted them, so a failure is retried

  def read_positions(self) -> dict:
    motors = [n for n, d in self._devices.items() if d.kind == 'motor']
    ticks = dict(zip(motors, self._link.encoders([self._devices[n].port for n in motors]))) if motors else {}
    result = {}
    for name, device in self._devices.items():
      if device.kind == 'motor':
        wire = ticks[name] / device.ticks_per_rev * 360.0
      else:   # servos have no feedback: report what was last commanded
        wire = self._sent.get(name, device.center_deg)
      result[name] = math.radians(device.from_wire_degrees(wire))
    return result


class Esp32GripperBackend(GripperBackend):
  """Gripper on one servo: min_deg = open, max_deg = closed. PLACEHOLDER: no position
  feedback, and 'holding' comes from a contact input (gripper_contact)."""

  def __init__(self, link, config, servo: str = 'gripper', contact: str = 'gripper_contact',
               holding_position: float = 0.5):
    self._link = link
    self._servo = config.device(servo, 'servo')
    self._contact = config.device(contact, 'din')
    self._holding_position = holding_position
    self._closed = False
    self._link.servos({self._servo.port: self._angle(False)})

  def _angle(self, closed: bool) -> float:
    return self._servo.max_deg if closed else self._servo.min_deg

  def set_closed(self, closed: bool) -> None:
    self._link.servos({self._servo.port: self._angle(closed)})
    self._closed = closed

  def read_state(self) -> GripperState:
    touching = self._link.din(self._contact.port) != self._contact.invert
    holding = self._closed and touching
    position = self._holding_position if holding else (1.0 if self._closed else 0.0)
    return GripperState(self._closed, position, holding)


class Esp32CrusherBackend(CrusherBackend):
  """Crusher motor plus three safety inputs. A link failure raises, and CrusherController
  treats an unreadable sensor as unsafe, so a dead link refuses to start and aborts a cycle."""

  def __init__(self, link, config, motor: str = 'crusher',
               chamber_closed: str = 'crusher_chamber_closed',
               lock_engaged: str = 'crusher_lock_engaged',
               contents_ok: str = 'crusher_contents_ok'):
    self._link = link
    self._motor = config.device(motor, 'motor')
    self._inputs = [config.device(n, 'din') for n in (chamber_closed, lock_engaged, contents_ok)]

  def _read(self, device) -> bool:
    return self._link.din(device.port) != device.invert

  def read_safety(self) -> CrusherSafety:
    closed, locked, ok = (self._read(d) for d in self._inputs)
    return CrusherSafety(closed, locked, ok)

  def start(self) -> None:
    self._link.motors({self._motor.port: self._motor.wire_permille(self._motor.max_permille)})

  def stop(self) -> None:
    self._link.stop([self._motor.port])
