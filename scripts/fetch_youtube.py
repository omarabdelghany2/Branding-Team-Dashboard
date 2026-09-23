#!/usr/bin/env python3
"""
YouTube collector for owned channels → snapshot social.json.

Preferred path: YouTube Data API v3 (free API key in scripts/secrets.local.json).
  Gets: subscriber count, total channel views, and recent videos' view counts.
Fallback: none automated here — without a key, deep metrics need YouTube Studio.

WHAT THE API KEY GETS (public):  subs, per-video views, likes, comments.
WHAT IT DOES NOT GET (needs YouTube Studio access/export):  impressions,
engagement rate, average view duration.

Prereq:
  1) YouTube accounts in config.json (socialAccounts.accounts, platform "YouTube",
     with accountUrl or a "channelId").
  2) youtube_api_key set in scripts/secrets.local.json (copy from the .example).

Usage:
  python3 scripts/fetch_youtube.py --date 2026-08-29
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.parse, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

from _viewstats import WINDOW, view_stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://www.googleapis.com/youtube/v3"
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


def api_get(path, params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=25, context=_SSL) as r:
        return json.loads(r.read().decode("utf-8"))


def resolve_channel_id(acc, key):
    if acc.get("channelId"):
        return acc["channelId"]
    url = acc.get("accountUrl", "")
    # .../channel/UCxxxx
    if "/channel/" in url:
        return url.rstrip("/").split("/channel/")[-1].split("?")[0]
    # @handle
    handle = None
    if "/@" in url:
        handle = "@" + url.split("/@")[-1].split("/")[0].split("?")[0]
    elif acc.get("accountName", "").startswith("@"):
        handle = acc["accountName"]
    if handle:
        res = api_get("channels", {"part": "id", "forHandle": handle, "key": key})
        items = res.get("items") or []
        if items:
            return items[0]["id"]
    return None


def recent_video_views(uploads_playlist, key, n=WINDOW):
    pl = api_get("playlistItems", {"part": "contentDetails", "playlistId": uploads_playlist, "maxResults": n, "key": key})
    vids = [it["contentDetails"]["videoId"] for it in pl.get("items", [])]
    if not vids:
        return []
    vr = api_get("videos", {"part": "statistics", "id": ",".join(vids), "key": key})
    return [int(v["statistics"].get("viewCount", 0)) for v in vr.get("items", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    sec_path = os.path.join(os.path.dirname(__file__), "secrets.local.json")
    key = None
    if os.path.exists(sec_path):
        key = load(sec_path).get("youtube_api_key")
    if not key:
        sys.exit("✗ No youtube_api_key. Copy scripts/secrets.local.json.example → secrets.local.json and add a free key "
                 "(Google Cloud Console → enable 'YouTube Data API v3' → create API key). NEEDS CREDENTIALS.")

    cfg = load(os.path.join(DATA, "config.json"))
    accounts = [a for a in cfg["socialAccounts"]["accounts"] if a.get("platform", "").lower() == "youtube"]
    if not accounts:
        sys.exit("✗ No YouTube accounts in config.json yet (待确认 — get the list from Fei).")

    snap = os.path.join(DATA, "snapshots", args.date)
    social = load(os.path.join(snap, "social.json"))
    by_url = {a.get("accountUrl"): a for a in social.get("accounts", [])}

    ok, gaps = 0, []
    for acc in accounts:
        try:
            cid = resolve_channel_id(acc, key)
            if not cid:
                gaps.append(acc.get("accountName")); continue
            ch = api_get("channels", {"part": "statistics,contentDetails", "id": cid, "key": key})
            item = (ch.get("items") or [None])[0]
            if not item:
                gaps.append(acc.get("accountName")); continue
            stats = item["statistics"]
            uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
            views = recent_video_views(uploads, key)
            vstats = view_stats(views)
            subs = int(stats.get("subscriberCount", 0))

            rec = by_url.get(acc.get("accountUrl"), {})
            # NOTE: by_url is THIS week's snapshot, so it cannot supply a prior baseline.
            # Leave start/growth null and let scripts/link_wow.py fill them from the
            # PREVIOUS snapshot; guessing here produced a spurious flat 0 in W37.
            rec.update({
                "country": acc.get("country"), "platform": "YouTube",
                "accountName": acc.get("accountName"), "accountUrl": acc.get("accountUrl"),
                "accountType": acc.get("accountType"),
                "startFollowers": None,
                "endFollowers": subs,
                "netFollowerGrowth": None,
                # not uploads-in-period; the API window is a sample. Leave null so the
                # monthly rollup does not sum the sample size as if it were posts.
                "posts": None,
                "impressions": None,      # NEEDS CREDENTIALS (YouTube Studio)
                "engagementRate": None,   # NEEDS CREDENTIALS (YouTube Studio)
                "source": "youtube-api",
                "views": vstats["medianVideoViews"],
                "notes": "API key (exact subs). Report MEDIAN video views; impressions/eng-rate need YouTube Studio",
                **vstats,
            })
            by_url[acc.get("accountUrl")] = rec
            ok += 1
            print(f"✓ {acc.get('accountName')}: {subs} subs, median views "
                  f"{vstats['medianVideoViews']:,} / mean {vstats['avgVideoViews']:,} "
                  f"(n={vstats['viewsSampleSize']}"
                  + (", OUTLIER-DOMINATED" if vstats["viewsOutlierFlag"] else "") + ")")
        except (urllib.error.URLError, KeyError, ValueError) as e:
            gaps.append(acc.get("accountName")); print(f"✗ {acc.get('accountName')}: {e}", file=sys.stderr)

    social["accounts"] = list(by_url.values())
    save(os.path.join(snap, "social.json"), social)
    print(f"\nSaved. Collected {ok}, gaps {gaps or 'none'}.")


if __name__ == "__main__":
    main()
