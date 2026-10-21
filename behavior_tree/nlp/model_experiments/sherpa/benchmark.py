"""
Accuracy (WER) and speed of every stt.py model on the same clips.

to use:
  python benchmark.py                                  # all models, 200 LibriSpeech test-clean clips
  python benchmark.py --models whisper-tiny moonshine-tiny -n 50
  python benchmark.py --data my_set.tsv                # tsv lines: path<TAB>transcript (16 kHz wav)
  python benchmark.py --selftest                       # check the WER math

Writes results.csv next to this file.
WER = (substitutions + deletions + insertions) / reference words, lower is better.
RTF = compute time / audio length, lower is faster (0.1 = 10x faster than real time).
"""
import argparse
import csv
import glob
import os
import re

from stt import HERE, MODELS, SR, load, model_files, read_audio, transcribe

LIBRISPEECH = os.path.join(HERE, "data", "LibriSpeech", "test-clean")


# LibriSpeech spells these out, the models abbreviate
ABBREV = {"mr": "mister", "mrs": "missus", "dr": "doctor", "st": "saint", "etc": "et cetera"}


def normalize(text):
    # ponytail: numbers aren't normalized ("27th" vs "twenty seventh" counts as an error),
    # swap in whisper's EnglishTextNormalizer if that skews results
    words = re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split()
    return " ".join(ABBREV.get(w, w) for w in words).split()


def edit_distance(ref, hyp):
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1]


def load_clips(data, n):
    if data.endswith(".tsv"):
        base = os.path.dirname(os.path.abspath(data))
        with open(data) as f:
            clips = [(os.path.join(base, p), t) for p, t in (l.rstrip("\n").split("\t", 1) for l in f if l.strip())]
    else:  # LibriSpeech layout: speaker/chapter/*.trans.txt
        clips = []
        for trans in sorted(glob.glob(os.path.join(data, "*", "*", "*.trans.txt"))):
            for line in open(trans):
                utt, text = line.split(" ", 1)
                clips.append((os.path.join(os.path.dirname(trans), utt + ".flac"), text.strip()))
    step = max(1, len(clips) // n)  # spread the subset across speakers
    return clips[::step][:n]


def run(name, clips, threads):
    rec = load(name, threads)
    transcribe(rec, clips[0][0])  # warm-up, not timed
    errors = words = 0
    compute = audio = 0.0
    worst = []
    for samples, ref in clips:
        hyp, dt = transcribe(rec, samples)
        r, h = normalize(ref), normalize(hyp)
        e = edit_distance(r, h)
        errors, words, compute, audio = errors + e, words + len(r), compute + dt, audio + len(samples) / SR
        worst.append((e / max(1, len(r)), ref, hyp))
    size_mb = sum(os.path.getsize(p) for p in model_files(name).values()) / 1e6
    worst.sort(reverse=True)
    return {"model": name, "params_m": MODELS[name][2], "disk_mb": round(size_mb),
            "wer_pct": round(100 * errors / words, 2), "rtf": round(compute / audio, 4),
            "avg_latency_s": round(compute / len(clips), 3)}, worst[:3]


def selftest():
    assert edit_distance("a b c".split(), "a b c".split()) == 0
    assert edit_distance("a b c".split(), "a x c".split()) == 1  # substitution
    assert edit_distance("a b c".split(), "a c".split()) == 1  # deletion
    assert edit_distance("a b".split(), "a b c d".split()) == 2  # insertions
    assert edit_distance([], "a".split()) == 1
    assert normalize("Hello, WALL-E's  world!") == ["hello", "wall", "e's", "world"]
    assert normalize("Mr. Smith, etc.") == ["mister", "smith", "et", "cetera"]
    print("selftest ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    p.add_argument("--data", default=LIBRISPEECH)
    p.add_argument("-n", type=int, default=200, help="number of clips")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--out", default=os.path.join(HERE, "results.csv"))
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        return selftest()

    clips = [(read_audio(path), text) for path, text in load_clips(args.data, args.n)]
    clips = [c for c in clips if len(c[0]) <= 28 * SR]  # whisper caps at 30 s incl. sherpa padding
    print(f"{len(clips)} clips, {sum(len(s) for s, _ in clips) / SR / 60:.1f} min of audio\n")
    rows = []
    for name in args.models:
        row, worst = run(name, clips, args.threads)
        rows.append(row)
        print(row)
        for w, ref, hyp in worst:
            print(f"   {w:.0%}  ref: {ref}\n         hyp: {hyp}")

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n| model | params | disk | WER | RTF | avg latency |\n|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["params_m"]):
        print(f"| {r['model']} | {r['params_m']}M | {r['disk_mb']} MB | {r['wer_pct']}% | {r['rtf']} | {r['avg_latency_s']}s |")


if __name__ == "__main__":
    main()
