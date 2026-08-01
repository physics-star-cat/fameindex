#!/usr/bin/env python3
"""
refresh_news.py — re-fetch just the news dimension for one or more periods.

The news signal comes from a single BigQuery query per period, while the other
signals need one slow, rate-limited HTTP call per person. So when only the news
matching changes — a diacritic fix, a new alias — there is no reason to re-run
the whole backfill. This refreshes news alone in about ten seconds per period.

    python scripts/refresh_news.py 2026-Q1 2026-Q2
    python scripts/refresh_news.py --dry-run 2026-Q2

Aliases: GDELT extracts names from article text, which uses legal names for
performers who work under a stage name — "Abel Tesfaye", not "The Weeknd".
Without aliases those people score near zero on news, which is a systematic bias
against musicians rather than random noise. Each person is matched on their name
and every alias, and the highest count wins.
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")

from server.data.normalize import normalize_batch
from server.data.sources.gdelt_bigquery import news_counts_for_roster
from server.db import init_db
from server.db.queries import upsert_signal

PROJECT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("refresh_news")


def load_roster() -> list[dict]:
    """Active people with their aliases."""
    con = sqlite3.connect(PROJECT / "fame_index.db")
    rows = con.execute(
        "select id, name, coalesce(aliases,'') from persons where active=1").fetchall()
    con.close()
    return [
        {"id": pid, "name": name,
         "variants": [name] + [a for a in aliases.split("|") if a]}
        for pid, name, aliases in rows
    ]


def refresh(period: str, dry_run: bool = False) -> dict:
    """Re-fetch and store the news signal for one period."""
    roster = load_roster()

    # One query covering every name and alias.
    variants = sorted({v for p in roster for v in p["variants"]})
    counts = news_counts_for_roster(variants, period)

    matched, unmatched = {}, []
    for person in roster:
        best = max((counts.get(v, -1) for v in person["variants"]))
        if best >= 0:
            matched[person["id"]] = (person["name"], best)
        else:
            unmatched.append(person["name"])

    # A name that survives diacritic stripping, punctuation collapsing and its
    # aliases and STILL finds nothing was genuinely not named in the news that
    # quarter. Zero is then the honest measurement, and recording it keeps
    # dimension coverage uniform — without which people are ranked under
    # different weightings in the same table.
    #
    # Guarded, because that reasoning only holds while matching is working. A
    # sudden crop of non-matches means the matching broke, not that a fifth of
    # the roster left public life, and recording zeros then would repeat exactly
    # the fabrication this whole exercise was about.
    if len(unmatched) > len(roster) * 0.1:
        raise RuntimeError(
            f"{len(unmatched)}/{len(roster)} names unmatched for {period} — "
            "that is a matching failure, not genuine absence. Refusing to write "
            f"zeros. Unmatched: {', '.join(unmatched[:10])}")
    for person in roster:
        if person["name"] in unmatched:
            matched[person["id"]] = (person["name"], 0)

    print(f"  {period}: {len(matched)}/{len(roster)} matched"
          f"{f' — no match: {', '.join(unmatched)}' if unmatched else ''}")

    if dry_run:
        return {"matched": len(matched), "unmatched": unmatched}

    for pid, (name, mentions) in matched.items():
        sig = normalize_batch([{
            "person_id": pid, "week": period,
            "source": "gdelt_count", "raw_value": float(mentions),
        }])[0]
        upsert_signal(
            person_id=pid, week=period, source="gdelt_count",
            dimension=sig["dimension"], raw_value=sig["raw_value"],
            normalised_value=sig["normalised_value"],
        )
    return {"matched": len(matched), "unmatched": unmatched}


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh the news signal for periods.")
    ap.add_argument("periods", nargs="+", help="e.g. 2026-Q1 2026-Q2")
    ap.add_argument("--dry-run", action="store_true", help="Report matches, store nothing")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()

    for period in args.periods:
        refresh(period, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nRescore the affected periods so the news dimension is reflected:")
        print("  .venv/bin/python -c \"from server.scoring.engine import score_all; "
              "from server.db.queries import store_scores; "
              f"[store_scores(score_all(p)) for p in {args.periods}]\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
