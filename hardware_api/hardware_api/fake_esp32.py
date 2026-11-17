"""Pretend ESP32 that speaks the draft v0 message format (drive, servos, sensors). For tests and dry runs.

Behaves like a serial port: write() a command line, readline() the reply.
Mirrors the firmware rules we are asking electrical for: boot stopped, stop when no
command arrives within timeout, ideal encoders.
"""

import math
import time

from .esp32_protocol import READY


class FakeEsp32:

  def __init__(self, counts_per_rev: int = 8192, timeout: float = 0.5,
               battery_volts: float = 20.0, clock=time.monotonic, send_ready: bool = True,
               ultrasonic: tuple = (1.5,), servo_limits: dict | None = None,
               rotate_rpm: float = 60.0):
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
    if now - self._last_command > self.timeout and (self.rpm != [0.0, 0.0] or self.moving):
      self.rpm = [0.0, 0.0]
      self.targets = [None, None]
      self.timed_out = True
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
    else:
      self._replies.append('ERR unknown_command')
    return len(data)

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
