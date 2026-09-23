#!/usr/bin/env python3
"""
Scaffold a new weekly snapshot: clones the structure of the latest snapshot,
clears the data entries, sets fresh dates, and appends the week to manifest.json.

Run this every Monday before collection, then fill it with the fetch_* scripts
and by hand (social accounts, conclusions, risks).

Usage:
  python3 scripts/new_week.py --date 2026-09-05 --week 2026-W36 \
      --start 2026-08-30 --end 2026-09-05
"""
import argparse, json, os, sys, shutil
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def clear_entries(node):
    """Recursively empty any list called 'entries'/'accounts' and null capturedAt."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("entries", "accounts", "series") and isinstance(v, list):
                node[k] = []
            elif k == "capturedAt":
                node[k] = None
            else:
                clear_entries(v)
    elif isinstance(node, list):
        for it in node:
            clear_entries(it)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="new snapshot date, e.g. 2026-09-05")
    ap.add_argument("--week", required=True, help="ISO week label, e.g. 2026-W36")
    ap.add_argument("--start", required=True, help="collection period start")
    ap.add_argument("--end", required=True, help="collection period end")
    args = ap.parse_args()

    manifest = load(os.path.join(DATA, "manifest.json"))
    snaps = manifest["snapshots"]
    if any(s["date"] == args.date for s in snaps):
        sys.exit(f"✗ Snapshot {args.date} already exists in manifest.")
    prev = snaps[-1]["date"]
    src = os.path.join(DATA, "snapshots", prev)
    dst = os.path.join(DATA, "snapshots", args.date)
    if os.path.exists(dst):
        sys.exit(f"✗ Folder already exists: {dst}")
    shutil.copytree(src, dst)

    # meta
    meta = load(os.path.join(dst, "meta.json"))
    meta.update({
        "captureDate": args.date, "weekLabel": args.week,
        "collectionPeriod": {"start": args.start, "end": args.end},
        "isBaseline": False,
    })
    meta["dataQuality"] = [{
        "issue": f"Fresh week {args.week} — fill via fetch_* scripts + manual social/reviews.",
        "impact": "Empty until collected.", "status": "open", "owner": "Omar",
    }]
    save(os.path.join(dst, "meta.json"), meta)

    # clear data entries in the three section files
    for name in ("brand-voice.json", "social.json", "reviews.json"):
        obj = load(os.path.join(dst, name))
        clear_entries(obj)
        save(os.path.join(dst, name), obj)

    # reset the narrative report to a blank weekly template
    report = {
        "conclusions": [],
        "changeExplanation": {"verified": [], "hypotheses": []},
        "risks": [],
        "notes": f"Week {args.week}. Compare vs {prev}. Keep order: Conclusions → Data → Explanation → Risks → Quality.",
    }
    save(os.path.join(dst, "report.json"), report)

    manifest["snapshots"].append({"date": args.date, "weekLabel": args.week, "isBaseline": False})
    save(os.path.join(DATA, "manifest.json"), manifest)

    print(f"✓ Created snapshot {args.date} ({args.week}), cloned from {prev}.")
    print("  Next: python3 scripts/fetch_appstore.py --date", args.date)
    print("        python3 scripts/fetch_google_trends.py --date", args.date)
    print("  Then fill social accounts, conclusions and risks by hand.")


if __name__ == "__main__":
    main()
