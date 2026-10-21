"""
Chart results.csv (from benchmark.py) -> results.png

to use:
  python plot.py
  python plot.py --csv other.csv --out other.png --title "Jetson Orin Nano"
"""
import argparse
import csv
import os

import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
COLORS = {"moonshine": "#2a7de1", "whisper": "#e8833a"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(HERE, "results.csv"))
    p.add_argument("--out", default=os.path.join(HERE, "results.png"))
    p.add_argument("--title", default="M4 Max CPU, 2 threads")
    args = p.parse_args()

    rows = list(csv.DictReader(open(args.csv)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    panels = [("params_m", "Model size (million params)"), ("avg_latency_s", "Avg latency per clip (s)")]
    for ax, (x, xlabel) in zip(axes, panels):
        for r in rows:
            family = "moonshine" if "moonshine" in r["model"] else "whisper"
            ax.scatter(float(r[x]), float(r["wer_pct"]), s=90, color=COLORS[family], zorder=3)
            ax.annotate(r["model"], (float(r[x]), float(r["wer_pct"])),
                        textcoords="offset points", xytext=(7, 5), fontsize=9)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("WER % (lower is better)")
        ax.grid(alpha=0.3)
        ax.margins(x=0.2, y=0.15)
    for family, color in COLORS.items():
        axes[0].scatter([], [], color=color, label=family)
    axes[0].legend(loc="upper right")
    axes[0].set_title("Accuracy vs size")
    axes[1].set_title("Accuracy vs speed")
    fig.suptitle(f"Sherpa-ONNX STT on LibriSpeech test-clean ({args.title})")
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
