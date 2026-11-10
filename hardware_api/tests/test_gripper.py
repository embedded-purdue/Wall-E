import pytest

from hardware_api.arm import arm_specs
from hardware_api.gripper import MockGripperBackend


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


def make(**kwargs):
  clock = FakeClock()
  return MockGripperBackend(close_time=1.0, clock=clock, **kwargs), clock


def test_starts_open_and_not_holding():
  gripper, _ = make()
  state = gripper.read_state()
  assert (state.closed_command, state.position, state.holding) == (False, 0.0, False)


def test_closes_fully_when_empty_and_does_not_hold():
  gripper, clock = make()
  gripper.set_closed(True)
  clock.t = 0.5
  assert gripper.read_state().position == pytest.approx(0.5)
  assert not gripper.read_state().holding
  clock.t = 2.0
  state = gripper.read_state()
  assert state.position == 1.0 and not state.holding


def test_object_stops_closing_and_reports_holding():
  gripper, clock = make(object_fraction=0.5)
  gripper.object_present = True
  gripper.set_closed(True)
  clock.t = 0.25
  assert not gripper.read_state().holding  # still closing
  clock.t = 2.0
  state = gripper.read_state()
  assert state.position == pytest.approx(0.5)
  assert state.holding


def test_open_releases_and_clears_holding():
  gripper, clock = make()
  gripper.object_present = True
  gripper.set_closed(True)
  clock.t = 2.0
  assert gripper.read_state().holding
  gripper.set_closed(False)
  clock.t = 2.5
  state = gripper.read_state()
  assert state.position == pytest.approx(0.0)
  assert not state.holding and not state.closed_command


def test_losing_the_object_while_closed_is_not_holding():
  gripper, clock = make()
  gripper.object_present = True
  gripper.set_closed(True)
  clock.t = 2.0
  assert gripper.read_state().holding
  gripper.object_present = False
  clock.t = 4.0
  state = gripper.read_state()
  assert state.position == 1.0 and not state.holding


def test_rejects_bad_parameters():
  with pytest.raises(ValueError):
    MockGripperBackend(close_time=0.0)
  with pytest.raises(ValueError):
    MockGripperBackend(object_fraction=1.0)


# Arm joint configuration

def test_arm_specs_builds_joints():
  specs = arm_specs(['a', 'b'], [-1.0, -2.0], [1.0, 2.0], [1.0, 1.5], [0.0, 0.5])
  assert [s.name for s in specs] == ['a', 'b']
  assert specs[1].max_angle == 2.0 and specs[1].home == 0.5


def test_arm_specs_defaults_home_to_zero():
  assert arm_specs(['a'], [-1.0], [1.0], [1.0])[0].home == 0.0


def test_arm_specs_rejects_mismatched_lengths():
  with pytest.raises(ValueError):
    arm_specs(['a', 'b'], [-1.0], [1.0, 1.0], [1.0, 1.0])
