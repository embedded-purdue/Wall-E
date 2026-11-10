"""The robot model's names must match what the hardware API publishes."""

import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
URDF = ET.parse(ROOT / 'urdf' / 'wall_e.urdf').getroot()
JOINTS = {j.get('name'): j for j in URDF.findall('joint')}
LINKS = {link.get('name') for link in URDF.findall('link')}


def test_frames_from_topics_doc_exist():
  assert {'base_link', 'camera_link', 'ultrasonic_front'} <= LINKS


def test_every_joint_connects_known_links_and_tree_has_one_root():
  children = set()
  for joint in JOINTS.values():
    assert joint.find('parent').get('link') in LINKS
    child = joint.find('child').get('link')
    assert child in LINKS and child not in children
    children.add(child)
  assert LINKS - children == {'base_link'}


def test_head_and_eye_joints_match_head_eyes_node():
  for name in ('head_pan', 'head_tilt', 'eye_left', 'eye_right'):
    assert JOINTS[name].get('type') == 'revolute'


def test_arm_joints_and_limits_match_config():
  params = yaml.safe_load((ROOT / 'config' / 'peripherals.yaml').read_text())['arm_node']['ros__parameters']
  for name, lo, hi in zip(params['arm_joint_names'], params['arm_min'], params['arm_max']):
    limit = JOINTS[name].find('limit')
    assert float(limit.get('lower')) == lo and float(limit.get('upper')) == hi


def test_head_limits_match_config():
  params = yaml.safe_load((ROOT / 'config' / 'peripherals.yaml').read_text())['head_eyes_node']['ros__parameters']
  for name in ('head_pan', 'head_tilt'):
    limit = JOINTS[name].find('limit')
    assert float(limit.get('lower')) == params[f'{name}_min']
    assert float(limit.get('upper')) == params[f'{name}_max']
