"""Arm, crusher, gripper-contact and switch-input messages against the fake ESP32."""

import math

import pytest

from hardware_api.bench_esp32 import main as bench_main, run_crusher
from hardware_api.crusher import CrusherController
from hardware_api.esp32_backend import Esp32Link
from hardware_api.esp32_motors import Esp32ArmJointBackend, Esp32CrusherBackend
from hardware_api.esp32_protocol import (
  ProtocolError,
  Reply,
  encode_arm,
  encode_crusher,
  parse_arm,
  parse_inputs,
  parse_reply,
)
from hardware_api.fake_esp32 import FakeEsp32
from hardware_api.joints import JointController, JointSpec
from hardware_api.servo import Esp32ServoGripperBackend

SPECS = [JointSpec('shoulder_pan', -1.5, 1.5, 1.0), JointSpec('shoulder_lift', -0.5, 1.5, 1.0),
         JointSpec('elbow', 0.0, 2.5, 1.5, home=0.5), JointSpec('wrist', -1.5, 1.5, 2.0)]
CPR = [1000.0, 1000.0, -500.0, 1000.0]


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


@pytest.fixture
def clock():
  return FakeClock()


@pytest.fixture
def esp(clock):
  return FakeEsp32(clock=clock, send_ready=False)


@pytest.fixture
def link(esp):
  return Esp32Link(esp)


def safe(esp):
  esp.inputs.update(chamber_closed=True, lock_engaged=True, contents_ok=True)


# ---- wire format ------------------------------------------------------------

def test_encode_arm_and_crusher():
  assert encode_arm([0, -12, 340.6, 7]) == b'A 0 -12 341 7\n'
  assert encode_crusher(60.0) == b'C 60\n'
  assert encode_crusher(0) == b'C 0\n'
  for bad in (-1.0, 101.0, math.nan):
    with pytest.raises(ValueError):
      encode_crusher(bad)
  with pytest.raises(ValueError):
    encode_arm([])


def test_parse_arm_and_inputs():
  assert parse_arm(parse_reply(b'J 1 -2 3 4\n')) == [1, -2, 3, 4]
  assert parse_inputs(parse_reply(b'I 1 0 1 0\r\n')) == [True, False, True, False]
  for bad in (Reply('J', ('x',)), Reply('J', ())):
    with pytest.raises(ProtocolError):
      parse_arm(bad)
  for bad in (Reply('I', ('2',)), Reply('I', ()), Reply('OK', ('I',))):
    with pytest.raises(ProtocolError):
      parse_inputs(bad)


def test_read_inputs_by_name(esp, link):
  esp.inputs['lock_engaged'] = True
  assert link.read_inputs() == {'chamber_closed': False, 'lock_engaged': True,
                                'contents_ok': False, 'gripper_contact': False}
  assert esp.log == ['I']


# ---- arm ----------------------------------------------------------------------

def test_arm_sends_counts_relative_to_home(esp, link):
  backend = Esp32ArmJointBackend(link, SPECS, CPR)
  backend.set_positions({'shoulder_pan': 0.5, 'elbow': 1.0})
  assert esp.log == ['A 500 0 -250 0']
  positions = backend.read_positions()
  assert positions['shoulder_pan'] == pytest.approx(0.5)
  assert positions['elbow'] == pytest.approx(1.0)
  assert positions['wrist'] == pytest.approx(0.0)


def test_arm_clamps_and_skips_unchanged_targets(esp, link):
  backend = Esp32ArmJointBackend(link, SPECS, CPR)
  backend.set_positions({'shoulder_pan': 9.0})
  backend.set_positions({'shoulder_pan': 9.0})
  backend.set_positions({'shoulder_pan': 1.5001})
  assert esp.log == ['A 1500 0 0 0']


def test_arm_controller_slews_on_the_jetson(esp, link, clock):
  arm = JointController(Esp32ArmJointBackend(link, SPECS, CPR), SPECS, clock=clock)
  arm.command({'shoulder_pan': 1.0})
  arm.step()
  for _ in range(5):
    clock.t += 0.1
    arm.step()
  assert esp.arm[0] == 500  # 1 rad/s for 0.5 s
  assert len(esp.log) == 6  # one A per step that moved (first step sends home)


def test_arm_config_mismatch_is_refused(link):
  with pytest.raises(ValueError):
    Esp32ArmJointBackend(link, SPECS, [1000.0])
  with pytest.raises(ValueError):
    Esp32ArmJointBackend(link, SPECS, [1000.0, 0.0, 1.0, 1.0])


def test_arm_wrong_motor_count_is_an_error(link, esp):
  esp.arm = [0, 0]
  with pytest.raises(ProtocolError):
    Esp32ArmJointBackend(link, SPECS, CPR).read_positions()


def test_arm_holds_through_silence(esp, link, clock):
  Esp32ArmJointBackend(link, SPECS, CPR).set_positions({'wrist': 0.2})
  clock.t = 5.0
  assert link.read_arm() == [0, 0, 0, 200]


# ---- crusher ------------------------------------------------------------------

def test_crusher_refuses_unless_switches_closed(esp, link, clock):
  controller = CrusherController(Esp32CrusherBackend(link, 60.0), cycle_time=2.0, clock=clock)
  started, message = controller.run()
  assert not started and 'chamber_closed' in message
  assert esp.crusher == 0 and 'C 60' not in esp.log


def test_crusher_cycle_runs_then_stops(esp, link, clock):
  safe(esp)
  controller = CrusherController(Esp32CrusherBackend(link, 60.0), cycle_time=2.0, clock=clock)
  assert controller.run()[0]
  assert esp.crusher == 60
  clock.t = 2.0
  controller.step()
  assert esp.crusher == 0 and controller.last_result == 'complete'
  assert esp.log[-1] == 'C 0'


def test_crusher_aborts_when_a_switch_opens(esp, link, clock):
  safe(esp)
  controller = CrusherController(Esp32CrusherBackend(link), clock=clock)
  controller.run()
  esp.inputs['lock_engaged'] = False
  controller.step()
  assert esp.crusher == 0
  assert controller.last_result == 'aborted: hardware_lock_engaged'


def test_firmware_interlock_refuses_even_if_jetson_asks(esp, link):
  with pytest.raises(ProtocolError, match='interlock'):
    link.set_crusher(50)


def test_crusher_stops_on_silence_and_on_S(esp, link, clock):
  safe(esp)
  link.set_crusher(40)
  clock.t = 1.0
  link.heartbeat()
  assert esp.crusher == 0 and esp.timed_out
  link.set_crusher(40)
  link.stop()
  assert esp.crusher == 0


def test_dead_link_counts_as_unsafe(clock):
  class DeadPort:
    def write(self, data):
      pass

    def readline(self):
      return b''

  controller = CrusherController(Esp32CrusherBackend(Esp32Link(DeadPort())), clock=clock)
  assert controller.run() == (False, 'refused: safety_read_failed')


# ---- gripper finger switch ------------------------------------------------------

def test_gripper_holding_uses_finger_switch(esp, link):
  gripper = Esp32ServoGripperBackend(link, 4, 1200.0, 1800.0, use_contact=True)
  gripper.set_closed(True)
  assert not gripper.read_state().holding
  esp.inputs['gripper_contact'] = True
  state = gripper.read_state()
  assert state.holding and state.position == pytest.approx(1.0)
  gripper.set_closed(False)
  assert not gripper.read_state().holding


def test_gripper_without_switch_never_reports_holding(esp, link):
  gripper = Esp32ServoGripperBackend(link, 4, 1200.0, 1800.0)
  esp.inputs['gripper_contact'] = True
  gripper.set_closed(True)
  assert not gripper.read_state().holding
  assert 'I' not in esp.log


# ---- bench tool -------------------------------------------------------------------

def test_bench_crusher_always_stops(esp, link):
  safe(esp)
  times = iter([0.0, 0.0, 0.5, 1.5])
  run_crusher(link, 30, 1.0, sleep=lambda s: None, clock=lambda: next(times))
  assert esp.log[0] == 'C 30' and esp.log[-1] == 'C 0' and esp.crusher == 0


@pytest.mark.parametrize('argv', [
  ['--fake', 'inputs'], ['--fake', 'servo', '4', '1500'], ['--fake', 'servo-read', '4'],
  ['--fake', 'arm', '0', '0', '200', '0'], ['--fake', 'arm-read'],
  ['--fake', 'crusher', '30', '--seconds', '0'],
])
def test_bench_fake_runs(argv, capsys):
  assert bench_main(argv) == 0


def test_bench_refuses_fast_crusher():
  with pytest.raises(SystemExit):
    bench_main(['--fake', 'crusher', '90'])


def test_bench_reports_esp32_errors(capsys):
  assert bench_main(['--fake', 'arm', '1', '2']) == 1  # fake has 4 arm motors
  assert 'bad_args' in capsys.readouterr().err
