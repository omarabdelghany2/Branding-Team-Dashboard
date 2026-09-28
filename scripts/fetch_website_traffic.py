#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest monthly website-traffic numbers into data/website-traffic.json
(Section D — new module, manager request 2026-09-28).

We don't have web-analytics access yet, so this collector follows the same rule
as every other one: it NEVER writes placeholder numbers. With no source it prints
exactly what's needed and leaves the section's blocker intact. The moment someone
hands us a monthly export, point --csv at it and the section fills.

Canonical monthly CSV columns (header row required; extra columns ignored):
    month,sessions,users,newUsers,pageviews,avgEngagementTimeSec,bounceRate,conversions
`month` is 1-12 (calendar 2026). Blank cells stay blank (TBC), not zero.
A template lives at data/templates/website-traffic-template.csv.

Sources this maps cleanly from:
  - GA4  → Reports ▸ Engagement/Acquisition, export by month
  - SimilarWeb / Semrush → monthly traffic export
  - any hand-built monthly sheet using the columns above

Usage:
  python scripts/fetch_website_traffic.py                       # print what's needed
  python scripts/fetch_website_traffic.py --csv ga4_export.csv --site "51talk.com/ar"
"""
import argparse, csv, json, os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "website-traffic.json")

NUM_FIELDS = ["sessions", "users", "newUsers", "pageviews",
              "avgEngagementTimeSec", "bounceRate", "conversions"]

SETUP = """
Website traffic is BLOCKED on a data source — nothing written (by design).

To unblock, get ONE of:
  • GA4 property access (read) for the site(s) we want to track, or
  • a SimilarWeb / Semrush monthly export, or
  • a monthly CSV from whoever owns web analytics.

Then run:
  python scripts/fetch_website_traffic.py --csv <export.csv> --site "<domain>"

Canonical columns:
  month,sessions,users,newUsers,pageviews,avgEngagementTimeSec,bounceRate,conversions
Template: data/templates/website-traffic-template.csv
"""


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").rstrip("%")
    if s == "":
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="monthly canonical CSV export")
    ap.add_argument("--site", default="TBC", help="site/domain label for these rows")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    if not args.csv:
        print(SETUP)
        sys.exit(0)
    if not os.path.exists(args.csv):
        sys.exit(f"✗ CSV not found: {args.csv}")

    with open(OUT, encoding="utf-8") as f:
        doc = json.load(f)

    months = []
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            m = num(row.get("month"))
            if m is None:
                continue
            rec = {"month": int(m), "site": args.site}
            for k in NUM_FIELDS:
                rec[k] = num(row.get(k))
            months.append(rec)

    if not months:
        sys.exit("✗ No month rows parsed — check the header row matches the canonical columns.")

    doc["months"] = months
    doc.setdefault("sites", [])
    if args.site not in doc["sites"]:
        doc["sites"].append(args.site)
    doc["meta"]["status"] = "live"
    doc["meta"]["capturedAt"] = args.date
    doc["meta"]["source"] = f"CSV import ({os.path.basename(args.csv)})"

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"✓ wrote {len(months)} month(s) for {args.site} → {OUT}")


if __name__ == "__main__":
    main()
