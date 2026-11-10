# WALL-E NLP benchmarks

Two benchmarks over the same 91-request test set, run on Gilbreth against
un-fine-tuned models. Both ask the same thing: **is the weak baseline a limit of
the model, or of the prompt?** They give opposite answers.

| | task | answer |
|---|---|---|
| [Classification](results/sweep/) | label a request `task` / `cannot_do` / `conversation` / `unclear` | **solved by a bigger model** |
| [Tree generation](results/tree_sweep/) | emit a BehaviorTree.CPP XML tree | **not solved by a bigger model** |

---

## 1. Classification — solved

Always answering `task` scores **54.9%**. That is the bar; anything below it has
learned nothing.

| model | acc | 95% CI | vs 54.9% | `unclear` F1 |
|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | **83.5%** | 74.6–89.7 | +28.6 | 0.56 |
| Phi-4-mini-instruct | 76.9% | 67.3–84.4 | +22.0 | **0.71** |
| Qwen3-1.7B | 75.8% | 66.1–83.5 | +20.9 | 0.14 |
| Llama-3.2-3B-Instruct | 70.3% | 60.3–78.7 | +15.4 | — |
| Qwen2.5-Coder-1.5B-Instruct | 67.0% | 56.9–75.8 | +12.1 | 0.00 |
| SmolLM3-3B | 64.8% | 54.6–73.9 | +9.9 | — |
| deepseek-coder-1.3b-instruct | 50.5% | 40.5–60.6 | −4.4 | 0.00 |
| Llama-3.2-1B-Instruct *(baseline)* | 38.5% | 29.1–48.7 | −16.5 | 0.00 |

Six of eight clear the bar. The 1B's 36.3% was never a prompt problem — it
answered `cannot_do` for **61 of 91** items when only 16 are, refusing 70% of
doable tasks. That is a degenerate classifier, not a weak one.

Full breakdown and per-class F1: [results/sweep/README.md](results/sweep/README.md).

## 2. Tree generation — not solved

Same test set, 49 tasks that carry a reference tree. `one_example` retrieves one
worked tree into the prompt; `no_example` does not.

| model | valid XML | action_match | arg_match |
|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | 93.9% | **20.4%** (10/49) | **12.2%** (6/49) |
| Qwen3-1.7B | 98.0% | 14.3% (7/49) | 8.2% (4/49) |
| Qwen2.5-Coder-1.5B-Instruct | 89.8% | 12.2% (6/49) | 6.1% (3/49) |
| Phi-4-mini-instruct | 98.0% | 12.2% (6/49) | 4.1% (2/49) |
| Llama-3.2-1B-Instruct | 85.7% | 2.0% (1/49) | 0% |
| *BTGenBot-2 (fine-tuned 1B)* | *75.5%* | *10.2% (5/49)* | *0%* |

*(all `one_example`; deepseek-coder missing, see Known issues)*

**Size helps 10x and is still not enough.** 2% → 20% from 1B to 4B, but 20% is
not shippable.

**An un-fine-tuned 4B beats the fine-tuned 1B** — 10/49 vs 5/49, and 6/49 vs
0/49 on arguments. BTGenBot-2 is a LoRA trained specifically for this task.
Fine-tuning a 1B is the wrong lever.

**Syntax is solved, semantics is not.** Valid XML runs 86–98% while action_match
sits at 12–20%: the models reliably emit well-formed trees that do the wrong
thing. Chasing validity further is wasted effort.

**`no_example` is 0/49 for every model**, including the 4B — 245 attempts, zero
valid trees. A fine-tuned 1B managed 17/49 on the same condition, so the format
is learnable and the prompt is the problem, not the models. That column
currently measures the prompt.

**`tricky` fails almost everywhere** (1/12, 0/12, 0/12, 0/12, 0/12). Same shape
as `unclear` in the classifier: the hard cases fail on both benchmarks.

## How grading works

Classification is graded by string match on the label. Tree generation is not,
and `matches_reference` in `run_tree_baseline.py` is exact string equality that
fires **0 out of 196** — a tree missing one step of three scores like garbage.
So `report_tree.py` compares structure instead, in two tiers:

| tier | ignores | reads as |
|---|---|---|
| `action_match` | all arguments | generous upper bound |
| `arg_match` | nothing | strict lower bound |

True correctness sits between them. `--disagreements` lists the cases where the
tiers differ — 6 trees rather than 74 blank cells, which is the only part still
needing a human.

## Running it

```bash
bash gilbreth_setup.sh          # login node: venv + pre-download weights
sbatch gilbreth_sweep.sbatch    # classification, ~1h on an A10
sbatch gilbreth_tree.sbatch     # tree generation, ~2-4h

python report_classifier.py "results/sweep/clf_*.csv"
python report_tree.py "results/tree_sweep/tree_*.csv" --by-difficulty
```

Both jobs resume: re-submitting skips work already on disk without loading a model.

## Known issues

- **deepseek-coder is missing from the tree sweep.** A missing space before a
  trailing `#` in the sbatch meant bash read it as `...instruct#` plus eight junk
  array entries. Fixed; re-submit to backfill.
- **Gemma 3n is excluded.** `AutoTokenizer` reports no chat template for it, so
  it would run unformatted while every other model gets its own.
- **n is small.** 91 classification items, 49 tree tasks, giving roughly ±10pp
  intervals. Enough to see who clears a baseline, not to separate models a few
  points apart. Top-three classification CIs overlap; so do Qwen3-4B's and
  Qwen3-1.7B's on trees. Single greedy sample, no seeds.
- **Deployment numbers are bf16.** A Jetson Orin Nano (8GB) would run Q4, which
  will move these scores — smaller models usually more. Re-run on the actual
  GGUF weights before choosing.
- **Test set:** `req_048` expects `move_arm(high_five)` but `wall_e.yaml` defines
  no pose vocabulary; `req_021`/`req_033` pass the spatial hint only to the
  search fallback, so a visible wrong object bypasses it; `req_007`'s reference
  uses `Say(...)` where every other reference uses `say(...)`.
- **One-example leakage.** Models copy the retrieved example's arguments —
  `search_for(ball, "in the room")` against an expected `"behind the table"`. The
  `one_example` condition partly measures retrieval quality, not generation.
