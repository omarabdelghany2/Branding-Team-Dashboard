#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse a GA4 "Reports snapshot" CSV export into data/website-traffic.json
(Section D · Website traffic).

GA4's Reports-snapshot export is a multi-section CSV: a summary block, top pages,
acquisition (source/medium), a daily new-vs-returning time-series ("Nth day"),
platform, and city-level geography. This reads the sections we care about and
shapes them for the board:

  - summary   : active users / new users / avg engagement / events (whole period)
  - monthly   : the daily series aggregated to calendar months (the TREND)
  - channels  : top session source / medium
  - topPages  : top pages by views
  - meMarkets : KSA / KWT / UAE broken out by known city (APPROXIMATE — GA4's
                snapshot has city, not country, so only mapped cities are counted)

IMPORTANT scope note carried into the file: this export is the GLOBAL 51talk.com
site, not an ME-filtered view. The ME breakdown is by city and approximate. A
precise per-market view needs a GA4 export filtered to each country.

Usage:
  python scripts/fetch_ga4_snapshot.py --csv ~/Downloads/Reports_snapshot.csv
  python scripts/fetch_ga4_snapshot.py --csv <file> --date 2026-10-04
"""
import argparse, csv, io, json, os, sys
from datetime import date, timedelta
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "website-traffic.json")

# City → market. Only the well-known ME cities; everything else is left out of the
# ME rollup (labelled approximate). Lowercased match.
KSA = {"riyadh", "jeddah", "jiddah", "dammam", "mecca", "makkah", "medina", "madinah",
       "al khobar", "khobar", "tabuk", "buraydah", "buraidah", "khamis mushait", "abha",
       "hail", "najran", "jubail", "yanbu", "taif", "al hofuf", "hofuf", "qatif",
       "al qatif", "ta'if", "unaizah", "sakaka", "arar", "jizan", "al bahah"}
UAE = {"dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "ras al-khaimah",
       "fujairah", "al ain", "umm al quwain", "khor fakkan"}
KWT = {"kuwait city", "hawalli", "as salimiyah", "salmiya", "al ahmadi", "al farwaniyah",
       "al jahra", "sabah as salim", "mangaf", "fahaheel"}
MARKET_OF = {}
for s, code in ((KSA, "KSA"), (UAE, "UAE"), (KWT, "KWT")):
    for c in s:
        MARKET_OF[c] = code


def split_sections(path):
    """Return {header_line: [row, ...]} splitting the multi-block GA4 CSV.
    A section starts at a non-# line whose first cell is non-numeric (a dimension
    header) and runs until the next blank/# line."""
    rows = list(csv.reader(io.open(path, encoding="utf-8-sig")))
    sections, i = {}, 0
    while i < len(rows):
        r = rows[i]
        cell0 = (r[0] if r else "").strip()
        is_comment = cell0.startswith("#")
        is_header = bool(cell0) and not is_comment and not _isnum(cell0)
        if is_header:
            hdr = ",".join(r)
            data = []
            j = i + 1
            while j < len(rows) and rows[j] and not rows[j][0].strip().startswith("#"):
                data.append(rows[j]); j += 1
            sections[hdr] = data
            i = j
        else:
            i += 1
    return sections


def _isnum(s):
    try:
        float(s.replace(",", "")); return True
    except ValueError:
        return False


def num(s):
    s = (s or "").strip().replace(",", "")
    if s == "":
        return None
    try:
        f = float(s); return int(f) if f.is_integer() else f
    except ValueError:
        return None


def find(sections, prefix):
    for hdr, data in sections.items():
        if hdr.startswith(prefix):
            return hdr, data
    return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--period-start", default="2026-01-01",
                    help="first day of the export (day 0 of the Nth-day series)")
    ap.add_argument("--period-end", default="2026-10-03")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    if not os.path.exists(args.csv):
        sys.exit(f"✗ not found: {args.csv}")

    sec = split_sections(args.csv)

    # --- summary ---
    _, s = find(sec, "Active users,New users")
    summary = None
    if s:
        r = s[0]
        summary = {"activeUsers": num(r[0]), "newUsers": num(r[1]),
                   "avgEngagementSec": round(num(r[2]) or 0, 1), "eventCount": num(r[3])}

    # --- monthly trend from "Nth day,new,returning" ---
    _, nd = find(sec, "Nth day,new,returning")
    start = date.fromisoformat(args.period_start)
    buckets = {}
    for r in nd:
        if len(r) < 3:
            continue
        n = num(r[0])
        if n is None:
            continue
        d = start + timedelta(days=int(n))
        key = d.strftime("%Y-%m")
        b = buckets.setdefault(key, {"month": key, "newUsers": 0, "returningUsers": 0})
        b["newUsers"] += int(num(r[1]) or 0)
        b["returningUsers"] += int(num(r[2]) or 0)
    monthly = []
    for key in sorted(buckets):
        b = buckets[key]
        b["activeUsers"] = b["newUsers"] + b["returningUsers"]
        monthly.append(b)

    # --- channels: Session source / medium ---
    _, ss = find(sec, "Session source / medium,Sessions")
    channels = [{"source": r[0], "sessions": num(r[1])} for r in ss if len(r) >= 2][:args.top]

    # --- top pages ---
    _, pg = find(sec, "Page title and screen class,Views")
    topPages = [{"page": r[0], "views": num(r[1]), "activeUsers": num(r[2]),
                 "bounceRate": round(num(r[4]) or 0, 3)} for r in pg if len(r) >= 5][:args.top]

    # --- ME markets by city (approximate) ---
    _, ct = find(sec, "City,Active users")
    me = {"KSA": {"market": "KSA", "activeUsers": 0, "cities": []},
          "UAE": {"market": "UAE", "activeUsers": 0, "cities": []},
          "KWT": {"market": "KWT", "activeUsers": 0, "cities": []}}
    for r in ct:
        if len(r) < 2:
            continue
        code = MARKET_OF.get(r[0].strip().lower())
        if code:
            v = int(num(r[1]) or 0)
            me[code]["activeUsers"] += v
            me[code]["cities"].append({"city": r[0], "activeUsers": v})
    meMarkets = [me[c] for c in ("KSA", "UAE", "KWT")]
    for m in meMarkets:
        m["cities"] = sorted(m["cities"], key=lambda x: -x["activeUsers"])[:6]

    doc = {
        "meta": {
            "section": "D. Website traffic / 官网流量",
            "status": "live",
            "source": "GA4 · Reports snapshot export",
            "property": "51Talk Website (GA4 property 304476779)",
            "scope": "GLOBAL site (51talk.com). ME markets below are broken out by CITY and are APPROXIMATE — a precise per-market view needs a GA4 export filtered to KSA/KWT/UAE.",
            "period": {"start": args.period_start, "end": args.period_end},
            "capturedAt": args.date,
            "note": "Whole-period aggregates + a monthly trend built from GA4's daily new/returning series. Channels = session source/medium. Never fabricated — only what the export contains.",
            "metrics": ["activeUsers", "newUsers", "returningUsers"],
        },
        "summary": summary,
        "monthly": monthly,
        "channels": channels,
        "meMarkets": meMarkets,
        "topPages": topPages,
        "sites": ["51talk.com (global)"],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2); f.write("\n")

    print(f"✓ wrote {OUT}")
    if summary:
        print(f"  summary: {summary['activeUsers']:,} active · {summary['newUsers']:,} new · "
              f"{summary['avgEngagementSec']}s avg · {summary['eventCount']:,} events")
    print(f"  monthly points: {len(monthly)}  ({monthly[0]['month']}→{monthly[-1]['month']})" if monthly else "  monthly: none")
    print(f"  channels: {len(channels)} · top pages: {len(topPages)}")
    for m in meMarkets:
        print(f"  {m['market']}: {m['activeUsers']:,} active users (top city: {m['cities'][0]['city'] if m['cities'] else '—'})")


if __name__ == "__main__":
    main()
