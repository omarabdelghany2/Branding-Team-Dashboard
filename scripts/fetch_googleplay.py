#!/usr/bin/env python3
"""
Fetch Google Play ratings + recent reviews for EACH tracked 51Talk app, per market.
This is what fills the KSA/UAE sentiment gap the Apple public feed can't cover.

Requires:  pip install --user google-play-scraper
Apps come from config.json → brand.apps.android.tracked (list of {packageName,label}).

IMPORTANT CAVEAT (recorded in config): Google Play's aggregate rating & rating COUNT
are largely GLOBAL, not per-storefront. So per-market GP rating comparison is weak —
GP's real value here is per-country/lang REVIEWS (sentiment). We still record the
score but flag it.

Writes (MERGED by store — only Google Play rows replaced, App Store rows kept):
  reviews.json → storeRatings + representativeReviews for store "Google Play"

Usage:
  python3 scripts/fetch_googleplay.py --date 2026-09-03
"""
import argparse, json, os, sys
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
STORE = "Google Play"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    try:
        from google_play_scraper import app as gp_app, reviews as gp_reviews, Sort
    except ImportError:
        sys.exit("✗ google-play-scraper not installed. Run: pip install --user google-play-scraper")

    cfg = load(os.path.join(DATA, "config.json"))
    tracked = cfg["brand"]["apps"]["android"].get("tracked") or []
    if not tracked:
        sys.exit("✗ No Android packages in config.json (brand.apps.android.tracked). (待确认)")

    snap = os.path.join(DATA, "snapshots", args.date)
    rv = load(os.path.join(snap, "reviews.json"))

    rating_entries, rep_by_market, gaps = [], {}, []
    for appcfg in tracked:
        pkg, label = appcfg["packageName"], appcfg.get("label", appcfg["packageName"])
        for m in cfg["markets"]:
            cc = m["storeCountry"]
            try:
                a = gp_app(pkg, lang="ar", country=cc)
                rating_entries.append({
                    "market": m["code"], "store": STORE, "app": label, "packageName": pkg,
                    "rating": round(a.get("score"), 2) if a.get("score") else None,
                    "ratingCount": a.get("ratings"), "ratingCountNote": "Google Play count is global",
                    "prevRating": None, "prevRatingCount": None,
                    "oneTwoStarShare": None, "newReviews": None, "spikeWindow": None,
                })
                revs, _ = gp_reviews(pkg, lang="ar", country=cc, sort=Sort.NEWEST, count=5)
                for r in revs:
                    content = (r.get("content") or "").strip()
                    if len(content) < 15:  # drop trivial noise
                        continue
                    score = r.get("score") or 0
                    sent = "negative" if score <= 2 else ("positive" if score >= 4 else "neutral")
                    rep_by_market.setdefault(m["code"], []).append({
                        "quote": (r.get("content") or "")[:400],
                        "link": f"https://play.google.com/store/apps/details?id={pkg}&gl={cc}",
                        "language": None, "market": m["code"], "store": STORE, "app": label,
                        "date": str(r.get("at"))[:10], "sentiment": sent, "evidenceStrength": "single review",
                    })
                print(f"✓ {label} / {m['code']}: score {rating_entries[-1]['rating']} , {len(revs)} reviews")
            except Exception as e:
                gaps.append(f"{label}/{m['code']}"); print(f"✗ {label}/{m['code']}: {type(e).__name__} {e}", file=sys.stderr)

    # GP's country param barely segments reviews (same 'newest' review repeats across
    # markets), so DEDUPE by quote while round-robining across markets. Up to 3 distinct.
    balanced, seen = [], set()
    while len(balanced) < 3 and any(rep_by_market.values()):
        progressed = False
        for mk in list(rep_by_market):
            while rep_by_market[mk]:
                r = rep_by_market[mk].pop(0)
                key = (r["quote"] or "").strip()
                if key and key not in seen:
                    seen.add(key); balanced.append(r); progressed = True
                    break
            if len(balanced) >= 3:
                break
        if not progressed:
            break

    rv["storeRatings"]["entries"] = [e for e in rv["storeRatings"].get("entries", []) if e.get("store") != STORE] + rating_entries
    rv["representativeReviews"]["entries"] = [e for e in rv["representativeReviews"].get("entries", []) if e.get("store") != STORE] + balanced
    save(os.path.join(snap, "reviews.json"), rv)
    print(f"\nSaved. Apps×markets ok: {len(rating_entries)}. Gaps: {gaps or 'none'}. GP reviews kept: {len(balanced)}.")


if __name__ == "__main__":
    main()
