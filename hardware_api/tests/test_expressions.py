import pytest

from hardware_api.expressions import EXPRESSIONS, LEFT_EYE, RIGHT_EYE, eye_targets
from hardware_api.joints import JointController, JointSpec, MockJointBackend


def test_neutral_is_zero():
  assert eye_targets('neutral') == {LEFT_EYE: 0.0, RIGHT_EYE: 0.0}


def test_names_are_case_and_space_insensitive():
  assert eye_targets('  Happy ') == eye_targets('happy')


def test_unknown_expression_raises():
  with pytest.raises(KeyError):
    eye_targets('furious')


def test_every_expression_fits_default_eye_limits():
  specs = [JointSpec(LEFT_EYE, -0.5, 0.5, 6.0), JointSpec(RIGHT_EYE, -0.5, 0.5, 6.0)]
  controller = JointController(MockJointBackend({s.name: 0.0 for s in specs}), specs)
  for name, (left, right) in EXPRESSIONS.items():
    applied = controller.command(eye_targets(name))
    assert applied == {LEFT_EYE: left, RIGHT_EYE: right}, name
