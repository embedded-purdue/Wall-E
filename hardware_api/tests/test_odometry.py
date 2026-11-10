import math

import pytest

from hardware_api.kinematics import DriveParams, OdometryIntegrator
from hardware_api.mock_backend import MockDriveBackend

PARAMS = DriveParams(wheel_radius=0.05, track_width=0.4, ticks_per_rev=2000, max_wheel_speed=1.0)
TICKS_PER_M = 2000 / (2.0 * math.pi * 0.05)


def ticks(meters):
  return round(meters * TICKS_PER_M)


def test_first_update_only_records_start():
  odom = OdometryIntegrator(PARAMS)
  pose, v, omega = odom.update(12345, -678, 0.1)
  assert (pose.x, pose.y, pose.theta, v, omega) == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_straight_line():
  odom = OdometryIntegrator(PARAMS)
  odom.update(500, 500, 0.0)
  pose, v, omega = odom.update(500 + ticks(1.0), 500 + ticks(1.0), 2.0)
  assert pose.x == pytest.approx(1.0, abs=1e-3)
  assert pose.y == pytest.approx(0.0)
  assert v == pytest.approx(0.5, abs=1e-3)
  assert omega == pytest.approx(0.0)


def test_spin_in_place_quarter_turn():
  odom = OdometryIntegrator(PARAMS)
  odom.update(0, 0, 0.0)
  arc = math.pi / 2 * 0.2  # quarter turn at half the track width
  pose, _, _ = odom.update(-ticks(arc), ticks(arc), 1.0)
  assert pose.x == pytest.approx(0.0, abs=1e-3)
  assert pose.y == pytest.approx(0.0, abs=1e-3)
  assert pose.theta == pytest.approx(math.pi / 2, abs=1e-3)


def test_quarter_circle_arc_in_small_steps():
  odom = OdometryIntegrator(PARAMS)
  radius, steps = 1.0, 200
  d_theta = (math.pi / 2) / steps
  left_step = d_theta * (radius - 0.2) * TICKS_PER_M
  right_step = d_theta * (radius + 0.2) * TICKS_PER_M
  odom.update(0, 0, 0.0)
  for i in range(1, steps + 1):
    pose, _, _ = odom.update(round(i * left_step), round(i * right_step), 0.01)
  assert pose.x == pytest.approx(radius, abs=5e-3)
  assert pose.y == pytest.approx(radius, abs=5e-3)
  assert pose.theta == pytest.approx(math.pi / 2, abs=5e-3)


def test_heading_wraps():
  odom = OdometryIntegrator(PARAMS)
  odom.update(0, 0, 0.0)
  arc = 1.5 * math.pi * 0.2  # 270 degrees left
  pose, _, _ = odom.update(-ticks(arc), ticks(arc), 1.0)
  assert pose.theta == pytest.approx(-math.pi / 2, abs=1e-3)


def test_mock_backend_drives_one_meter():
  t = [0.0]
  backend = MockDriveBackend(PARAMS, clock=lambda: t[0])
  odom = OdometryIntegrator(PARAMS)
  odom.update(*backend.read_encoders(), 0.0)
  backend.set_wheel_speeds(0.5, 0.5)
  t[0] = 2.0
  backend.stop()
  t[0] = 3.0
  pose, _, _ = odom.update(*backend.read_encoders(), 3.0)
  assert pose.x == pytest.approx(1.0, abs=1e-3)
