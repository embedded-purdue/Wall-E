import pytest

from hardware_api.esp32_backend import Esp32Link
from hardware_api.esp32_protocol import ProtocolError, parse_reply, parse_ultrasonic
from hardware_api.fake_esp32 import FakeEsp32
from hardware_api.sensors import Esp32SensorsBackend, MockSensorsBackend, battery_fraction


def test_ultrasonic_parse():
  assert parse_ultrasonic(parse_reply(b'U 0.42 -1\n')) == [0.42, None]
  with pytest.raises(ProtocolError):
    parse_ultrasonic(parse_reply(b'U\n'))
  with pytest.raises(ProtocolError):
    parse_ultrasonic(parse_reply(b'U abc\n'))


def test_esp32_sensors_backend():
  esp = FakeEsp32(battery_volts=18.5, ultrasonic=(0.8, None))
  backend = Esp32SensorsBackend(Esp32Link(esp))
  assert backend.read_battery() == pytest.approx(18.5)
  assert backend.read_ultrasonic() == [pytest.approx(0.8), None]


def test_mock_sensors_backend():
  backend = MockSensorsBackend(19.0, [2.0, 0.5])
  assert backend.read_battery() == 19.0
  assert backend.read_ultrasonic() == [2.0, 0.5]


def test_battery_fraction():
  assert battery_fraction(15.0, 15.0, 20.0) == 0.0
  assert battery_fraction(17.5, 15.0, 20.0) == 0.5
  assert battery_fraction(21.0, 15.0, 20.0) == 1.0
  assert battery_fraction(10.0, 15.0, 20.0) == 0.0
  with pytest.raises(ValueError):
    battery_fraction(17.0, 20.0, 15.0)


def test_shared_link_is_one_per_device(monkeypatch):
  opened = []

  def fake_open(cls, device, baud=115200, timeout=0.05):
    opened.append(device)
    return cls(FakeEsp32())

  monkeypatch.setattr(Esp32Link, 'open', classmethod(fake_open))
  monkeypatch.setattr(Esp32Link, '_shared', {})
  a = Esp32Link.shared('/dev/ttyTHS1')
  b = Esp32Link.shared('/dev/ttyTHS1')
  assert a is b and opened == ['/dev/ttyTHS1']
