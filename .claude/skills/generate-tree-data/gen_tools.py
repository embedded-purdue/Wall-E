#!/usr/bin/env python3
"""plan: emit diverse generation cells for one person. check: validate, run on mocks, dedupe, coverage, split.

  gen_tools.py plan  <person> [-n 30]      # person in PEOPLE
  gen_tools.py check [files...]            # default: training/walle/generated/*.json
Needs pyyaml (the BT validator imports it).
"""
import csv, glob, hashlib, json, random, re, sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "training/walle/generated"
sys.path[:0] = [str(REPO / "akshat-work/model"), str(REPO / "skills")]

PEOPLE = ["monish", "akshat", "adwaiy"]  # object pools are split by this order -> lanes never overlap
TARGET = 300
# primary action = the skill the request is *about*; the rest of the tree is supporting steps.
QUOTA = {"search": 35, "navigate": 35, "grab": 45, "release": 40, "arm": 30,
         "crush": 25, "look": 30, "say": 20, "express": 25, "query": 15}  # sums to 300
# Pure chat ("tell me a joke", "goodnight") is type=conversation in the test set: no tree. So Say is only
# ever part of a physical/perceptual task here, never the whole request.
# Shapes the mocks can actually run from an empty-handed start (grab needs NavigateTo first,
# Release/Crush need something held, LookAt/NavigateTo need a found object or user/home).
ARCH = {
    "search": ["find_only", "find_with_hint", "find_then_say_result"],
    "navigate": ["find_then_go", "go_to_user_or_home", "find_go_then_express"],
    "grab": ["find_go_grab", "find_go_grab_then_express", "grab_bring_to_user"],
    "release": ["grab_deliver_to_user", "grab_place_at_object", "grab_drop_at_home"],
    "arm": ["pose_only", "pose_then_say", "pose_then_express"],
    "crush": ["find_go_grab_crush", "crush_then_express"],
    "look": ["look_at_user", "find_then_look", "look_only_if_visible"],
    "say": ["say_if_visible", "find_go_then_say", "come_to_user_then_say"],
    "express": ["express_only", "express_if_visible", "express_then_say"],
    "query": ["report_if_visible", "report_if_at"],
}
NO_OBJECT = {"go_to_user_or_home", "look_at_user", "pose_only", "pose_then_say", "pose_then_express",
             "come_to_user_then_say", "express_only", "express_then_say"}
REGISTERS = ["terse command", "polite/please", "casual slang", "question form (can you...)",
             "indirect, with a reason or context", "speech-to-text style: lowercase, no punctuation, a filler word"]
# Ground truth for poses/emotions is the skills team's mocks, not a hand-copied list.
from skills.mock_skills import EMOTIONS, NAMED_POSES as POSES  # noqa: E402
POSES, EMOTIONS = list(POSES), [e for e in EMOTIONS if e != "neutral"]  # neutral = no reaction
# Small, safe-to-grab household items only (no scissors/candles/furniture).
OBJECTS = ("ball,toy car,sock,book,marker,pen,remote,keys,shoe,teddy bear,water bottle,stapler,red mug,crayon,"
           "lunchbox,slipper,charger,hat,tape measure,spoon,cup,dog toy,phone,headphones,wallet,glasses,notebook,"
           "banana,apple,towel,hairbrush,toothbrush,frisbee,puzzle piece,paper airplane,coaster,flashlight,"
           "computer mouse,deck of cards,sponge,calculator,blue folder,tennis ball,action figure,juice bottle,"
           "napkin,toy dinosaur,bowl,plastic fork,whistle,rubber duck,yo-yo,glue stick,eraser,mitten,beanie").split(",")
PLACES = ["table", "low shelf", "toy bin", "laundry basket", "desk", "cardboard box", "recycling bin", "doormat"]  # release destinations
# Crush is only for empty aluminum drink cans (BT contract); variants split per person like OBJECTS.
CRUSHABLE = ["empty soda can", "empty aluminum can", "empty energy drink can", "empty sparkling water can",
             "crumpled soda can", "empty iced tea can", "empty root beer can", "empty lemonade can", "empty ginger ale can"]
MESSAGES = ["dinner is ready", "the door is open", "it found the object", "it is done", "hello to the object or pet",
            "the floor is clean", "it is heading out", "it is back", "it needs help", "the battery is low"]  # things to relay, not chat
STOP = set("a an the to and or of in on at is it me my you your please can could would go over up for with then if so "
           "wall-e walle hey just that this um uh like".split())
SEQ = {"Sequence", "ReactiveSequence", "SequenceStar", "PipelineSequence"}
FALLBACK = {"Fallback", "ReactiveFallback"}
PASSTHROUGH = {"RetryUntilSuccessful", "Timeout", "Delay", "RateController", "Repeat"}
REQUIRED = ("id", "request", "description", "tree_xml", "primary", "archetype", "object", "register",
            "source", "review_status")


def toks(s):
    return {t for t in re.findall(r"[a-z']+", s.lower()) if t not in STOP}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def family(it):
    return f"{it['primary']}|{it['archetype']}|{it['object']}"


def split_of(it):  # whole family stays in one split -> no leakage between variants
    return "validation" if int(hashlib.sha1(family(it).encode()).hexdigest(), 16) % 10 == 0 else "train"


def load(path):
    return json.loads(Path(path).read_text()) if Path(path).exists() else []


def simulate(node, world, trace):
    """Tick the tree once against skills.mock_skills.MockWorld (same rules as mock_skills_node)."""
    tag = node.get("ID") if node.tag in ("Action", "Condition") else node.tag
    kids = list(node)
    if tag in ("root", "BehaviorTree"):
        return simulate(kids[0], world, trace)
    if tag in SEQ:
        return all(simulate(k, world, trace) for k in kids)
    if tag in FALLBACK:
        return any(simulate(k, world, trace) for k in kids)
    if tag == "Inverter":
        return not simulate(kids[0], world, trace)
    if tag in ("ForceSuccess", "ForceFailure"):
        simulate(kids[0], world, trace)
        return tag == "ForceSuccess"
    if tag in PASSTHROUGH:
        return simulate(kids[0], world, trace)
    if kids:
        raise ValueError(f"{tag} is not simulated")
    goal = {k: v for k, v in node.attrib.items() if k not in ("ID", "name")}
    skill = re.sub(r"(?<!^)(?=[A-Z])", "_", tag).lower()
    if skill == "move_arm":
        goal = {"pose_name": goal.get("pose", "")}
    if skill in ("navigate_to", "look_at", "grab", "release", "is_at"):  # BT leaf passes <name>.location if found
        goal["has_location"] = (goal.get("target") or goal.get("object", "")).strip().lower() in world.visible
    out = world.run(skill, **goal)
    trace.append(f"{tag}{'' if out.success else '!' + (out.reason or 'false')}")
    return out.success


def plan(person, n):
    assert person in PEOPLE, f"person must be one of {PEOPLE}"
    mine = load(GEN / f"{person}.json")
    have = Counter(i["primary"] for i in mine)
    used = Counter(i["object"] for i in mine)
    batch = len(mine)  # new seed each time you have more data -> no repeated cells
    rng = random.Random(f"{person}-{batch}")
    pool = OBJECTS[PEOPLE.index(person)::len(PEOPLE)]
    need = {k: max(QUOTA[k] - have[k], 0) for k in QUOTA}
    cells = []
    for i in range(n):
        left = {k: v for k, v in need.items() if v > 0}
        if not left:
            break
        p = rng.choices(list(left), weights=list(left.values()))[0]
        need[p] -= 1
        arch = rng.choice(ARCH[p])
        if arch in NO_OBJECT:
            obj = rng.choice(["user", "home"]) if arch == "go_to_user_or_home" else "none"
        else:  # least-used objects first so a person's pool is spread evenly
            opts = CRUSHABLE[PEOPLE.index(person)::len(PEOPLE)] if p == "crush" else pool
            low = min(used[o] for o in opts)
            obj = rng.choice([o for o in opts if used[o] == low])
            used[obj] += 1
        c = {"cell": f"{person}-{batch + i:03d}", "primary": p, "archetype": arch,
             "object": obj, "register": rng.choice(REGISTERS)}
        if arch == "find_with_hint" or (p in ("search", "grab", "release") and rng.random() < .25):
            c["hint"] = "add a location hint (under/behind/next to/on something) and pass it to SearchFor"
        if p == "arm":
            c["pose"] = rng.choice([p for p in POSES if p != "crush_drop"])  # crush_drop is only ever part of a crush
        if "express" in arch or "emotion" in arch:
            c["emotion"] = rng.choice(EMOTIONS)
        if arch == "grab_place_at_object":
            c["place"] = rng.choice(PLACES)  # must be searched for before NavigateTo, like the object
        if arch in ("come_to_user_then_say", "pose_then_say", "express_then_say"):
            c["message"] = rng.choice(MESSAGES)
        cells.append(c)
    print(json.dumps({"person": person, "have": dict(have), "remaining_after": need, "cells": cells}, indent=1))


def check(files):
    from bt_validator import BehaviorTreeValidator
    from skills.mock_skills import MockWorld
    v = BehaviorTreeValidator.from_yaml(REPO / "akshat-work/model/wall_e.yaml")
    with open(REPO / "akshat-work/model/benchmark/test_set.csv", newline="") as f:
        ref = [(r["request"], "test set " + r["id"]) for r in csv.DictReader(f)]
    ref += [(s["request"], "example " + s["id"]) for s in load(REPO / "akshat-work/model/benchmark/example_library.json")]
    files = [Path(f) for f in (files or sorted(glob.glob(str(GEN / "*.json"))))]
    data = {f: load(f) for f in files}
    errs, seen, ids, shapes = [], [], set(), Counter()
    for path, items in data.items():
        before = json.dumps(items, indent=2) + "\n"
        for it in items:
            tag = f"{path.stem}/{it.get('id')}"
            missing = [k for k in REQUIRED if not it.get(k)]
            if missing:
                errs.append(f"{tag}: missing {missing}")
                continue
            if it["id"] in ids:
                errs.append(f"{tag}: duplicate id")
            ids.add(it["id"])
            try:
                root = v.validate(it["tree_xml"])
                canon = ET.fromstring(it["tree_xml"])  # one whitespace layout for every target, same as the seeds
                ET.indent(canon, "    ")
                it["tree_xml"] = ET.tostring(canon, encoding="unicode")
                for nd in root.iter():
                    a = nd.attrib
                    if any(c in x for x in a.values() for c in "{}"):
                        errs.append(f"{tag}: unbound placeholder")
                    if "emotion" in a and a["emotion"] not in EMOTIONS:
                        errs.append(f"{tag}: bad emotion {a['emotion']}")
                    if nd.tag == "MoveArm" and a.get("pose") not in POSES:
                        errs.append(f"{tag}: bad pose {a.get('pose')}")
                trace = []
                if not simulate(root, MockWorld(), trace):
                    errs.append(f"{tag}: fails on mocks: {' > '.join(trace)}")
                shapes[re.sub(r'="[^"]*"', "", re.sub(r"\s+", "", it["tree_xml"]))] += 1
            except Exception as e:
                errs.append(f"{tag}: invalid tree: {e}")
            if it["primary"] not in QUOTA or it["archetype"] not in ARCH[it["primary"]]:
                errs.append(f"{tag}: primary/archetype not in plan vocabulary")
            t = toks(it["request"])
            for r, src in ref + seen:
                if jac(t, toks(r)) >= .6:
                    errs.append(f"{tag}: near-duplicate of [{src}] '{r}' ~ '{it['request']}'")
                    break
            seen.append((it["request"], tag))
            it["split"] = split_of(it)
        after = json.dumps(items, indent=2) + "\n"
        if after != before:  # only touch files whose split stamps changed -> no churn in teammates' files
            path.write_text(after)
    print(f"{'person':8}" + "".join(f"{k[:6]:>8}" for k in QUOTA) + "   total")
    for path, items in data.items():
        c = Counter(i.get("primary") for i in items)
        print(f"{path.stem:8}" + "".join(f"{c[k]:>4}/{QUOTA[k]:<3}" for k in QUOTA) + f"  {len(items)}/{TARGET}")
    tot = sum(map(len, data.values()))
    for s, n in shapes.most_common(5):
        if tot >= 20 and n / tot > .15:
            errs.append(f"tree shape is {n}/{tot} of data (>15%): {s[:80]}")
    print(f"\n{len(errs)} problem(s)")
    print("\n".join(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["plan"]:
        plan(a[1], int(a[a.index("-n") + 1]) if "-n" in a else 30)
    elif a[:1] == ["check"]:
        sys.exit(check(a[1:]))
    else:
        print(__doc__)
