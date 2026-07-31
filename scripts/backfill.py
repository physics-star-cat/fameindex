#!/usr/bin/env python3
"""
backfill.py — reconstruct past quarters of the Fame Index.

The site last updated at 2026-W13 and now publishes quarterly. This rebuilds the
missing quarters from sources that can genuinely report on a past period.

WHAT IS AND IS NOT RECONSTRUCTED

Five sources are excluded because they cannot report historically — Reddit,
YouTube, Google News, Spotify and TMDB all return *current* values whatever period
you ask for. Including them would stamp today's numbers across every backfilled
quarter: a flat line in the data, and rankings skewed by it. See
server/data/pipeline.py:_fetch_all_dimensions.

Backfilled quarters therefore rest on Wikipedia pageviews, Google Trends, GDELT,
wiki edit velocity and Wikidata recognition. The scoring engine re-normalises
dimension weights over whatever signals are present, so these weeks stay
comparable to live ones (see server/scoring/engine.py).

USAGE

    python scripts/backfill.py                    # every missing quarter up to last complete
    python scripts/backfill.py --from 2026-Q1 --to 2026-Q2
    python scripts/backfill.py --dry-run          # show the plan, fetch nothing
    python scripts/backfill.py --force            # redo weeks already scored

Resumable: quarters that already have scores are skipped unless --force is given,
so an interrupted run can simply be restarted.
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, ".")

from server.data.pipeline import run_pipeline
from server.data.week_utils import (
    date_to_quarter, last_complete_quarter, period_to_dates, previous_quarter,
)
from server.db import init_db
from server.db.queries import get_all_persons, get_all_scored_weeks, store_scores
from server.scoring.engine import score_all

logger = logging.getLogger("backfill")

# Courtesy pause between quarters. Google Trends throttles aggressively and a
# backfill is ~120 lookups per quarter against it.
DELAY_BETWEEN_QUARTERS = 5.0


def quarters_between(start: str, end: str) -> list[str]:
    """Every quarter from start to end inclusive."""
    out, cur = [], start
    # Walk backwards from end so the ordering logic stays trivial
    seen = []
    q = end
    while True:
        seen.append(q)
        if q == start:
            break
        prev = previous_quarter(q)
        if period_to_dates(prev)[0] < period_to_dates(start)[0]:
            break
        q = prev
    return list(reversed(seen))


def backfill_period(week: str, persons: list[dict]) -> dict:
    """Reconstruct a single period. Returns a summary dict."""
    logger.info("--- %s", week)

    result = run_pipeline(week, persons=persons, historical_only=True)
    logger.info("    signals: %d  errors: %d",
                result["signals_collected"], len(result["errors"]))

    scores = score_all(week)
    store_scores(scores)
    logger.info("    scored: %d persons", len(scores))

    return {
        "week": week,
        "signals": result["signals_collected"],
        "errors": len(result["errors"]),
        "scored": len(scores),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill past Fame Index quarters.")
    ap.add_argument("--from", dest="start", help="First quarter, e.g. 2026-Q1")
    ap.add_argument("--to", dest="end", help="Last quarter, e.g. 2026-Q2")
    ap.add_argument("--dry-run", action="store_true", help="Show the plan, fetch nothing")
    ap.add_argument("--force", action="store_true", help="Redo quarters that already have scores")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    init_db()
    done = set(get_all_scored_weeks())

    end = args.end or last_complete_quarter()
    if args.start:
        start = args.start
    elif done:
        # Resume from the quarter after the latest already scored
        quarters_done = [d for d in done if "-Q" in d]
        if quarters_done:
            latest = max(quarters_done)
            start = date_to_quarter(period_to_dates(latest)[1] + timedelta(days=1))
        else:
            start = "2026-Q1"
    else:
        print("No existing scores and no --from given; nothing to infer from.")
        return 1

    planned = quarters_between(start, end)
    todo = planned if args.force else [w for w in planned if w not in done]

    print(f"Already scored : {len(done)} quarter(s) — {', '.join(sorted(done))}")
    print(f"Range          : {start} .. {end}  ({len(planned)} quarters)")
    print(f"To reconstruct : {len(todo)} quarter(s)")
    if not todo:
        print("Nothing to do.")
        return 0
    print(f"                 {', '.join(todo)}")

    if args.dry_run:
        print("\n--dry-run: stopping before any network calls.")
        return 0

    persons = [
        {"id": p.id, "name": p.name, "wikipedia_title": p.wikipedia_title,
         "spotify_id": p.spotify_id, "tmdb_id": p.tmdb_id}
        for p in get_all_persons()
    ]
    print(f"Persons        : {len(persons)}\n")

    summaries, failed = [], []
    for i, week in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {week}")
        try:
            summaries.append(backfill_period(week, persons))
        except Exception as e:
            # One bad quarter must not lose the ones already reconstructed.
            logger.error("    FAILED: %s", e)
            failed.append((week, str(e)))
        if i < len(todo):
            time.sleep(DELAY_BETWEEN_QUARTERS)

    print("\n=== Backfill summary ===")
    for s in summaries:
        print(f"  {s['week']}  signals={s['signals']:>5}  scored={s['scored']:>4}  errors={s['errors']}")
    if failed:
        print(f"\n  {len(failed)} quarter(s) FAILED — rerun to retry, completed quarters are skipped:")
        for w, e in failed:
            print(f"    {w}: {e[:100]}")
        return 1
    print(f"\n  {len(summaries)} quarter(s) reconstructed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
