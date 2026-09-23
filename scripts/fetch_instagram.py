#!/usr/bin/env python3
"""
Instagram (Business/Creator) metrics via the Meta Graph API → snapshot social.json.
This is the API leg of the hybrid plan for the OWNED IG account(s).

Gets (for an owned IG Business account):
  followers_count, media_count, recent-media likes+comments (engagement),
  account reach/views (insights).  Impressions naming varies by Graph version —
  the script requests a set and keeps whatever the API returns.

Requires (in scripts/secrets.local.json):
  "meta_access_token"        : a (long-lived) token with instagram_basic +
                               instagram_manage_insights + pages_show_list +
                               pages_read_engagement
  "ig_business_account_id"   : the IG Business Account ID (see social-api-setup.txt)

If either is missing the script prints setup guidance and exits (no fabrication).

Usage:
  python3 scripts/fetch_instagram.py --date 2026-09-07
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.parse, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
GRAPH = "https://graph.facebook.com/v21.0"
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


def graph(path, params):
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=25, context=_SSL) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    sec = os.path.join(os.path.dirname(__file__), "secrets.local.json")
    s = load(sec) if os.path.exists(sec) else {}
    token, ig = s.get("meta_access_token"), s.get("ig_business_account_id")
    if not token or not ig:
        sys.exit("✗ Missing meta_access_token / ig_business_account_id in scripts/secrets.local.json.\n"
                 "  See social-api-setup.txt for how to create the Meta app + get the token + IG account id. (NEEDS CREDENTIALS)")

    cfg = load(os.path.join(DATA, "config.json"))
    ig_acc = next((a for a in cfg["socialAccounts"]["accounts"]
                   if a.get("platform", "").lower() == "instagram" and a.get("accountType") == "brand-main"), None)
    if not ig_acc:
        sys.exit("✗ No brand-main Instagram account in config.")

    try:
        prof = graph(ig, {"fields": "followers_count,media_count", "access_token": token})
        followers = prof.get("followers_count")
        # recent media engagement
        media = graph(f"{ig}/media", {"fields": "like_count,comments_count", "limit": 25, "access_token": token})
        items = media.get("data", [])
        likes = sum(m.get("like_count", 0) for m in items)
        comments = sum(m.get("comments_count", 0) for m in items)
        # account insights — request several, keep what returns
        reach = None
        try:
            ins = graph(f"{ig}/insights", {"metric": "reach", "period": "days_28", "access_token": token})
            vals = (ins.get("data") or [{}])[0].get("values") or []
            reach = sum(v.get("value", 0) for v in vals) if vals else None
        except urllib.error.HTTPError:
            pass
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ Graph API error {e.code}: {e.read().decode()[:200]} — check token scopes / IG id.")

    snap = os.path.join(DATA, "snapshots", args.date)
    social = load(os.path.join(snap, "social.json"))
    by_url = {a.get("accountUrl"): a for a in social.get("accounts", [])}
    rec = by_url.get(ig_acc.get("accountUrl"), {
        "country": ig_acc.get("country"), "platform": "Instagram",
        "accountName": ig_acc.get("accountName"), "accountUrl": ig_acc.get("accountUrl"),
        "accountType": ig_acc.get("accountType"),
    })
    rec.update({
        "followers": followers, "posts": prof.get("media_count"),
        "likes": likes, "comments": comments, "reach": reach,
        "engagement": (likes + comments) if items else None,
        "source": "instagram-api",
        "notes": "Meta Graph API; impressions/views naming varies by Graph version",
    })
    by_url[ig_acc.get("accountUrl")] = rec
    social["accounts"] = list(by_url.values())
    save(os.path.join(snap, "social.json"), social)
    print(f"✓ Instagram {ig_acc['accountName']}: followers={followers} posts={prof.get('media_count')} "
          f"likes(25)={likes} comments(25)={comments} reach={reach}")


if __name__ == "__main__":
    main()
