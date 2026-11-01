import pytest

from hardware_api.audio import AudioBackend, AudioController, MockAudioBackend


class FakeClock:
  def __init__(self):
    self.t = 0.0

  def __call__(self):
    return self.t


def test_play_accepts_clip_and_reports_playing():
  clock = FakeClock()
  backend = MockAudioBackend(clip_duration=1.0, clock=clock)
  controller = AudioController(backend)
  assert controller.play('hello') == (True, 'playing')
  assert backend.played == ['hello']
  assert controller.playing()
  clock.t = 1.5
  assert not controller.playing()


def test_play_strips_and_rejects_empty():
  backend = MockAudioBackend()
  controller = AudioController(backend)
  accepted, _ = controller.play('   ')
  assert not accepted
  assert backend.played == []
  controller.play('  beep ')
  assert backend.played == ['beep']


def test_unknown_clip_is_rejected_without_changing_playback():
  clock = FakeClock()
  backend = MockAudioBackend(known_clips={'beep'}, clock=clock)
  controller = AudioController(backend)
  accepted, message = controller.play('nope')
  assert not accepted and 'nope' in message
  assert not controller.playing()


def test_new_clip_replaces_current():
  clock = FakeClock()
  backend = MockAudioBackend(clip_duration=1.0, clock=clock)
  controller = AudioController(backend)
  controller.play('a')
  clock.t = 0.8
  controller.play('b')
  clock.t = 1.5
  assert controller.playing()  # b started at 0.8, ends at 1.8


def test_stop_cuts_playback():
  backend = MockAudioBackend()
  controller = AudioController(backend)
  controller.play('a')
  controller.stop()
  assert not controller.playing()


def test_chunk_size_follows_rate_and_chunk_ms():
  controller = AudioController(MockAudioBackend(), sample_rate=16000, chunk_ms=20)
  assert controller.chunk_samples == 320
  assert len(controller.read_chunk()) == 640


def test_short_mic_read_is_zero_padded():
  class ShortMic(MockAudioBackend):
    def read_mic(self, n_samples):
      return b'\x01\x02' * 10

  chunk = AudioController(ShortMic(), sample_rate=16000, chunk_ms=20).read_chunk()
  assert len(chunk) == 640
  assert chunk[:20] == b'\x01\x02' * 10
  assert chunk[20:] == bytes(620)


def test_long_mic_read_is_truncated():
  class LongMic(MockAudioBackend):
    def read_mic(self, n_samples):
      return bytes([1]) * 5000

  assert len(AudioController(LongMic(), sample_rate=16000, chunk_ms=20).read_chunk()) == 640


def test_rejects_bad_framing():
  with pytest.raises(ValueError):
    AudioController(MockAudioBackend(), sample_rate=0)
  with pytest.raises(ValueError):
    AudioController(MockAudioBackend(), sample_rate=100, chunk_ms=1)


def test_backend_is_abstract():
  with pytest.raises(TypeError):
    AudioBackend()
