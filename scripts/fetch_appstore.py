#!/usr/bin/env python3
"""
Fetch iOS App Store ratings + recent reviews for EACH tracked 51Talk app,
per market, using Apple's public endpoints (no key, stdlib only).

  iTunes Lookup:  https://itunes.apple.com/lookup?id=<APP_ID>&country=<cc>
  Customer RSS:   https://itunes.apple.com/<cc>/rss/customerreviews/id=<APP_ID>/sortBy=mostRecent/json

Apps come from data/config.json → brand.apps.ios.tracked  (list of {appId,label}).
Markets come from config.json (storeCountry per market).

Writes:
  - brand-voice.json  → appStore.entries   (Section A, iOS only; overwritten)
  - reviews.json      → storeRatings + representativeReviews for store "App Store"
                        (MERGED: only App Store rows are replaced; Google Play rows kept)

Never invents data: markets/apps that fail are logged and left as gaps.

Usage:
  python3 scripts/fetch_appstore.py --date 2026-09-03
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
STORE = "App Store"

# Robust SSL: some Python installs lack the system cert store; prefer certifi.
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "51Talk-ME-Dashboard/0.1"})
    with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
        return json.loads(r.read().decode("utf-8"))


def lookup(app_id, cc):
    data = get_json(f"https://itunes.apple.com/lookup?id={app_id}&country={cc}")
    res = data.get("results") or []
    if not res:
        return None
    a = res[0]
    return {
        "rating": a.get("averageUserRatingForCurrentVersion") or a.get("averageUserRating"),
        "ratingCount": a.get("userRatingCountForCurrentVersion") or a.get("userRatingCount"),
        "version": a.get("version"),
        "versionDate": (a.get("currentVersionReleaseDate") or "")[:10],
        "rank": None,  # rank not exposed by lookup; gap unless an ASO source is added
    }


def reviews(app_id, cc, limit=5):
    url = f"https://itunes.apple.com/{cc}/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"
    entries = (get_json(url).get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):  # iTunes returns a single object (not a list) when there's 1 review
        entries = [entries]
    out = []
    for e in entries:
        if "im:rating" not in e:
            continue
        c = e.get("content")
        content = (c.get("label") if isinstance(c, dict) else (c if isinstance(c, str) else "") or "").strip()
        if len(content) < 15:  # drop trivial noise ("ok", "iguhh", emojis-only)
            continue
        out.append({
            "quote": content[:400],
            "rating": int(e["im:rating"]["label"]),
            "link": (e.get("link", {}) or {}).get("attributes", {}).get("href"),
            "date": (e.get("updated", {}).get("label") or "")[:10],
        })
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    cfg = load(os.path.join(DATA, "config.json"))
    tracked = cfg["brand"]["apps"]["ios"].get("tracked") or []
    if not tracked:
        sys.exit("✗ No iOS apps in config.json (brand.apps.ios.tracked). (待确认)")

    snap = os.path.join(DATA, "snapshots", args.date)
    bv = load(os.path.join(snap, "brand-voice.json"))
    rv = load(os.path.join(snap, "reviews.json"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    as_entries, rating_entries, rep_by_market, gaps = [], [], {}, []
    for appcfg in tracked:
        app_id, label = appcfg["appId"], appcfg.get("label", appcfg["appId"])
        for m in cfg["markets"]:
            cc = m["storeCountry"]
            try:
                info = lookup(app_id, cc)
                if not info:
                    gaps.append(f"{label}/{m['code']}"); continue
                as_entries.append({"market": m["code"], "app": label, "appId": app_id, **info})
                rating_entries.append({
                    "market": m["code"], "store": STORE, "app": label, "appId": app_id,
                    "rating": info["rating"], "ratingCount": info["ratingCount"],
                    "prevRating": None, "prevRatingCount": None,
                    "oneTwoStarShare": None, "newReviews": None, "spikeWindow": None,
                })
                for rvw in reviews(app_id, cc):
                    sent = "negative" if rvw["rating"] <= 2 else ("positive" if rvw["rating"] >= 4 else "neutral")
                    rep_by_market.setdefault(m["code"], []).append({
                        "quote": rvw["quote"], "link": rvw["link"], "language": None,
                        "market": m["code"], "store": STORE, "app": label, "date": rvw["date"],
                        "sentiment": sent, "evidenceStrength": "single review",
                    })
                print(f"✓ {label} / {m['code']}: rating {info['rating']} ({info['ratingCount']}), v{info['version']}")
            except (urllib.error.URLError, KeyError, ValueError) as e:
                gaps.append(f"{label}/{m['code']}"); print(f"✗ {label}/{m['code']}: {e}", file=sys.stderr)

    # Balanced App Store review sample: round-robin across markets, up to 2
    # (combined with Google Play's ~3, weekly total stays near the brief's 3-5).
    balanced = []
    while len(balanced) < 2 and any(rep_by_market.values()):
        for mk in list(rep_by_market):
            if rep_by_market[mk]:
                balanced.append(rep_by_market[mk].pop(0))
                if len(balanced) >= 2:
                    break

    # Section A (iOS only) — overwrite.
    bv["appStore"]["entries"] = as_entries
    bv["appStore"]["capturedAt"] = now

    # Section C — merge by store: replace only App Store rows, keep Google Play rows.
    rv["storeRatings"]["entries"] = [e for e in rv["storeRatings"].get("entries", []) if e.get("store") != STORE] + rating_entries
    rv["representativeReviews"]["entries"] = [e for e in rv["representativeReviews"].get("entries", []) if e.get("store") != STORE] + balanced

    save(os.path.join(snap, "brand-voice.json"), bv)
    save(os.path.join(snap, "reviews.json"), rv)
    print(f"\nSaved. Apps×markets ok: {len(as_entries)}. Gaps: {gaps or 'none'}. App Store reviews kept: {len(balanced)}.")
    print("Note: rank + 1-2★ share + prev-week deltas need an ASO source / prior snapshot — left as gaps.")


if __name__ == "__main__":
    main()
