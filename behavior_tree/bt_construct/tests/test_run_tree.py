"""Runs the example trees against mock_skills_node and checks what happened.

Needs a sourced workspace with wall_e_interfaces, skills and bt_construct built:
    colcon build --packages-select wall_e_interfaces skills bt_construct
    source install/setup.bash
    python -m pytest behavior_tree/bt_construct/tests
"""

import os
import random
import signal
import subprocess
import time
from pathlib import Path

import pytest

TREES = Path(__file__).resolve().parent.parent / 'trees'


@pytest.fixture
def ros_env():
  # A random domain per test keeps parallel runs (and teammates' robots) out of each other's way.
  env = dict(os.environ, ROS_DOMAIN_ID=str(random.randint(1, 200)))
  return env


def start_mocks(env, log_path, **params):
  """Starts mock_skills_node with fast actions plus any overrides."""
  params.setdefault('mock_delay_s', 0.2)
  args = ['ros2', 'run', 'skills', 'mock_skills_node', '--ros-args']
  for key, value in params.items():
    args += ['-p', f'{key}:={value}']
  # Log to a file, not a pipe: an unread pipe fills up and stalls the node.
  with open(log_path, 'w') as log:  # the child keeps its own copy of the handle
    proc = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
  deadline = time.time() + 15
  while time.time() < deadline:
    if 'mock_skills_node up' in Path(log_path).read_text():
      return proc
    time.sleep(0.1)
  stop(proc)
  pytest.fail('mock_skills_node did not start:\n' + Path(log_path).read_text())


def stop(proc):
  """Ctrl-C the whole process group (ros2 run starts a child), then force it."""
  try:
    os.killpg(proc.pid, signal.SIGINT)
    proc.wait(timeout=5)
  except subprocess.TimeoutExpired:
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def run_tree(env, tree, timeout=30):
  return subprocess.run(['ros2', 'run', 'bt_construct', 'run_tree', str(TREES / tree)],
                        env=env, capture_output=True, text=True, timeout=timeout)


@pytest.fixture
def mocks(ros_env, tmp_path):
  procs = []

  def start(**params):
    procs.append(start_mocks(ros_env, tmp_path / 'mock_skills.log', **params))

  yield start
  for p in procs:
    stop(p)


def test_find_and_crush_succeeds(ros_env, mocks):
  mocks()
  result = run_tree(ros_env, 'find_and_crush.xml')
  assert result.returncode == 0, result.stdout + result.stderr
  assert 'tree finished: SUCCESS' in result.stdout


def test_skips_search_when_can_is_already_visible(ros_env, mocks):
  mocks(mock_visible_objects="['can']")
  result = run_tree(ros_env, 'find_and_crush.xml')
  assert result.returncode == 0, result.stdout + result.stderr
  assert '[ SearchFor ]' not in result.stdout  # the Fallback never needed it


def test_fails_with_reason_when_can_is_missing(ros_env, mocks):
  mocks(mock_missing_objects="['can']")
  result = run_tree(ros_env, 'find_and_crush.xml')
  assert result.returncode == 1
  assert 'not_found' in result.stdout + result.stderr


def test_fallback_settles_for_a_can(ros_env, mocks):
  mocks(mock_missing_objects="['ball']")
  result = run_tree(ros_env, 'search_or_settle.xml')
  assert result.returncode == 0, result.stdout + result.stderr


def test_crusher_refusal_fails_the_tree(ros_env, mocks):
  mocks(mock_crusher_safe='false')
  result = run_tree(ros_env, 'find_and_crush.xml')
  assert result.returncode == 1
  assert 'crusher_unsafe' in result.stdout + result.stderr


def test_unknown_node_is_a_clear_error(ros_env, tmp_path):
  tree = tmp_path / 'say.xml'
  tree.write_text('<root BTCPP_format="4" main_tree_to_execute="M"><BehaviorTree ID="M">'
                  '<Say text="hi"/></BehaviorTree></root>')
  result = subprocess.run(['ros2', 'run', 'bt_construct', 'run_tree', str(tree)],
                          env=ros_env, capture_output=True, text=True, timeout=30)
  assert result.returncode == 2
  assert 'Say' in result.stderr
