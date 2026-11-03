import math

import pytest

from skills import mock_skills as m
from skills.mock_skills import MockConfig, MockWorld, Outcome, plan_wait


def world(**config):
  return MockWorld(MockConfig(**config))


# A full tree: find a can, drive to it, grab it, crush it.

def test_find_drive_grab_crush_tree():
  w = world()
  assert not w.run('is_visible', object='can').success
  found = w.run('search_for', object='can', hint='')
  assert found.success and found.location == (1.5, 0.0, 0.0)
  assert w.run('is_visible', object='can').success
  assert not w.run('is_at', target='can', has_location=True).success
  assert w.run('navigate_to', target='can', has_location=True).success
  assert w.run('is_at', target='can', has_location=True).success
  assert w.run('grab', object='can', has_location=True).success
  assert w.run('crush', object='can').success
  assert w.holding is None
  assert not w.run('is_visible', object='can').success  # it was crushed


def test_names_are_case_and_space_insensitive():
  w = world()
  w.run('search_for', object=' Can ')
  assert w.run('is_visible', object='CAN').success


# Failure reasons

def test_search_for_missing_object_is_not_found():
  assert world(missing_objects={'ball'}).run('search_for', object='ball') == Outcome(False, m.NOT_FOUND)


def test_failing_skills_force_mock_failure():
  w = world(failing_skills={'say'})
  assert w.run('say', text='hi') == Outcome(False, m.MOCK_FAILURE)
  assert w.run('express', emotion='happy').success


@pytest.mark.parametrize('skill, goal', [
  ('search_for', {'object': ''}),
  ('navigate_to', {'target': ' '}),
  ('say', {'text': ''}),
  ('express', {'emotion': ''}),
  ('look_at', {'target': ''}),
  ('move_arm', {'pose_name': ''}),
  ('grab', {'object': ''}),
])
def test_empty_required_field_is_invalid_goal(skill, goal):
  assert world().run(skill, **goal).reason == m.INVALID_GOAL


def test_navigate_to_needs_a_location_found_object_or_known_spot():
  w = world()
  assert w.run('navigate_to', target='ball').reason == m.UNKNOWN_TARGET
  assert w.run('navigate_to', target='user').success
  assert w.run('navigate_to', target='ball', has_location=True).success


def test_look_at_needs_target_in_view():
  w = world()
  assert w.run('look_at', target='can').reason == m.NOT_VISIBLE
  w.run('search_for', object='can')
  assert w.run('look_at', target='can').success


def test_emotions_are_checked():
  w = world()
  assert w.run('say', text='hi', emotion='angry').reason == m.UNKNOWN_EMOTION
  assert w.run('say', text='hi', emotion='').success
  assert w.run('say', text='hi', emotion='Happy').success
  assert w.run('express', emotion='angry').reason == m.UNKNOWN_EMOTION


def test_move_arm_named_pose_or_target():
  w = world()
  assert w.run('move_arm', pose_name='wave').success
  assert w.run('move_arm', pose_name='dab').reason == m.UNKNOWN_POSE
  assert w.run('move_arm', pose_name='', has_target=True).success


def test_grab_rules():
  w = world()
  assert w.run('grab', object='can', has_location=True).reason == m.OUT_OF_REACH
  assert w.run('grab', object='can').success  # known spot in front
  assert w.run('grab', object='cup').reason == m.ALREADY_HOLDING


def test_release_and_crush_need_something_held():
  w = world()
  assert w.run('release').reason == m.NOT_HOLDING
  assert w.run('crush', object='can').reason == m.NOT_HOLDING
  w.run('grab', object='can')
  assert w.run('crush', object='cup').reason == m.WRONG_OBJECT
  assert w.run('release', target='user').success
  assert w.holding is None


def test_crusher_unsafe_keeps_the_item():
  w = world(crusher_safe=False)
  w.run('grab', object='can')
  assert w.run('crush', object='can').reason == m.CRUSHER_UNSAFE
  assert w.holding == 'can'


def test_is_at_distance():
  w = world()
  assert math.isnan(w.run('is_at', target='ball').distance)
  assert w.run('is_at', target='user').distance == pytest.approx(1.5)
  w.run('navigate_to', target='user')
  at = w.run('is_at', target='user', threshold=1.0)
  assert at.success and at.distance < 1.0


def test_reset_restores_initial_view():
  w = MockWorld(visible=('ball',))
  w.run('grab', object='can')
  w.run('search_for', object='can')
  w.reset()
  assert w.visible == {'ball'} and w.holding is None and w.at is None


def test_unknown_skill_raises():
  with pytest.raises(KeyError):
    world().run('dance')


# Timing

def test_plan_wait():
  assert plan_wait(1.0, 0.0) == (1.0, False)
  assert plan_wait(1.0, 2.0) == (1.0, False)
  assert plan_wait(1.0, 0.3) == (0.3, True)
  assert plan_wait(-1.0, 0.0) == (0.0, False)
