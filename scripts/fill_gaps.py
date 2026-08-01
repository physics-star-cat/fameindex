#!/usr/bin/env python3
"""
fill_gaps.py — retry only the signals a run failed to collect.

Sources fail intermittently: Wikidata's SPARQL endpoint times out, Wikimedia
throttles a burst. A handful of gaps in an otherwise good run should not mean
re-fetching everything, and it must not mean publishing with them.

Gaps matter more than they look. Dimension weights are re-normalised over the
dimensions a person actually has, so if five people are missing their
institutional signal they are ranked under different weightings from the other
116 — in the same table, presented as one league.

    python scripts/fill_gaps.py 2026-Q1 2026-Q2
    python scripts/fill_gaps.py --dry-run 2026-Q2
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from server.data.normalize import normalize_batch
from server.db import init_db
from server.db.queries import upsert_signal

PROJECT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("fill_gaps")

# Sources worth retrying per person. News is excluded: it is bulk-fetched for the
# whole roster in one BigQuery query, so use refresh_news.py for that instead.
RETRYABLE = {
    "wikidata_recognition": lambda p, period: _wikidata(p),
    "wikipedia_pageviews": lambda p, period: _pageviews(p, period),
    "wiki_edit_velocity": lambda p, period: _velocity(p, period),
}


def _wikidata(person):
    from server.data.sources.wikidata_cache import institutional_score_cached
    return float(institutional_score_cached(person["wikipedia_title"]))


def _pageviews(person, period):
    from server.data.sources.wikipedia import weekly_aggregate
    return float(weekly_aggregate(person["wikipedia_title"], period))


def _velocity(person, period):
    from server.data.sources.social import fetch_mention_velocity
    return float(fetch_mention_velocity(person["wikipedia_title"], period)["velocity"])


def find_gaps(period: str) -> list[tuple]:
    """(person_id, name, wikipedia_title, source) for every missing signal."""
    con = sqlite3.connect(PROJECT / "fame_index.db")
    people = con.execute(
        "select id, name, wikipedia_title from persons where active=1").fetchall()
    gaps = []
    for pid, name, title in people:
        present = {s for (s,) in con.execute(
            "select source from signals where week=? and person_id=?", (period, pid))}
        for source in RETRYABLE:
            if source not in present:
                gaps.append((pid, name, title, source))
    con.close()
    return gaps


def main() -> int:
    ap = argparse.ArgumentParser(description="Retry signals a run failed to collect.")
    ap.add_argument("periods", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()

    total_fixed = total_failed = 0
    for period in args.periods:
        gaps = find_gaps(period)
        print(f"\n{period}: {len(gaps)} gap(s)")
        if not gaps:
            continue
        for pid, name, title, source in gaps:
            print(f"  {name} / {source}", end="")
            if args.dry_run:
                print("  (dry run)")
                continue
            try:
                value = RETRYABLE[source]({"id": pid, "name": name,
                                           "wikipedia_title": title}, period)
                sig = normalize_batch([{"person_id": pid, "week": period,
                                        "source": source, "raw_value": value}])[0]
                upsert_signal(person_id=pid, week=period, source=source,
                              dimension=sig["dimension"], raw_value=sig["raw_value"],
                              normalised_value=sig["normalised_value"])
                print(f"  -> {value:,.0f}")
                total_fixed += 1
            except Exception as e:
                print(f"  -> STILL FAILING: {str(e)[:80]}")
                total_failed += 1
            time.sleep(1.5)

    if not args.dry_run:
        print(f"\nfilled {total_fixed}, still failing {total_failed}")
        if total_fixed:
            print("Rescore so the new signals are reflected:")
            print("  .venv/bin/python -c \"from server.scoring.engine import score_all; "
                  "from server.db.queries import store_scores; "
                  f"[store_scores(score_all(p)) for p in {args.periods}]\"")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
