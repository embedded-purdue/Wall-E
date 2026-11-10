import math

import pytest

from hardware_api.kinematics import (
  DriveParams, normalize_angle, ticks_to_distance, twist_to_wheels, wheels_to_twist)

PARAMS = DriveParams(wheel_radius=0.05, track_width=0.4, ticks_per_rev=2000, max_wheel_speed=1.0)


def test_straight_line_drives_both_wheels_equally():
  assert twist_to_wheels(0.5, 0.0, 0.4) == (0.5, 0.5)


def test_spin_in_place_drives_wheels_opposite():
  left, right = twist_to_wheels(0.0, 1.0, 0.4)
  assert left == pytest.approx(-0.2)
  assert right == pytest.approx(0.2)


def test_positive_omega_turns_left():
  left, right = twist_to_wheels(0.3, 0.5, 0.4)
  assert right > left


@pytest.mark.parametrize('v, omega', [(0.3, 0.0), (0.0, -1.2), (0.4, 0.7), (-0.2, 0.3)])
def test_wheels_round_trip(v, omega):
  assert wheels_to_twist(*twist_to_wheels(v, omega, 0.4), 0.4) == pytest.approx((v, omega))


def test_one_revolution_is_one_circumference():
  assert ticks_to_distance(2000, PARAMS) == pytest.approx(2.0 * math.pi * 0.05)


@pytest.mark.parametrize('theta, expected', [
  (0.0, 0.0), (math.pi / 2, math.pi / 2), (3 * math.pi / 2, -math.pi / 2), (-5 * math.pi / 2, -math.pi / 2)])
def test_normalize_angle(theta, expected):
  assert normalize_angle(theta) == pytest.approx(expected)
