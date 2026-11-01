# Wall-E training seed data v1

This prepares two separate tasks as described in the
[NLP Team Guide](https://docs.google.com/document/d/1kVWOesDs5m6Jtm0fs7xgr1CHDk92gWmk/edit)
and the Oct 27 chat: a main model returns request type/reply/emotion; a tree
model generates XML using only Wall-E's 11 skills. They may start from the same
Llama-3.2-1B base and use different adapters. No model is trained here.

| Candidate dataset | Train | Validation |
|---|---:|---:|
| Tree generator | 11 | 2 |
| Main classifier/replies | 20 | 4 |

These are small **candidate seeds**, not a sufficient fine-tuning corpus or a
meaningful model evaluation. Human and BT review remains required. The five
emotion labels and runtime blackboard mapping are provisional; see the
[shared contract](../../behavior_tree/bt_construct/schema.md).

## Build

From the repository root after installing the benchmark's `requirements.txt`:

```bash
.venv/bin/python training/walle/build_data.py
```

`data/` contains committed JSON arrays with `instruction`, `input`, `output`,
matching the [BTGenBot-2 dataset format](https://github.com/AIRLab-POLIMI/BTGenBot-2#-dataset-generation).
The tree input uses the same request summary and YAML-derived action list as
baseline inference. Main-model outputs are JSON strings containing exactly
`type`, `reply`, `emotion`. Train the two tasks separately.

`manifest.json` records source hashes, origin, split, review status, and detected
near-duplicates. Generation is deterministic. All candidates are checked before
output files are written. The exporter rejects malformed/unknown XML nodes and
ports, unbound `{...}` values, unsupported emotions, malformed main-model
targets, duplicate seed IDs/requests and normalized exact test-request overlap.
Near-duplicate test requests are flagged for manual review; the current seeds
have none under the word-overlap check. That check cannot prove semantic
independence. Both splits must be present for each task.

## Provenance and review choices

- Tree seeds derive from the existing handwritten example library, keeping
  source IDs. The book-delivery/showing family (`ex_03`, `ex_13`) is held out
  together for validation. Do not generate training variants from that family.
- The juice-box crushing and repeated bottle-cap collection examples were
  excluded because physical eligibility and loop termination need clarification.
  A candidate empty-aluminum-can tree covers `Crush`; its dimensions and
  preconditions still need BT approval.
- The pen example drops navigation the request did not ask for. Shelf placement
  explicitly assumes a low shelf within reach. All 11 skills are represented.
- Main seeds are hand-authored, balanced across all four types (six each), with
  one validation example per type. They are not extracted from the test set or
  the classifier's few-shot prompt examples.
- The original retrieval library and historical benchmark inputs are unchanged.
  Retrieval examples are prompt-visible exemplars, not held-out test outputs.

## Before running QLoRA on Anvil

1. Have BT approve the shared skill ports, blackboard keys and each seed's
   intended behavior; have Integration approve emotion labels. Record the actual
   reviewers in seed provenance. Do not label machine validation as human approval.
2. Expand **training seeds only** using the upstream
   [dataset-generation notebooks](https://github.com/AIRLab-POLIMI/BTGenBot-2/tree/main/dataset).
   Keep each seed family and all its variations in a single split. Add candidates
   to the source JSON, validate them and spot-check semantics by hand. Do not
   train on the 91 benchmark requests or their reference trees.
3. Keep only reviewed, valid task/tree pairs. Preserve the complete YAML skill
   list in every input. The exporter currently uses zero-shot training records,
   matching upstream format; retrieval is supplied separately during inference.
4. Adapt the [upstream LoRA notebook](https://github.com/AIRLab-POLIMI/BTGenBot-2/blob/main/training/llama-3-2-lora-ft.ipynb)
   to the generated tree train/validation files. Start tree adaptation from the
   released BTGenBot-2 model per the guide; keep the main-model adapter separate.
   Inspect whether the checkpoint is merged or an adapter before loading it.
   This branch does not download upstream datasets or launch training jobs.
5. Freeze a baseline before training. Evaluate the adapted generator on the same
   untouched test set, with and without retrieval. Report human-graded task
   success, classifier accuracy and latency; do not substitute XML pass rates.
