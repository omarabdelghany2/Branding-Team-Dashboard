"""Shared video-view statistics for the owned-social collectors.

Why this exists: fetch_social_public.py (RSS, 15 videos) and fetch_youtube.py
(Data API, 10 videos) both wrote `avgVideoViews` for the SAME channel and
disagreed 24,968 vs 1,096 — whichever ran last silently won. Two causes:

  1. Different sample windows (15 vs 10 most-recent uploads).
  2. The mean is hijacked by one viral video. On 2026-09-22 the 15-video
     window held a 355,574-view outlier, 61x the next highest; the medians
     of both windows were identical at 1,460.

Brief §3B is explicit: 不得用单条爆款代表平均水平 — a single hit must not
stand in for the average. So every collector now uses ONE window (WINDOW)
and reports mean, median, sample size and max together, flagging the sample
when an outlier dominates. The board can then show a defensible number and
the evidence next to it.

The window/method is still pending formal sign-off from Patrick/Fei
(config.definitions.tiktokAvgViews) — WINDOW is the proposal, not the ruling.
"""

WINDOW = 10          # most-recent uploads sampled, shared by all collectors
OUTLIER_RATIO = 5    # max > this x median ⇒ the sample is outlier-dominated


def view_stats(views, window=WINDOW):
    """views: view counts, NEWEST FIRST. Returns a dict of comparable stats.

    Returns None-filled stats (never zeros) when there is nothing to measure,
    so a gap stays a gap rather than becoming a fabricated 0.
    """
    sample = [int(v) for v in (views or [])[:window]]
    if not sample:
        return {
            "avgVideoViews": None, "medianVideoViews": None,
            "viewsSampleSize": 0, "viewsMax": None,
            "viewsOutlierFlag": False, "viewsMethod": _method(window),
        }

    ordered = sorted(sample)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else round((ordered[n // 2 - 1] + ordered[n // 2]) / 2)
    mean = round(sum(ordered) / n)
    top = ordered[-1]

    return {
        "avgVideoViews": mean,
        "medianVideoViews": median,
        "viewsSampleSize": n,
        "viewsMax": top,
        # median 0 with a non-zero max is still outlier-dominated
        "viewsOutlierFlag": bool(top > OUTLIER_RATIO * median) if median else bool(top),
        "viewsMethod": _method(window),
    }


def _method(window):
    return f"mean+median of the {window} most recent uploads (excl. live); relative to capture date"


def note(stats):
    """One-line provenance string for the snapshot's `notes` field."""
    if not stats or not stats.get("viewsSampleSize"):
        return "video views: no sample available"
    base = (f"views n={stats['viewsSampleSize']}, median {stats['medianVideoViews']:,}, "
            f"mean {stats['avgVideoViews']:,}")
    if stats.get("viewsOutlierFlag"):
        base += (f" — OUTLIER-DOMINATED (max {stats['viewsMax']:,}); "
                 f"report the median, not the mean")
    return base
