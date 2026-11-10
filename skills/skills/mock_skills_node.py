"""ROS 2 node serving every BT skill as a mock (no hardware needed).

  Actions (wall_e_interfaces/action):
    /skills/search_for  SearchFor     /skills/move_arm  MoveArm
    /skills/navigate_to NavigateTo    /skills/grab      Grab
    /skills/say         Say           /skills/release   Release
    /skills/express     Express       /skills/crush     Crush
    /skills/look_at     LookAt
  Services (wall_e_interfaces/srv):
    /skills/is_visible  IsVisible     /skills/is_at     IsAt
    /skills/mock/reset  std_srvs/Trigger: forget what was found, held and reached

An action succeeds (goal status SUCCEEDED, result.success=true) or aborts
(ABORTED, result.success=false, result.reason set). Canceling ends it with
CANCELED and reason 'canceled'. Each action takes mock_delay_s and publishes
feedback while it runs. Parameters are re-read on every goal, so
`ros2 param set /mock_skills_node mock_failing_skills "['grab']"` works live.
"""

from __future__ import annotations

import math
import threading
import time

import rclpy
from geometry_msgs.msg import PointStamped
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger
from wall_e_interfaces.action import (Crush, Express, Grab, LookAt, MoveArm, NavigateTo, Release,
                                      Say, SearchFor)
from wall_e_interfaces.srv import IsAt, IsVisible

from .mock_skills import CANCELED, TIMEOUT, MockConfig, MockWorld, plan_wait

TICK_S = 0.1


def _has(point: PointStamped) -> bool:
  return bool(point.header.frame_id)


# skill -> (action type, goal -> MockWorld.run kwargs)
ACTIONS = {
  'search_for': (SearchFor, lambda g: {'object': g.object, 'hint': g.hint}),
  'navigate_to': (NavigateTo, lambda g: {'target': g.target, 'has_location': _has(g.location)}),
  'say': (Say, lambda g: {'text': g.text, 'emotion': g.emotion}),
  'express': (Express, lambda g: {'emotion': g.emotion}),
  'look_at': (LookAt, lambda g: {'target': g.target, 'has_location': _has(g.location)}),
  'move_arm': (MoveArm, lambda g: {'pose_name': g.pose_name, 'has_target': _has(g.target)}),
  'grab': (Grab, lambda g: {'object': g.object, 'has_location': _has(g.location)}),
  'release': (Release, lambda g: {'target': g.target, 'has_location': _has(g.location)}),
  'crush': (Crush, lambda g: {'object': g.object}),
}


def _strings(values) -> set:
  return {v.strip().lower() for v in values if v.strip()}


class MockSkillsNode(Node):

  def __init__(self):
    super().__init__('mock_skills_node')
    self.declare_parameter('mock_delay_s', 1.0)
    self.declare_parameter('mock_missing_objects', [''])
    self.declare_parameter('mock_failing_skills', [''])
    self.declare_parameter('mock_known_spots', ['user', 'home'])
    self.declare_parameter('mock_object_location', [1.5, 0.0, 0.0])
    self.declare_parameter('mock_crusher_safe', True)
    self.declare_parameter('location_frame', 'odom')
    visible = self.declare_parameter('mock_visible_objects', ['']).value

    self._lock = threading.Lock()
    self._world = MockWorld(self._config(), visible=tuple(visible))
    group = ReentrantCallbackGroup()
    self._servers = [
      ActionServer(
        self, action_type, f'skills/{skill}',
        execute_callback=lambda handle, s=skill: self._execute(s, handle),
        goal_callback=lambda _: GoalResponse.ACCEPT,
        cancel_callback=lambda _: CancelResponse.ACCEPT,
        callback_group=group)
      for skill, (action_type, _) in ACTIONS.items()
    ]
    self.create_service(IsVisible, 'skills/is_visible', self._on_is_visible, callback_group=group)
    self.create_service(IsAt, 'skills/is_at', self._on_is_at, callback_group=group)
    self.create_service(Trigger, 'skills/mock/reset', self._on_reset, callback_group=group)
    self.get_logger().info('mock_skills_node up: all skills are mocks')

  def _config(self) -> MockConfig:
    p = lambda name: self.get_parameter(name).value
    return MockConfig(
      missing_objects=_strings(p('mock_missing_objects')),
      failing_skills=_strings(p('mock_failing_skills')),
      known_spots=_strings(p('mock_known_spots')),
      object_location=tuple(float(v) for v in p('mock_object_location')),
      crusher_safe=p('mock_crusher_safe'),
    )

  def _run(self, skill: str, **goal):
    with self._lock:
      self._world.config = self._config()
      return self._world.run(skill, **goal)

  def _point(self, xyz) -> PointStamped:
    msg = PointStamped()
    msg.header.stamp = self.get_clock().now().to_msg()
    msg.header.frame_id = self.get_parameter('location_frame').value
    msg.point.x, msg.point.y, msg.point.z = (float(v) for v in xyz)
    return msg

  def _feedback(self, skill: str, action_type, fraction: float):
    fb = action_type.Feedback()
    if skill == 'search_for':
      fb.rotated = 2.0 * math.pi * fraction
    elif skill == 'navigate_to':
      fb.distance_remaining = 1.5 * (1.0 - fraction)
    elif skill == 'grab':
      fb.stage = 'reaching' if fraction < 0.5 else 'closing' if fraction < 0.9 else 'checking'
    elif skill == 'crush':
      fb.stage = 'dropping' if fraction < 0.5 else 'crushing'
    else:
      return None  # no feedback fields
    return fb

  def _execute(self, skill: str, handle):
    action_type, to_kwargs = ACTIONS[skill]
    goal = handle.request
    result = action_type.Result()
    wait_s, timed_out = plan_wait(self.get_parameter('mock_delay_s').value, goal.timeout_s)

    start = time.monotonic()
    while True:
      elapsed = time.monotonic() - start
      if handle.is_cancel_requested:
        handle.canceled()
        result.success, result.reason = False, CANCELED
        return result
      fb = self._feedback(skill, action_type, min(1.0, elapsed / wait_s) if wait_s > 0 else 1.0)
      if fb is not None:
        handle.publish_feedback(fb)
      if elapsed >= wait_s:
        break
      time.sleep(min(TICK_S, wait_s - elapsed))

    if timed_out:
      result.success, result.reason = False, TIMEOUT
    else:
      outcome = self._run(skill, **to_kwargs(goal))
      result.success, result.reason = outcome.success, outcome.reason
      if skill == 'search_for' and outcome.location is not None:
        result.location = self._point(outcome.location)

    if result.success:
      handle.succeed()
    else:
      handle.abort()
      self.get_logger().info(f'{skill} failed: {result.reason}')
    return result

  def _on_is_visible(self, request, response):
    outcome = self._run('is_visible', object=request.object)
    response.visible = outcome.success
    if outcome.location is not None:
      response.location = self._point(outcome.location)
    return response

  def _on_is_at(self, request, response):
    outcome = self._run('is_at', target=request.target,
                        has_location=_has(request.location), threshold=request.threshold)
    response.at = outcome.success
    response.distance = outcome.distance
    return response

  def _on_reset(self, request, response):
    with self._lock:
      self._world.reset()
    response.success, response.message = True, 'mock world reset'
    return response


def main(args=None):
  rclpy.init(args=args)
  node = MockSkillsNode()
  executor = MultiThreadedExecutor()
  executor.add_node(node)
  try:
    executor.spin()
  except KeyboardInterrupt:
    pass
  finally:
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
  main()
