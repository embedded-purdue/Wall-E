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
    with open(path, newline="") as stream:
        rows = list(csv.DictReader(stream))
    groups = defaultdict(list)
    for row in rows:
        groups[row["model"], row["condition"]].append(row)
    lines = ["## Tree generation", "",
             "Validity checks XML structure and vocabulary, not task correctness.",
             "Tree success requires human grading. Pending means valid trees remain ungraded.", "",
             "| Model | Condition | Tasks | Valid XML | Matches reference | Tree success | Ungraded | Median latency |",
             "|---|---|---|---|---|---|---|---|"]
    for (model, condition), rs in groups.items():
        n = len(rs)
        valid = sum(r["valid"] == "y" for r in rs)
        match = sum(r["matches_reference"] == "y" for r in rs)
        ok = sum(r["valid"] == "y" and r["does_what_was_asked"].strip().lower() == "y" for r in rs)
        ungraded = sum(r["valid"] == "y" and not r["does_what_was_asked"].strip() for r in rs)
        success = f"Pending ({ok} confirmed)" if ungraded else pct(ok, n)
        latency = statistics.median(float(r["latency_s"]) for r in rs)
        lines.append(f"| {model} | {condition} | {n} | {pct(valid, n)} | {pct(match, n)} | {success} | {ungraded} | {latency:.2f}s |")
    if any(r["model"].startswith("mock") for r in rows):
        lines += ["", "**Mock run: wiring check only; these are not model accuracy results.**"]
    return lines


def classifier_section(path: Path) -> list[str]:
    with open(path, newline="") as stream:
        rows = list(csv.DictReader(stream))
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
            if not Path(str(path) + ".meta.json").exists():
                lines += [f"_{path.name}: historical CSV without a provenance sidecar; runtime and exact model revisions are not recorded._", ""]
            lines += fn(path) + [""]
        else:
            lines += [f"_{path.name} not found, skipped._", ""]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
