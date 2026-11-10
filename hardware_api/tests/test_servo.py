import pytest

from hardware_api.esp32_backend import Esp32Link
from hardware_api.esp32_protocol import ProtocolError, encode_read_servo, encode_servo, parse_reply, parse_servo
from hardware_api.fake_esp32 import FakeEsp32
from hardware_api.joints import JointController, JointSpec
from hardware_api.servo import Esp32ServoGripperBackend, Esp32ServoJointBackend, ServoChannel

PAN = JointSpec('head_pan', -1.0, 1.0, 2.0)
TILT = JointSpec('head_tilt', -0.5, 0.5, 2.0)


def test_servo_messages():
  assert encode_servo(3, 1500.4) == b'P 3 1500\n'
  assert encode_read_servo(3) == b'Q 3\n'
  assert parse_servo(parse_reply(b'Q 3 1500\n'), 3) == 1500.0
  with pytest.raises(ProtocolError):
    parse_servo(parse_reply(b'Q 4 1500\n'), 3)
  with pytest.raises(ValueError):
    encode_servo(-1, 1500)
  with pytest.raises(ValueError):
    encode_servo(0, float('nan'))


def test_channel_maps_angle_range_onto_pulse_range():
  channel = ServoChannel(0, 1000.0, 2000.0)
  assert channel.to_us(-1.0, PAN) == 1000.0
  assert channel.to_us(0.0, PAN) == 1500.0
  assert channel.to_us(1.0, PAN) == 2000.0
  assert channel.to_us(5.0, PAN) == 2000.0  # clamped to the joint limit
  assert channel.to_angle(1750.0, PAN) == pytest.approx(0.5)


def test_reversed_servo():
  channel = ServoChannel(0, 2000.0, 1000.0)
  assert channel.to_us(1.0, PAN) == 1000.0


def test_bad_channel_rejected():
  with pytest.raises(ValueError):
    ServoChannel(0, 1500.0, 1500.0)
  with pytest.raises(ValueError):
    ServoChannel(-1, 1000.0, 2000.0)


def make_head(esp):
  channels = {'head_pan': ServoChannel(0, 1000.0, 2000.0), 'head_tilt': ServoChannel(1, 1200.0, 1800.0)}
  return Esp32ServoJointBackend(Esp32Link(esp), [PAN, TILT], channels)


def test_head_backend_sends_pulses():
  esp = FakeEsp32()
  backend = make_head(esp)
  backend.set_positions({'head_pan': 0.5, 'head_tilt': -0.5})
  assert esp.servos == {0: 1750.0, 1: 1200.0}
  assert backend.read_positions() == {'head_pan': 0.5, 'head_tilt': -0.5}


def test_head_backend_skips_unchanged_pulses():
  esp = FakeEsp32()
  backend = make_head(esp)
  backend.set_positions({'head_pan': 0.0})
  backend.set_positions({'head_pan': 0.0})
  backend.set_positions({'head_pan': 0.0001})  # under 1 us change
  assert [line for line in esp.log if line.startswith('P')] == ['P 0 1500']


def test_missing_channel_rejected():
  with pytest.raises(ValueError):
    Esp32ServoJointBackend(Esp32Link(FakeEsp32()), [PAN, TILT], {'head_pan': ServoChannel(0, 1000.0, 2000.0)})


def test_firmware_out_of_range_raises():
  esp = FakeEsp32(servo_limits={0: (1400.0, 1600.0)})
  with pytest.raises(ProtocolError, match='out_of_range'):
    make_head(esp).set_positions({'head_pan': 1.0})


def test_joint_controller_drives_servos():
  esp = FakeEsp32()
  t = [0.0]
  controller = JointController(make_head(esp), [PAN, TILT], clock=lambda: t[0])
  controller.command({'head_pan': 1.0})
  for i in range(1, 30):
    t[0] = i * 0.05
    controller.step()
  assert esp.servos[0] == 2000.0  # reached the target at the slew limit
  assert esp.servos[1] == 1500.0  # tilt stayed home


def test_gripper_backend():
  esp = FakeEsp32()
  gripper = Esp32ServoGripperBackend(Esp32Link(esp), channel=4, open_us=1200.0, closed_us=1800.0)
  gripper.set_closed(True)
  assert esp.servos[4] == 1800.0
  state = gripper.read_state()
  assert state.closed_command and state.position == pytest.approx(1.0)
  assert state.holding is False  # a plain servo can't tell
  gripper.set_closed(False)
  assert gripper.read_state().position == pytest.approx(0.0)
