# Reproducing the Wall-E baseline

The Oct 28 CSVs and images in `results/` are historical evidence. They remain
unchanged. `baseline_report.md` is regenerated from those CSVs with results
separated by **model and example condition**, and ungraded success marked pending.
The historical classifier's `json_ok` only checked parsing and request type;
new runs also check the complete `type/reply/emotion` schema. Historical
`matches_reference` used readable steps; new runs compare canonical XML.

## Offline checks (no Hugging Face access)

From the repository root, with Python 3.11+:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r akshat-work/model/benchmark/requirements.txt
.venv/bin/python -m unittest discover -s akshat-work/model/benchmark -p 'test_*.py' -v
.venv/bin/python akshat-work/model/benchmark/run_tree_baseline.py --dry-run --limit 2
.venv/bin/python akshat-work/model/benchmark/run_classifier.py --print-prompt
.venv/bin/python akshat-work/model/benchmark/summarize.py
.venv/bin/python training/walle/build_data.py
```

Paths are resolved from the scripts, so an absolute script path also works from
another working directory. Tests run the full 196-row tree mock and 91-row
classifier mock in temporary folders. Mock outputs are labeled `mock`; their
accuracy is not evidence of model quality.

## Real model runs

Use Python 3.11 for the pinned model packages. Install
`requirements-models.txt` in that environment. Obtain gated Llama access, then
set `HF_TOKEN` in your shell or an ignored `.env` file. Do not commit the token.
The model dependency pins are a proposed runtime; offline checks do not certify
that stack or model performance on your hardware.

```bash
python akshat-work/model/benchmark/run_classifier.py --device cuda \
  --out akshat-work/model/benchmark/results/runs/classifier_results.csv
python akshat-work/model/benchmark/run_tree_baseline.py --device cuda \
  --retriever tfidf --attempts 1 \
  --out akshat-work/model/benchmark/results/runs/tree_results.csv
python akshat-work/model/benchmark/summarize.py \
  --trees akshat-work/model/benchmark/results/runs/tree_results.csv \
  --classifier akshat-work/model/benchmark/results/runs/classifier_results.csv \
  --out akshat-work/model/benchmark/results/runs/baseline_report.md
```

Use `--device mps` on an Apple laptop or `--device cpu` where needed. Default
tree models are the released BTGenBot-2 checkpoint and Llama-3.2-1B-Instruct;
each runs 49 tasks with and without an example (196 rows total). The classifier
runs all 91 requests. `req_050` (Stop) has no reference tree and is explicitly
reported as excluded; see the shared contract for the unresolved stop API.

TF-IDF is explicit and deterministic; installed embedding packages no longer
silently change retrieval. Embeddings remain an opt-in `--retriever embed`
experiment requiring sentence-transformers. Keep that experiment in a separate
output path. Its full embedding dependency/model pinning remains future work.

New runs write a neighboring `.csv.meta.json`: input/code hashes, arguments,
seed, package/Python/platform versions, Git commit, and resolved model revision,
device and dtype. A different device/runtime can still change outputs and timing.
For an exact model revision, run one model at a time with `--models <HF-id>`
(or classifier `--model <HF-id>`) and `--revision <commit-from-metadata>`.
For adapter checkpoints also pass `--base-revision <base-commit-from-metadata>`;
the loader pins both repositories, and resume reuses both recorded commits.

Existing CSVs are never overwritten. Pick a new `--out` for a new experiment.
For an interrupted tree run, repeat the **same command** with `--resume`.
Resume verifies provenance and reuses recorded model commits. Changed code,
settings, inputs or environment require a new output. Classifier runs restart
with a new output path. Preserve each CSV and its metadata together.

## Grading and baseline boundaries

- Keep the original 91 requests frozen while comparing model versions. Review
  their reference semantics with BT before treating reference matches as truth:
  `req_002`, for example, asks for grabbing but its reference omits it.
- XML validity checks structure and allowed ports; it does not prove the task was
  performed. Every passing new tree needs `does_what_was_asked=y/n` and a short
  `grader_comment`. Invalid trees are automatic failures. Equivalent trees can
  succeed without matching the reference XML.
- `--attempts 1` is the baseline. Higher values are a separate resampling
  experiment, not the planned validator-error repair loop.
- Report generation latency separately from end-to-end speech latency. Timings
  exclude model loading; they do not measure Jetson deployment performance.

Shared schema: [`schema.md`](../../../../behavior_tree/bt_construct/schema.md).
Training preparation: [`training/walle`](../../../../training/walle/README.md).
