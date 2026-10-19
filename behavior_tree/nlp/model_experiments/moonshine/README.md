# Moonshine STT Demos

Two speech-to-text demos using Moonshine:

| Script | Runs through | Highlights |
|---|---|---|
| `moonshine_demo1.py` | Sherpa-ONNX | Original tiny/base models, Silero VAD |
| `moonshine_demo2.py` | Moonshine Voice (official library) | Streaming (live text), keyterms so "Wall-E" isn't "wally" |

## Setup

**1. Venv** (from `behavior_tree/nlp`):
```bash
python3 -m venv venv
source venv/bin/activate
```

**2. Dependencies** (from this folder):
```bash
pip install -r requirements.txt
```
Linux/Jetson only: `sudo apt install libportaudio2`

**3. Models for demo1** (download into this folder, they're gitignored):
```bash
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-moonshine-tiny-en-int8.tar.bz2
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-moonshine-base-en-int8.tar.bz2
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
tar xjf sherpa-onnx-moonshine-tiny-en-int8.tar.bz2
tar xjf sherpa-onnx-moonshine-base-en-int8.tar.bz2
rm *.tar.bz2
```

demo2 downloads its models automatically on first run (first start is slow, then cached).

## Usage

Run from this folder.

**demo1:**
```bash
python moonshine_demo1.py                # mic, tiny
python moonshine_demo1.py --size base    # mic, base
python moonshine_demo1.py --wav file.wav # 16 kHz mono .wav
```

**demo2:**
```bash
python moonshine_demo2.py                          # mic, tiny-streaming
python moonshine_demo2.py --size medium-streaming  # more accurate
python moonshine_demo2.py --no-keyterms            # turn off Wall-E biasing
python moonshine_demo2.py --wav file.wav
```
Sizes: `tiny`, `base`, `tiny-streaming`, `base-streaming`, `small-streaming`, `medium-streaming`. Keyterms only work with streaming sizes.

Test clips: `sherpa-onnx-moonshine-tiny-en-int8/test_wavs/`

## Reading the output

```
[6.6s audio -> 0.07s] transcript
```
Length of the audio -> latency

## Notes

- **Mac:** allow Terminal mic access in System Settings > Privacy & Security > Microphone.
- **demo1 response speed:** `min_silence_duration` in `make_vad()` (default 0.5s) is how long a pause counts as "done talking". Lower = faster, but may cut you off.
- **demo1 models** are the original Moonshine tiny/base, converted to ONNX int8 by the Sherpa-ONNX team. **demo2 models** are newer, already quantized, from [moonshine-ai/moonshine](https://github.com/moonshine-ai/moonshine).