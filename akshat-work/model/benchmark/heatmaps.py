"""Heatmaps of the baseline results, saved to results/images/.

  - tree_results_<model>.png       one per model (e.g. tree_results_btgenbot2.png) in tree_results.csv: valid XML and tree success
                                   by difficulty, with and without an example tree
  - classifier_confusion_<model>.png  request type: true type vs. predicted type

    python plot_heatmaps.py
    python plot_heatmaps.py --trees results/tree_results.csv --classifier results/classifier_results.csv

Run it after grading, since tree success only counts trees marked `y` in does_what_was_asked.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

HERE = Path(__file__).parent
DIFFS = ["easy", "medium", "hard", "tricky"]
TYPES = ["task", "cannot_do", "conversation", "unclear"]
CONDITIONS = {"no_example": "no example", "one_example": "one example"}
NAMES = {
    "llama-3.2-1b-it-ft-lora-bt": "BTGenBot-2",
    "Llama-3.2-1B-Instruct": "Llama-3.2-1B-Instruct",
    "Llama-3.2-1B": "Llama-3.2-1B (base)",
}

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# One-hue sequential ramp (light = low, dark = high).
CMAP = LinearSegmentedColormap.from_list(
    "seq_blue",
    [
        "#f3f7fd",
        "#cde2fb",
        "#9ec5f4",
        "#6da7ec",
        "#3987e5",
        "#256abf",
        "#184f95",
        "#0d366b",
    ],
)

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
    }
)


SLUGS = {
    "llama-3.2-1b-it-ft-lora-bt": "btgenbot2",
    "Llama-3.2-1B-Instruct": "llama3.2_1b_instruct",
    "Llama-3.2-1B": "llama3.2_1b_base",
}


def slug(model: str) -> str:
    if model in SLUGS:
        return SLUGS[model]
    return re.sub(r"[^a-z0-9.]+", "_", NAMES.get(model, model).lower()).strip("_")


def is_yes(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.lower().str.startswith("y")


def draw(ax, rates: pd.DataFrame, labels: pd.DataFrame, **kw):
    sns.heatmap(
        rates,
        ax=ax,
        annot=labels,
        fmt="",
        cmap=CMAP,
        vmin=0,
        vmax=1,
        linewidths=2,
        linecolor=SURFACE,
        annot_kws={"fontsize": 10, "linespacing": 1.4},
        cbar_kws={"format": matplotlib.ticker.PercentFormatter(1.0), "shrink": 0.8},
        **kw,
    )
    ax.tick_params(length=0)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    cbar = ax.collections[0].colorbar
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(length=0, colors=INK_2)


def cell(k: int, n: int) -> str:
    return f"{k / n:.0%}\n{k}/{n}" if n else "—"


def tree_heatmaps(path: Path, out_dir: Path) -> list[Path]:
    df = pd.read_csv(path, dtype=str).fillna("")
    df["model"] = df["model"].str.split("/").str[-1]
    df["is_valid"] = df["valid"] == "y"
    df["is_success"] = df["is_valid"] & is_yes(df["does_what_was_asked"])
    df["ungraded"] = df["is_valid"] & (df["does_what_was_asked"].str.strip() == "")

    saved = []
    for model, m in df.groupby("model", sort=False):
        conds = [c for c in CONDITIONS if c in set(m["condition"])]
        cols = [(metric, c) for metric in ("is_valid", "is_success") for c in conds]
        col_names = [
            f"{'Valid XML' if met == 'is_valid' else 'Tree success'}\n{CONDITIONS[c]}"
            for met, c in cols
        ]
        row_names = [d for d in DIFFS if d in set(m["difficulty"])] + ["all"]

        rates = pd.DataFrame(
            index=[r.capitalize() for r in row_names], columns=col_names, dtype=float
        )
        labels = rates.astype(object)
        for r in row_names:
            sub = m if r == "all" else m[m["difficulty"] == r]
            for (met, c), name in zip(cols, col_names):
                s = sub[sub["condition"] == c][met]
                rates.loc[r.capitalize(), name] = s.mean() if len(s) else float("nan")
                labels.loc[r.capitalize(), name] = cell(int(s.sum()), len(s))

        fig, ax = plt.subplots(
            figsize=(2.0 * len(cols) + 2.5, 0.75 * len(row_names) + 2.2)
        )
        draw(ax, rates, labels)
        ax.axhline(
            len(row_names) - 1, color=INK_2, linewidth=1
        )  # separate the "All" row
        if len(conds) > 1:
            ax.axvline(
                len(conds), color=SURFACE, linewidth=8
            )  # separate the two metrics
        ax.xaxis.tick_top()
        ax.set_xlabel(""), ax.set_ylabel("")
        ax.set_title(
            f"{NAMES.get(model, model)}: tree generation baseline", loc="left", pad=48
        )

        n_tasks = m["id"].nunique()
        note = f"{n_tasks} doable tasks per condition. Tree success = valid XML and graded as doing what was asked."
        ungraded = int(m["ungraded"].sum())
        if ungraded:
            note += f"\n{ungraded} valid trees not graded yet, so tree success is a lower bound."
        fig.text(0.01, 0.01, note, fontsize=9, color=INK_2, va="bottom")
        fig.tight_layout(rect=(0, 0.06 if ungraded else 0.04, 1, 1))

        out = out_dir / f"tree_results_{slug(model)}.png"
        fig.savefig(out, dpi=200)
        plt.close(fig)
        saved.append(out)
    return saved


def classifier_heatmap(path: Path, out_dir: Path) -> Path:
    df = pd.read_csv(path, dtype=str).fillna("")
    model = (
        df["model"].iloc[0].split("/")[-1] if "model" in df and len(df) else "main LLM"
    )
    df["pred"] = df["pred_type"].replace("", "bad JSON")
    pred_cols = TYPES + (["bad JSON"] if (df["pred"] == "bad JSON").any() else [])

    counts = pd.crosstab(df["type"], df["pred"]).reindex(
        index=TYPES, columns=pred_cols, fill_value=0
    )
    totals = counts.sum(axis=1)
    rates = counts.div(totals.where(totals > 0), axis=0)
    labels = pd.DataFrame(
        [
            [cell(counts.loc[t, p], totals[t]) if totals[t] else "—" for p in pred_cols]
            for t in TYPES
        ],
        index=TYPES,
        columns=pred_cols,
    )

    pretty = lambda xs: [x.replace("_", " ") for x in xs]
    rates.index, rates.columns = pretty(TYPES), pretty(pred_cols)
    labels.index, labels.columns = rates.index, rates.columns

    fig, ax = plt.subplots(figsize=(1.6 * len(pred_cols) + 3, 5.2))
    draw(ax, rates, labels)
    for i in range(len(TYPES)):  # outline the diagonal (correct answers)
        ax.add_patch(
            plt.Rectangle((i, i), 1, 1, fill=False, edgecolor=INK, linewidth=1.5)
        )
    ax.set_xlabel("Predicted type"), ax.set_ylabel("True type")
    acc = (df["pred_type"] == df["type"]).mean()
    shots = (
        "with worked examples"
        if df.get("few_shot", pd.Series(["y"])).iloc[0] == "y"
        else "no worked examples"
    )
    ax.set_title(f"{NAMES.get(model, model)}: request type", loc="left", pad=28)
    ax.text(
        0,
        1.02,
        f"Correct type {acc:.0%} ({(df['pred_type'] == df['type']).sum()}/{len(df)}), "
        f"{shots}. Each row sums to 100%; outlined cells are correct.",
        transform=ax.transAxes,
        fontsize=9,
        color=INK_2,
    )
    fig.tight_layout()

    out = out_dir / f"classifier_confusion_{slug(model)}.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--trees", default=HERE / "results" / "tree_results.csv")
    ap.add_argument("--classifier", default=HERE / "results" / "classifier_results.csv")
    ap.add_argument("--out-dir", default=HERE / "results" / "images")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    if Path(args.trees).exists():
        saved += tree_heatmaps(Path(args.trees), out_dir)
    else:
        print(f"Skipped trees: {args.trees} not found")
    if Path(args.classifier).exists():
        saved.append(classifier_heatmap(Path(args.classifier), out_dir))
    else:
        print(f"Skipped classifier: {args.classifier} not found")
    for p in saved:
        print(f"Saved {p}")


if __name__ == "__main__":
    main()
