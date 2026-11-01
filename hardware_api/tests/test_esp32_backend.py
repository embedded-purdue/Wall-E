import math

import pytest

from hardware_api.bench_drive import run_step
from hardware_api.controller import DriveController
from hardware_api.esp32_backend import Esp32DriveBackend, Esp32Link
from hardware_api.esp32_protocol import ProtocolError
from hardware_api.fake_esp32 import FakeEsp32
from hardware_api.kinematics import DriveParams

PARAMS = DriveParams(wheel_radius=0.05, track_width=0.4, ticks_per_rev=8192, max_wheel_speed=1.0)


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


@pytest.fixture
def clock():
  return FakeClock()


@pytest.fixture
def esp(clock):
  return FakeEsp32(counts_per_rev=8192, clock=clock)


def test_ready_after_boot_is_skipped(esp):
  link = Esp32Link(esp)
  link.heartbeat()
  assert esp.log == ['H']


def test_drive_sends_rpm_and_encoders_count(esp, clock):
  link = Esp32Link(esp)
  link.drive(60.0, -30.0)
  clock.t = 0.4
  assert link.read_encoders() == (round(0.4 * 8192), round(-0.2 * 8192))


def test_firmware_timeout_stops_motors(esp, clock):
  link = Esp32Link(esp)
  link.drive(60.0, 60.0)
  clock.t = 2.0
  left, _ = link.read_encoders()
  assert esp.timed_out
  assert left == round(0.5 * 8192)  # ran only until the 0.5 s timeout


def test_err_reply_raises(esp):
  link = Esp32Link(esp)
  with pytest.raises(ProtocolError):
    link.request(b'X\n')


def test_no_reply_raises():
  class Silent:
    def write(self, data):
      return len(data)

    def readline(self):
      return b''

  with pytest.raises(ProtocolError):
    Esp32Link(Silent()).heartbeat()


def test_backend_converts_mps_to_rpm(esp):
  backend = Esp32DriveBackend(PARAMS, Esp32Link(esp))
  backend.set_wheel_speeds(2.0 * math.pi * 0.05, 0.0)
  assert esp.log[-1] == 'D 60.00 0.00'
  backend.stop()
  assert esp.log[-1] == 'S'


def test_controller_drives_straight_through_esp32(esp, clock):
  controller = DriveController(Esp32DriveBackend(PARAMS, Esp32Link(esp)), PARAMS, clock=clock)
  controller.step()
  for i in range(1, 21):
    controller.command(0.3, 0.0)  # under the 0.6 m/s cap
    clock.t = i * 0.05
    pose, v, _ = controller.step()
  assert pose.x == pytest.approx(0.3 * 0.95, rel=0.02)
  assert pose.y == pytest.approx(0.0, abs=1e-6)


def test_bench_step_reports_count_change(esp, clock):
  link = Esp32Link(esp)

  def sleep(dt):
    clock.t += dt

  left, right = run_step(link, 'left', 30.0, 0.0, 1.0, sleep=sleep, clock=clock)
  # 30 RPM for about 1 s (the last heartbeat period can overrun) is about half a turn.
  assert left == pytest.approx(0.5 * 8192, rel=0.15)
  assert right == 0
  assert esp.log[-2] == 'S'
