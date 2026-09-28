#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build data/appstore-history.json — the rating TREND behind Section A's
12-month rolling view (manager request 2026-09-28: "a trend view, not just the
current value").

Reality: Apple's public endpoints expose only the CURRENT aggregate rating —
there is no public rating history. So we build the trend two ways:

  1. SEED from every weekly snapshot we've already captured
     (data/snapshots/<date>/brand-voice.json → appStore.entries). That gives us
     real points back to the first capture (W35, 2026-08-29).
  2. APPEND a fresh live point today via the iTunes Lookup API (--live).

Each run is idempotent: points are keyed by date and de-duplicated, so re-seeding
never doubles a day. The rolling window fills forward month by month; a true
12-month BACKFILL needs a paid ASO history source (AppFollow / Sensor Tower /
AppTweak) — that's flagged in the file's meta and surfaced on the board.

Usage:
  python scripts/fetch_appstore_history.py            # seed from snapshots
  python scripts/fetch_appstore_history.py --live     # + append today's live point
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.error
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "appstore-history.json")
STORE = "App Store"

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def key(appId, market):
    return f"{appId}::{market}"


def collect_from_snapshots(series):
    manifest = load(os.path.join(DATA, "manifest.json"))
    for snap in manifest.get("snapshots", []):
        d = snap["date"]
        bvp = os.path.join(DATA, "snapshots", d, "brand-voice.json")
        if not os.path.exists(bvp):
            continue
        bv = load(bvp)
        captured = bv.get("appStore", {}).get("capturedAt", d)
        for e in bv.get("appStore", {}).get("entries", []) or []:
            if e.get("rating") is None:
                continue
            k = key(e["appId"], e["market"])
            s = series.setdefault(k, {
                "appId": e["appId"], "app": e.get("app", e["appId"]),
                "market": e["market"], "store": STORE, "points": {},
            })
            # snapshots also carry a prevRating — a free extra (earlier) point,
            # but with no reliable date, so we only take the dated current one.
            s["points"][captured] = {
                "date": captured,
                "rating": round(float(e["rating"]), 3),
                "ratingCount": e.get("ratingCount"),
            }


def lookup(app_id, cc):
    url = f"https://itunes.apple.com/lookup?id={app_id}&country={cc}"
    req = urllib.request.Request(url, headers={"User-Agent": "51Talk-ME-Dashboard/0.1"})
    with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
        res = (json.loads(r.read().decode("utf-8")).get("results") or [])
    if not res:
        return None
    a = res[0]
    rating = a.get("averageUserRating")
    if rating is None:
        return None
    return {"rating": round(float(rating), 3),
            "ratingCount": a.get("userRatingCount")}


def append_live(series, when):
    cfg = load(os.path.join(DATA, "config.json"))
    tracked = cfg["brand"]["apps"]["ios"].get("tracked") or []
    for appcfg in tracked:
        app_id, label = appcfg["appId"], appcfg.get("label", appcfg["appId"])
        for m in cfg["markets"]:
            try:
                info = lookup(app_id, m["storeCountry"])
                if not info:
                    continue
                k = key(app_id, m["code"])
                s = series.setdefault(k, {
                    "appId": app_id, "app": label, "market": m["code"],
                    "store": STORE, "points": {},
                })
                s["points"][when] = {"date": when, **info}
                print(f"✓ live {label} / {m['code']}: {info['rating']} ({info['ratingCount']})")
            except (urllib.error.URLError, KeyError, ValueError) as e:
                print(f"✗ live {label}/{m['code']}: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also append today's live iTunes point")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    series = {}
    collect_from_snapshots(series)
    print(f"seeded {sum(len(s['points']) for s in series.values())} points "
          f"across {len(series)} app×market series from snapshots")
    if args.live:
        append_live(series, args.date)

    out_series = []
    for s in series.values():
        pts = sorted(s["points"].values(), key=lambda p: p["date"])
        out_series.append({**{k: s[k] for k in ("appId", "app", "market", "store")}, "points": pts})
    out_series.sort(key=lambda s: (s["app"], s["market"]))

    doc = {
        "meta": {
            "source": "iTunes Lookup API (current aggregate) + our weekly captures",
            "window": "12-month rolling",
            "capturedAt": args.date,
            "note": ("Apple exposes only the CURRENT aggregate rating — no public "
                     "history. This file accumulates one dated point per capture, so "
                     "the rolling view fills forward from our first snapshot. Full "
                     "12-month backfill needs a paid ASO history source."),
            "backfillBlocked": True,
            "backfillNeeds": "Paid ASO tool (AppFollow / Sensor Tower / AppTweak) for historical ratings",
            "backfillOwner": "Patrick / Omar",
        },
        "series": out_series,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"✓ wrote {OUT} — {len(out_series)} series")


if __name__ == "__main__":
    main()
