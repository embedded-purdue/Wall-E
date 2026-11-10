"""Grade tree-generation runs automatically against the reference trees.

`matches_reference` in run_tree_baseline.py is exact string equality on the step
shorthand, and it fires 0/196 on real data -- a tree missing one step out of three
scores the same as garbage. That is why every valid tree ends up as a blank
`does_what_was_asked` cell waiting on a human.

The references in test_set.csv are structured, so most of that is automatable.
Two tiers, both mechanical:

  action_match  same actions, same order, arguments ignored  -> generous upper bound
  arg_match     same actions AND same normalised arguments   -> strict lower bound

True "does what was asked" sits between them. The gap is where a human is actually
needed, and it is far smaller than grading every valid tree.

  python report_tree.py results/tree_results.csv
  python report_tree.py "results/tree_sweep/*.csv" --by-difficulty --csv summary.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import re
from collections import Counter

OPEN, CLOSE = "([{", ")]}"


def wilson(correct: int, n: int) -> tuple[float, float]:
    """95% Wilson interval; the normal approximation misbehaves at 0, which occurs here."""
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, correct / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def split_top(s: str, sep: str) -> list[str]:
    """Split on `sep` only at bracket depth 0 and outside quotes."""
    parts, buf, depth, quote = [], [], 0, False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            quote = not quote
        if not quote:
            if c in OPEN:
                depth += 1
            elif c in CLOSE:
                depth -= 1
            elif depth == 0 and s.startswith(sep, i):
                parts.append("".join(buf))
                buf = []
                i += len(sep)
                continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def wrapped(s: str, open_c: str, close_c: str) -> bool:
    """True if `open_c` at position 0 closes at the final character."""
    if not (s.startswith(open_c) and s.endswith(close_c)):
        return False
    depth = 0
    for i, c in enumerate(s):
        depth += (c in OPEN) - (c in CLOSE)
        if depth == 0 and i < len(s) - 1:
            return False
    return True


def norm_arg(a: str) -> str:
    return re.sub(r"\s+", " ", a.strip().strip('"').strip()).lower()


def parse(s: str, args: bool):
    """Shorthand -> comparable tuple. `args=False` compares structure only.

    Grammar mirrors walle_bt.shorthand: `a -> b`, `[a | b]`, `(a -> b)`,
    `Decorator(params){ a ; b }`, and leaves `action(arg, "text")`.
    """
    s = s.strip()
    if not s:
        return None
    seq = split_top(s, "->")
    if len(seq) > 1:
        return ("seq", tuple(parse(p, args) for p in seq))
    if wrapped(s, "[", "]"):
        # Fallback children are unordered: a frozenset so branch order can't matter.
        return ("fb", frozenset(parse(p, args) for p in split_top(s[1:-1], "|")))
    if wrapped(s, "(", ")"):
        return parse(s[1:-1], args)
    if s.endswith("}") and "{" in s:
        head, body = s[: s.index("{")], s[s.index("{") + 1 : -1]
        name, params = split_call(head)
        return ("dec", name, params if args else (), tuple(parse(k, args) for k in split_top(body, ";")))
    name, params = split_call(s)
    return ("act", name, params if args else ())


def split_call(s: str) -> tuple[str, tuple]:
    s = s.strip()
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$", s, re.S)
    if not m:
        return (s.lower(), ())
    return (m.group(1).lower(), tuple(norm_arg(a) for a in split_top(m.group(2), ",")))


def grade(row) -> tuple[bool, bool]:
    """(action_match, arg_match). Invalid trees fail both without parsing."""
    if row.get("valid") != "y":
        return (False, False)
    gen, exp = row.get("generated_steps", ""), row.get("expected_steps", "")
    if not gen.strip() or not exp.strip():
        return (False, False)
    try:
        return (parse(gen, False) == parse(exp, False), parse(gen, True) == parse(exp, True))
    except Exception:
        return (False, False)


def pct(c: int, n: int) -> str:
    lo, hi = wilson(c, n)
    return f"{c / n * 100:5.1f}% {c:>3}/{n:<3} {lo * 100:4.1f}-{hi * 100:<5.1f}" if n else " " * 26


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="tree result CSVs (globs ok)")
    ap.add_argument("--by-difficulty", action="store_true")
    ap.add_argument("--disagreements", action="store_true",
                    help="list trees where the two tiers disagree: the ones worth a human look")
    ap.add_argument("--csv", help="also write the summary table here")
    args = ap.parse_args()

    rows = []
    for path in sorted({p for pat in args.files for p in glob.glob(pat)}):
        rows += list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit("No rows found in: " + ", ".join(args.files))
    for r in rows:
        r["_action"], r["_arg"] = grade(r)

    models = sorted({r["model"] for r in rows})
    conds = sorted({r["condition"] for r in rows})

    print("\nDenominator is every attempted task; invalid trees count as failures.")
    print("action_match ignores arguments (upper bound); arg_match requires them (lower bound).\n")
    head = f"{'model':<30}{'condition':<13}{'valid XML':>26}{'action_match':>26}{'arg_match':>26}"
    print(head)
    print("-" * len(head))
    out = []
    for m in models:
        for c in conds:
            sub = [r for r in rows if r["model"] == m and r["condition"] == c]
            if not sub:
                continue
            n = len(sub)
            v = sum(1 for r in sub if r["valid"] == "y")
            a = sum(1 for r in sub if r["_action"])
            g = sum(1 for r in sub if r["_arg"])
            print(f"{m.split('/')[-1]:<30}{c:<13}{pct(v, n):>26}{pct(a, n):>26}{pct(g, n):>26}")
            out.append([m.split("/")[-1], c, n, v, a, g])

    if args.by_difficulty:
        tiers = ["easy", "medium", "hard", "tricky"]
        for m in models:
            print(f"\n{m.split('/')[-1]} by difficulty (valid / action_match / arg_match):")
            print(f"  {'condition':<13}" + "".join(f"{t:>22}" for t in tiers))
            for c in conds:
                cells = ""
                for t in tiers:
                    sub = [r for r in rows if r["model"] == m and r["condition"] == c and r["difficulty"] == t]
                    n = len(sub)
                    if not n:
                        cells += f"{'-':>22}"
                        continue
                    v = sum(1 for r in sub if r["valid"] == "y")
                    a = sum(1 for r in sub if r["_action"])
                    g = sum(1 for r in sub if r["_arg"])
                    cells += f"{f'{v}/{a}/{g} of {n}':>22}"
                print(f"  {c:<13}{cells}")

    if args.disagreements:
        dis = [r for r in rows if r["_action"] and not r["_arg"]]
        print(f"\nRight actions, wrong arguments -- {len(dis)} cases, the ones worth a human look:")
        for r in dis[:25]:
            print(f"\n  {r['id']} [{r['model'].split('/')[-1]} {r['condition']}]")
            print(f"    exp: {r['expected_steps'][:110]}")
            print(f"    gen: {r['generated_steps'][:110]}")

    # A reference that never validates is a point no model can score.
    bad = Counter(r["id"] for r in rows if r["expected_steps"].strip()
                  and parse(r["expected_steps"], True) is None)
    if bad:
        print(f"\n  ! unparseable reference trees: {sorted(bad)}")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["model", "condition", "n", "valid", "action_match", "arg_match"])
            w.writerows(out)
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
