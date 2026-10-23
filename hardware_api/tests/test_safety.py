import math

import pytest

from hardware_api.controller import DriveController
from hardware_api.drive_backend import DriveBackend
from hardware_api.kinematics import DriveParams, wheels_to_twist
from hardware_api.safety import SpeedLimiter, Watchdog

PARAMS = DriveParams(wheel_radius=0.05, track_width=0.4, ticks_per_rev=2000, max_wheel_speed=1.0)


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


class RecordingBackend(DriveBackend):
  def __init__(self):
    self.calls = []

  def set_wheel_speeds(self, left, right):
    self.calls.append(('speeds', left, right))

  def stop(self):
    self.calls.append(('stop',))

  def read_encoders(self):
    return 0, 0


# Speed cap

def test_cap_defaults_to_60_percent():
  limiter = SpeedLimiter(0.4, 1.0)
  assert limiter.max_wheel_speed == pytest.approx(0.6)


def test_under_cap_passes_through():
  assert SpeedLimiter(0.4, 1.0).limit(0.3, 0.0) == pytest.approx((0.3, 0.3))


def test_linear_speed_clamped():
  assert SpeedLimiter(0.4, 1.0).limit(5.0, 0.0) == pytest.approx((0.6, 0.6))
  assert SpeedLimiter(0.4, 1.0).limit(-5.0, 0.0) == pytest.approx((-0.6, -0.6))


def test_angular_speed_clamped():
  left, right = SpeedLimiter(0.4, 1.0).limit(0.0, 100.0)
  assert (left, right) == pytest.approx((-0.6, 0.6))


def test_combined_command_scales_wheels_together():
  limiter = SpeedLimiter(0.4, 1.0)
  v, omega = 0.5, 1.5  # both under their own clamp, but outer wheel would hit 0.8
  left, right = limiter.limit(v, omega)
  assert max(abs(left), abs(right)) == pytest.approx(0.6)
  v_out, omega_out = wheels_to_twist(left, right, 0.4)
  assert v_out / omega_out == pytest.approx(v / omega)  # same turning radius


def test_cap_fraction_is_configurable():
  assert SpeedLimiter(0.4, 1.0, cap_fraction=0.3).limit(5.0, 0.0) == pytest.approx((0.3, 0.3))


@pytest.mark.parametrize('fraction', [0.0, -0.1, 1.5])
def test_invalid_cap_fraction_rejected(fraction):
  with pytest.raises(ValueError):
    SpeedLimiter(0.4, 1.0, cap_fraction=fraction)


@pytest.mark.parametrize('v, omega', [(math.nan, 0.0), (0.0, math.inf), (-math.inf, 0.1)])
def test_non_finite_command_stops(v, omega):
  assert SpeedLimiter(0.4, 1.0).limit(v, omega) == (0.0, 0.0)


# Watchdog

def test_watchdog_starts_expired():
  assert Watchdog(0.5, FakeClock()).expired()


def test_watchdog_expires_after_timeout():
  clock = FakeClock()
  dog = Watchdog(0.5, clock)
  dog.feed()
  clock.t = 0.5
  assert not dog.expired()
  clock.t = 0.51
  assert dog.expired()


def test_watchdog_feed_resets_timer():
  clock = FakeClock()
  dog = Watchdog(0.5, clock)
  dog.feed()
  clock.t = 0.4
  dog.feed()
  clock.t = 0.8
  assert not dog.expired()


def test_watchdog_expire_forces_expired():
  dog = Watchdog(0.5, FakeClock())
  dog.feed()
  dog.expire()
  assert dog.expired()


# Controller: safety wiring

def make_controller(**kwargs):
  clock, backend = FakeClock(), RecordingBackend()
  return DriveController(backend, PARAMS, clock=clock, **kwargs), backend, clock


def test_controller_applies_cap():
  controller, backend, _ = make_controller()
  controller.command(10.0, 0.0)
  controller.step()
  assert backend.calls[-1] == ('speeds', pytest.approx(0.6), pytest.approx(0.6))


def test_controller_stops_when_commands_stop_arriving():
  timeouts = []
  controller, backend, clock = make_controller(on_timeout=lambda: timeouts.append(clock.t))
  controller.command(0.3, 0.0)
  clock.t = 0.4
  controller.step()
  assert backend.calls[-1][0] == 'speeds'
  clock.t = 0.6
  controller.step()
  assert backend.calls[-1] == ('stop',)
  assert timeouts == [0.6]


def test_controller_keeps_driving_while_fed():
  controller, backend, clock = make_controller()
  for i in range(50):
    clock.t = i * 0.1
    controller.command(0.3, 0.0)
    controller.step()
  assert all(call[0] == 'speeds' for call in backend.calls)


def test_stop_reaches_backend_immediately_and_clears_target():
  controller, backend, clock = make_controller()
  controller.command(0.3, 0.0)
  controller.step()
  controller.stop()
  assert backend.calls[-1] == ('stop',)
  clock.t = 0.1  # still inside the watchdog window
  controller.step()
  assert backend.calls[-1] == ('stop',)


def test_new_command_after_stop_drives_again():
  controller, backend, _ = make_controller()
  controller.stop()
  controller.command(0.3, 0.0)
  controller.step()
  assert backend.calls[-1][0] == 'speeds'
