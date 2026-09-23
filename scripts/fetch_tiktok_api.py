#!/usr/bin/env python3
"""
TikTok (owned account) metrics via the TikTok Business/Display API → snapshot social.json.

TikTok requires a TikTok-for-Developers app + OAuth access token (and, for the
Business API analytics, app approval). This is the API leg for the owned TikTok
account, replacing the blocked public scrape.

Requires (in scripts/secrets.local.json):
  "tiktok_access_token"   : OAuth access token for the owned account
  (optional) "tiktok_open_id" / business id depending on the API tier

If the token is missing the script prints setup guidance and exits (no fabrication).
Endpoint/fields differ by API tier — see social-api-setup.txt; wire the exact
fields once the developer app + token exist.

Usage:
  python3 scripts/fetch_tiktok_api.py --date 2026-09-07
"""
import argparse, json, os, ssl, sys, urllib.request, urllib.error
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):  # Windows consoles default to cp1252; keep the ✓/✗ glyphs printable
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.parse_args()

    sec = os.path.join(os.path.dirname(__file__), "secrets.local.json")
    s = load(sec) if os.path.exists(sec) else {}
    if not s.get("tiktok_access_token"):
        sys.exit("✗ Missing tiktok_access_token in scripts/secrets.local.json.\n"
                 "  TikTok needs a TikTok-for-Developers app + OAuth (Business API analytics require app approval).\n"
                 "  See social-api-setup.txt. Until then, use the Hootsuite export for TikTok metrics. (NEEDS CREDENTIALS)")

    # Token present: wire the exact endpoint/fields for your approved API tier here.
    # (Display API: /v2/user/info/ for follower/likes/video counts;
    #  Business API: /v1.3/business/get/ for video_views, reach, engagement, etc.)
    sys.exit("ℹ tiktok_access_token found, but the endpoint/fields must be wired to your approved TikTok API tier.\n"
             "  Tell me which tier was approved (Display vs Business) and I'll complete this fetcher.")


if __name__ == "__main__":
    main()
