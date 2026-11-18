"""Bench tool: send one arm, crusher, gripper/servo or input command to the ESP32. No ROS needed.

  python3 -m hardware_api.bench_esp32 --fake inputs           # dry run, no hardware
  python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 inputs
  python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 servo 4 1500
  python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 arm 0 0 200 0
  python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 arm-read
  python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 crusher 30 --seconds 1

Raw values on purpose (Maestro channel + microseconds, arm encoder counts, crusher duty %)
so electrical can check each motor and channel before the config is filled in. The
crusher always gets `C 0` afterwards, and Ctrl+C stops it. For the treads use bench_drive.
"""

import argparse
import sys
import time

from .esp32_backend import DEFAULT_BAUD, Esp32Link
from .esp32_protocol import ProtocolError
from .fake_esp32 import FakeEsp32

HEARTBEAT_PERIOD = 0.1  # s; well inside the ESP32's 0.5 s timeout
MAX_BENCH_CRUSHER = 60  # % duty; the same cap as config/esp32.yaml


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  where = parser.add_mutually_exclusive_group(required=True)
  where.add_argument('--port', help='serial device of the ESP32, e.g. /dev/ttyUSB0 or COM5')
  where.add_argument('--fake', action='store_true', help='use a pretend ESP32 (dry run)')
  parser.add_argument('--baud', type=int, default=DEFAULT_BAUD)
  sub = parser.add_subparsers(dest='command', required=True)
  servo = sub.add_parser('servo', help='move a Maestro channel to a pulse width (P)')
  servo.add_argument('channel', type=int)
  servo.add_argument('us', type=float, help='pulse width in microseconds, e.g. 1500 = center')
  sub.add_parser('servo-read', help="read a Maestro channel's pulse width (Q)").add_argument('channel', type=int)
  arm = sub.add_parser('arm', help='move the arm motors to absolute encoder counts (A)')
  arm.add_argument('counts', type=int, nargs='+', help='one per arm motor, in firmware order')
  sub.add_parser('arm-read', help='read the arm encoder counts (J)')
  crusher = sub.add_parser('crusher', help='run the crusher for a few seconds, then stop (C)')
  crusher.add_argument('percent', type=float, help=f'duty %%, 1..{MAX_BENCH_CRUSHER}')
  crusher.add_argument('--seconds', type=float, default=1.0)
  sub.add_parser('inputs', help='read the switch inputs (I)')
  return parser


def run_crusher(link: Esp32Link, percent: float, seconds: float,
                sleep=time.sleep, clock=time.monotonic) -> None:
  """Run the crusher at percent for seconds, keeping the link alive, then always stop it."""
  try:
    link.set_crusher(percent)
    end = clock() + seconds
    while clock() < end:
      link.heartbeat()
      sleep(HEARTBEAT_PERIOD)
  finally:
    link.set_crusher(0.0)


def run(args, link: Esp32Link) -> None:
  if args.command == 'servo':
    link.set_servo(args.channel, args.us)
    print(f'channel {args.channel} -> {args.us:.0f} us')
  elif args.command == 'servo-read':
    print(f'channel {args.channel}: {link.read_servo(args.channel):.0f} us')
  elif args.command == 'arm':
    link.set_arm(args.counts)
    print('arm target sent; now at', ' '.join(str(c) for c in link.read_arm()))
  elif args.command == 'arm-read':
    print(' '.join(str(c) for c in link.read_arm()))
  elif args.command == 'crusher':
    print(f'crusher at {args.percent:.0f} % for {args.seconds:.1f} s')
    run_crusher(link, args.percent, args.seconds)
    print('crusher stopped')
  elif args.command == 'inputs':
    for name, value in link.read_inputs().items():
      print(f'{name:16} {int(value)}')


def main(argv=None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  if args.command == 'crusher' and not 0 < args.percent <= MAX_BENCH_CRUSHER:
    parser.error(f'crusher percent must be between 0 and {MAX_BENCH_CRUSHER} for a bench test')
  if args.fake:
    fake = FakeEsp32(send_ready=False)
    fake.inputs = dict.fromkeys(fake.inputs, True)  # dry run: every switch closed
    link = Esp32Link(fake)
  else:
    link = Esp32Link.open(args.port, args.baud)
  try:
    run(args, link)
  except ProtocolError as exc:
    print(f'error: {exc}', file=sys.stderr)
    return 1
  except KeyboardInterrupt:
    print('\nstopping')
  finally:
    link.close()
  return 0


if __name__ == '__main__':
  sys.exit(main())
