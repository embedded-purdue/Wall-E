"""Week 3 tree baseline. Runs every doable task in the test set through each model,
with no example tree and with one retrieved example tree.

Default models:
  - BTGenBot-2 (AIRLab-POLIMI/llama-3.2-1b-it-ft-lora-bt): the released fine-tuned model
  - Llama-3.2-1B-Instruct: the model BTGenBot-2 was fine-tuned from (shows what their fine-tuning adds)

    python run_tree_baseline.py                          # all models x both conditions
    python run_tree_baseline.py --models btgenbot2       # just one model
    python run_tree_baseline.py --dry-run --limit 2      # print prompts only, no model
    python run_tree_baseline.py --resume                 # continue an interrupted run

Each output row is one (model, request, condition). Invalid trees and exact matches with the
reference are graded automatically; fill in `does_what_was_asked` (y/n) for the rest, then run
summarize.py.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from bt_validator import BehaviorTreeValidator, BTValidationError  # noqa: E402
from walle_bt import (
    BTGENBOT2,
    DEFAULT_MAIN_LLM,
    ExampleLibrary,
    action_list,  # noqa: E402
    build_messages,
    clean_output,
    load_chat_model,
    load_env,
    near_duplicates,
    steps_from_xml,
)

ALIASES = {"btgenbot2": BTGENBOT2, "llama": DEFAULT_MAIN_LLM}

FIELDS = [
    "model",
    "id",
    "request",
    "difficulty",
    "condition",
    "retriever",
    "example_id",
    "example_request",
    "retrieval_score",
    "valid",
    "validator_error",
    "matches_reference",
    "does_what_was_asked",
    "grader_comment",
    "generated_steps",
    "expected_steps",
    "notes",
    "generated_xml",
    "expected_tree_xml",
    "raw_output",
    "had_extra_text",
    "attempts_used",
    "latency_s",
    "new_tokens",
]


def mock_generator(reference_by_request):
    """Smoke test without a model: returns the reference tree."""

    def generate(messages, max_new_tokens=0, sample=False, stop=None):
        request = messages[-1]["content"].split('"')[1]
        return reference_by_request.get(request, "<root/>"), 0

    generate.unload = lambda: None
    return generate


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--test-set", default=HERE / "test_set.csv")
    ap.add_argument(
        "--yaml", default=HERE / "wall_e.yaml", help="BT team's shared skill YAML"
    )
    ap.add_argument("--library", default=HERE / "example_library.json")
    ap.add_argument("--retriever", default="auto", choices=["auto", "embed", "tfidf"])
    ap.add_argument(
        "--models",
        default="btgenbot2,llama",
        help="comma-separated Hugging Face ids, or the aliases btgenbot2 / llama",
    )
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--conditions", default="no_example,one_example")
    ap.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="1 = baseline (one greedy try). >1 resamples after a validator failure",
    )
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument(
        "--limit", type=int, help="only the first N tasks (for a quick check)"
    )
    ap.add_argument("--out", default=HERE / "results" / "tree_results.csv")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument(
        "--dry-run", action="store_true", help="print prompts, don't load a model"
    )
    ap.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    load_env()

    models = [ALIASES.get(m.strip(), m.strip()) for m in args.models.split(",")]
    validator = BehaviorTreeValidator.from_yaml(args.yaml)
    actions = action_list(args.yaml)
    library = ExampleLibrary(args.library, args.retriever)
    print(f"Example retrieval: {library.retriever}")
    for ex in library.items:  # every example must itself be valid
        validator.validate(ex["tree_xml"])

    rows = [
        r
        for r in csv.DictReader(open(args.test_set, newline=""))
        if r["type"] == "task" and r["expected_tree_xml"].strip()
    ]
    if args.limit:
        rows = rows[: args.limit]
    conditions = args.conditions.split(",")

    for test_req, lib_req in near_duplicates([r["request"] for r in rows], library):
        print(f"WARNING near-duplicate: test '{test_req}' ~ library '{lib_req}'")
    print(
        f"{len(models)} models x {len(rows)} tasks x {len(conditions)} conditions\n{actions}\n"
    )

    if args.dry_run:
        for r in rows:
            for cond in conditions:
                ex = (
                    library.retrieve(r["request"])[0] if cond == "one_example" else None
                )
                print(f"===== {r['id']} [{cond}] example={ex['id'] if ex else None}")
                for m in build_messages(r["request"], actions, ex)[1:]:
                    print(f"--- {m['role']}\n{m['content']}")
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.resume and out.exists():
        done = {
            (r["model"], r["id"], r["condition"])
            for r in csv.DictReader(open(out, newline=""))
        }
    mode = "a" if done else "w"

    with open(out, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if mode == "w":
            w.writeheader()
        for model_id in models:
            todo = [
                (r, c)
                for r in rows
                for c in conditions
                if (model_id, r["id"], c) not in done
            ]
            if not todo:
                continue
            generate = (
                mock_generator({r["request"]: r["expected_tree_xml"] for r in rows})
                if args.mock
                else load_chat_model(model_id, args.device)
            )
            for i, (r, cond) in enumerate(todo, 1):
                ex, score = (
                    library.retrieve(r["request"])
                    if cond == "one_example"
                    else (None, None)
                )
                messages = build_messages(r["request"], actions, ex)

                valid, error, attempts, tokens, xml, raw, extra = (
                    False,
                    "",
                    0,
                    0,
                    "",
                    "",
                    False,
                )
                t0 = time.perf_counter()
                for attempts in range(1, args.attempts + 1):
                    raw, n = generate(
                        messages,
                        args.max_new_tokens,
                        sample=attempts > 1,
                        stop=["</root>"],
                    )
                    tokens += n
                    xml, extra = clean_output(raw)
                    try:
                        validator.validate(xml)
                        valid, error = True, ""
                        break
                    except BTValidationError as e:
                        error = str(e)
                latency = time.perf_counter() - t0

                gen_steps = steps_from_xml(xml)
                match = valid and gen_steps == r["expected_steps"]
                w.writerow(
                    dict(
                        model=model_id,
                        id=r["id"],
                        request=r["request"],
                        difficulty=r["difficulty"],
                        condition=cond,
                        retriever=library.retriever if ex else "",
                        example_id=ex["id"] if ex else "",
                        example_request=ex["request"] if ex else "",
                        retrieval_score=f"{score:.2f}" if score is not None else "",
                        valid="y" if valid else "n",
                        validator_error=error,
                        matches_reference="y" if match else "n",
                        does_what_was_asked=(
                            "y" if match else ("n" if not valid else "")
                        ),
                        grader_comment="",
                        generated_steps=gen_steps,
                        expected_steps=r["expected_steps"],
                        notes=r["notes"],
                        generated_xml=xml,
                        expected_tree_xml=r["expected_tree_xml"],
                        raw_output=raw,
                        had_extra_text="y" if extra else "n",
                        attempts_used=attempts,
                        latency_s=f"{latency:.2f}",
                        new_tokens=tokens,
                    )
                )
                f.flush()
                print(
                    f"[{model_id.split('/')[-1]} {i}/{len(todo)}] {r['id']} {cond:12s} "
                    f"valid={valid!s:5s} match={match!s:5s} {latency:5.1f}s {error[:60]}"
                )
            generate.unload()
    print(
        f"\nWrote {out}. Grade the blank `does_what_was_asked` cells, then run summarize.py"
    )


if __name__ == "__main__":
    main()
