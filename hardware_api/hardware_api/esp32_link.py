"""Jetson side of the ESP32 link: send a command, wait for its reply. No ROS imports.

One request at a time (guarded by a lock, so several ROS callbacks may share a link).
A lost or garbled reply is retried with the SAME seq; the firmware must not run it twice.
"""
import threading
import time
from abc import ABC, abstractmethod

from esp32_protocol import EVENT_SEQ, MAX_SEQ, ProtocolError, decode, encode


class Esp32Error(RuntimeError):
  """Base class for link failures."""


class Esp32Timeout(Esp32Error):
  """No valid reply after all retries. Treat the ESP32 as unreachable."""


class Esp32Refused(Esp32Error):
  """The ESP32 answered ERR; it changed nothing."""

  def __init__(self, reason: str):
    super().__init__(reason)
    self.reason = reason


class Transport(ABC):
  """Byte pipe to the ESP32 (serial port, or the fake one in tests)."""

  @abstractmethod
  def write(self, data: bytes) -> None: ...

  @abstractmethod
  def readline(self, timeout: float) -> bytes:
    """One line including '\\n', or b'' / a partial line if `timeout` seconds pass first."""

  def close(self) -> None:
    pass


class SerialTransport(Transport):
  def __init__(self, port: str, baud: int):
    import serial  # pyserial; imported here so the rest works without it
    self._serial = serial.Serial(port, baud, timeout=0)

  def write(self, data: bytes) -> None:
    self._serial.write(data)
    self._serial.flush()

  def readline(self, timeout: float) -> bytes:
    self._serial.timeout = timeout
    return self._serial.readline()

  def close(self) -> None:
    self._serial.close()


class Esp32Link:
  def __init__(self, transport: Transport, reply_timeout: float = 0.1, retries: int = 2,
               clock=time.monotonic):
    self._transport = transport
    self._reply_timeout = reply_timeout
    self._retries = retries
    self._clock = clock
    self._lock = threading.RLock()
    self._seq = 0
    self._events: list[tuple[str, tuple[str, ...]]] = []
    self.bad_frames = 0   # garbled replies seen; a number that keeps growing means a bad cable or baud

  # ---- core ---------------------------------------------------------------
  def request(self, verb: str, *args) -> tuple[str, ...]:
    """Send one command; return the reply values. Raises Esp32Refused or Esp32Timeout."""
    with self._lock:
      self._seq = self._seq % MAX_SEQ + 1
      seq = self._seq
      frame = encode(seq, verb, *args)
      for _ in range(self._retries + 1):
        self._transport.write(frame)
        deadline = self._clock() + self._reply_timeout
        while self._clock() < deadline:
          raw = self._transport.readline(max(0.0, deadline - self._clock()))
          if not raw:
            break
          try:
            reply = decode(raw)
          except ProtocolError:
            self.bad_frames += 1
            continue
          if reply.seq == EVENT_SEQ:
            if reply.verb == 'EVT' and reply.args:
              self._events.append((reply.args[0], reply.args[1:]))
            continue
          if reply.seq != seq:
            continue              # a late reply to an earlier request
          if reply.verb == 'OK':
            return reply.args
          if reply.verb == 'ERR':
            raise Esp32Refused(reply.args[0] if reply.args else 'unknown')
          self.bad_frames += 1
      raise Esp32Timeout(f'no reply to {verb} after {self._retries + 1} tries')

  def pop_events(self) -> list[tuple[str, tuple[str, ...]]]:
    """Unsolicited messages from the ESP32 (e.g. ('watchdog', ())), oldest first."""
    with self._lock:
      events, self._events = self._events, []
      return events

  def close(self) -> None:
    try:
      self.stop()
    except Esp32Error:
      pass
    self._transport.close()

  # ---- one method per verb ---------------------------------------------------
  def ping(self) -> str:
    args = self.request('PING')
    return args[0] if args else ''

  def heartbeat(self) -> None:
    self.request('HB')

  def stop(self, ports=()) -> None:
    """Stop these motors now (none listed = every motor)."""
    self.request('STOP', *ports)

  def motors(self, speeds: dict) -> None:
    """{port: permille}"""
    self.request('MOT', *[x for port, pm in speeds.items() for x in (port, pm)])

  def turn(self, moves: dict) -> None:
    """{port: (degrees_from_now, permille)}"""
    self.request('TURN', *[x for port, (deg, pm) in moves.items() for x in (port, deg, pm)])

  def goto(self, moves: dict) -> None:
    """{port: (absolute_degrees, permille)}"""
    self.request('GOTO', *[x for port, (deg, pm) in moves.items() for x in (port, deg, pm)])

  def servos(self, angles: dict) -> None:
    """{port: degrees}"""
    self.request('SRV', *[x for port, deg in angles.items() for x in (port, deg)])

  def dout(self, port: str, value: bool) -> None:
    self.request('DOUT', port, 1 if value else 0)

  def din(self, port: str) -> bool:
    return self._ints(self.request('DIN', port), 1)[0] != 0

  def encoders(self, ports) -> list[int]:
    ports = list(ports)
    return self._ints(self.request('ENC', *ports), len(ports))

  def zero_encoders(self, ports) -> None:
    self.request('ENCZ', *ports)

  def range_mm(self, port: str) -> int:
    return self._ints(self.request('RNG', port), 1)[0]

  @staticmethod
  def _ints(values, count: int) -> list[int]:
    try:
      numbers = [int(v) for v in values]
    except ValueError as exc:
      raise Esp32Error(f'reply is not numeric: {values}') from exc
    if len(numbers) != count:
      raise Esp32Error(f'expected {count} values, got {len(numbers)}')
    return numbers


def open_serial_link(settings) -> Esp32Link:
  """Open the real serial port from a LinkSettings."""
  return Esp32Link(SerialTransport(settings.serial_port, settings.baud),
                   settings.reply_timeout, settings.retries)
