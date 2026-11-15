"""Bench tool: send single commands to the ESP32 using the names in config/esp32.yaml.

  python3 -m hardware_api.esp32_bench --config config/esp32.yaml check
  python3 -m hardware_api.esp32_bench --config config/esp32.yaml ping
  python3 -m hardware_api.esp32_bench --config config/esp32.yaml motor tread_left 200 --seconds 1
  python3 -m hardware_api.esp32_bench --config config/esp32.yaml turn tread_left 90 --speed 200
  python3 -m hardware_api.esp32_bench --config config/esp32.yaml servo head_pan 20
Add --loopback to run against the fake ESP32 with no hardware. Directions and speed caps from
the config apply, exactly as in the real backends. Any motor command is followed by STOP.
"""
import argparse
import sys
import time

from .esp32_config import load_config
from .esp32_fake import FakeEsp32, LoopbackTransport
from .esp32_link import Esp32Error, Esp32Link, SerialTransport


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--config', required=True, help='path to esp32.yaml')
  parser.add_argument('--loopback', action='store_true', help='use the fake ESP32')
  parser.add_argument('--serial-port', help='override serial_port from the config')
  parser.add_argument('--baud', type=int, help='override baud from the config')
  sub = parser.add_subparsers(dest='command', required=True)
  sub.add_parser('check', help='validate the config and list devices')
  sub.add_parser('ping')
  stop = sub.add_parser('stop', help='stop motors (all if none named)')
  stop.add_argument('devices', nargs='*')
  motor = sub.add_parser('motor', help='run a motor at a speed for a few seconds')
  motor.add_argument('device')
  motor.add_argument('permille', type=int, help='-1000..1000, capped by max_permille')
  motor.add_argument('--seconds', type=float, default=1.0)
  turn = sub.add_parser('turn', help='turn a motor by degrees from now')
  turn.add_argument('device')
  turn.add_argument('degrees', type=float)
  turn.add_argument('--speed', type=int, default=200, help='permille, capped by max_permille')
  servo = sub.add_parser('servo', help='move a servo to degrees from its center')
  servo.add_argument('device')
  servo.add_argument('degrees', type=float)
  for name in ('enc', 'din', 'range'):
    sub.add_parser(name).add_argument('device')
  return parser


def main(argv=None) -> int:
  args = build_parser().parse_args(argv)
  config = load_config(args.config)
  problems = config.problems(hardware=not args.loopback)
  if args.command == 'check':
    for device in config.devices.values():
      flag = '  <- placeholder' if device.is_placeholder else ''
      print(f'{device.name:24} {device.kind:6} {device.port}{flag}')
    for problem in problems:
      print(f'PROBLEM: {problem}')
    return 1 if problems else 0
  if problems:
    for problem in problems:
      print(f'refusing to talk to hardware: {problem}', file=sys.stderr)
    return 1

  if args.loopback:
    link = Esp32Link(LoopbackTransport(FakeEsp32.from_config(config)))
  else:
    settings = config.link
    link = Esp32Link(SerialTransport(args.serial_port or settings.serial_port, args.baud or settings.baud),
                     settings.reply_timeout, settings.retries)
  try:
    return _run(args, config, link)
  except (Esp32Error, KeyError, ValueError) as exc:
    print(f'error: {exc}', file=sys.stderr)
    return 1
  finally:
    link.close()


def _run(args, config, link) -> int:
  command = args.command
  if command == 'ping':
    print('firmware:', link.ping())
  elif command == 'stop':
    link.stop([config.device(n, 'motor').port for n in args.devices])
    print('stopped')
  elif command == 'motor':
    device = config.device(args.device, 'motor')
    wire = device.wire_permille(args.permille)
    print(f'{device.name}: port {device.port}, sending {wire} permille for {args.seconds} s')
    try:
      link.motors({device.port: wire})
      end = time.monotonic() + args.seconds
      while time.monotonic() < end:     # keep feeding the watchdog while it runs
        link.heartbeat()
        time.sleep(0.1)
    finally:
      link.stop([device.port])
    print('stopped; raw encoder ticks (sign as the ESP32 reports it):', link.encoders([device.port])[0])
  elif command == 'turn':
    device = config.device(args.device, 'motor')
    degrees = -args.degrees if device.invert else args.degrees
    speed = max(1, min(device.max_permille, abs(args.speed)))
    print(f'{device.name}: port {device.port}, turning {degrees} deg at {speed} permille')
    link.turn({device.port: (degrees, speed)})
  elif command == 'servo':
    device = config.device(args.device, 'servo')
    wire = device.wire_degrees(args.degrees)
    print(f'{device.name}: port {device.port}, moving to {wire} deg')
    link.servos({device.port: wire})
  elif command == 'enc':
    print(link.encoders([config.device(args.device, 'motor').port])[0])
  elif command == 'din':
    device = config.device(args.device, 'din')
    print(int(link.din(device.port) != device.invert))
  elif command == 'range':
    print(link.range_mm(config.device(args.device, 'range').port), 'mm')
  return 0


if __name__ == '__main__':
  sys.exit(main())
