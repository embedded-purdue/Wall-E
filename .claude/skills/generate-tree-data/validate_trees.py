#!/usr/bin/env python3
"""Validate every tree_xml in a generated data file against akshat-work/model/wall_e.yaml.

  validate_trees.py [files...]     # default: training/walle/generated/akshat.json
Read-only: never rewrites the data file. Exits 1 if any tree is invalid. Needs pyyaml.
"""
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MODEL = REPO / "akshat-work/model"
sys.path.insert(0, str(MODEL))
from bt_validator import BehaviorTreeValidator  # noqa: E402


def main(files):
    v = BehaviorTreeValidator.from_yaml(MODEL / "wall_e.yaml")
    bad = total = 0
    for path in map(Path, files or [REPO / "training/walle/generated/akshat.json"]):
        for i, it in enumerate(json.loads(path.read_text())):
            total += 1
            tag = f"{path.name}/{it.get('id', f'#{i}')}"
            try:
                v.validate(it.get("tree_xml"))
            except Exception as e:  # BTValidationError, or anything odd about the entry
                bad += 1
                print(f"FAIL {tag}: {e}")
    print(f"\n{total - bad}/{total} trees valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
