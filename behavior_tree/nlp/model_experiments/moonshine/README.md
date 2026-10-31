# Moonshine STT Demos

Speech-to-text demos using Moonshine, plus a benchmark harness:

| Script | Runs through | Highlights |
|---|---|---|
| `moonshine_demo1.py` | Sherpa-ONNX | Original tiny/base models, Silero VAD |
| `moonshine_demo2.py` | Moonshine Voice (official library) | Streaming (live text), keyterms so "Wall-E" isn't "wally" |
| `moonshine_demo3.py` | Moonshine Voice (official library) | demo2 + wake word: ignores everything until you say "WALL-E" |
| `moonshine_demo4.py` | reuses demo1 + demo2 loaders | Benchmark: WER + latency for every model on one recorded test set |

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

demo2 and demo3 download their models automatically on first run (first start is slow, then cached).

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

**demo3** (same flags as demo2, plus `--timeout`):
```bash
python moonshine_demo3.py              # mic, asleep until it hears "WALL-E"
python moonshine_demo3.py --timeout 10 # stay awake 10s instead of 5s
python moonshine_demo3.py --wav file.wav
```
The mic always runs, but transcripts are dropped until the wake word lands. Then whatever
follows it is the command, either in the same breath ("WALL-E, go forward") or the next
utterance. After one command, or `--timeout` seconds of silence, it goes back to sleep.

**demo4** (benchmark, three subcommands):
```bash
python moonshine_demo4.py list                  # models + how much of the test set exists
python moonshine_demo4.py record --noise quiet  # record the prompts in a quiet room
python moonshine_demo4.py record --noise noisy  # same prompts, with noise playing
python moonshine_demo4.py run                   # every model, full report
python moonshine_demo4.py run --models demo1-tiny demo2-small-streaming
python moonshine_demo4.py run --length short --noise noisy   # one category
python moonshine_demo4.py run --per-utterance    # print every imperfect transcript
python moonshine_demo4.py run --csv results.csv  # per-utterance rows for plots
```

Test clips: `sherpa-onnx-moonshine-tiny-en-int8/test_wavs/`

## demo4: benchmarking

### The test set

Four categories, so we can see which model wins where:

| | quiet | noisy |
|---|---|---|
| **short** (1-3s, "find the ball") | 8 clips | 8 clips |
| **long** (5-10s, multi-step) | 8 clips | 8 clips |

`record` reads you each prompt from `PROMPTS` in the script, you press Enter to start
and Enter to stop, and it writes `test_set/{length}_{noise}_{NN}.wav` plus
`test_set/manifest.json` (the wav, the reference text, and its category). Record the
noisy condition the same way with background noise playing. Re-running `record`
overwrites that condition's clips.

Keep `PROMPTS` stable once recorded — editing the text invalidates existing clips,
since the manifest stores the reference transcript per file. Commit `test_set/` so
everyone benchmarks against identical audio.

### Adding a model

One entry in `MODELS`; the loaders come from the demo scripts, so there is no
model-loading code in demo4:

```python
MODELS = {
    "demo1-tiny":  {"backend": "sherpa",          "size": "tiny"},   # demo1.make_recognizer
    "demo2-base":  {"backend": "moonshine-voice", "size": "base"},   # demo2.make_transcriber
}
```

A genuinely new runtime needs a `load_*` function returning `transcribe(samples, sr) -> text`,
registered in `BACKENDS`. Models that fail to load (missing dep or model dir) are
reported and skipped, so a partial setup still benchmarks the rest.

### Reading the report

```
model                    category         n     WER  med lat  max lat    RTF
demo1-tiny               short/quiet      8    0.0%    0.06s    0.08s   0.01
demo1-tiny               long/noisy       8    4.2%    0.20s    0.31s   0.01
demo1-tiny               OVERALL         16    3.0%    0.13s    0.31s   0.01
```

- **WER** = (substitutions + deletions + insertions) / reference words, pooled across
  the category rather than averaged per clip, so long clips carry proportional weight.
  Compared after lowercasing and stripping punctuation, so "WALL-E," matches "wall e".
- **med/max lat** = decode wall time per clip. The first clip is a discarded warmup, so
  one-off init isn't counted.
- **RTF** = decode time / audio duration; under 1.0 is faster than real time.
- A **best-per-category** summary follows the table, ties broken by median latency.

Latency here is decode time only — it excludes VAD endpointing (demo1) and streaming
partial behavior (demo2), which is what actually governs how fast Wall-E feels. Use
demo2/demo3 for that.

## Reading the output

```
[6.6s audio -> 0.07s] transcript
```
Length of the audio -> latency

## Notes

- **Mac:** allow Terminal mic access in System Settings > Privacy & Security > Microphone.
- **demo1 response speed:** `min_silence_duration` in `make_vad()` (default 0.5s) is how long a pause counts as "done talking". Lower = faster, but may cut you off.
- **demo3 wake word:** STT spells it a lot of ways, so `WAKE_VARIANTS` matches "wall e", "walle", "wally", etc. Add spellings there if yours gets missed. Detection runs on partials, so it wakes mid-sentence rather than after the pause.
- **demo1 models** are the original Moonshine tiny/base, converted to ONNX int8 by the Sherpa-ONNX team. **demo2 models** are newer, already quantized, from [moonshine-ai/moonshine](https://github.com/moonshine-ai/moonshine).