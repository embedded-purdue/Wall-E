import pytest

from hardware_api.drive_backend import DriveBackend
from hardware_api.kinematics import DriveParams
from hardware_api.roboclaw_backend import RoboClawBackend

PARAMS = DriveParams(wheel_radius=0.05, track_width=0.4, ticks_per_rev=2000, max_wheel_speed=1.0)


def test_stub_implements_interface_and_defaults():
  backend = RoboClawBackend(PARAMS, port='')
  assert isinstance(backend, DriveBackend)
  assert (backend._address, backend._baud) == (0x80, 38400)


def test_stub_methods_not_implemented():
  backend = RoboClawBackend(PARAMS, port='')
  with pytest.raises(NotImplementedError):
    backend.set_wheel_speeds(0.0, 0.0)
  with pytest.raises(NotImplementedError):
    backend.stop()
  with pytest.raises(NotImplementedError):
    backend.read_encoders()
