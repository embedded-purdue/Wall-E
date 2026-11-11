"""Turn graded results into the baseline score table (results/baseline_report.md).

    python summarize.py
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DIFFS = ["easy", "medium", "hard", "tricky"]


def pct(a, b):
    return f"{a / b:.1%} ({a}/{b})" if b else "—"


def tree_section(path: Path) -> list[str]:
    rows = list(csv.DictReader(open(path, newline="")))
    by_cond = defaultdict(list)
    for r in rows:
        by_cond[r["condition"]].append(r)

    lines = ["## Tree generation (BTGenBot-2, released model)", "",
             "Tree success = passes the validator **and** graded as doing what was asked.", "",
             "| Condition | Tasks | Valid XML | Matches reference | Tree success | Ungraded | Median latency |",
             "|---|---|---|---|---|---|---|"]
    ungraded_total = 0
    for cond, rs in by_cond.items():
        n = len(rs)
        valid = sum(r["valid"] == "y" for r in rs)
        match = sum(r["matches_reference"] == "y" for r in rs)
        ok = sum(r["valid"] == "y" and r["does_what_was_asked"].strip().lower().startswith("y") for r in rs)
        ungraded = sum(r["valid"] == "y" and not r["does_what_was_asked"].strip() for r in rs)
        ungraded_total += ungraded
        lat = statistics.median(float(r["latency_s"]) for r in rs)
        lines.append(f"| {cond} | {n} | {pct(valid, n)} | {pct(match, n)} | {pct(ok, n)} | {ungraded} | {lat:.1f}s |")

    lines += ["", "Tree success by difficulty:", "",
              "| Condition | " + " | ".join(DIFFS) + " |", "|---" * (len(DIFFS) + 1) + "|"]
    for cond, rs in by_cond.items():
        cells = []
        for d in DIFFS:
            sub = [r for r in rs if r["difficulty"] == d]
            ok = sum(r["valid"] == "y" and r["does_what_was_asked"].strip().lower().startswith("y") for r in sub)
            cells.append(pct(ok, len(sub)))
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")

    errors = defaultdict(int)
    for r in rows:
        if r["valid"] != "y":
            errors[r["validator_error"].split(":")[0][:60]] += 1
    if errors:
        lines += ["", "Most common validator errors:", ""]
        lines += [f"- {e} ({c})" for e, c in sorted(errors.items(), key=lambda x: -x[1])[:8]]
    if ungraded_total:
        lines += ["", f"**{ungraded_total} valid trees still need grading**, so tree success is a lower bound."]
    return lines


def classifier_section(path: Path) -> list[str]:
    rows = list(csv.DictReader(open(path, newline="")))
    n = len(rows)
    lines = ["## Request type (main LLM)", "",
             f"- Correct type: {pct(sum(r['type_correct'] == 'y' for r in rows), n)}",
             f"- Valid JSON: {pct(sum(r['json_ok'] == 'y' for r in rows), n)}"]
    emo = [r for r in rows if r["emotion_ok"]]
    lines.append(f"- Emotion matches label (where one is given): {pct(sum(r['emotion_ok'] == 'y' for r in emo), len(emo))}")
    lines.append(f"- Median latency: {statistics.median(float(r['latency_s']) for r in rows):.2f}s")
    lines += ["", "| True type | Correct | Predicted as |", "|---|---|---|"]
    for t in ["task", "cannot_do", "conversation", "unclear"]:
        sub = [r for r in rows if r["type"] == t]
        wrong = defaultdict(int)
        for r in sub:
            if r["type_correct"] != "y":
                wrong[r["pred_type"] or "bad JSON"] += 1
        lines.append(f"| {t} | {pct(len(sub) - sum(wrong.values()), len(sub))} | "
                     + (", ".join(f"{k} ×{v}" for k, v in wrong.items()) or "—") + " |")
    misses = [r for r in rows if r["type_correct"] != "y"]
    if misses:
        lines += ["", "Misclassified:", ""]
        lines += [f"- {r['id']} \"{r['request']}\": {r['type']} → {r['pred_type'] or 'bad JSON'}" for r in misses]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trees", default=HERE / "results" / "tree_results.csv")
    ap.add_argument("--classifier", default=HERE / "results" / "classifier_results.csv")
    ap.add_argument("--out", default=HERE / "results" / "baseline_report.md")
    args = ap.parse_args()

    lines = ["# Wall-E NLP baseline (week 3)", ""]
    for path, fn in [(Path(args.trees), tree_section), (Path(args.classifier), classifier_section)]:
        if path.exists():
            lines += fn(path) + [""]
        else:
            lines += [f"_{path.name} not found, skipped._", ""]
    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
