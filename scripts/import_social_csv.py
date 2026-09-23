#!/usr/bin/env python3
"""
Import a week's owned-social metrics from a canonical CSV into a snapshot's
social.json. This is the HYBRID ingestion point (Norah's Phase-2): whatever the
source — Hootsuite export, Buffer export, YouTube API, or manual — reshape it into
the canonical columns and import it here.

Canonical CSV columns (see data/templates/social-metrics-template.csv):
  platform, account, followers, posts, views, likes, comments, shares,
  impressions, reach, engagement
  (leave a cell BLANK if unknown — stored as a gap, never 0)

Behaviour:
  - Matches each CSV row to a configured account by platform + account name.
  - engagementRate is derived (engagement / impressions) when both are present.
  - followerGrowth is derived vs the previous snapshot's followers for that account.
  - Merges into the snapshot: updates matched accounts, keeps any already-collected
    public data for the rest.

Usage:
  python3 scripts/import_social_csv.py --date 2026-09-07 --csv path/to/week.csv
"""
import argparse, csv, json, os, sys
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
METRICS = ["followers", "posts", "views", "likes", "comments", "shares", "impressions", "reach", "engagement"]


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def num(s):
    s = (s or "").strip().replace(",", "")
    if s == "":
        return None
    try:
        return int(s) if s.isdigit() else round(float(s), 2)
    except ValueError:
        return None


def norm(s):
    return (s or "").strip().lstrip("@").lower()


def prev_followers(cfg_date, url):
    """Followers for this account in the snapshot immediately before cfg_date."""
    manifest = load(os.path.join(DATA, "manifest.json"))["snapshots"]
    dates = [s["date"] for s in manifest]
    if cfg_date not in dates:
        return None
    idx = dates.index(cfg_date)
    for d in reversed(dates[:idx]):
        social = load(os.path.join(DATA, "snapshots", d, "social.json"))
        for a in social.get("accounts", []):
            if a.get("accountUrl") == url:
                f = a.get("followers", a.get("endFollowers"))
                if f is not None:
                    return f
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--source", default="import (Hootsuite/Buffer/manual)",
                    help="provenance recorded on each imported row, e.g. 'browser-capture'")
    args = ap.parse_args()

    cfg = load(os.path.join(DATA, "config.json"))
    # index configured accounts by (platform, normalized name)
    by_key = {}
    for a in cfg["socialAccounts"]["accounts"]:
        by_key[(a.get("platform", "").lower(), norm(a.get("accountName")))] = a

    snap = os.path.join(DATA, "snapshots", args.date)
    if not os.path.isdir(snap):
        sys.exit(f"✗ Snapshot {args.date} not found. Run scripts/new_week.py first.")
    social = load(os.path.join(snap, "social.json"))
    existing = {a.get("accountUrl"): a for a in social.get("accounts", [])}

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    updated, unmatched = 0, []
    for r in rows:
        plat = (r.get("platform") or "").strip()
        acct = (r.get("account") or "").strip()
        cfg_acc = by_key.get((plat.lower(), norm(acct)))
        if not cfg_acc:
            unmatched.append(f"{plat}/{acct}"); continue
        url = cfg_acc.get("accountUrl")
        rec = existing.get(url, {
            "country": cfg_acc.get("country"), "platform": cfg_acc.get("platform"),
            "accountName": cfg_acc.get("accountName"), "accountUrl": url,
            "accountType": cfg_acc.get("accountType"),
        })
        vals = {m: num(r.get(m)) for m in METRICS}
        if all(v is None for v in vals.values()):
            continue  # blank row — skip, don't wipe existing
        rec.update({k: v for k, v in vals.items()})
        # derived
        imp, eng = vals.get("impressions"), vals.get("engagement")
        rec["engagementRate"] = round(eng / imp * 100, 2) if (imp and eng) else rec.get("engagementRate")
        pf = prev_followers(args.date, url)
        rec["followerGrowth"] = (vals["followers"] - pf) if (vals.get("followers") is not None and pf is not None) else None
        rec["source"] = args.source
        existing[url] = rec
        updated += 1
        print(f"✓ {plat}/{acct}: followers={vals.get('followers')} impressions={vals.get('impressions')} engagement={vals.get('engagement')}")

    social["accounts"] = list(existing.values())
    social["status"] = f"imported {updated} account(s) from CSV on {args.date}"
    save(os.path.join(snap, "social.json"), social)
    print(f"\nSaved {updated} account(s) to {args.date}. Unmatched rows: {unmatched or 'none'}.")
    if unmatched:
        print("  (Unmatched = platform+account not found in config.socialAccounts.accounts — check spelling/handle.)")


if __name__ == "__main__":
    main()
