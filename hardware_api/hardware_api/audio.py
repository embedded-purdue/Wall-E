"""Audio playback and microphone logic between the ROS node and an AudioBackend. No ROS imports.

Microphone data is raw PCM: signed 16-bit little-endian, mono, at the sample rate
the controller was built with.
"""

import time
from abc import ABC, abstractmethod


class AudioBackend(ABC):
  """Speaker and microphone interface. Real and mock backends implement this."""

  @abstractmethod
  def play(self, clip: str) -> None:
    """Start playing a clip (a clip name or file path), replacing any current clip.

    Raises KeyError or FileNotFoundError if the clip cannot be found.
    """

  @abstractmethod
  def stop_playback(self) -> None:
    """Stop playing immediately."""

  @abstractmethod
  def is_playing(self) -> bool:
    """True while a clip is still playing."""

  @abstractmethod
  def read_mic(self, n_samples: int) -> bytes:
    """Return up to n_samples of microphone PCM (s16le mono); fewer if not ready."""


class MockAudioBackend(AudioBackend):
  """Hardware-free audio: plays nothing, records the clips, and the mic is silent."""

  def __init__(self, clip_duration: float = 1.0, known_clips=None, clock=time.monotonic):
    self._clip_duration = clip_duration
    self._known_clips = None if known_clips is None else set(known_clips)
    self._clock = clock
    self._ends_at = None
    self.played: list[str] = []

  def play(self, clip: str) -> None:
    if self._known_clips is not None and clip not in self._known_clips:
      raise KeyError(f"unknown clip '{clip}'")
    self.played.append(clip)
    self._ends_at = self._clock() + self._clip_duration

  def stop_playback(self) -> None:
    self._ends_at = None

  def is_playing(self) -> bool:
    return self._ends_at is not None and self._clock() < self._ends_at

  def read_mic(self, n_samples: int) -> bytes:
    return bytes(2 * n_samples)


class AudioController:
  """Validates play requests and frames the microphone stream into fixed-size chunks."""

  def __init__(self, backend: AudioBackend, sample_rate: int = 16000, chunk_ms: int = 20):
    if sample_rate <= 0 or chunk_ms <= 0:
      raise ValueError('sample_rate and chunk_ms must be > 0')
    self._backend = backend
    self.sample_rate = sample_rate
    self.chunk_samples = sample_rate * chunk_ms // 1000
    if self.chunk_samples <= 0:
      raise ValueError('chunk_ms is too small for this sample_rate')

  def play(self, clip: str) -> tuple[bool, str]:
    """Start a clip. Returns (accepted, message); a rejected clip changes nothing."""
    clip = clip.strip()
    if not clip:
      return False, 'empty clip name'
    try:
      self._backend.play(clip)
    except (KeyError, FileNotFoundError) as exc:
      return False, str(exc)
    return True, 'playing'

  def stop(self) -> None:
    self._backend.stop_playback()

  def playing(self) -> bool:
    return self._backend.is_playing()

  def read_chunk(self) -> bytes:
    """Return exactly chunk_samples of mic PCM, zero-padded if the backend had less."""
    size = 2 * self.chunk_samples
    data = self._backend.read_mic(self.chunk_samples)[:size]
    return data + bytes(size - len(data))
