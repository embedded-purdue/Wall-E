"""RGB-D frame type, camera backend interface and a mock camera. No ROS imports.

Color is rgb8 (row-major, 3 bytes per pixel). Depth is float32 little-endian
meters (row-major, 4 bytes per pixel) aligned to the color image; NaN means no
reading, which is also what a color-only camera should return.
"""

import math
import sys
from abc import ABC, abstractmethod
from array import array
from dataclasses import dataclass


@dataclass(frozen=True)
class RGBDFrame:
  width: int
  height: int
  color: bytes
  depth: bytes

  def __post_init__(self):
    if self.width <= 0 or self.height <= 0:
      raise ValueError('width and height must be > 0')
    if len(self.color) != self.width * self.height * 3:
      raise ValueError('color must be width * height * 3 bytes (rgb8)')
    if len(self.depth) != self.width * self.height * 4:
      raise ValueError('depth must be width * height * 4 bytes (float32)')

  def depth_at(self, x: int, y: int) -> float:
    """Depth in meters at pixel (x, y); NaN if there is no reading."""
    if not (0 <= x < self.width and 0 <= y < self.height):
      raise IndexError(f'pixel ({x}, {y}) is outside {self.width}x{self.height}')
    values = array('f')
    values.frombytes(self.depth)
    if sys.byteorder == 'big':
      values.byteswap()
    return values[y * self.width + x]


def pinhole_intrinsics(width: int, height: int, hfov: float) -> tuple[float, float, float, float]:
  """Return (fx, fy, cx, cy) for an ideal pinhole camera with square pixels."""
  if not 0.0 < hfov < math.pi:
    raise ValueError(f'hfov must be in (0, pi) radians, got {hfov}')
  fx = (width / 2.0) / math.tan(hfov / 2.0)
  return fx, fx, width / 2.0, height / 2.0


class CameraBackend(ABC):
  """Camera interface. Real (Jetson CSI / depth camera) and mock backends implement this."""

  @abstractmethod
  def read(self) -> RGBDFrame:
    """Return the latest color + depth frame."""


class MockCameraBackend(CameraBackend):
  """Synthetic scene: gray wall at depth_m, optionally a red box in the center third."""

  def __init__(self, width: int = 320, height: int = 240, depth_m: float = 2.0,
               object_depth_m: float | None = None):
    if width <= 0 or height <= 0:
      raise ValueError('width and height must be > 0')
    self._width = width
    self._height = height
    self._depth_m = depth_m
    self._object_depth_m = object_depth_m
    self._frame = None

  def set_object_depth(self, depth_m: float | None) -> None:
    """Put the box at depth_m meters, or remove it with None."""
    self._object_depth_m = depth_m
    self._frame = None

  def _in_box(self, x: int, y: int) -> bool:
    return (self._width // 3 <= x < 2 * self._width // 3
            and self._height // 3 <= y < 2 * self._height // 3)

  def _build(self) -> RGBDFrame:
    color = bytearray()
    depth = array('f')
    for y in range(self._height):
      for x in range(self._width):
        if self._object_depth_m is not None and self._in_box(x, y):
          color += bytes((200, 30, 30))
          depth.append(self._object_depth_m)
        else:
          color += bytes((128, 128, 128))
          depth.append(self._depth_m)
    if sys.byteorder == 'big':
      depth.byteswap()
    return RGBDFrame(self._width, self._height, bytes(color), depth.tobytes())

  def read(self) -> RGBDFrame:
    if self._frame is None:
      self._frame = self._build()
    return self._frame
