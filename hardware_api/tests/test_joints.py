import math

import pytest

from hardware_api.joints import JointController, JointSpec, MockJointBackend


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


def make(specs=None):
  specs = specs or [
    JointSpec('pan', -1.0, 1.0, 2.0),
    JointSpec('tilt', -0.5, 0.5, 1.0, home=0.1),
  ]
  backend = MockJointBackend({s.name: s.home for s in specs})
  clock = FakeClock()
  return JointController(backend, specs, clock=clock), backend, clock


# JointSpec

def test_spec_rejects_bad_limits():
  with pytest.raises(ValueError):
    JointSpec('j', 1.0, -1.0, 1.0)
  with pytest.raises(ValueError):
    JointSpec('j', -1.0, 1.0, 0.0)
  with pytest.raises(ValueError):
    JointSpec('j', -1.0, 1.0, 1.0, home=2.0)


def test_spec_clamp():
  spec = JointSpec('j', -1.0, 1.0, 1.0)
  assert spec.clamp(5.0) == 1.0
  assert spec.clamp(-5.0) == -1.0
  assert spec.clamp(0.3) == 0.3


# Controller

def test_rejects_empty_and_duplicate_joints():
  backend = MockJointBackend({})
  with pytest.raises(ValueError):
    JointController(backend, [])
  spec = JointSpec('j', -1.0, 1.0, 1.0)
  with pytest.raises(ValueError):
    JointController(backend, [spec, spec])


def test_first_step_sends_home():
  controller, backend, _ = make()
  assert controller.step() == {'pan': 0.0, 'tilt': 0.1}
  assert backend.read_positions() == {'pan': 0.0, 'tilt': 0.1}


def test_command_clamps_to_limits():
  controller, _, _ = make()
  applied = controller.command({'pan': 9.0, 'tilt': -9.0})
  assert applied == {'pan': 1.0, 'tilt': -0.5}


def test_slew_limit_caps_speed():
  controller, _, clock = make()
  controller.step()
  controller.command({'pan': 1.0})
  clock.t = 0.1
  assert controller.step()['pan'] == pytest.approx(0.2)  # 2 rad/s * 0.1 s
  clock.t = 0.2
  assert controller.step()['pan'] == pytest.approx(0.4)


def test_reaches_target_without_overshoot():
  controller, _, clock = make()
  controller.step()
  controller.command({'pan': 0.3})
  for i in range(1, 20):
    clock.t = i * 0.1
    assert controller.step()['pan'] <= 0.3 + 1e-12
  assert controller.at_target()


def test_unknown_joint_raises_and_applies_nothing():
  controller, _, _ = make()
  with pytest.raises(KeyError):
    controller.command({'pan': 0.5, 'nope': 1.0})
  assert controller.targets()['pan'] == 0.0


def test_non_finite_angle_is_ignored():
  controller, _, _ = make()
  controller.command({'pan': 0.5})
  controller.command({'pan': math.nan, 'tilt': math.inf})
  assert controller.targets() == {'pan': 0.5, 'tilt': 0.1}


def test_partial_command_leaves_other_joints():
  controller, _, _ = make()
  controller.command({'pan': 0.5})
  assert controller.targets()['tilt'] == 0.1


def test_hold_stops_motion():
  controller, _, clock = make()
  controller.step()
  controller.command({'pan': 1.0})
  clock.t = 0.1
  controller.step()
  controller.hold()
  clock.t = 0.5
  assert controller.step()['pan'] == pytest.approx(0.2)
  assert controller.at_target()


def test_clock_going_backwards_does_not_move_joints():
  controller, _, clock = make()
  clock.t = 1.0
  controller.step()
  controller.command({'pan': 1.0})
  clock.t = 0.5
  assert controller.step()['pan'] == 0.0
