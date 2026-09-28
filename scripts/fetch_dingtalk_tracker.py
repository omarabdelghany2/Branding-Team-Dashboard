#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pull the team's owned-social monthly numbers from the DingTalk sheet
"5.2 Yearly Target Tracker" and write them to data/social-tracker.json.

This is the "rely on their numbers" path (manager, 2026-09-28): Section B of the
dashboard reflects the social team's own monthly tracker rather than re-deriving
everything from scrapes. The sheet is the source of truth; this script just
mirrors it into the board, faithfully — blanks stay blank, never zero-filled.

The sheet has one tab per market (KSA, KWT, UAE). Each tab is a fixed monthly
grid (row 3 = month 1 … row 14 = month 12, row 15 = Yearly) with four metric
blocks laid out in fixed columns:

    A            month
    B..I         Followers Increasing : TikTok Instagram Snapchat X YouTube  Total Target %
    J..Q         Leads                : TikTok Instagram Snapchat X YouTube  Total Target %
    R..V         Total Views          : TikTok Instagram Snapchat X YouTube
    W..Y         Ave. TikTok View     : value Target %

We read raw values (not the formatted display), so "8,336" comes back as 8336
and a "85%" cell comes back as the true ratio 0.8496.

Usage:
    python scripts/fetch_dingtalk_tracker.py
    python scripts/fetch_dingtalk_tracker.py --dws ~/.local/bin/dws

Requires: the `dws` CLI, authenticated (`dws auth status`). No Python deps.
"""

import argparse
import io
import json
import os
import subprocess
import sys
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NODE = "P0MALyR8kl4DxXd2TQ7K11jBW3bzYmDO"
SOURCE_URL = f"https://alidocs.dingtalk.com/i/nodes/{NODE}"

# sheetId per market tab (from `dws sheet list`)
MARKET_SHEETS = {
    "KSA": "st-27d7eb08-51245",
    "KWT": "st-27d7eb08-52111",
    "UAE": "st-27d7eb08-52118",
}

CHANNELS = ["tiktok", "instagram", "snapchat", "x", "youtube"]

# 0-based column offsets inside the A:Y read window (A = 0).
COLS = {
    "month": 0,
    "followers": {"channels": [1, 2, 3, 4, 5], "total": 6, "target": 7, "pct": 8},
    "leads":     {"channels": [9, 10, 11, 12, 13], "total": 14, "target": 15, "pct": 16},
    "views":     {"channels": [17, 18, 19, 20, 21]},
    "avgTikTokView": {"value": 22, "target": 23, "pct": 24},
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_PATH = os.path.abspath(os.path.join(DATA_DIR, "social-tracker.json"))


def run_dws(dws, sheet_id):
    """Return a list-of-rows (each a list of raw string values) for A3:Y15."""
    cmd = [
        dws, "sheet", "range", "read",
        "--node", NODE, "--sheet-id", sheet_id,
        "--range", "A3:Y15", "--value-render-option", "raw_value",
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"✗ dws read failed for {sheet_id}:\n{out.stderr or out.stdout}")
    payload = json.loads(out.stdout)
    res = payload.get("result", payload)
    cells = res.get("cells")
    if cells is None:
        raise SystemExit(f"✗ unexpected dws payload for {sheet_id}: {list(res)[:8]}")
    rows = []
    for row in cells:
        rows.append([(c.get("value") if isinstance(c, dict) else c) for c in row])
    return rows


def num(v):
    """Raw cell → int / float / None. Blank stays None (never 0-filled)."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "":
        return None
    try:
        f = float(s)
    except ValueError:
        return s  # keep unexpected text visible rather than dropping it
    return int(f) if f.is_integer() else f


def cell(row, idx):
    return num(row[idx]) if idx < len(row) else None


def block(row, spec, with_total=True):
    ch = {name: cell(row, idx) for name, idx in zip(CHANNELS, spec["channels"])}
    if with_total:
        ch["total"] = cell(row, spec["total"])
        ch["target"] = cell(row, spec["target"])
        ch["pct"] = cell(row, spec["pct"])
    else:
        # Views block has no Total/Target/% column in the sheet — compute a
        # convenience sum so the board can show a channel total, but leave
        # target/pct null (the team doesn't track those for views).
        vals = [v for v in ch.values() if isinstance(v, (int, float))]
        ch["total"] = sum(vals) if vals else None
        ch["target"] = None
        ch["pct"] = None
    return ch


def parse_market(rows):
    months = []
    yearly = None
    for row in rows:
        label = row[COLS["month"]] if row else None
        label_s = str(label).strip() if label is not None else ""
        rec = {
            "followers": block(row, COLS["followers"]),
            "leads": block(row, COLS["leads"]),
            "views": block(row, COLS["views"], with_total=False),
            "avgTikTokView": {
                "value": cell(row, COLS["avgTikTokView"]["value"]),
                "target": cell(row, COLS["avgTikTokView"]["target"]),
                "pct": cell(row, COLS["avgTikTokView"]["pct"]),
            },
        }
        if label_s.lower().startswith("year"):
            yearly = rec
        elif label_s not in ("", "None"):
            rec = {"month": int(float(label_s)), **rec}
            months.append(rec)
    return months, yearly


def month_has_data(m):
    for metric in ("followers", "leads", "views"):
        for k in CHANNELS:
            v = m[metric].get(k)
            if isinstance(v, (int, float)) and v != 0:
                return True
    v = m["avgTikTokView"].get("value")
    return isinstance(v, (int, float)) and v != 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dws", default=os.path.expanduser("~/.local/bin/dws"))
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="capture date (YYYY-MM-DD); defaults to today")
    args = ap.parse_args()

    markets = {}
    for code, sheet_id in MARKET_SHEETS.items():
        print(f"… reading {code} ({sheet_id})")
        rows = run_dws(args.dws, sheet_id)
        months, yearly = parse_market(rows)
        n = sum(1 for m in months if month_has_data(m))
        markets[code] = {
            "code": code,
            "hasData": n > 0,
            "monthsWithData": n,
            "months": months,
            "yearly": yearly,
        }
        print(f"  ✓ {code}: {len(months)} months, {n} with data")

    doc = {
        "meta": {
            "source": "DingTalk · 5.2 Yearly Target Tracker",
            "sourceUrl": SOURCE_URL,
            "nodeId": NODE,
            "owner": "Social team (maintained in DingTalk) — Norah / Fei",
            "capturedAt": args.date,
            "year": 2026,
            "note": (
                "Owned-social MONTHLY performance vs target, mirrored from the team's "
                "own tracker. 'views' = Total Views per channel (Views block has no "
                "target in the sheet); 'avgTikTokView' = Ave. TikTok View (mean views "
                "per TikTok video) with its own monthly target. pct fields are true "
                "ratios (0.85 = 85%). Blank stays blank — never zero-filled. KWT/UAE "
                "tabs are empty templates: no market-specific accounts exist yet."
            ),
            "channels": CHANNELS,
            "metrics": ["followers", "leads", "views", "avgTikTokView"],
            "metricLabels": {
                "followers": "Followers Increasing",
                "leads": "Leads",
                "views": "Total Views",
                "avgTikTokView": "Ave. TikTok View",
            },
        },
        "markets": markets,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"\n✓ wrote {OUT_PATH}")
    for code, m in markets.items():
        print(f"   {code}: hasData={m['hasData']} monthsWithData={m['monthsWithData']}")


if __name__ == "__main__":
    main()
