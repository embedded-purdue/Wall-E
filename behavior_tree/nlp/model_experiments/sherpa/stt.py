"""
Speech-to-text for Wall-E through Sherpa-ONNX: one interface, swap models by name.
Mic/VAD loop is from Adwaiy's moonshine_demo1.py.

to use:
  python stt.py --list                          # show models
  python stt.py --model whisper-base            # live mic
  python stt.py --model moonshine-tiny --wav clip.wav

in code:
  from stt import load, transcribe
  rec = load("whisper-small")
  text, seconds = transcribe(rec, samples)      # 16 kHz mono float32

Add a model: download its sherpa-onnx folder into models/ and add a MODELS line.
"""
import argparse
import glob
import os
import time

import numpy as np
import sherpa_onnx

SR = 16000
HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "models")
VAD_MODEL = os.path.join(MODELS_DIR, "silero_vad.onnx")

# name: (family, folder in models/, params in millions)
MODELS = {
    "moonshine-tiny": ("moonshine", "sherpa-onnx-moonshine-tiny-en-int8", 27),
    "moonshine-base": ("moonshine", "sherpa-onnx-moonshine-base-en-int8", 61),
    "whisper-tiny": ("whisper", "sherpa-onnx-whisper-tiny.en", 39),
    "whisper-base": ("whisper", "sherpa-onnx-whisper-base.en", 74),
    "distil-whisper-small": ("whisper", "sherpa-onnx-whisper-distil-small.en", 166),
    "whisper-small": ("whisper", "sherpa-onnx-whisper-small.en", 244),
}


def model_files(name):
    """The onnx/tokens files load() uses, so callers can measure on-disk size."""
    family, folder, _ = MODELS[name]
    d = os.path.join(MODELS_DIR, folder)
    if family == "moonshine":
        names = ["preprocess.onnx", "encode.int8.onnx", "uncached_decode.int8.onnx",
                 "cached_decode.int8.onnx", "tokens.txt"]
        return {n.split(".")[0]: os.path.join(d, n) for n in names}
    # whisper folders prefix files with the model name, e.g. tiny.en-encoder.int8.onnx
    one = lambda pat: glob.glob(os.path.join(d, pat))[0]
    return {"encoder": one("*-encoder.int8.onnx"), "decoder": one("*-decoder.int8.onnx"),
            "tokens": one("*-tokens.txt")}


def load(name, threads=2):
    family = MODELS[name][0]
    f = model_files(name)
    if family == "moonshine":
        return sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=f["preprocess"], encoder=f["encode"],
            uncached_decoder=f["uncached_decode"], cached_decoder=f["cached_decode"],
            tokens=f["tokens"], num_threads=threads)
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=f["encoder"], decoder=f["decoder"], tokens=f["tokens"],
        language="en", task="transcribe", num_threads=threads)


def transcribe(recognizer, samples):
    t0 = time.perf_counter()
    stream = recognizer.create_stream()
    stream.accept_waveform(SR, samples)
    recognizer.decode_stream(stream)
    return stream.result.text.strip(), time.perf_counter() - t0


def read_audio(path):
    import soundfile as sf
    samples, sr = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    assert sr == SR, f"{path}: expected {SR} Hz, got {sr}"
    return samples


def make_vad():
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = VAD_MODEL
    config.silero_vad.min_silence_duration = 0.5  # how long a pause = "done talking"
    config.silero_vad.min_speech_duration = 0.25
    config.sample_rate = SR
    return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)


def run_mic(recognizer):
    import sounddevice as sd
    vad = make_vad()
    window = vad.config.silero_vad.window_size  # VAD wants fixed-size chunks
    print("Listening... speak a command (Ctrl+C to stop)")
    with sd.InputStream(channels=1, samplerate=SR, dtype="float32") as mic:
        buf = np.array([], dtype=np.float32)
        while True:
            chunk, _ = mic.read(int(0.1 * SR))  # 100 ms at a time
            buf = np.concatenate([buf, chunk.flatten()])
            while len(buf) >= window:
                vad.accept_waveform(buf[:window])
                buf = buf[window:]
            while not vad.empty():  # VAD found a finished utterance
                samples = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                text, dt = transcribe(recognizer, samples)
                print(f"[{len(samples) / SR:.1f}s audio -> {dt:.2f}s] {text}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=MODELS, default="moonshine-tiny")
    p.add_argument("--wav", help="transcribe this file instead of the mic")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    if args.list:
        for name, (family, folder, params) in MODELS.items():
            have = "ok" if os.path.isdir(os.path.join(MODELS_DIR, folder)) else "missing"
            print(f"{name:22} {params:4}M  {have}")
        return
    recognizer = load(args.model, args.threads)
    if args.wav:
        samples = read_audio(args.wav)
        text, dt = transcribe(recognizer, samples)
        print(f"[{len(samples) / SR:.1f}s audio -> {dt:.2f}s] {text}")
    else:
        try:
            run_mic(recognizer)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
