#!/usr/bin/env python3
"""
Best-effort PUBLIC social collector — grabs whatever follower/subscriber counts
(and YouTube recent video views) are visible WITHOUT any credentials, for every
account in config.socialAccounts.accounts, and writes them into the snapshot's
social.json.

Reality (verified 2026-09-03):
  WORKS no-login:  YouTube subscribers (rounded, e.g. "2.08K"), YouTube recent
                   video views (RSS), Snapchat subscribers, Pinterest followers.
  BLOCKED no-login: TikTok, Instagram, X, Threads, Facebook → left as gaps
                   (need API key / backend / weekly export — the next stage).

Never fabricates: any account it can't read is written with null metrics + a note.
For deep metrics (impressions, reach, engagement rate) see the credentialed path.

Usage:
  python3 scripts/fetch_social_public.py --date 2026-09-03
"""
import argparse, json, os, re, ssl, sys, urllib.request, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

from _viewstats import view_stats

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


def get(url, extra=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
        return r.read().decode("utf-8", "ignore")


def to_int(s):
    s = s.strip().replace(",", "")
    mult = 1
    if s and s[-1] in "KkMmBb":
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[s[-1].lower()]; s = s[:-1]
    return int(float(s) * mult)


def youtube(acc):
    html = get(acc["accountUrl"], {"Cookie": "CONSENT=YES+1"})
    m = re.search(r'"([\d.,]+[KMB]?) subscribers"', html) or re.search(r'([\d.,]+[KMB]?) subscribers', html)
    subs = to_int(m.group(1)) if m else None
    approx = bool(m and re.search(r'[KMB]', m.group(1)))
    stats = view_stats([])
    cid = acc.get("channelId")
    if cid:
        try:
            xml = get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
            # the feed is newest-first; view_stats trims to the shared window so this
            # agrees with fetch_youtube.py instead of averaging a wider, viral-skewed set
            views = [int(v) for v in re.findall(r'views="(\d+)"', xml)]
            stats = view_stats(views)
        except Exception:
            pass
    return {"followers": subs, "approx": approx, **stats}


def snapchat(acc):
    html = get(acc["accountUrl"])
    m = re.search(r'([\d.,]+[KMB]?)\s*[Ss]ubscribers', html) or re.search(r'"subscriberCount":"?(\d+)', html)
    return {"followers": to_int(m.group(1)) if m else None}


def pinterest(acc):
    html = get(acc["accountUrl"])
    m = re.search(r'"follower_count":(\d+)', html)
    return {"followers": int(m.group(1)) if m else None}


def tiktok(acc):
    html = get(acc["accountUrl"])
    m = re.search(r'"followerCount":(\d+)', html)
    return {"followers": int(m.group(1)) if m else None}


def instagram(acc):
    html = get(acc["accountUrl"])
    m = re.search(r'"edge_followed_by":\{"count":(\d+)', html)
    return {"followers": int(m.group(1)) if m else None}


HANDLERS = {"youtube": youtube, "snapchat": snapchat, "pinterest": pinterest,
            "tiktok": tiktok, "instagram": instagram}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    cfg = load(os.path.join(DATA, "config.json"))
    accounts = cfg["socialAccounts"]["accounts"]
    snap = os.path.join(DATA, "snapshots", args.date)
    social = load(os.path.join(snap, "social.json"))
    prev = {a.get("accountUrl"): a for a in social.get("accounts", [])}

    out, got, gaps = [], 0, []
    for acc in accounts:
        rec = {
            "country": acc.get("country"), "platform": acc.get("platform"),
            "accountName": acc.get("accountName"), "accountUrl": acc.get("accountUrl"),
            "accountType": acc.get("accountType"),
            "startFollowers": None, "endFollowers": None, "netFollowerGrowth": None,
            "posts": None, "impressions": None, "engagement": None, "engagementRate": None,
            "notes": "",
        }
        handler = HANDLERS.get((acc.get("platform") or "").lower())
        try:
            data = handler(acc) if handler else {}
            f = data.get("followers")
            if f is not None:
                prev_end = prev.get(acc.get("accountUrl"), {}).get("endFollowers")
                rec["startFollowers"] = prev_end
                rec["endFollowers"] = f
                rec["netFollowerGrowth"] = None if prev_end is None else f - prev_end
                for k in ("avgVideoViews", "medianVideoViews", "viewsSampleSize",
                          "viewsMax", "viewsOutlierFlag", "viewsMethod"):
                    if data.get(k) is not None:
                        rec[k] = data[k]
                rec["notes"] = "public" + (" (approx/rounded)" if data.get("approx") else "") + "; impressions/eng-rate need backend"
                got += 1
                print(f"✓ {acc['platform']}/{acc['accountName']}: {f} followers" +
                      (f", median views {data['medianVideoViews']:,} (n={data['viewsSampleSize']}"
                       + (", OUTLIER" if data.get("viewsOutlierFlag") else "") + ")"
                       if data.get('medianVideoViews') is not None else ""))
            else:
                rec["notes"] = "public metrics not readable — needs API key / backend / export"
                gaps.append(f"{acc['platform']}/{acc['accountName']}")
        except (urllib.error.URLError, ValueError, KeyError, TypeError) as e:
            rec["notes"] = f"blocked ({type(e).__name__}) — needs API key / backend / export"
            gaps.append(f"{acc['platform']}/{acc['accountName']}")
        out.append(rec)

    social["accounts"] = out
    social["status"] = f"public-partial: {got}/{len(accounts)} accounts have public data"
    save(os.path.join(snap, "social.json"), social)
    print(f"\nSaved. Got public data for {got}/{len(accounts)}. Gaps (need access): {len(gaps)}")
    for g in gaps:
        print("   -", g)


if __name__ == "__main__":
    main()
