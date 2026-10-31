"""
Moonshine speech-to-text demo for Wall-E, gated on a wake word.
Same models/library as moonshine_demo2.py (official Moonshine Voice, keyterms).

The mic always runs, but transcripts are ignored until the wake word is heard.
Say "WALL-E" and everything after it (same breath or next one) becomes a command.
After one command, or after --timeout seconds of nothing, it goes back to sleep.

to use:
  python moonshine_demo3.py                         # live mic, tiny-streaming
  python moonshine_demo3.py --size small-streaming  # bigger, more accurate
  python moonshine_demo3.py --timeout 10            # stay awake longer
  python moonshine_demo3.py --wav path.wav          # run a .wav through the same gate

takeaways:
- wake word is matched on partials, so it wakes mid-sentence instead of after the pause
- STT spells "WALL-E" a lot of different ways, hence WAKE_VARIANTS below
"""
import argparse
import re
import time

from moonshine_voice import ModelArch, get_model_for_language, load_wav_file
from moonshine_voice.transcriber import Transcriber

SIZES = {
    "tiny": ModelArch.TINY,
    "base": ModelArch.BASE,
    "tiny-streaming": ModelArch.TINY_STREAMING,
    "base-streaming": ModelArch.BASE_STREAMING,
    "small-streaming": ModelArch.SMALL_STREAMING,
    "medium-streaming": ModelArch.MEDIUM_STREAMING,
}

# Words the model should expect. Only works with streaming models.
KEYTERMS = ["Wall-E"]

# How the models actually spell it. Punctuation is stripped before matching,
# so "WALL-E," and "wall e" both arrive here as "wall e".
WAKE_VARIANTS = ["wall e", "walle", "wally", "wallie", "wall ee", "wahlee", "volley"]
WAKE_RE = re.compile(r"\b(" + "|".join(WAKE_VARIANTS) + r")\b")


def normalize(text):
    """Lowercase, punctuation to spaces, collapse runs of whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def find_wake(text):
    """Return (heard_wake_word, text_after_it) for a normalized transcript."""
    match = WAKE_RE.search(text)
    if not match:
        return False, ""
    return True, text[match.end():].strip()


class WakeGate:
    """Ignores transcripts until the wake word shows up, then collects one command."""

    def __init__(self, timeout):
        self.timeout = timeout
        self.awake_until = None
        self.wake_seen_in_current_line = False

    @property
    def awake(self):
        return self.awake_until is not None

    def sleep(self):
        self.awake_until = None
        self.wake_seen_in_current_line = False

    def on_partial(self, text):
        """Wake as early as possible, while the user is still talking."""
        if self.awake:
            return
        heard, _ = find_wake(normalize(text))
        if heard:
            self.awake_until = time.monotonic() + self.timeout
            self.wake_seen_in_current_line = True
            print("\r[wake] WALL-E here, listening...")

    def on_final(self, text):
        """Pull the command out of a finished utterance, or report none yet."""
        text = normalize(text)
        if self.wake_seen_in_current_line:
            # Wake word is inside this line; the command is whatever follows it.
            self.wake_seen_in_current_line = False
            _, command = find_wake(text)
        elif self.awake:
            command = text
        else:
            # Asleep and the partials never matched (short utterance, no partial).
            heard, command = find_wake(text)
            if not heard:
                return None
            self.awake_until = time.monotonic() + self.timeout
            print("\r[wake] WALL-E here, listening...")

        if not command:
            self.awake_until = time.monotonic() + self.timeout  # wait for the command
            return None
        self.sleep()
        return command

    def check_timeout(self):
        if self.awake and time.monotonic() > self.awake_until:
            self.sleep()
            print("[sleep] timed out, waiting for wake word again")


def handle_command(command, latency=None):
    """Stand-in for the behavior tree hand-off."""
    stamp = f" ({latency:.2f}s)" if latency is not None else ""
    print(f"[command]{stamp} {command}")


def make_transcriber(size, use_keyterms):
    model_path, model_arch = get_model_for_language("en", SIZES[size])
    transcriber = Transcriber(model_path, model_arch)
    if use_keyterms and "streaming" in size:
        transcriber.set_keyterms(KEYTERMS)
    return transcriber


def run_wav(transcriber, path, gate):
    samples, sr = load_wav_file(path)
    transcript = transcriber.transcribe_without_streaming(samples, sample_rate=sr)
    for line in transcript.lines:
        print(f"  heard: {line.text.strip()}")
        command = gate.on_final(line.text)
        if command:
            handle_command(command)


def run_mic(transcriber, gate):
    from moonshine_voice.mic_transcriber import MicTranscriber

    def show_partial(text):
        gate.on_partial(text)
        if gate.awake:
            print(f"\r  ... {text}", end="", flush=True)

    def show_final(line):
        command = gate.on_final(line.text)
        if command:
            handle_command(command, line.last_transcription_latency_ms / 1000)

    mic = MicTranscriber().use_transcriber(transcriber).on_text(show_partial).on_line(show_final)
    mic.load()
    mic.start()
    print('Asleep. Say "WALL-E" to wake it, then give a command (Ctrl+C to stop)')
    try:
        while True:
            time.sleep(0.1)
            gate.check_timeout()
    finally:
        mic.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wav", help="transcribe this file instead of the mic")
    p.add_argument("--size", choices=list(SIZES), default="tiny-streaming")
    p.add_argument("--no-keyterms", action="store_true", help="turn off Wall-E word biasing")
    p.add_argument("--timeout", type=float, default=5.0, help="seconds to stay awake")
    args = p.parse_args()

    if args.size in ("tiny", "base") and not args.no_keyterms:
        print("Note: keyterms only work with streaming models, running without them.")

    transcriber = make_transcriber(args.size, not args.no_keyterms)
    gate = WakeGate(args.timeout)
    if args.wav:
        run_wav(transcriber, args.wav, gate)
    else:
        try:
            run_mic(transcriber, gate)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
