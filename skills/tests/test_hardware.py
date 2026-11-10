import math
import sys
from array import array

import pytest

from skills.fake_hardware import FakeHardware
from skills.hardware import Frame


def make_frame(width=4, height=2, depth=2.0, nan_at=None):
  values = array('f', [depth] * (width * height))
  if nan_at is not None:
    values[nan_at[1] * width + nan_at[0]] = math.nan
  if sys.byteorder == 'big':
    values.byteswap()
  return Frame(width, height, bytes(width * height * 3), values.tobytes(), fx=2.0, fy=2.0, cx=2.0, cy=1.0)


def test_depth_at_reads_pixel_and_nan():
  frame = make_frame(nan_at=(3, 1))
  assert frame.depth_at(0, 0) == pytest.approx(2.0)
  assert math.isnan(frame.depth_at(3, 1))
  with pytest.raises(IndexError):
    frame.depth_at(4, 0)


def test_deproject_center_and_offset():
  frame = make_frame()
  assert frame.deproject(2.0, 1.0, 2.0) == pytest.approx((0.0, 0.0, 2.0))
  assert frame.deproject(4.0, 1.0, 2.0) == pytest.approx((2.0, 0.0, 2.0))
  with pytest.raises(ValueError):
    frame.deproject(0.0, 0.0, math.nan)


def test_fake_gripper_reports_holding_only_with_an_object():
  hw = FakeHardware()
  hw.set_gripper(True)
  assert not hw.gripper().holding
  hw.object_in_gripper = True
  hw.set_gripper(True)
  assert hw.gripper().holding
  hw.set_gripper(False)
  assert not hw.gripper().holding


def test_fake_crusher_refuses_when_unsafe():
  hw = FakeHardware()
  hw.crusher_safe = False
  assert hw.run_crusher() == (False, 'refused: unsafe')
  hw.crusher_safe = True
  assert hw.run_crusher()[0] and hw.crusher().result == 'complete'


def test_fake_records_calls():
  hw = FakeHardware()
  hw.drive(0.2, 0.1)
  hw.stop()
  assert hw.calls == [('drive', 0.2, 0.1), ('stop',)]
  assert hw.cmd == (0.0, 0.0)
