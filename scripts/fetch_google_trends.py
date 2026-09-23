#!/usr/bin/env python3
"""
Fetch Google Trends RELATIVE interest for 51Talk (+ confirmed competitors) per
market, and write it into a snapshot's brand-voice.json.

Google Trends returns a RELATIVE index (0-100), NOT absolute search volume —
the dashboard labels it as such. Never report it as volume (brief §5).

Requires pytrends:  pip install pytrends
(pytrends is unofficial and can rate-limit / break; on failure the script leaves
 gaps rather than inventing numbers.)

Geo codes: KSA=SA, Kuwait=KW, UAE=AE.

TIMEFRAME (changed 2026-09-22): default is 'today 12-m', which Google returns as
NATIVE WEEKLY points. The old default 'today 3-m' returns DAILY points, and in
low-volume markets almost every day rounds to 0 — Kuwait and UAE looked like flat
zeros when they actually carry sparse, spiky interest. Weekly buckets aggregate
those searches into a visible signal.

KEYWORDS: read from config.json → brand.keywords.trendsKeywords. All of a market's
keywords go in ONE payload, because Trends normalises to 100 WITHIN a request —
that makes the keywords comparable to each other, but never across markets or
across snapshots.

PARTIAL PERIODS: the still-accumulating current week comes back with isPartial=True
and an artificially low value. It is dropped, not reported as a number.

Usage:
  python scripts/fetch_google_trends.py --date 2026-09-22
  python scripts/fetch_google_trends.py --date 2026-09-22 --keyword "51Talk"
"""
import argparse, json, os, sys
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
GEO = {"KSA": "SA", "KWT": "KW", "UAE": "AE"}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def to_weekly(s):
    """Return (series, granularity). Resample only if the data is sub-weekly."""
    if len(s) > 1:
        gap_days = (s.index[1] - s.index[0]).days
        if gap_days < 7:
            return s.resample("W-SAT").mean().round().astype(int), "resampled daily→weekly (Sun–Sat)"
    return s.round().astype(int), "native weekly"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--keyword", default=None,
                    help="override; default = config brand.keywords.trendsKeywords")
    ap.add_argument("--timeframe", default="today 12-m")
    args = ap.parse_args()

    try:
        from pytrends.request import TrendReq
    except ImportError:
        sys.exit("✗ pytrends not installed. Run: pip install pytrends")

    cfg = load(os.path.join(DATA, "config.json"))
    kws = ([args.keyword] if args.keyword
           else cfg["brand"]["keywords"].get("trendsKeywords") or ["51Talk"])
    kws = kws[:5]  # Trends allows at most 5 terms per payload

    snap = os.path.join(DATA, "snapshots", args.date)
    bv = load(os.path.join(snap, "brand-voice.json"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pt = TrendReq(hl="en-US", tz=180)
    entries, gaps = [], []
    for code, geo in GEO.items():
        try:
            pt.build_payload(kws, timeframe=args.timeframe, geo=geo)
            df = pt.interest_over_time()
            if df.empty:
                gaps.append(f"{code}/all"); continue
            if "isPartial" in df.columns:
                df = df[~df["isPartial"].astype(bool)]
            if df.empty:
                gaps.append(f"{code}/partial-only"); continue

            for kw in kws:
                if kw not in df.columns:
                    gaps.append(f"{code}/{kw}"); continue
                weekly, gran = to_weekly(df[kw])
                if weekly.empty or int(weekly.max()) == 0:
                    gaps.append(f"{code}/{kw}")
                    print(f"✗ {code}/{kw}: no measurable interest (all weeks 0 — below Trends' "
                          f"reporting threshold, NOT proof of zero searches)", file=sys.stderr)
                    continue
                series = [{"date": d.strftime("%Y-%m-%d"), "value": int(v)} for d, v in weekly.items()]
                cur = series[-1]["value"]
                prev = series[-2]["value"] if len(series) > 1 else None
                peak = max(series, key=lambda x: x["value"])["date"]
                entries.append({
                    "market": code, "keyword": kw,
                    "current": cur, "prevWeek": prev, "yoy": None,
                    "peakDate": peak, "series": series[-4:],
                    "seriesGranularity": gran,
                    "timeframe": args.timeframe,
                    "weeksAvailable": len(series),
                    "comparableWith": [k for k in kws if k != kw],
                })
                print(f"✓ {code}/{kw}: current {cur} (prev {prev}), peak {peak} [{len(series)} weeks, {gran}]")
        except Exception as e:  # pytrends throws many things; do not fabricate on failure
            gaps.append(f"{code}/*"); print(f"✗ {code}: {e}", file=sys.stderr)

    bv["googleTrends"]["entries"] = entries
    bv["googleTrends"]["capturedAt"] = now
    bv["googleTrends"]["keyword"] = ", ".join(kws)
    bv["googleTrends"]["keywords"] = kws
    bv["googleTrends"]["timeframe"] = args.timeframe
    bv["googleTrends"]["note"] = (
        "RELATIVE index 0–100, never absolute volume. Keywords are fetched in ONE payload per "
        "market, so they are comparable TO EACH OTHER within a market — but NOT across markets "
        "and NOT across snapshots (Trends re-normalises every request). Partial weeks dropped.")
    save(os.path.join(snap, "brand-voice.json"), bv)
    print(f"\nSaved {len(entries)} entr(y/ies). Gaps: {gaps or 'none'}. Index is RELATIVE, not volume.")


if __name__ == "__main__":
    main()
