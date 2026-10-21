"""
Speech-to-text with OpenAI Whisper (small model).

Install:
    pip install -U openai-whisper
    # ffmpeg is required for reading audio files:
    #   macOS:   brew install ffmpeg
    #   Ubuntu:  sudo apt install ffmpeg
    #   Windows: winget install ffmpeg   (or choco install ffmpeg)
    # Optional, for --mic recording:
    pip install sounddevice numpy

Usage:
    python transcribe.py audio.mp3
    python transcribe.py audio.wav --language en --output transcript.txt
    python transcribe.py --mic --seconds 10
"""

import argparse
import sys

import whisper

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono audio


def record_from_mic(seconds: float):
    print("RECORDING FROM MIC")
    """Record audio from the default microphone and return a float32 numpy array."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        sys.exit("Mic recording needs extra packages: pip install sounddevice numpy")

    print(f"Recording for {seconds} seconds... speak now.")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32"
    )
    sd.wait()
    print("Recording finished.")
    return np.squeeze(audio)


def format_timestamp(t: float) -> str:
    minutes, seconds = divmod(t, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe speech with Whisper (small)."
    )
    parser.add_argument(
        "audio", nargs="?", help="Path to an audio/video file (mp3, wav, m4a, mp4, ...)"
    )
    parser.add_argument(
        "--mic",
        action="store_true",
        help="Record from the microphone instead of a file",
    )
    parser.add_argument(
        "--seconds", type=float, default=5, help="Mic recording length (default: 5)"
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code, e.g. 'en'. Auto-detected if omitted",
    )
    parser.add_argument(
        "--translate", action="store_true", help="Translate speech to English"
    )
    parser.add_argument(
        "--timestamps", action="store_true", help="Print segment timestamps"
    )
    parser.add_argument("--output", help="Save the transcript to this text file")
    args = parser.parse_args()

    if not args.mic and not args.audio:
        parser.error("Give an audio file path or use --mic")

    print("Loading Whisper 'small' model (downloads ~460 MB on first run)...")
    model = whisper.load_model("small")  # uses GPU automatically if CUDA is available

    source = record_from_mic(args.seconds) if args.mic else args.audio

    result = model.transcribe(
        source,
        language=args.language,
        task="translate" if args.translate else "transcribe",
        fp16=model.device.type
        == "cuda",  # fp16 only works on GPU; avoids a CPU warning
    )

    print(f"\nDetected language: {result.get('language')}\n")

    if args.timestamps:
        lines = [
            f"[{format_timestamp(seg['start'])} -> {format_timestamp(seg['end'])}] {seg['text'].strip()}"
            for seg in result["segments"]
        ]
        text = "\n".join(lines)
    else:
        text = result["text"].strip()

    print(text)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\nSaved transcript to {args.output}")


if __name__ == "__main__":
    main()
