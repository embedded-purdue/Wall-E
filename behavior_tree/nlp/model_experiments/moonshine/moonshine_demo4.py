"""
STT benchmark for Wall-E: runs every model we have against one recorded test set
and reports WER + latency, broken down by category.

Model loading is reused from the other demos, not duplicated:
  demo1 -> Sherpa-ONNX recognizers (make_recognizer / transcribe)
  demo2 -> Moonshine Voice transcribers (make_transcriber, keyterms)
Adding a future model = one entry in MODELS below, pointing at whichever
demo script knows how to load it.

The test set has four categories, so we can see which model wins where:
  short commands (1-3s, "find the ball")      x  quiet / noisy
  long commands  (5-10s, multi-step)          x  quiet / noisy

to use:
  python moonshine_demo4.py record --noise quiet       # record the prompts, quiet room
  python moonshine_demo4.py record --noise noisy       # same prompts, noise playing
  python moonshine_demo4.py run                        # benchmark every model
  python moonshine_demo4.py run --models demo1-tiny demo2-small-streaming
  python moonshine_demo4.py run --per-utterance        # show every bad transcript
  python moonshine_demo4.py run --csv results.csv      # for plots/spreadsheets
  python moonshine_demo4.py list                       # models + test set status

Run from this folder (demo1 looks for its model dirs relative to cwd).
"""
import argparse
import csv
import importlib
import json
import os
import re
import statistics
import time

import numpy as np

SR = 16000
TEST_DIR = "test_set"
MANIFEST = os.path.join(TEST_DIR, "manifest.json")

LENGTHS = ["short", "long"]
NOISES = ["quiet", "noisy"]
CATEGORIES = [(length, noise) for length in LENGTHS for noise in NOISES]

# What to read while recording the test set. Keep these stable once recorded,
# otherwise old recordings no longer match the reference text.
PROMPTS = {
    "short": [
        "Wall-E, find the ball",
        "Wall-E, stop",
        "Wall-E, turn left",
        "Wall-E, go forward two meters",
        "Wall-E, pick up the can",
        "Wall-E, what do you see",
        "Wall-E, come back here",
        "Wall-E, drop it in the can crusher",
    ],
    "long": [
        "Wall-E, go find the red ball in the corner, pick it up, and bring it back to me",
        "Wall-E, drive forward until you reach the wall, then turn around and come back to where you started",
        "Wall-E, I need you to look around the room and tell me how many cans you can find on the floor",
        "Wall-E, pick up every can you find and put them all in the can crusher, then let me know when you are done",
        "Wall-E, wait here for a few seconds, then follow me into the next room and stop when I stop",
        "Wall-E, if you see the ball move to your left, follow it, but if it goes behind the table just stay put",
        "Wall-E, scan the area in front of you, drive around anything in the way, and park next to the charging station",
        "Wall-E, could you go check whether the door is open, and if it is, come back and tell me right away",
    ],
}

# backend: which demo script loads it. size: that script's own size name.
MODELS = {
    "demo1-tiny": {"backend": "sherpa", "size": "tiny"},
    "demo1-base": {"backend": "sherpa", "size": "base"},
    "demo2-tiny": {"backend": "moonshine-voice", "size": "tiny"},
    "demo2-base": {"backend": "moonshine-voice", "size": "base"},
    "demo2-tiny-streaming": {"backend": "moonshine-voice", "size": "tiny-streaming"},
    "demo2-base-streaming": {"backend": "moonshine-voice", "size": "base-streaming"},
    "demo2-small-streaming": {"backend": "moonshine-voice", "size": "small-streaming"},
    "demo2-medium-streaming": {"backend": "moonshine-voice", "size": "medium-streaming"},
}


# ---------------------------------------------------------------- model loading

def load_sherpa(size, threads, _keyterms):
    """Reuse demo1's recognizer. Imported lazily so a missing dep only kills
    the backends that need it."""
    demo1 = importlib.import_module("moonshine_demo1")
    recognizer = demo1.make_recognizer(threads, size)

    def transcribe(samples, sr):
        assert sr == demo1.SR, f"demo1 expects {demo1.SR} Hz, got {sr}"
        text, _ = demo1.transcribe(recognizer, samples)  # ignore its timing, we time it here
        return text

    return transcribe


def load_moonshine_voice(size, _threads, keyterms):
    """Reuse demo2's transcriber, including its keyterm handling."""
    demo2 = importlib.import_module("moonshine_demo2")
    transcriber = demo2.make_transcriber(size, keyterms)

    def transcribe(samples, sr):
        transcript = transcriber.transcribe_without_streaming(samples, sample_rate=sr)
        return " ".join(line.text.strip() for line in transcript.lines)

    return transcribe


BACKENDS = {"sherpa": load_sherpa, "moonshine-voice": load_moonshine_voice}


# ------------------------------------------------------------------------- WER

def normalize(text):
    """Lowercase, punctuation to spaces, collapse whitespace. Same idea as demo3,
    so "WALL-E," and "wall e" compare equal."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def edit_counts(ref_words, hyp_words):
    """Levenshtein over words, returning (substitutions, deletions, insertions)."""
    n, m = len(ref_words), len(hyp_words)
    # dp[i][j] = (cost, sub, del, ins) for ref[:i] vs hyp[:j]
    dp = [[(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = (i, 0, i, 0)
    for j in range(1, m + 1):
        dp[0][j] = (j, 0, 0, j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
                continue
            cost_s, s, d, ins = dp[i - 1][j - 1]
            cost_d, s2, d2, ins2 = dp[i - 1][j]
            cost_i, s3, d3, ins3 = dp[i][j - 1]
            best = min(cost_s, cost_d, cost_i)
            if best == cost_s:
                dp[i][j] = (best + 1, s + 1, d, ins)
            elif best == cost_d:
                dp[i][j] = (best + 1, s2, d2 + 1, ins2)
            else:
                dp[i][j] = (best + 1, s3, d3, ins3 + 1)
    _, subs, dels, inss = dp[n][m]
    return subs, dels, inss


def score(reference, hypothesis):
    """Per-utterance error counts. WER is aggregated corpus-wide later, not averaged."""
    ref_words = normalize(reference).split()
    hyp_words = normalize(hypothesis).split()
    subs, dels, inss = edit_counts(ref_words, hyp_words)
    return {"ref_words": len(ref_words), "errors": subs + dels + inss,
            "subs": subs, "dels": dels, "inss": inss}


# ------------------------------------------------------------------- test set io

def load_manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST) as f:
        return json.load(f)


def save_manifest(entries):
    os.makedirs(TEST_DIR, exist_ok=True)
    entries = sorted(entries, key=lambda e: (e["length"], e["noise"], e["index"]))
    with open(MANIFEST, "w") as f:
        json.dump(entries, f, indent=2)


def load_wav(path):
    """Mono float32 at SR, so every model sees identical audio."""
    import soundfile as sf
    samples, sr = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"{path} is {sr} Hz; the test set must be {SR} Hz mono")
    return samples


def record(noise, lengths, max_seconds):
    """Walk the prompts and record each one. Enter to start, Enter again to stop."""
    import sounddevice as sd
    import soundfile as sf

    os.makedirs(TEST_DIR, exist_ok=True)
    entries = {(e["length"], e["noise"], e["index"]): e for e in load_manifest()}
    print(f"Recording the '{noise}' condition. Ctrl+C to stop early; reruns overwrite.\n")

    for length in lengths:
        for index, prompt in enumerate(PROMPTS[length]):
            name = f"{length}_{noise}_{index:02d}.wav"
            path = os.path.join(TEST_DIR, name)
            done = " (already recorded, re-recording)" if os.path.exists(path) else ""
            print(f"[{length}/{noise} {index + 1}/{len(PROMPTS[length])}]{done}")
            print(f'  say: "{prompt}"')
            input("  Enter to start recording...")
            buffer = sd.rec(int(max_seconds * SR), samplerate=SR, channels=1, dtype="float32")
            input("  recording... Enter to stop. ")
            sd.stop()
            samples = trim_silence(buffer)
            sf.write(path, samples, SR)
            print(f"  saved {name} ({len(samples) / SR:.1f}s)\n")
            entries[(length, noise, index)] = {
                "file": name, "text": prompt, "length": length,
                "noise": noise, "index": index,
            }
            save_manifest(list(entries.values()))

    print(f"Done. Manifest: {MANIFEST}")


def trim_silence(buffer):
    """sd.rec pre-allocates the whole buffer, so the unused tail is exact zeros.
    Cut back to the last sample the mic actually wrote."""
    samples = buffer.flatten()
    nonzero = np.nonzero(samples)[0]
    return samples[: nonzero[-1] + 1] if len(nonzero) else samples[:0]


# ------------------------------------------------------------------ benchmarking

def benchmark(model_name, entries, threads, keyterms, per_utterance):
    spec = MODELS[model_name]
    print(f"\n=== {model_name} ({spec['backend']} / {spec['size']}) ===")
    t0 = time.perf_counter()
    try:
        transcribe = BACKENDS[spec["backend"]](spec["size"], threads, keyterms)
    except Exception as exc:  # missing dep or missing model dir: skip, keep going
        print(f"  skipped, failed to load: {exc}")
        return None
    print(f"  loaded in {time.perf_counter() - t0:.1f}s")

    # Warm up on the first clip; the first decode pays one-off init costs.
    warmup = load_wav(os.path.join(TEST_DIR, entries[0]["file"]))
    transcribe(warmup, SR)

    rows = []
    for entry in entries:
        samples = load_wav(os.path.join(TEST_DIR, entry["file"]))
        t0 = time.perf_counter()
        hypothesis = transcribe(samples, SR)
        latency = time.perf_counter() - t0
        row = {"model": model_name, "file": entry["file"], "length": entry["length"],
               "noise": entry["noise"], "reference": entry["text"], "hypothesis": hypothesis,
               "audio_seconds": len(samples) / SR, "latency": latency}
        row.update(score(entry["text"], hypothesis))
        rows.append(row)
        if per_utterance and row["errors"]:
            print(f"  {entry['file']} ({row['errors']}/{row['ref_words']} wrong, {latency:.2f}s)")
            print(f"    ref: {normalize(entry['text'])}")
            print(f"    hyp: {normalize(hypothesis)}")
    return rows


def summarize(rows):
    """Corpus WER (total errors / total reference words) plus latency stats."""
    if not rows:
        return None
    ref_words = sum(r["ref_words"] for r in rows)
    latencies = [r["latency"] for r in rows]
    audio = sum(r["audio_seconds"] for r in rows)
    return {
        "utterances": len(rows),
        "wer": sum(r["errors"] for r in rows) / ref_words if ref_words else float("nan"),
        "subs": sum(r["subs"] for r in rows),
        "dels": sum(r["dels"] for r in rows),
        "inss": sum(r["inss"] for r in rows),
        "median_latency": statistics.median(latencies),
        "max_latency": max(latencies),
        "rtf": sum(latencies) / audio if audio else float("nan"),
    }


def print_report(all_rows):
    header = f"{'model':<24} {'category':<14} {'n':>3} {'WER':>7} {'med lat':>8} {'max lat':>8} {'RTF':>6}"
    print("\n" + "=" * len(header))
    print("RESULTS")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for model_name, rows in all_rows.items():
        for length, noise in CATEGORIES:
            subset = [r for r in rows if r["length"] == length and r["noise"] == noise]
            stats = summarize(subset)
            if not stats:
                continue
            print(f"{model_name:<24} {length + '/' + noise:<14} {stats['utterances']:>3} "
                  f"{stats['wer'] * 100:>6.1f}% {stats['median_latency']:>7.2f}s "
                  f"{stats['max_latency']:>7.2f}s {stats['rtf']:>6.2f}")
        overall = summarize(rows)
        print(f"{model_name:<24} {'OVERALL':<14} {overall['utterances']:>3} "
              f"{overall['wer'] * 100:>6.1f}% {overall['median_latency']:>7.2f}s "
              f"{overall['max_latency']:>7.2f}s {overall['rtf']:>6.2f}")
        print("-" * len(header))

    print("\nBest WER per category (ties -> faster median latency):")
    for length, noise in CATEGORIES:
        ranked = []
        for model_name, rows in all_rows.items():
            stats = summarize([r for r in rows if r["length"] == length and r["noise"] == noise])
            if stats:
                ranked.append((stats["wer"], stats["median_latency"], model_name))
        if not ranked:
            print(f"  {length + '/' + noise:<14} no recordings")
            continue
        wer, latency, model_name = min(ranked)
        print(f"  {length + '/' + noise:<14} {model_name:<24} {wer * 100:.1f}% WER, {latency:.2f}s median")
    print("\nWER = (sub + del + ins) / reference words, pooled per category.")
    print("RTF = total decode time / total audio; < 1.0 is faster than real time.")


def write_csv(path, all_rows):
    fields = ["model", "file", "length", "noise", "audio_seconds", "latency",
              "ref_words", "errors", "subs", "dels", "inss", "reference", "hypothesis"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for rows in all_rows.values():
            writer.writerows(rows)
    print(f"\nPer-utterance rows written to {path}")


# -------------------------------------------------------------------- commands

def cmd_run(args):
    entries = load_manifest()
    if not entries:
        raise SystemExit(f"No test set yet. Record one first:\n"
                         f"  python moonshine_demo4.py record --noise quiet\n"
                         f"  python moonshine_demo4.py record --noise noisy")
    if args.length:
        entries = [e for e in entries if e["length"] in args.length]
    if args.noise:
        entries = [e for e in entries if e["noise"] in args.noise]
    missing = [e["file"] for e in entries if not os.path.exists(os.path.join(TEST_DIR, e["file"]))]
    if missing:
        raise SystemExit(f"Manifest references missing files: {', '.join(missing)}")
    if not entries:
        raise SystemExit("No recordings match that filter.")

    print(f"{len(entries)} recordings, {len(args.models)} model(s)")
    all_rows = {}
    for model_name in args.models:
        rows = benchmark(model_name, entries, args.threads, not args.no_keyterms, args.per_utterance)
        if rows:
            all_rows[model_name] = rows
    if not all_rows:
        raise SystemExit("\nEvery model failed to load.")
    print_report(all_rows)
    if args.csv:
        write_csv(args.csv, all_rows)


def cmd_list(_args):
    print("Models:")
    for name, spec in MODELS.items():
        print(f"  {name:<24} {spec['backend']} / {spec['size']}")
    print("\nTest set:")
    entries = load_manifest()
    if not entries:
        print(f"  none yet ({MANIFEST} missing)")
    for length, noise in CATEGORIES:
        subset = [e for e in entries if e["length"] == length and e["noise"] == noise]
        expected = len(PROMPTS[length])
        seconds = sum(len(load_wav(os.path.join(TEST_DIR, e["file"]))) / SR for e in subset)
        print(f"  {length + '/' + noise:<14} {len(subset)}/{expected} recorded, {seconds:.1f}s audio")


def cmd_record(args):
    record(args.noise, args.length or LENGTHS, args.max_seconds)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="benchmark models on the recorded test set")
    p_run.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    p_run.add_argument("--length", nargs="+", choices=LENGTHS, help="only these lengths")
    p_run.add_argument("--noise", nargs="+", choices=NOISES, help="only these conditions")
    p_run.add_argument("--threads", type=int, default=2, help="Sherpa-ONNX threads (demo1)")
    p_run.add_argument("--no-keyterms", action="store_true", help="turn off demo2 Wall-E biasing")
    p_run.add_argument("--per-utterance", action="store_true", help="print every imperfect transcript")
    p_run.add_argument("--csv", help="write per-utterance rows here")
    p_run.set_defaults(func=cmd_run)

    p_rec = sub.add_parser("record", help="record the prompts for one condition")
    p_rec.add_argument("--noise", choices=NOISES, required=True)
    p_rec.add_argument("--length", nargs="+", choices=LENGTHS, help="only these lengths")
    p_rec.add_argument("--max-seconds", type=float, default=15.0, help="recording cap per prompt")
    p_rec.set_defaults(func=cmd_record)

    p_list = sub.add_parser("list", help="show models and test set status")
    p_list.set_defaults(func=cmd_list)

    args = p.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
