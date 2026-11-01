"""Validate seed data and export separate tree-generator and main-model datasets."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BENCHMARK = REPO / "akshat-work/model/benchmark"
sys.path[:0] = [str(BENCHMARK), str(BENCHMARK.parent)]
from bt_validator import BehaviorTreeValidator
from run_classifier import FEW_SHOT, system_prompt
from walle_bt import (SCHEMA, EMOTIONS, TYPES, SYSTEM_PROMPT, action_list,
                      user_message, _tokens)


def normalized(text):
    return " ".join(_tokens(text))


def build(out, tree_source=HERE / "tree_seeds.json", main_source=HERE / "main_seeds.json",
          test_set=BENCHMARK / "test_set.csv", schema=SCHEMA):
    validator = BehaviorTreeValidator.from_yaml(schema)
    trees = json.loads(tree_source.read_text())
    main = json.loads(main_source.read_text())
    with test_set.open(newline="") as stream:
        tests = list(csv.DictReader(stream))
    reserved = {normalized(row["request"]) for row in tests}
    reserved.update(normalized(req) for req, _ in FEW_SHOT)
    # Tree retrieval seeds already share a few classifier prompt examples; the
    # tree dataset excludes only the held-out test set, not that separate task's prompt.
    held_out = {normalized(row["request"]) for row in tests}
    outputs = {f"{job}_{split}": [] for job in ("tree", "main")
               for split in ("train", "validation")}
    warnings = []
    provenance = []
    for job, seeds in (("tree", trees), ("main", main)):
        seen = set()
        seen_ids = set()
        for seed in seeds:
            request = seed["request"]
            key = normalized(request)
            if not key or key in seen or seed["id"] in seen_ids:
                raise ValueError(f"Empty/duplicate {job} seed: {seed['id']}")
            if seed["split"] not in {"train", "validation"}:
                raise ValueError(f"Bad split: {seed['id']}")
            if key in (held_out if job == "tree" else reserved):
                raise ValueError(f"Held-out/prompt leakage: {seed['id']}")
            if not seed.get("source") or not seed.get("review_status"):
                raise ValueError(f"Missing provenance: {seed['id']}")
            seen.add(key)
            seen_ids.add(seed["id"])
            if job == "tree":
                xml = seed["tree_xml"]
                root = validator.validate(xml)
                if any("{" in value or "}" in value for node in root.iter()
                       for value in node.attrib.values()):
                    raise ValueError(f"Unbound blackboard placeholder: {seed['id']}")
                for node in root.iter():
                    if "emotion" in node.attrib and node.attrib["emotion"] not in EMOTIONS:
                        raise ValueError(f"Unknown emotion: {seed['id']}")
                row = {"instruction": SYSTEM_PROMPT,
                       "input": user_message(request, action_list(schema)), "output": xml}
            else:
                response = seed["response"]
                if (set(response) != {"type", "reply", "emotion"}
                    or response["type"] not in TYPES
                    or (response["reply"] is not None and not isinstance(response["reply"], str))
                    or (response["emotion"] is not None and response["emotion"] not in EMOTIONS)
                    or (response["type"] != "task" and not response["reply"])):
                    raise ValueError(f"Bad main-model target: {seed['id']}")
                row = {"instruction": system_prompt(schema, EMOTIONS),
                       "input": request, "output": json.dumps(response)}
            outputs[f"{job}_{seed['split']}"].append(row)
            provenance.append({"job": job, **{k: v for k, v in seed.items()
                                              if k not in {"tree_xml", "response"}}})
            a = set(_tokens(request))
            for test in tests:
                b = set(_tokens(test["request"]))
                if a and b and len(a & b) / len(a | b) >= .6:
                    warnings.append({"job": job, "seed_id": seed["id"],
                                     "test_id": test["id"], "reason": "near-duplicate; review before training"})
        if not outputs[f"{job}_train"] or not outputs[f"{job}_validation"]:
            raise ValueError(f"Both splits required for {job}")
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in outputs.items():
        (out / f"{name}.json").write_text(json.dumps(rows, indent=2) + "\n")
    sources = [tree_source, main_source, test_set, schema]
    manifest = {"status": "candidate seed data; human/BT review required before training",
                "format": "BTGenBot-2 instruction/input/output JSON array; separate jobs",
                "counts": {name: len(rows) for name, rows in outputs.items()},
                "main_types": dict(Counter(s["response"]["type"] for s in main)),
                "source_sha256": {str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p):
                                  hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                "near_duplicate_warnings": warnings, "examples": provenance}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "data")
    args = parser.parse_args()
    manifest = build(args.out)
    print(json.dumps({"counts": manifest["counts"],
                      "near_duplicates": manifest["near_duplicate_warnings"]}, indent=2))
