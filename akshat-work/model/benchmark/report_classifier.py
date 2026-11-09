"""Compare classifier sweep runs against the baselines that actually matter.

Accuracy alone is misleading here: the test set is 4 unbalanced classes, and always
answering "task" scores 54.9%. Any model below that line has learned nothing.

  python report_classifier.py results/sweep/*.csv
  python report_classifier.py results/sweep/*.csv --csv summary.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
from collections import Counter

TYPES = ["task", "cannot_do", "conversation", "unclear"]


def wilson(correct: int, n: int) -> tuple[float, float]:
    """95% Wilson interval. Normal approximation misbehaves near 0, and `unclear`
    scores exactly 0, so use Wilson throughout."""
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, correct / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def prf(rows, label):
    tp = sum(1 for r in rows if r["type"] == label and r["pred_type"] == label)
    fp = sum(1 for r in rows if r["type"] != label and r["pred_type"] == label)
    fn = sum(1 for r in rows if r["type"] == label and r["pred_type"] != label)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def score(rows):
    n = len(rows)
    correct = sum(1 for r in rows if r["type_correct"] == "y")
    # A parse failure is a different defect from a wrong label; keep them apart.
    bad_json = sum(1 for r in rows if r["json_ok"] != "y")
    f1s = [prf(rows, t)[2] for t in TYPES]
    lo, hi = wilson(correct, n)
    return {
        "n": n,
        "correct": correct,
        "acc": correct / n if n else 0.0,
        "lo": lo,
        "hi": hi,
        "macro_f1": sum(f1s) / len(f1s),
        "bad_json": bad_json,
        "never_predicted": [t for t in TYPES if not any(r["pred_type"] == t for r in rows)],
        "pred_dist": Counter(r["pred_type"] for r in rows),
        "per_class": {t: prf(rows, t) for t in TYPES},
    }


def baselines(rows):
    """What you get for free: always-majority, and uniform random."""
    truth = Counter(r["type"] for r in rows)
    n = sum(truth.values())
    top, top_n = truth.most_common(1)[0]
    return {"majority_label": top, "majority_acc": top_n / n, "random_acc": 1 / len(TYPES)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="classifier result CSVs (globs ok)")
    ap.add_argument("--csv", help="also write the summary table here")
    args = ap.parse_args()

    paths = sorted({p for pat in args.files for p in glob.glob(pat)})
    runs = []
    for path in paths:
        rows = list(csv.DictReader(open(path)))
        if not rows:
            continue
        name = rows[0].get("model") or os.path.basename(path)
        runs.append((name.split("/")[-1], rows, score(rows)))
    if not runs:
        raise SystemExit("No rows found in: " + ", ".join(args.files))

    base = baselines(runs[0][1])
    maj = base["majority_acc"]
    print(f'\nBaselines: always-"{base["majority_label"]}" {maj * 100:.1f}%  |  '
          f'random {base["random_acc"] * 100:.1f}%  |  n = {len(runs[0][1])}')
    print("A model below the majority line has learned nothing.\n")

    head = f"{'model':<32}{'acc':>7}{'95% CI':>15}{'vs maj':>9}{'macroF1':>9}{'badJSON':>9}"
    print(head)
    print("-" * len(head))
    for name, _rows, s in sorted(runs, key=lambda r: -r[2]["acc"]):
        delta = (s["acc"] - maj) * 100
        beats = "+" if delta > 0 else ""
        print(f"{name:<32}{s['acc'] * 100:>6.1f}%"
              f"{s['lo'] * 100:>7.1f}-{s['hi'] * 100:<7.1f}"
              f"{beats}{delta:>7.1f}{s['macro_f1']:>9.3f}{s['bad_json']:>9}")

    print("\nPer-class F1 (P/R in parentheses):")
    print(f"{'model':<32}" + "".join(f"{t:>22}" for t in TYPES))
    for name, _rows, s in sorted(runs, key=lambda r: -r[2]["macro_f1"]):
        cells = ""
        for t in TYPES:
            p, r, f1 = s["per_class"][t]
            cells += f"{f1:>8.2f} ({p:.2f}/{r:.2f})"
        print(f"{name:<32}{cells}")

    for name, _rows, s in runs:
        if s["never_predicted"]:
            print(f"\n  ! {name} never predicted: {', '.join(s['never_predicted'])}"
                  f"  (predictions: {dict(s['pred_dist'])})")

    print("\nCIs are Wilson 95%. Overlapping intervals mean the gap is not resolvable "
          f"at n={len(runs[0][1])}; add seeds or items before ranking.")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["model", "n", "correct", "accuracy", "ci_low", "ci_high",
                        "vs_majority", "macro_f1", "bad_json"]
                       + [f"f1_{t}" for t in TYPES])
            for name, _rows, s in sorted(runs, key=lambda r: -r[2]["acc"]):
                w.writerow([name, s["n"], s["correct"], round(s["acc"], 4),
                            round(s["lo"], 4), round(s["hi"], 4),
                            round(s["acc"] - maj, 4), round(s["macro_f1"], 4), s["bad_json"]]
                           + [round(s["per_class"][t][2], 4) for t in TYPES])
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
