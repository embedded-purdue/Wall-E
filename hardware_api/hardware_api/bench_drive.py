"""Bench test for the drive treads through the ESP32. No ROS needed.

  python3 -m hardware_api.bench_drive --port /dev/ttyUSB0
  python3 -m hardware_api.bench_drive --fake        # dry run, no hardware

Spins the left tread, then the right, then both, each for a few seconds at a low speed,
and prints the encoder counts after each step. Use it to check which motor is left,
which way is forward, and how many counts one turn gives. Ctrl+C stops the motors.
"""

import argparse
import sys
import time

from .esp32_backend import DEFAULT_BAUD, Esp32Link
from .fake_esp32 import FakeEsp32

HEARTBEAT_PERIOD = 0.1  # s; well inside the ESP32's 0.5 s timeout


def run_step(link: Esp32Link, name: str, left_rpm: float, right_rpm: float, seconds: float,
             sleep=time.sleep, clock=time.monotonic) -> tuple[int, int]:
  """Drive at (left_rpm, right_rpm) for seconds, then stop; return the change in counts."""
  start = link.read_encoders()
  print(f'{name}: left {left_rpm:+.1f} RPM, right {right_rpm:+.1f} RPM for {seconds:.1f} s')
  end_time = clock() + seconds
  try:
    while clock() < end_time:
      link.drive(left_rpm, right_rpm)  # resending is also the heartbeat
      sleep(HEARTBEAT_PERIOD)
  finally:
    link.stop()
  end = link.read_encoders()
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
  args = parser.parse_args(argv)

  if args.rpm <= 0 or args.rpm > 30:
    parser.error('--rpm must be between 0 and 30 for a bench test')

  link = Esp32Link(FakeEsp32()) if args.fake else Esp32Link.open(args.port, args.baud)
  try:
    link.stop()
    print(f'battery: {link.read_battery():.2f} V')
    run_step(link, 'left tread only', args.rpm, 0.0, args.seconds)
    run_step(link, 'right tread only', 0.0, args.rpm, args.seconds)
    run_step(link, 'both forward', args.rpm, args.rpm, args.seconds)
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
  return 0


if __name__ == '__main__':
  sys.exit(main())
