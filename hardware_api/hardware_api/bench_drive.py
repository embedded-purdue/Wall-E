"""Bench test for the drive treads through the ESP32. No ROS needed.

  python3 -m hardware_api.bench_drive --port /dev/ttyUSB0
  python3 -m hardware_api.bench_drive --fake        # dry run, no hardware

Spins the left tread, then the right, then both, each for a few seconds at a low speed,
and prints the encoder counts after each step. Use it to check which motor is left,
which way is forward, and how many counts one turn gives. Ctrl+C stops the motors.

For PID tuning, add --log run.csv: every heartbeat it saves the speed we asked for and
the speed the wheel actually reached (from the encoders), so you can plot the two and
see how fast the wheel gets up to speed and whether it wobbles. Pass --counts-per-rev
once you know it; until then the file has raw encoder counts only.

  python3 -m hardware_api.bench_drive --port /dev/ttyUSB0 --log run.csv --counts-per-rev 8192
"""

import argparse
import csv
import sys
import time

from .esp32_backend import DEFAULT_BAUD, Esp32Link
from .fake_esp32 import FakeEsp32

HEARTBEAT_PERIOD = 0.1  # s; well inside the ESP32's 0.5 s timeout

LOG_COLUMNS = ['time_s', 'step', 'cmd_left_rpm', 'cmd_right_rpm',
               'left_counts', 'right_counts', 'left_rpm', 'right_rpm']


class SpeedLog:
  """Writes one CSV row per heartbeat: asked-for RPM vs measured RPM."""

  def __init__(self, file, counts_per_rev: float | None = None, clock=time.monotonic):
    self._writer = csv.writer(file)
    self._writer.writerow(LOG_COLUMNS)
    self._counts_per_rev = counts_per_rev
    self._clock = clock
    self._t0 = clock()
    self._last = None  # (time, left_counts, right_counts)

  def record(self, step: str, cmd_left: float, cmd_right: float, counts: tuple[int, int]) -> None:
    now = self._clock()
    left_rpm = right_rpm = ''
    if self._counts_per_rev and self._last is not None and now > self._last[0]:
      dt_min = (now - self._last[0]) / 60.0
      left_rpm = f'{(counts[0] - self._last[1]) / self._counts_per_rev / dt_min:.2f}'
      right_rpm = f'{(counts[1] - self._last[2]) / self._counts_per_rev / dt_min:.2f}'
    self._last = (now, counts[0], counts[1])
    self._writer.writerow([f'{now - self._t0:.3f}', step, f'{cmd_left:.2f}', f'{cmd_right:.2f}',
                           counts[0], counts[1], left_rpm, right_rpm])


def run_step(link: Esp32Link, name: str, left_rpm: float, right_rpm: float, seconds: float,
             sleep=time.sleep, clock=time.monotonic, log: SpeedLog | None = None) -> tuple[int, int]:
  """Drive at (left_rpm, right_rpm) for seconds, then stop; return the change in counts."""
  start = link.read_encoders()
  if log:
    log.record(name, left_rpm, right_rpm, start)
  print(f'{name}: left {left_rpm:+.1f} RPM, right {right_rpm:+.1f} RPM for {seconds:.1f} s')
  end_time = clock() + seconds
  try:
    while clock() < end_time:
      link.drive(left_rpm, right_rpm)  # resending is also the heartbeat
      sleep(HEARTBEAT_PERIOD)
      if log:
        log.record(name, left_rpm, right_rpm, link.read_encoders())
  finally:
    link.stop()
  end = link.read_encoders()
  if log:
    log.record(name + ' (stopped)', 0.0, 0.0, end)
  delta = (end[0] - start[0], end[1] - start[1])
  print(f'  counts changed by left {delta[0]:+d}, right {delta[1]:+d}')
  return delta


def main(argv=None) -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  where = parser.add_mutually_exclusive_group(required=True)
  where.add_argument('--port', help='serial device of the ESP32, e.g. /dev/ttyUSB0 or COM5')
  where.add_argument('--fake', action='store_true', help='use a pretend ESP32 (dry run)')
  parser.add_argument('--baud', type=int, default=DEFAULT_BAUD)
  parser.add_argument('--rpm', type=float, default=10.0, help='test speed in wheel RPM (default 10, keep it low)')
  parser.add_argument('--seconds', type=float, default=3.0, help='how long each step runs')
  parser.add_argument('--log', help='save asked-for vs measured speed to this CSV file (for PID tuning)')
  parser.add_argument('--counts-per-rev', type=float, default=0.0,
                      help='encoder counts per wheel turn; needed for measured RPM in the log')
  args = parser.parse_args(argv)

  if args.rpm <= 0 or args.rpm > 30:
    parser.error('--rpm must be between 0 and 30 for a bench test')

  link = Esp32Link(FakeEsp32()) if args.fake else Esp32Link.open(args.port, args.baud)
  log_file = open(args.log, 'w', newline='') if args.log else None
  log = SpeedLog(log_file, args.counts_per_rev or None) if log_file else None
  try:
    link.stop()
    print(f'battery: {link.read_battery():.2f} V')
    run_step(link, 'left tread only', args.rpm, 0.0, args.seconds, log=log)
    run_step(link, 'right tread only', 0.0, args.rpm, args.seconds, log=log)
    run_step(link, 'both forward', args.rpm, args.rpm, args.seconds, log=log)
    expected = args.rpm / 60.0 * args.seconds
    print(f'\nEach step should turn a wheel about {expected:.2f} times.')
    print('Counts per wheel turn = counts changed / that number. Put it in config/drive.yaml as ticks_per_rev.')
  except KeyboardInterrupt:
    print('\nstopping')
  finally:
    try:
      link.stop()
    finally:
      link.close()
      if log_file:
        log_file.close()
        print(f'speed log saved to {args.log}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
