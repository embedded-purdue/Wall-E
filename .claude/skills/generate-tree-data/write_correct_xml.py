#!/usr/bin/env python3
"""Write hand-corrected <id>.xml files back into the JSON's tree_xml fields (inverse of view_xml.py).

Each <id>.xml in xml_dir is matched to the entry with that id; XML comments are
stripped and the remaining text replaces the entry's tree_xml.

  write_correct_xml.py [json_file] [-i xml_dir] [--dry-run]
  default json_file: training/walle/generated/akshat.json
  default xml_dir:   training/walle/generated/xml/<json stem>/
"""
import argparse, json, re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "training/walle/generated"
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_comments(text: str) -> str:
    text = COMMENT.sub("", text)
    # drop lines left empty by comment removal, keep the rest of the formatting as-is
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file", nargs="?", default=str(GEN / "akshat.json"))
    ap.add_argument("-i", "--xml-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing the JSON")
    args = ap.parse_args()

    src = Path(args.json_file)
    xml_dir = Path(args.xml_dir) if args.xml_dir else GEN / "xml" / src.stem

    items = json.loads(src.read_text())
    by_id = {item["id"]: item for item in items if "id" in item}

    changed = unchanged = 0
    for f in sorted(xml_dir.glob("*.xml")):
        item = by_id.get(f.stem)
        if item is None:
            print(f"skip {f.name}: no entry with id {f.stem!r}")
            continue
        xml = strip_comments(f.read_text())
        if item.get("tree_xml") == xml:
            unchanged += 1
            continue
        print(f"update {f.stem}")
        item["tree_xml"] = xml
        changed += 1

    if changed and not args.dry_run:
        src.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {changed} entries ({unchanged} unchanged) in {src}")


if __name__ == "__main__":
    main()
