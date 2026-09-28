# Brand Weekly Monitoring Dashboard

**Live:** https://omarabdelghany2.github.io/Branding-Team-Dashboard/

A weekly brand-health board for the Middle East markets (Saudi Arabia, Kuwait,
UAE): search interest, owned social channels, and app-store ratings & reviews,
captured as a dated snapshot each week so changes are visible over time.

Static site — no framework, no bundler, no server.

## Run locally

Browsers block `fetch()` over `file://`, so serve the folder:

```bash
python -m http.server 8000
# open http://localhost:8000
```

## How the data is organised

```
index.html            # the board
assets/               # css + vanilla-JS app (no dependencies)
data/
  config.json         # markets, keywords, tracked apps, accounts, rules
  manifest.json       # ordered snapshot list; the app reads the latest + last 4
  snapshots/<date>/
    meta.json         # collection period, capture date, data-quality log
    report.json       # conclusions, change explanation, risks
    brand-voice.json  # search interest + app-store presence
    social.json       # one record per owned account
    reviews.json      # store ratings + representative reviews
scripts/              # collection scripts (stdlib + a few optional deps)
```

## Design rules

These are enforced in the data and the rendering, not just documented:

- **Never fabricate.** A missing value is rendered as a `待确认 / TBC` gap, never
  as a zero or a guess. Collectors exit with setup guidance rather than writing
  placeholder numbers.
- **Search interest is a RELATIVE index**, never absolute volume, and it is not
  comparable across snapshots — the provider re-normalises per request.
- **Never sum across incompatible scopes.** Follower counts are stock values
  aggregated per account; posts/likes/impressions are per-period flows. The
  monthly rollup treats them differently on purpose.
- **Averages are reported with a median beside them**, plus sample size and max,
  so a single viral item cannot masquerade as typical performance.
- **Rounded sources are labelled.** Public profiles often round follower counts;
  each account records `followersPrecision`, and growth below that granularity
  is not reported as real movement.

## Weekly update

```bash
python scripts/new_week.py --date <mon> --week <ISO> --start <sun> --end <sat>
# ... run the collectors ...
python scripts/link_wow.py --date <mon>     # ALWAYS LAST — fills prev-week baselines

git add data/ && git commit -m "W<nn> data" && git push
```

## Deployment

Deployed to **GitHub Pages** by `.github/workflows/deploy.yml`; every push to
`main` rebuilds and redeploys in about a minute.

`build.sh` assembles `./public` from **only** `index.html`, `assets/` and
`data/`, so the collection scripts and any local notes are never served.
`robots.txt` and `X-Robots-Tag: noindex` keep the board out of search results.

The workflow also refuses to publish if any credential-shaped file or `.py`
script ends up in `public/`, so a mistake in `build.sh` cannot leak through the
deploy.

`render.yaml` is kept in the repo so the site can be moved to Render instead
without reconfiguring anything.

`data/*` is served `no-cache` and the app cache-busts its own fetches, so a
push appears on the live board immediately.

### Troubleshooting a push that doesn't show

1. Check the Render deploy log — a failed build leaves the previous version up.
2. Confirm the new snapshot is listed in `data/manifest.json`; the app reads the
   manifest, not the folder listing.
3. Check the browser console — a 404 on a snapshot file means it wasn't committed.

## Note on credentials

`.gitignore` excludes credential-shaped files, and `.git/hooks/pre-commit`
blocks commits containing them. **Hooks are not copied by `git clone`** — 
reinstall it on any new machine.

---

## Working on another machine

```bash
git clone https://github.com/omarabdelghany2/Branding-Team-Dashboard.git
cd Branding-Team-Dashboard

# 1. Enable the credential-blocking pre-commit hook.
#    Git does NOT enable hooks from a clone automatically — this one line
#    points git at the tracked .githooks/ directory. Do it once per machine.
git config core.hooksPath .githooks

# 2. Install the two optional collector dependencies (everything else is stdlib).
pip install -r requirements.txt

# 3. Serve the board locally.
python -m http.server 8000     # → http://localhost:8000
```

### Verify the hook is active

```bash
git config core.hooksPath        # must print: .githooks
```

If that prints nothing, the hook is **not** running and credential files are
protected only by `.gitignore`.

### API keys

`scripts/secrets.local.json` is deliberately not in this repository. Copy
`scripts/secrets.local.json.example` to `scripts/secrets.local.json` and fill in
what you have. Without it, `fetch_youtube.py`, `fetch_instagram.py` and
`fetch_tiktok_api.py` exit with setup instructions rather than writing fake data;
every other collector runs fine without any key.

### Python version

Use Python 3.12 where possible — `pytrends` pulls in `pandas`, which has the
widest wheel coverage there. All scripts force UTF-8 output, so the ✓/✗ glyphs
work on a Windows console (cp1252) without crashing.
