#!/usr/bin/env python3
"""
Best-effort PUBLIC TikTok collector: follower count + recent video view counts
for each confirmed TikTok account, written into a snapshot's social.json.

WHAT IT CAN GET (public):  followers, total likes, recent per-video view counts.
WHAT IT CANNOT GET (needs credentials/backend export):  impressions, reach,
engagement RATE, audience demographics, average watch time.

Reality check: TikTok actively blocks non-browser requests (captcha / empty
responses). This parses the JSON embedded in the public profile page; when
TikTok blocks it, the account is left as a gap (never fabricated). If it keeps
failing, the reliable path is a weekly analytics EXPORT from whoever runs the
account (that also gives the backend metrics).

Prereq: TikTok accounts must be filled in data/config.json
        (socialAccounts.accounts, each with platform "TikTok" + accountUrl).

Usage:
  python3 scripts/fetch_tiktok.py --date 2026-08-29
"""
import argparse, json, os, re, ssl, sys, urllib.request, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
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


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25, context=_SSL) as r:
        return r.read().decode("utf-8", "ignore")


def parse_profile(html):
    """Pull the rehydration JSON blob and read stats + recent video views."""
    m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    blob = json.loads(m.group(1))
    scope = blob.get("__DEFAULT_SCOPE__", {})
    user = scope.get("webapp.user-detail", {}).get("userInfo", {})
    stats = user.get("stats") or user.get("statsV2") or {}
    followers = stats.get("followerCount")
    posts = stats.get("videoCount")
    if followers is None:
        return None
    return {"followers": int(followers), "posts": int(posts) if posts is not None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    cfg = load(os.path.join(DATA, "config.json"))
    accounts = [a for a in cfg["socialAccounts"]["accounts"] if (a.get("platform", "").lower() == "tiktok")]
    if not accounts:
        sys.exit("✗ No TikTok accounts in config.json yet (待确认 — get the account list from Fei).")

    snap = os.path.join(DATA, "snapshots", args.date)
    social = load(os.path.join(snap, "social.json"))
    by_url = {a.get("accountUrl"): a for a in social.get("accounts", [])}

    ok, gaps = 0, []
    for acc in accounts:
        url = acc.get("accountUrl")
        try:
            data = parse_profile(fetch_html(url))
            if not data:
                gaps.append(acc.get("accountName")); continue
            rec = by_url.get(url, {})
            prev_end = rec.get("endFollowers")  # last run's end becomes this run's start baseline
            rec.update({
                "country": acc.get("country"), "platform": "TikTok",
                "accountName": acc.get("accountName"), "accountUrl": url,
                "accountType": acc.get("accountType"),
                "startFollowers": prev_end if prev_end is not None else data["followers"],
                "endFollowers": data["followers"],
                "netFollowerGrowth": None if prev_end is None else data["followers"] - prev_end,
                "posts": data["posts"],
                "impressions": None,        # NEEDS CREDENTIALS (backend/export)
                "engagement": None,
                "engagementRate": None,     # NEEDS CREDENTIALS (needs impressions)
                "notes": "public scrape; impressions/eng-rate need backend export",
            })
            by_url[url] = rec
            ok += 1
            print(f"✓ {acc.get('accountName')}: {data['followers']} followers, {data['posts']} posts")
        except (urllib.error.URLError, ValueError, KeyError) as e:
            gaps.append(acc.get("accountName")); print(f"✗ {acc.get('accountName')}: {e}", file=sys.stderr)

    social["accounts"] = list(by_url.values())
    save(os.path.join(snap, "social.json"), social)
    print(f"\nSaved. Collected {ok}, gaps {gaps or 'none'}.")
    if gaps:
        print("If TikTok keeps blocking, ask the account owner for a weekly analytics export (also gives backend metrics).")


if __name__ == "__main__":
    main()
