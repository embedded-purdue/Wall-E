"""Pretend ESP32 that speaks the draft v0 message format (drive, servos, arm, crusher, sensors). For tests and dry runs.

Behaves like a serial port: write() a command line, readline() the reply.
Mirrors the firmware rules we are asking electrical for: boot stopped, stop when no
command arrives within timeout (treads and crusher; the arm holds), ideal encoders,
arm motors that reach their target at once, and a crusher that refuses to start
unless chamber_closed, lock_engaged and contents_ok are all set.
"""

import math
import time

from .esp32_protocol import INPUTS, READY


class FakeEsp32:

  def __init__(self, counts_per_rev: int = 8192, timeout: float = 0.5,
               battery_volts: float = 20.0, clock=time.monotonic, send_ready: bool = True,
               ultrasonic: tuple = (1.5,), servo_limits: dict | None = None,
               rotate_rpm: float = 60.0, arm_motors: int = 4):
    self.counts_per_rev = counts_per_rev
    self.timeout = timeout
    self.battery_volts = battery_volts
    self.rpm = [0.0, 0.0]
    self.rotate_rpm = rotate_rpm  # how fast an R move turns the sprockets
    self.targets: list[float | None] = [None, None]  # encoder count an R move is heading to
    self.timed_out = False
    self.log = []  # every command line received, for tests
    self._clock = clock
    self._counts = [0.0, 0.0]
    self._last = clock()
    self._last_command = self._last
    self._replies = [READY] if send_ready else []
    self.ultrasonic = list(ultrasonic)  # meters, None = no echo
    self.servos: dict[int, float] = {}  # channel -> pulse width us
    # channel -> (min_us, max_us) the firmware refuses outside of; default 500..2500 for any channel
    self.servo_limits = servo_limits or {}
    self.arm = [0] * arm_motors  # arm encoder counts (ideal: at the target as soon as it is sent)
    self.crusher = 0  # crusher duty %, 0 = stopped
    self.inputs = {name: False for name in INPUTS}  # switch inputs; set them in tests

  def _advance(self) -> None:
    now = self._clock()
    # Motors run until the timeout, then the firmware stops them.
    run_until = min(now, self._last_command + self.timeout)
    dt = max(0.0, run_until - self._last)
    for i in (0, 1):
      if self.targets[i] is None:
        self._counts[i] += self.rpm[i] / 60.0 * self.counts_per_rev * dt
      else:  # R move: run toward the target, then stop there
        gap = self.targets[i] - self._counts[i]
        step = self.rotate_rpm / 60.0 * self.counts_per_rev * dt
        if abs(gap) <= step:
          self._counts[i], self.targets[i] = self.targets[i], None
        else:
          self._counts[i] += math.copysign(step, gap)
    if now - self._last_command > self.timeout and (self.rpm != [0.0, 0.0] or self.moving or self.crusher):
      self.rpm = [0.0, 0.0]
      self.targets = [None, None]
      self.crusher = 0
      self.timed_out = True
    # The firmware's own interlock: a switch opening stops the crusher at once.
    if self.crusher and not self._crusher_safe():
      self.crusher = 0
    self._last = now

  def write(self, data: bytes) -> int:
    self._advance()
    text = data.decode('ascii').strip()
    self.log.append(text)
    self._last_command = self._clock()
    kind, *args = text.split() or ['']
    if kind == 'D' and len(args) == 2:
      try:
        self.rpm = [float(args[0]), float(args[1])]
        self.targets = [None, None]
        self._replies.append('OK D')
      except ValueError:
        self._replies.append('ERR bad_args')
    elif kind == 'R' and len(args) == 2:
      try:
        revs = [float(args[0]), float(args[1])]
      except ValueError:
        self._replies.append('ERR bad_args')
      else:
        self.rpm = [0.0, 0.0]
        self.targets = [self._counts[i] + revs[i] * self.counts_per_rev for i in (0, 1)]
        self._replies.append('OK R')
    elif kind == 'S' and not args:
      self.rpm = [0.0, 0.0]
      self.targets = [None, None]
      self.crusher = 0
      self._replies.append('OK S')
    elif kind == 'H' and not args:
      self._replies.append('OK H')
    elif kind == 'E' and not args:
      self._replies.append(f'E {round(self._counts[0])} {round(self._counts[1])}')
    elif kind == 'B' and not args:
      self._replies.append(f'B {self.battery_volts:.2f}')
    elif kind == 'U' and not args:
      self._replies.append('U ' + ' '.join('-1' if d is None else f'{d:.3f}' for d in self.ultrasonic))
    elif kind == 'P' and len(args) == 2:
      try:
        channel, pulse = int(args[0]), float(args[1])
      except ValueError:
        self._replies.append('ERR bad_args')
      else:
        lo, hi = self.servo_limits.get(channel, (500.0, 2500.0))
        if lo <= pulse <= hi:
          self.servos[channel] = pulse
          self._replies.append('OK P')
        else:
          self._replies.append('ERR out_of_range')
    elif kind == 'Q' and len(args) == 1:
      try:
        channel = int(args[0])
      except ValueError:
        self._replies.append('ERR bad_args')
      else:
        self._replies.append(f'Q {channel} {round(self.servos.get(channel, 0.0))}')
    elif kind == 'A' and args:
      try:
        counts = [int(arg) for arg in args]
      except ValueError:
        self._replies.append('ERR bad_args')
      else:
        if len(counts) != len(self.arm):
          self._replies.append('ERR bad_args')
        else:
          self.arm = counts
          self._replies.append('OK A')
    elif kind == 'J' and not args:
      self._replies.append('J ' + ' '.join(str(c) for c in self.arm))
    elif kind == 'C' and len(args) == 1:
      try:
        duty = int(args[0])
      except ValueError:
        self._replies.append('ERR bad_args')
      else:
        if not 0 <= duty <= 100:
          self._replies.append('ERR out_of_range')
        elif duty and not self._crusher_safe():
          self.crusher = 0
          self._replies.append('ERR interlock')
        else:
          self.crusher = duty
          self._replies.append('OK C')
    elif kind == 'I' and not args:
      self._replies.append('I ' + ' '.join('1' if self.inputs[name] else '0' for name in INPUTS))
    else:
      self._replies.append('ERR unknown_command')
    return len(data)

  def _crusher_safe(self) -> bool:
    return all(self.inputs[name] for name in ('chamber_closed', 'lock_engaged', 'contents_ok'))

  @property
  def moving(self) -> bool:
    """True while an R move is still turning a sprocket."""
    return any(t is not None for t in self.targets)

  def readline(self) -> bytes:
    if not self._replies:
      return b''  # what pyserial returns on timeout
    return (self._replies.pop(0) + '\n').encode('ascii')

  def close(self) -> None:
    pass
