#!/usr/bin/env python3
"""Write each example's tree_xml to its own <id>.xml file for easy viewing.

  view_xml.py [json_file] [-o out_dir] [--force]
  Existing <id>.xml files are left untouched unless --force is given.
  default json_file: training/walle/generated/akshat.json
  default out_dir:   training/walle/generated/xml/<json stem>/
"""
import argparse, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "training/walle/generated"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file", nargs="?", default=str(GEN / "akshat.json"))
    ap.add_argument("-o", "--out-dir", default=None)
    ap.add_argument("-f", "--force", action="store_true", help="overwrite existing .xml files")
    args = ap.parse_args()

    src = Path(args.json_file)
    out = Path(args.out_dir) if args.out_dir else GEN / "xml" / src.stem
    out.mkdir(parents=True, exist_ok=True)

    items = json.loads(src.read_text())
    n = skipped = 0
    for item in items:
        xml = item.get("tree_xml")
        if not xml:
            print(f"skip {item.get('id', '?')}: no tree_xml")
            continue
        dest = out / f"{item['id']}.xml"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        # "--" is illegal inside an XML comment, and a trailing "-" would form "--->"
        req = " ".join(item.get("request", "").split()).replace("--", "- -").rstrip("-")
        dest.write_text(f"<!-- request: {req} -->\n" + xml.rstrip() + "\n")
        n += 1
    print(f"wrote {n} xml files to {out} ({skipped} already existed, skipped)")


if __name__ == "__main__":
    main()
