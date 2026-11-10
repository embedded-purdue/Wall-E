"""Mock BT skills: correct inputs, outputs and failure reasons, with pretend behavior.

No ROS imports and no hardware. MockWorld keeps just enough state (what has been
found, where Wall-E is, what it is holding) that a real tree behaves sensibly:
is_visible(can) is false until search_for(can) runs, grab needs the object in
reach, crush needs something held, and so on. mock_skills_node.py wraps it.

These are placeholders for the BT team (week 3). The real simple skills replace
them behind the same actions and services, so trees do not change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

ACTION_SKILLS = ('search_for', 'navigate_to', 'say', 'express', 'look_at',
                 'move_arm', 'grab', 'release', 'crush')
CONDITION_SKILLS = ('is_visible', 'is_at')

# Same names as hardware_api/hardware_api/expressions.py. TODO(NLP): confirm the labels.
EMOTIONS = ('neutral', 'happy', 'sad', 'surprised', 'curious', 'confused', 'sleepy')
NAMED_POSES = ('rest', 'wave', 'grab_front', 'crush_drop')

DEFAULT_STOP_DISTANCE = 0.5  # m, navigate_to / is_at threshold from the team guide

# Failure reasons. Every skill returns one of these on failure ('' on success).
INVALID_GOAL = 'invalid_goal'          # a required field is empty
NOT_FOUND = 'not_found'                # search_for gave up
UNKNOWN_TARGET = 'unknown_target'      # no location given and not a found object or known spot
NOT_VISIBLE = 'not_visible'            # look_at target is not in view
UNKNOWN_EMOTION = 'unknown_emotion'
UNKNOWN_POSE = 'unknown_pose'
OUT_OF_REACH = 'out_of_reach'          # grab target is not where Wall-E is
ALREADY_HOLDING = 'already_holding'
NOT_HOLDING = 'not_holding'            # release/crush with an empty hand, or grab closed on nothing
WRONG_OBJECT = 'wrong_object'          # crush(x) while holding something else
CRUSHER_UNSAFE = 'crusher_unsafe'      # run_crusher refused
TIMEOUT = 'timeout'
CANCELED = 'canceled'
MOCK_FAILURE = 'mock_failure'          # forced by the failing_skills parameter


@dataclass(frozen=True)
class Outcome:
  success: bool
  reason: str = ''
  location: Optional[Tuple[float, float, float]] = None  # odom frame, for search_for / is_visible
  distance: float = math.nan                             # for is_at


@dataclass
class MockConfig:
  missing_objects: Set[str] = field(default_factory=set)   # search_for never finds these
  failing_skills: Set[str] = field(default_factory=set)    # always fail with MOCK_FAILURE
  known_spots: Set[str] = field(default_factory=lambda: {'user', 'home'})
  object_location: Tuple[float, float, float] = (1.5, 0.0, 0.0)  # where found objects are
  crusher_safe: bool = True


def plan_wait(delay_s: float, timeout_s: float) -> Tuple[float, bool]:
  """How long a mock action runs, and whether it ends in TIMEOUT.

  timeout_s <= 0 means no timeout from the goal.
  """
  delay_s = max(0.0, delay_s)
  if timeout_s > 0.0 and timeout_s < delay_s:
    return timeout_s, True
  return delay_s, False


def _name(value: str) -> str:
  return value.strip().lower()


class MockWorld:
  """Pretend world state shared by all mock skills."""

  def __init__(self, config: Optional[MockConfig] = None, visible: Tuple[str, ...] = ()):
    self.config = config or MockConfig()
    self._initial_visible = {_name(v) for v in visible if v.strip()}
    self.reset()

  def reset(self) -> None:
    self.visible: Set[str] = set(self._initial_visible)  # objects found or in view
    self.at: Optional[str] = None                         # target Wall-E is at
    self.holding: Optional[str] = None                    # object in the gripper

  def run(self, skill: str, **goal) -> Outcome:
    """Run one skill against the world. goal holds the skill's fields as keyword args."""
    if skill not in ACTION_SKILLS + CONDITION_SKILLS:
      raise KeyError(f"unknown skill '{skill}'")
    if skill in self.config.failing_skills:
      return Outcome(False, MOCK_FAILURE)
    return getattr(self, '_' + skill)(**goal)

  def _known(self, target: str, has_location: bool) -> bool:
    return has_location or target in self.visible or target in self.config.known_spots

  # Perception + expression

  def _search_for(self, object: str, hint: str = '') -> Outcome:
    obj = _name(object)
    if not obj:
      return Outcome(False, INVALID_GOAL)
    if obj in self.config.missing_objects:
      return Outcome(False, NOT_FOUND)
    self.visible.add(obj)
    return Outcome(True, location=self.config.object_location)

  def _is_visible(self, object: str) -> Outcome:
    obj = _name(object)
    if obj and obj in self.visible:
      return Outcome(True, location=self.config.object_location)
    return Outcome(False)

  def _look_at(self, target: str, has_location: bool = False) -> Outcome:
    target = _name(target)
    if not target and not has_location:
      return Outcome(False, INVALID_GOAL)
    if not has_location and target not in self.visible and target not in self.config.known_spots:
      return Outcome(False, NOT_VISIBLE)
    return Outcome(True)

  def _say(self, text: str, emotion: str = '') -> Outcome:
    if not text.strip():
      return Outcome(False, INVALID_GOAL)
    if emotion.strip() and _name(emotion) not in EMOTIONS:
      return Outcome(False, UNKNOWN_EMOTION)
    return Outcome(True)

  def _express(self, emotion: str) -> Outcome:
    if not emotion.strip():
      return Outcome(False, INVALID_GOAL)
    if _name(emotion) not in EMOTIONS:
      return Outcome(False, UNKNOWN_EMOTION)
    return Outcome(True)

  # Driving

  def _navigate_to(self, target: str, has_location: bool = False) -> Outcome:
    target = _name(target)
    if not target:
      return Outcome(False, INVALID_GOAL)
    if not self._known(target, has_location):
      return Outcome(False, UNKNOWN_TARGET)
    self.at = target
    return Outcome(True)

  def _is_at(self, target: str, has_location: bool = False, threshold: float = 0.0) -> Outcome:
    target = _name(target)
    threshold = threshold if threshold > 0.0 else DEFAULT_STOP_DISTANCE
    if target and self.at == target:
      return Outcome(True, distance=0.8 * threshold)
    if self._known(target, has_location):
      return Outcome(False, distance=math.dist((0.0, 0.0, 0.0), self.config.object_location))
    return Outcome(False)

  # Arm

  def _move_arm(self, pose_name: str = '', has_target: bool = False) -> Outcome:
    pose = _name(pose_name)
    if not pose:
      return Outcome(True) if has_target else Outcome(False, INVALID_GOAL)
    if pose not in NAMED_POSES:
      return Outcome(False, UNKNOWN_POSE)
    return Outcome(True)

  def _grab(self, object: str, has_location: bool = False) -> Outcome:
    obj = _name(object)
    if not obj:
      return Outcome(False, INVALID_GOAL)
    if self.holding is not None:
      return Outcome(False, ALREADY_HOLDING)
    # No location = the known spot in front of Wall-E (the must-have this semester).
    if has_location and self.at != obj:
      return Outcome(False, OUT_OF_REACH)
    self.holding = obj
    return Outcome(True)

  def _release(self, target: str = '', has_location: bool = False) -> Outcome:
    if self.holding is None:
      return Outcome(False, NOT_HOLDING)
    self.holding = None
    return Outcome(True)

  def _crush(self, object: str) -> Outcome:
    obj = _name(object)
    if self.holding is None:
      return Outcome(False, NOT_HOLDING)
    if obj and obj != self.holding:
      return Outcome(False, WRONG_OBJECT)
    if not self.config.crusher_safe:
      return Outcome(False, CRUSHER_UNSAFE)
    self.visible.discard(self.holding)
    self.holding = None
    return Outcome(True)
