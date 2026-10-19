"""
Moonshine speech-to-text demo for Wall-E 
Uses Sherpa-ONNX
Uses a VAD
prints "time of audio clip -> latency"

to use:
  python moonshine_demo.py                  # normal live mic
  python moonshine_demo.py --wav clip.wav   # transcribe a file
  python moonshine_demo.py --size base      # use Moonshine base model instead of tiny model


"""
import argparse
import time

import numpy as np
import sherpa_onnx

SR = 16000
VAD_MODEL = "silero_vad.onnx"


def make_recognizer(threads, size):
    MODEL_DIR = f"sherpa-onnx-moonshine-{size}-en-int8"
    return sherpa_onnx.OfflineRecognizer.from_moonshine(
        preprocessor=f"{MODEL_DIR}/preprocess.onnx",
        encoder=f"{MODEL_DIR}/encode.int8.onnx",
        uncached_decoder=f"{MODEL_DIR}/uncached_decode.int8.onnx",
        cached_decoder=f"{MODEL_DIR}/cached_decode.int8.onnx",
        tokens=f"{MODEL_DIR}/tokens.txt",
        num_threads=threads,
    )


def make_vad():
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = VAD_MODEL
    config.silero_vad.min_silence_duration = 0.5  # how long a pause = "done talking"
    config.silero_vad.min_speech_duration = 0.25
    config.sample_rate = SR
    return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)


def transcribe(recognizer, samples):
    t0 = time.perf_counter()
    stream = recognizer.create_stream()
    stream.accept_waveform(SR, samples)
    recognizer.decode_stream(stream)
    dt = time.perf_counter() - t0
    return stream.result.text.strip(), dt


def run_wav(recognizer, path):
    import soundfile as sf
    samples, sr = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    assert sr == SR, f"expected {SR} Hz, got {sr}"
    text, dt = transcribe(recognizer, samples)
    audio_len = len(samples) / SR
    print(f"[{audio_len:.1f}s audio -> {dt:.2f}s] {text}")


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
    p.add_argument("--wav", help="transcribe this file instead of the mic")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--size", choices=["tiny", "base"], default="tiny")
    args = p.parse_args()

    recognizer = make_recognizer(args.threads, args.size)
    if args.wav:
        run_wav(recognizer, args.wav)
    else:
        try:
            run_mic(recognizer)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()