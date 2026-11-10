# Classifier model sweep (Gilbreth)

Eight un-fine-tuned models run through the **same** request-type classifier
benchmark Akshat built — same 91 requests, same prompt, same worked examples.
Only the model changes.

**Question:** was Llama-3.2-1B's 36.3% a limit of the model, or of the prompt?

**Answer:** the model. Six of eight models clear the baseline without any fine-tuning.

## Read the baseline first

The test set has 4 unbalanced classes. Always answering `task` scores **54.9%**.
Anything below that line has learned nothing, no matter how it looks.

| | |
|---|---|
| always-`task` (majority) | **54.9%** |
| uniform random | 25.0% |
| items | n = 91 |

## Results

| model | acc | 95% CI | vs 54.9% | macro F1 | bad JSON |
|---|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | **83.5%** | 74.6–89.7 | **+28.6** | 0.785 | 0 |
| Phi-4-mini-instruct | 76.9% | 67.3–84.4 | +22.0 | 0.763 | 0 |
| Qwen3-1.7B | 75.8% | 66.1–83.5 | +20.9 | 0.638 | 0 |
| Llama-3.2-3B-Instruct | 70.3% | 60.3–78.7 | +15.4 | 0.641 | 0 |
| Qwen2.5-Coder-1.5B-Instruct | 67.0% | 56.9–75.8 | +12.1 | 0.530 | 0 |
| SmolLM3-3B | 64.8% | 54.6–73.9 | +9.9 | 0.598 | 0 |
| deepseek-coder-1.3b-instruct | 50.5% | 40.5–60.6 | −4.4 | 0.326 | 3 |
| Llama-3.2-1B-Instruct *(baseline)* | 38.5% | 29.1–48.7 | −16.5 | 0.344 | 1 |

## What to take from it

**Don't rank the top three.** Qwen3-4B (74.6–89.7) and Phi-4-mini (67.3–84.4)
overlap heavily. At n=91 the gap isn't resolvable — you'd need more items or
multiple seeds to call a winner.

**`unclear` is the hard class for everyone.**

| | overall | `unclear` F1 |
|---|---|---|
| Qwen3-4B | 83.5% | 0.56 (P 1.00 / R 0.38) |
| **Phi-4-mini** | 76.9% | **0.71** (P 0.67 / R 0.77) |
| Qwen2.5-Coder, deepseek, Llama-1B | — | **0.00 — never predicted** |

Phi-4-mini is the only model that reliably notices ambiguity. Qwen3-4B is never
*wrong* when it says `unclear`, but misses ~60% of them. If WALL-E should ask
"put what, where?" rather than guess, that trade-off matters more than the
6.6-point accuracy gap.

**Why the 1B scored so badly.** It answered `cannot_do` for 61 of 91 items when
only 16 are — 100% recall, 26% precision. It refused 70% of genuinely doable
tasks. That's a degenerate classifier, not a weak one. See
`../images/classifier_confusion_llama3.2_1b_instruct.png`.

**Coder models underperformed.** deepseek-coder lands *below* the majority line.
Classification here is semantic; code tuning didn't transfer.

## Reproducing

```bash
bash gilbreth_setup.sh          # login node: venv + pre-download weights
sbatch gilbreth_sweep.sbatch    # A10, ~1h; skips models whose CSV already exists
python report_classifier.py "results/sweep/clf_*.csv"
```

## Files

| file | what |
|---|---|
| `clf_<model>.csv` | per-request predictions, one row per item |
| `summary.csv` | the table above |
| `slurm-12302138.out` | job log |

## Known issues

- **`report_classifier.py` crashes on re-run** with `KeyError: 'type_correct'`.
  Its glob `results/sweep/*.csv` now matches the `summary.csv` it wrote last
  time. Use `clf_*.csv` until this is fixed.
- **Gemma 3n is missing.** It's multimodal and builds a timm vision tower at
  init, which needs `pillow` and `timm` (now in `gilbreth_setup.sh`). On the
  retry it loaded but reported *no chat template*, so it ran unformatted while
  every other model got its instruct template. Excluded as not comparable.
  (Likely because `AutoTokenizer` doesn't see the template on a multimodal repo,
  where it ships with the processor — unverified.)
- **n=91 gives ±10pp intervals.** Enough to see who clears 54.9%, not enough to
  separate models a few points apart. Single greedy sample, no seeds.
- **Test set bugs, unfixed:** `req_048` expects `move_arm(high_five)` but
  `wall_e.yaml` defines no pose vocabulary; `req_021`/`req_033` pass the spatial
  hint only to the search fallback, so a visible wrong object bypasses it.
