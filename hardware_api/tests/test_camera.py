import math

import pytest

from hardware_api.camera import MockCameraBackend, RGBDFrame, pinhole_intrinsics


def test_frame_rejects_wrong_buffer_sizes():
  with pytest.raises(ValueError):
    RGBDFrame(2, 2, bytes(11), bytes(16))
  with pytest.raises(ValueError):
    RGBDFrame(2, 2, bytes(12), bytes(15))
  with pytest.raises(ValueError):
    RGBDFrame(0, 2, b'', b'')


def test_mock_frame_shape_and_wall_depth():
  frame = MockCameraBackend(width=30, height=18, depth_m=2.5).read()
  assert (frame.width, frame.height) == (30, 18)
  assert len(frame.color) == 30 * 18 * 3
  assert len(frame.depth) == 30 * 18 * 4
  assert frame.depth_at(0, 0) == pytest.approx(2.5)
  assert frame.depth_at(29, 17) == pytest.approx(2.5)


def test_mock_object_sits_in_center_third():
  camera = MockCameraBackend(width=30, height=30, depth_m=2.0, object_depth_m=0.4)
  frame = camera.read()
  assert frame.depth_at(15, 15) == pytest.approx(0.4)
  assert frame.depth_at(2, 2) == pytest.approx(2.0)
  assert frame.color[(15 * 30 + 15) * 3:(15 * 30 + 15) * 3 + 3] == bytes((200, 30, 30))


def test_set_object_depth_changes_and_removes_object():
  camera = MockCameraBackend(width=30, height=30, depth_m=2.0)
  assert camera.read().depth_at(15, 15) == pytest.approx(2.0)
  camera.set_object_depth(0.5)
  assert camera.read().depth_at(15, 15) == pytest.approx(0.5)
  camera.set_object_depth(None)
  assert camera.read().depth_at(15, 15) == pytest.approx(2.0)


def test_read_returns_same_frame_until_scene_changes():
  camera = MockCameraBackend(width=6, height=6)
  assert camera.read() is camera.read()


def test_depth_at_rejects_out_of_range_pixel():
  frame = MockCameraBackend(width=6, height=6).read()
  with pytest.raises(IndexError):
    frame.depth_at(6, 0)
  with pytest.raises(IndexError):
    frame.depth_at(0, -1)


def test_pinhole_intrinsics():
  fx, fy, cx, cy = pinhole_intrinsics(640, 480, math.pi / 2)
  assert fx == pytest.approx(320.0)
  assert fy == fx
  assert (cx, cy) == (320.0, 240.0)


def test_pinhole_rejects_bad_fov():
  with pytest.raises(ValueError):
    pinhole_intrinsics(640, 480, 0.0)
  with pytest.raises(ValueError):
    pinhole_intrinsics(640, 480, math.pi)
