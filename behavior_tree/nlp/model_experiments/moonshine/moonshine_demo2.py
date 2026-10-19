"""
Moonshine speech-to-text demo for Wall-E (official Moonshine Voice library).
Uses keyterms, so "WALL-E" doesn't become "wally"
does not use Sherpa-ONNX

Models download automatically on first run (cached afterward).

to use:
  python moonshine_demo2.py                         # live mic, tiny-streaming
  python moonshine_demo2.py --size small-streaming  # bigger, more accurate
  python moonshine_demo2.py --wav path.wav          # transcribe .wav file
  python moonshine_demo2.py --no-keyterms           # turn off Wall-E word biasing

takeaways:
- medium streaming is phenomenal
"""
import argparse
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
KEYTERMS = ["Wall-E", "can crusher"]


def make_transcriber(size, use_keyterms):
    model_path, model_arch = get_model_for_language("en", SIZES[size])
    transcriber = Transcriber(model_path, model_arch)
    if use_keyterms and "streaming" in size:
        transcriber.set_keyterms(KEYTERMS)
    return transcriber


def run_wav(transcriber, path):
    samples, sr = load_wav_file(path)
    t0 = time.perf_counter()
    transcript = transcriber.transcribe_without_streaming(samples, sample_rate=sr)
    dt = time.perf_counter() - t0
    text = " ".join(line.text.strip() for line in transcript.lines)
    print(f"[{len(samples) / sr:.1f}s audio -> {dt:.2f}s] {text}")


def run_mic(transcriber):
    from moonshine_voice.mic_transcriber import MicTranscriber

    def show_partial(text):
        print(f"\r  ... {text}", end="", flush=True)

    def show_final(line):
        print(f"\r[{line.duration:.1f}s audio -> {line.last_transcription_latency_ms / 1000:.2f}s] {line.text}")

    mic = MicTranscriber().use_transcriber(transcriber).on_text(show_partial).on_line(show_final)
    mic.load()
    mic.start()
    print("Listening... speak a command (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(0.1)
    finally:
        mic.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wav", help="transcribe this file instead of the mic")
    p.add_argument("--size", choices=list(SIZES), default="tiny-streaming")
    p.add_argument("--no-keyterms", action="store_true", help="turn off Wall-E word biasing")
    args = p.parse_args()

    if args.size in ("tiny", "base") and not args.no_keyterms:
        print("Note: keyterms only work with streaming models, running without them.")

    transcriber = make_transcriber(args.size, not args.no_keyterms)
    if args.wav:
        run_wav(transcriber, args.wav)
    else:
        try:
            run_mic(transcriber)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()