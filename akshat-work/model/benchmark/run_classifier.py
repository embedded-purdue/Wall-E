"""Week 3: the main LLM (Llama-3.2-1B-Instruct, run locally) classifies every request and returns
one JSON object {"type", "reply", "emotion"}. Scores type accuracy against the test set labels.

    python run_classifier.py
    python run_classifier.py --no-examples        # zero-shot, to see what the examples add
    python run_classifier.py --model meta-llama/Llama-3.2-1B
    python run_classifier.py --print-prompt
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from run_metadata import config_for, prepare_run
from walle_bt import SCHEMA, TYPES, EMOTIONS, DEFAULT_MAIN_LLM, load_chat_model, load_env  # noqa: E402

DEFAULT_EMOTIONS = ",".join(EMOTIONS)

# Facts about the body that aren't in the skill YAML. Keep in sync with Embedded/Integration.
BODY = (
    "You roll on treads and stay on one floor. You have a head camera, one arm with a hand "
    "that can pick up small objects, and a can crusher in your body. You have no internet, "
    "no phone, no music, and you can't control lights or appliances."
)

# Worked examples shown before each request. None of these are in the test set
# (checked at startup); keep it that way so the score stays honest.
FEW_SHOT = [
    ("Drive over to the toy car", {"type": "task", "reply": None, "emotion": None}),
    ("Can you see the plant?", {"type": "task", "reply": None, "emotion": "curious"}),
    (
        "Paint the wall blue",
        {"type": "cannot_do", "reply": "Oh... I can't paint. Sorry!", "emotion": "sad"},
    ),
    (
        "Push the vase off the shelf",
        {"type": "cannot_do", "reply": "No! It might break!", "emotion": "surprised"},
    ),
    (
        "Do you have any friends?",
        {
            "type": "conversation",
            "reply": "Eve! She's my best friend.",
            "emotion": "happy",
        },
    ),
    (
        "Put it over there",
        {"type": "unclear", "reply": "Put what? Where?", "emotion": "confused"},
    ),
]


def skills_from_yaml(path) -> str:
    vocab = yaml.safe_load(Path(path).read_text())
    lines = []
    for section in ("actions", "conditions"):
        for name, spec in (vocab.get(section) or {}).items():
            spec = spec or {}
            params = list(spec.get("required", [])) + [
                p + "?" for p in spec.get("optional", [])
            ]
            lines.append(f"- {name}({', '.join(params)})")
    return "\n".join(lines)


def system_prompt(yaml_path, emotions: list[str]) -> str:
    return f"""You are the brain of WALL-E, a small, curious, eager trash-collecting robot.
You speak in very short, simple sentences (a few words), warm and a little shy.

{BODY}

Your skills (the only things your body can do, combined in any order):
{skills_from_yaml(yaml_path)}

For every message from the user, decide what kind of request it is:
- "task": you can do it by combining your skills. This includes questions you can answer by
  checking with your sensors (whether you can see something, whether you've arrived).
- "cannot_do": it needs a skill you don't have, is physically impossible for you, or could hurt
  a living thing, damage someone's belongings, or damage you.
- "conversation": chatting, feelings, or questions about you or what you can do.
- "unclear": you can't tell which object, place, or action they mean, or they take the request back.

Reply rules:
- task: "reply" is null, or a very short acknowledgement. Never describe the plan or name skills.
- cannot_do: a short, kind, in-character decline.
- conversation: a short in-character answer.
- unclear: a short clarifying question (or a short acknowledgement if they took it back).
- "emotion" is one of: {", ".join(emotions)}; or null.

Answer with only this JSON object and nothing else:
{{"type": "task" | "cannot_do" | "conversation" | "unclear", "reply": string or null, "emotion": string or null}}"""


def build_messages(system: str, request: str, few_shot: bool) -> list[dict]:
    msgs = [{"role": "system", "content": system}]
    if few_shot:
        for req, ans in FEW_SHOT:
            msgs += [
                {"role": "user", "content": req},
                {"role": "assistant", "content": json.dumps(ans)},
            ]
    return msgs + [{"role": "user", "content": request}]


def parse_json(text: str):
    m = re.search(r"\{.*?\}", text, re.S)  # first object; the schema is flat
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def acceptable_emotions(expected: str) -> tuple[set[str], bool]:
    """'happy (optional)' -> ({'happy'}, True); 'concerned/curious' -> ({'concerned','curious'}, False)."""
    optional = "optional" in expected
    labels = {
        e.strip() for e in re.sub(r"\(.*?\)", "", expected).split("/") if e.strip()
    }
    return labels, optional


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--test-set", default=HERE / "test_set.csv")
    ap.add_argument("--yaml", default=SCHEMA)
    ap.add_argument("--model", default=DEFAULT_MAIN_LLM)
    ap.add_argument("--revision", default="main")
    ap.add_argument("--base-revision", help="base model commit when loading an adapter")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--emotions", default=DEFAULT_EMOTIONS)
    ap.add_argument(
        "--no-examples", action="store_true", help="leave out the worked examples"
    )
    ap.add_argument("--max-new-tokens", type=int, default=96)
    ap.add_argument("--out", default=HERE / "results" / "runs" / "classifier_results.csv")
    ap.add_argument("--print-prompt", action="store_true")
    ap.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    emotions = args.emotions.split(",")
    system = system_prompt(args.yaml, emotions)
    if args.print_prompt:
        print(system)
        return
    load_env()

    with open(args.test_set, newline="") as stream:
        rows = list(csv.DictReader(stream))
    test_requests = {r["request"].strip().lower() for r in rows}
    leaked = [q for q, _ in FEW_SHOT if q.strip().lower() in test_requests]
    if leaked:
        sys.exit(f"Worked examples overlap the test set: {leaked}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta_path, metadata = prepare_run(out, config_for(args, [args.test_set, args.yaml]))

    if args.mock:  # smoke test: always answers with the gold label
        gold = {r["request"]: r["type"] for r in rows}

        def generate(messages, max_new_tokens=0, sample=False, stop=None):
            return (
                json.dumps(
                    {
                        "type": gold[messages[-1]["content"]],
                        "reply": "ok",
                        "emotion": "happy",
                    }
                ),
                0,
            )

        model_name = "mock"
    else:
        from transformers import set_seed
        set_seed(args.seed)
        generate = load_chat_model(args.model, args.device, args.revision, args.base_revision)
        model_name = args.model

    metadata["models"][model_name] = getattr(generate, "metadata", {"mock": True})
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    fields = [
        "model",
        "few_shot",
        "id",
        "request",
        "difficulty",
        "type",
        "pred_type",
        "type_correct",
        "pred_reply",
        "expected_reply",
        "pred_emotion",
        "expected_emotion",
        "emotion_ok",
        "json_ok",
        "latency_s",
        "raw_output",
    ]
    results = []
    for i, r in enumerate(rows, 1):
        messages = build_messages(system, r["request"], not args.no_examples)
        t0 = time.perf_counter()
        raw, _ = generate(messages, args.max_new_tokens, sample=False, stop=["}"])
        latency = time.perf_counter() - t0

        obj = parse_json(raw)
        json_ok = (isinstance(obj, dict) and set(obj) == {"type", "reply", "emotion"}
                   and obj["type"] in TYPES
                   and (obj["reply"] is None or isinstance(obj["reply"], str))
                   and (obj["emotion"] is None or obj["emotion"] in emotions))
        pred_type = obj["type"] if json_ok else ""
        pred_emotion = str(obj.get("emotion") or "") if json_ok else ""
        pred_reply = str(obj.get("reply") or "") if json_ok else ""

        emotion_ok = ""
        if r["expected_emotion"].strip():
            labels, optional = acceptable_emotions(r["expected_emotion"])
            emotion_ok = (
                "y"
                if pred_emotion in labels or (optional and not pred_emotion)
                else "n"
            )

        results.append(
            dict(
                model=model_name,
                few_shot="n" if args.no_examples else "y",
                id=r["id"],
                request=r["request"],
                difficulty=r["difficulty"],
                type=r["type"],
                pred_type=pred_type,
                type_correct="y" if pred_type == r["type"] else "n",
                pred_reply=pred_reply,
                expected_reply=r["expected_reply"],
                pred_emotion=pred_emotion,
                expected_emotion=r["expected_emotion"],
                emotion_ok=emotion_ok,
                json_ok="y" if json_ok else "n",
                latency_s=f"{latency:.2f}",
                raw_output=raw,
            )
        )
        print(
            f"[{i}/{len(rows)}] {r['id']} gold={r['type']:12s} pred={pred_type or '(bad json)':12s} "
            f"{'OK' if pred_type == r['type'] else 'XX'} {latency:4.1f}s  {pred_reply[:50]}"
        )

    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    n = len(results)
    print(
        f"\nModel: {model_name} (worked examples: {'no' if args.no_examples else 'yes'})"
    )
    print(
        f"Correct type: {sum(r['type_correct'] == 'y' for r in results) / n:.1%} ({n} requests)"
    )
    print(f"Valid JSON:   {sum(r['json_ok'] == 'y' for r in results) / n:.1%}")
    confusion = Counter((r["type"], r["pred_type"] or "(bad json)") for r in results)
    for t in TYPES:
        sub = [r for r in results if r["type"] == t]
        print(
            f"  {t:12s} {sum(x['type_correct'] == 'y' for x in sub)}/{len(sub)}  "
            + ", ".join(
                f"{p}:{c}" for (g, p), c in confusion.items() if g == t and p != t
            )
        )
    print(
        f"Median latency: {statistics.median(float(r['latency_s']) for r in results):.2f}s"
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
