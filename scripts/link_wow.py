#!/usr/bin/env python3
"""
Fill week-over-week baselines in a snapshot by comparing to the PREVIOUS snapshot
in the manifest. Run this AFTER the fetchers each week — it sets:
  - Section A App Store  : prevRating / prevRatingCount   (→ ΔRating)
  - Section C storeRatings: prevRating / prevRatingCount   (App Store + Google Play)
  - Section B social      : startFollowers + follower growth (net, WoW)

Baseline week (no previous snapshot) → nothing to link; that's expected.

Usage:
  python3 scripts/link_wow.py --date 2026-09-07
"""
import argparse, json, os
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


def prev_date(date):
    dates = [s["date"] for s in load(os.path.join(DATA, "manifest.json"))["snapshots"]]
    if date not in dates:
        return None
    i = dates.index(date)
    return dates[i - 1] if i > 0 else None


def followers_of(a):
    return a.get("followers") if a.get("followers") is not None else a.get("endFollowers")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    pd = prev_date(args.date)
    if not pd:
        print("No previous snapshot — WoW baselines skipped (baseline week).")
        return
    cur = os.path.join(DATA, "snapshots", args.date)
    prev = os.path.join(DATA, "snapshots", pd)
    print(f"Linking WoW: {args.date}  vs  {pd}")

    # Section A App Store
    bv, pbv = load(f"{cur}/brand-voice.json"), load(f"{prev}/brand-voice.json")
    pmap = {(e.get("market"), e.get("appId")): e for e in pbv["appStore"].get("entries", [])}
    n = 0
    for e in bv["appStore"].get("entries", []):
        p = pmap.get((e.get("market"), e.get("appId")))
        if p:
            e["prevRating"], e["prevRatingCount"] = p.get("rating"), p.get("ratingCount"); n += 1
    save(f"{cur}/brand-voice.json", bv)

    # Section C storeRatings (App Store + Google Play)
    rv, prv = load(f"{cur}/reviews.json"), load(f"{prev}/reviews.json")
    pmap2 = {(e.get("market"), e.get("store"), e.get("app")): e for e in prv["storeRatings"].get("entries", [])}
    m = 0
    for e in rv["storeRatings"].get("entries", []):
        p = pmap2.get((e.get("market"), e.get("store"), e.get("app")))
        if p:
            e["prevRating"], e["prevRatingCount"] = p.get("rating"), p.get("ratingCount"); m += 1
    save(f"{cur}/reviews.json", rv)

    # Section B social followers → growth
    soc, psoc = load(f"{cur}/social.json"), load(f"{prev}/social.json")
    pmap3 = {a.get("accountUrl"): followers_of(a) for a in psoc.get("accounts", [])}
    g = 0
    for a in soc.get("accounts", []):
        pf, cf = pmap3.get(a.get("accountUrl")), followers_of(a)
        if pf is not None and cf is not None:
            a["startFollowers"] = pf
            a["followerGrowth"] = cf - pf
            a["netFollowerGrowth"] = cf - pf
            g += 1
    save(f"{cur}/social.json", soc)

    print(f"  linked: {n} App Store cells, {m} store-rating cells, {g} social accounts.")


if __name__ == "__main__":
    main()
