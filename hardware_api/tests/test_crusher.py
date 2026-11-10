import pytest

from hardware_api.crusher import (
  CrusherBackend, CrusherController, CrusherSafety, MockCrusherBackend)


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


def make(safe=True, cycle_time=5.0):
  backend = MockCrusherBackend()
  if safe:
    backend.chamber_closed = backend.hardware_lock_engaged = backend.contents_ok = True
  clock = FakeClock()
  return CrusherController(backend, cycle_time, clock), backend, clock


def test_refuses_by_default_and_never_starts_the_motor():
  controller, backend, _ = make(safe=False)
  started, message = controller.run()
  assert not started
  assert 'chamber_closed' in message and 'hardware_lock_engaged' in message
  assert 'contents_ok' in message
  assert not backend.running and not controller.running


@pytest.mark.parametrize('field', ['chamber_closed', 'hardware_lock_engaged', 'contents_ok'])
def test_each_safety_input_alone_blocks_a_run(field):
  controller, backend, _ = make()
  setattr(backend, field, False)
  started, message = controller.run()
  assert not started and field in message
  assert not backend.running


def test_runs_when_safe_and_completes_after_cycle_time():
  controller, backend, clock = make(cycle_time=5.0)
  assert controller.run() == (True, 'crush cycle started')
  assert backend.running and controller.running
  clock.t = 4.9
  assert controller.step() is True and backend.running
  clock.t = 5.0
  assert controller.step() is False
  assert not backend.running
  assert controller.last_result == 'complete'


def test_aborts_if_a_safety_input_drops_mid_cycle():
  controller, backend, clock = make()
  controller.run()
  clock.t = 1.0
  backend.chamber_closed = False
  assert controller.step() is False
  assert not backend.running
  assert controller.last_result == 'aborted: chamber_closed'


def test_stop_aborts_a_running_cycle():
  controller, backend, _ = make()
  controller.run()
  controller.stop()
  assert not backend.running and not controller.running
  assert controller.last_result == 'aborted: stop requested'


def test_stop_when_idle_still_stops_the_motor():
  controller, backend, _ = make()
  backend.running = True
  controller.stop()
  assert not backend.running
  assert controller.last_result == 'idle'


def test_second_run_while_running_is_refused():
  controller, _, _ = make()
  controller.run()
  assert controller.run() == (False, 'refused: already running')


def test_can_run_again_after_a_cycle_completes():
  controller, _, clock = make(cycle_time=1.0)
  controller.run()
  clock.t = 1.0
  controller.step()
  assert controller.run()[0] is True


def test_unreadable_safety_sensor_refuses_a_run():
  class Broken(MockCrusherBackend):
    def read_safety(self):
      raise OSError('sensor bus down')

  backend = Broken()
  controller = CrusherController(backend, 5.0, FakeClock())
  started, message = controller.run()
  assert not started and 'safety_read_failed' in message
  assert not backend.running


def test_unreadable_safety_sensor_aborts_a_running_cycle():
  controller, backend, clock = make()
  controller.run()

  def broken():
    raise OSError('sensor bus down')

  backend.read_safety = broken
  clock.t = 1.0
  assert controller.step() is False
  assert not backend.running
  assert controller.last_result == 'aborted: safety_read_failed'


def test_step_when_idle_does_nothing():
  controller, backend, _ = make()
  assert controller.step() is False
  assert not backend.running


def test_rejects_bad_cycle_time_and_abstract_backend():
  with pytest.raises(ValueError):
    CrusherController(MockCrusherBackend(), cycle_time=0.0)
  with pytest.raises(TypeError):
    CrusherBackend()


def test_safety_problems_lists_only_failures():
  assert CrusherSafety(True, True, True).problems() == []
  assert CrusherSafety(True, False, True).problems() == ['hardware_lock_engaged']
