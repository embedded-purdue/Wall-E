"""A pretend ESP32 for tests and bench dry runs. No ROS imports.

Speaks the protocol in esp32_protocol.py and does what the real firmware must do: drops
frames with a bad checksum, resends the cached reply for a repeated seq instead of running
the command twice, refuses unknown ports, and stops the motors if no valid frame arrives
for watchdog_timeout. Motors turn at full_speed_dps * permille / 1000.
"""
import math
import time
from collections import deque
from dataclasses import dataclass

from esp32_link import Transport
from esp32_protocol import EVENT_SEQ, ProtocolError, decode, encode


class _Refused(Exception):
  pass


@dataclass
class _Motor:
  ticks_per_rev: int
  deg: float = 0.0
  mode: str = 'idle'    # idle | speed | pos
  permille: int = 0
  target: float = 0.0


class FakeEsp32:
  def __init__(self, ports: dict, watchdog_timeout: float = 0.5,
               full_speed_dps: float = 360.0, clock=time.monotonic):
    """ports: {port: (kind, ticks_per_rev)}"""
    self._kinds = {port: kind for port, (kind, _) in ports.items()}
    self._motors = {port: _Motor(ticks) for port, (kind, ticks) in ports.items() if kind == 'motor'}
    self.servos: dict = {}
    self.inputs = {port: 0 for port, kind in self._kinds.items() if kind == 'din'}
    self.outputs = {port: 0 for port, kind in self._kinds.items() if kind == 'dout'}
    self.ranges = {port: 1000 for port, kind in self._kinds.items() if kind == 'range'}
    self._watchdog = watchdog_timeout
    self._full = full_speed_dps
    self._clock = clock
    self._t = clock()
    self._last_rx = None
    self._events: list[str] = []
    self._last_seq = None
    self._last_reply: list[bytes] = []

  @classmethod
  def from_config(cls, config, **kwargs):
    ports = {d.port: (d.kind, d.ticks_per_rev) for d in config.devices.values()}
    kwargs.setdefault('watchdog_timeout', config.link.watchdog_timeout)
    return cls(ports, **kwargs)

  def motor(self, port: str) -> _Motor:
    return self._motors[port]

  # ---- physics and watchdog -----------------------------------------------------
  def _integrate(self, t: float) -> None:
    dt = t - self._t
    if dt <= 0:
      return
    self._t = t
    for m in self._motors.values():
      if m.mode == 'speed':
        m.deg += m.permille / 1000.0 * self._full * dt
      elif m.mode == 'pos':
        step = abs(m.permille) / 1000.0 * self._full * dt
        gap = m.target - m.deg
        if abs(gap) <= step:
          m.deg, m.mode, m.permille = m.target, 'idle', 0
        else:
          m.deg += math.copysign(step, gap)

  def _stop_motors(self, ports=None) -> None:
    for port in (ports if ports is not None else self._motors):
      self._motors[port].mode, self._motors[port].permille = 'idle', 0

  def _advance(self, now: float) -> None:
    moving = any(m.mode != 'idle' for m in self._motors.values())
    if moving and self._last_rx is not None and now - self._last_rx > self._watchdog:
      self._integrate(self._last_rx + self._watchdog)   # it kept moving until the watchdog fired
      self._stop_motors()
      self._events.append('watchdog')
    self._integrate(now)

  def _drain_events(self) -> list[bytes]:
    frames = [encode(EVENT_SEQ, 'EVT', name) for name in self._events]
    self._events = []
    return frames

  # ---- protocol -------------------------------------------------------------------
  def poll(self) -> list[bytes]:
    """Unsolicited lines (events) that are waiting."""
    self._advance(self._clock())
    return self._drain_events()

  def handle(self, line: bytes) -> list[bytes]:
    """Process one received line; return the lines the ESP32 would send back."""
    now = self._clock()
    self._advance(now)
    try:
      frame = decode(line)
    except ProtocolError:
      return []                       # garbage is dropped silently and does not feed the watchdog
    self._last_rx = now
    out = self._drain_events()
    if frame.seq == self._last_seq:   # a retry: repeat the answer, do not repeat the action
      return out + list(self._last_reply)
    try:
      reply = encode(frame.seq, 'OK', *self._execute(frame))
    except _Refused as exc:
      reply = encode(frame.seq, 'ERR', str(exc))
    except (ValueError, IndexError):
      reply = encode(frame.seq, 'ERR', 'bad_args')
    self._last_seq, self._last_reply = frame.seq, [reply]
    return out + [reply]

  def _execute(self, frame) -> list:
    handler = getattr(self, '_do_' + frame.verb.lower(), None)
    if handler is None:
      raise _Refused('unknown_verb')
    return handler(frame.args)

  def _check(self, port: str, kind: str) -> str:
    if port not in self._kinds:
      raise _Refused('unknown_port')
    if self._kinds[port] != kind:
      raise _Refused('wrong_port_kind')
    return port

  @staticmethod
  def _groups(args, size: int) -> list:
    if not args or len(args) % size:
      raise _Refused('bad_args')
    return [args[i:i + size] for i in range(0, len(args), size)]

  def _do_ping(self, args):
    return ['FAKE-0.1']

  def _do_hb(self, args):
    return []

  def _do_stop(self, args):
    ports = [self._check(p, 'motor') for p in args] if args else list(self._motors)
    self._stop_motors(ports)
    return []

  def _do_mot(self, args):
    todo = [(self._check(p, 'motor'), int(v)) for p, v in self._groups(args, 2)]
    if any(not -1000 <= pm <= 1000 for _, pm in todo):
      raise _Refused('range')
    for port, pm in todo:
      m = self._motors[port]
      m.mode, m.permille = ('speed' if pm else 'idle'), pm
    return []

  def _move(self, args, relative: bool):
    todo = [(self._check(p, 'motor'), float(d), int(s)) for p, d, s in self._groups(args, 3)]
    if any(not 1 <= s <= 1000 for _, _, s in todo):
      raise _Refused('range')
    for port, deg, speed in todo:
      m = self._motors[port]
      m.target = m.deg + deg if relative else deg
      m.mode, m.permille = 'pos', speed
    return []

  def _do_turn(self, args):
    return self._move(args, relative=True)

  def _do_goto(self, args):
    return self._move(args, relative=False)

  def _do_srv(self, args):
    todo = [(self._check(p, 'servo'), float(d)) for p, d in self._groups(args, 2)]
    if any(not -180.0 <= d <= 180.0 for _, d in todo):
      raise _Refused('range')
    self.servos.update(todo)
    return []

  def _do_dout(self, args):
    if len(args) != 2 or args[1] not in ('0', '1'):
      raise _Refused('bad_args')
    self.outputs[self._check(args[0], 'dout')] = int(args[1])
    return []

  def _do_din(self, args):
    if len(args) != 1:
      raise _Refused('bad_args')
    return [str(self.inputs[self._check(args[0], 'din')])]

  def _do_enc(self, args):
    if not args:
      raise _Refused('bad_args')
    motors = [self._motors[self._check(p, 'motor')] for p in args]
    return [str(round(m.deg / 360.0 * m.ticks_per_rev)) for m in motors]

  def _do_encz(self, args):
    if not args:
      raise _Refused('bad_args')
    for port in [self._check(p, 'motor') for p in args]:
      m = self._motors[port]
      m.deg, m.target, m.mode, m.permille = 0.0, 0.0, 'idle', 0
    return []

  def _do_rng(self, args):
    if len(args) != 1:
      raise _Refused('bad_args')
    return [str(self.ranges[self._check(args[0], 'range')])]


class LoopbackTransport(Transport):
  """Connects an Esp32Link straight to a FakeEsp32. The two knobs break the link on purpose."""

  def __init__(self, fake: FakeEsp32):
    self._fake = fake
    self._rx: deque = deque()
    self.sent: list[bytes] = []
    self.corrupt_next_writes = 0   # damage this many outgoing frames
    self.drop_next_replies = 0     # lose this many replies (the ESP32 still ran the command)

  def write(self, data: bytes) -> None:
    for line in data.splitlines(keepends=True):
      self.sent.append(line)
      if self.corrupt_next_writes > 0:
        self.corrupt_next_writes -= 1
        line = b'X' + line[1:]
      replies = self._fake.handle(line)
      if self.drop_next_replies > 0 and replies:
        self.drop_next_replies -= 1
        continue
      self._rx.extend(replies)

  def readline(self, timeout: float) -> bytes:
    if not self._rx:
      self._rx.extend(self._fake.poll())
    return self._rx.popleft() if self._rx else b''
