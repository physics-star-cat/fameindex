#!/usr/bin/env python3
"""
roster.py — promotion and relegation for the Fame Index.

The roster was fixed at 121 people chosen once and never revisited. A fame index
with a permanent cast stops measuring fame and starts measuring how those
particular people are doing; it can never capture emergence, which is the most
interesting thing about the subject.

This makes the roster self-maintaining:

  discover   ask GDELT who was actually in the news this period
  filter     keep only real humans, via Wikidata "instance of human" (Q5)
  promote    add newcomers who clear the entry threshold
  relegate   retire anyone who has ranked in the bottom band for N periods

    python scripts/roster.py review 2026-M07          # report, change nothing
    python scripts/roster.py review 2026-M07 --apply  # promote and relegate

WHY THE WIKIDATA FILTER

GDELT extracts person names from article text and gets it wrong often enough to
matter. A raw top-40 for 2026-Q2 contained Los Angeles, Las Vegas, Abu Dhabi,
the Baltic Sea, El Nino, "Prime Minister", "Lok Sabha" and "Stacker Stacker"
alongside real people. Filtering on Wikidata Q5 is principled where a blocklist
would be endless.

Relegation is by RANK, not by score. Scores drift with signal coverage; rank is
relative to the same field, which is what "less famous than the others" means.
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")

from server.data.sources.gdelt_bigquery import _client, GKG_TABLE
from server.data.week_utils import period_to_dates, previous_period

PROJECT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("roster")

# Entry: appear in this many news items in one period. Set well above the noise
# floor so a single viral week does not earn a permanent place.
PROMOTION_MIN_MENTIONS = 5000

# Exit: ranked in the bottom fifth for this many consecutive periods. Two is
# deliberately patient — fame is lumpy, and one quiet month is not a career.
RELEGATION_PERIODS = 3
RELEGATION_BAND = 0.8  # bottom 20%


def discover(period: str, limit: int = 200) -> list[tuple[str, int]]:
    """Most-mentioned names in news for a period, before any filtering."""
    start, end = period_to_dates(period)
    sql = f"""
    SELECT TRIM(SPLIT(raw, ',')[OFFSET(0)]) AS person, COUNT(*) AS mentions
    FROM {GKG_TABLE}, UNNEST(SPLIT(V2Persons, ';')) AS raw
    WHERE _PARTITIONTIME BETWEEN TIMESTAMP('{start}') AND TIMESTAMP('{end}')
      AND raw != ''
    GROUP BY person
    HAVING mentions >= {PROMOTION_MIN_MENTIONS}
    ORDER BY mentions DESC
    LIMIT {limit}
    """
    return [(r.person, int(r.mentions)) for r in _client().query(sql).result()]


def is_human(name: str) -> bool:
    """
    True if Wikidata says this name is a human (Q5).

    This is what keeps Los Angeles and El Nino out of a list of famous people.
    """
    import requests
    try:
        resp = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "search": name,
                    "language": "en", "format": "json", "limit": 1},
            headers={"User-Agent": "FameIndex/1.0 (https://fameindex.net)"},
            timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("search", [])
        if not hits:
            return False
        qid = hits[0]["id"]

        resp = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            headers={"User-Agent": "FameIndex/1.0 (https://fameindex.net)"},
            timeout=15)
        resp.raise_for_status()
        claims = resp.json()["entities"][qid].get("claims", {})
        for c in claims.get("P31", []):  # P31 = instance of
            if c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") == "Q5":
                return True
        return False
    except Exception as e:
        logger.warning("Wikidata check failed for %s: %s", name, e)
        return False  # do not promote what we could not verify


def current_roster() -> dict[str, int]:
    con = sqlite3.connect(PROJECT / "fame_index.db")
    rows = dict(con.execute("select name, id from persons where active=1").fetchall())
    con.close()
    return rows


def relegation_candidates(period: str) -> list[tuple[int, str, list[int]]]:
    """People ranked in the bottom band for RELEGATION_PERIODS consecutive periods."""
    con = sqlite3.connect(PROJECT / "fame_index.db")
    periods = [period]
    p = period
    for _ in range(RELEGATION_PERIODS - 1):
        p = previous_period(p)
        periods.append(p)

    out = []
    for pid, name in con.execute("select id, name from persons where active=1"):
        ranks = []
        for per in periods:
            row = con.execute(
                "select rank, (select count(*) from scores where week=?) "
                "from scores where week=? and person_id=?", (per, per, pid)).fetchone()
            if not row or not row[0]:
                ranks = []
                break  # incomplete history — not enough evidence to relegate
            ranks.append((row[0], row[1]))
        if ranks and all(r >= total * RELEGATION_BAND for r, total in ranks):
            out.append((pid, name, [r for r, _ in ranks]))
    con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Review roster promotions and relegations.")
    ap.add_argument("command", choices=["review"])
    ap.add_argument("period")
    ap.add_argument("--apply", action="store_true", help="Actually promote and relegate")
    ap.add_argument("--limit", type=int, default=60, help="How many discovered names to check")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    roster = current_roster()
    print(f"Roster: {len(roster)} active\n")

    print(f"=== Discovery — most-mentioned in {args.period} ===")
    found = discover(args.period)
    newcomers = [(n, m) for n, m in found if n not in roster][:args.limit]
    print(f"{len(found)} names above {PROMOTION_MIN_MENTIONS:,} mentions; "
          f"{len(newcomers)} not already on the roster. Checking Wikidata...\n")

    promote = []
    for name, mentions in newcomers:
        if is_human(name):
            promote.append((name, mentions))
            print(f"  + {name:<32} {mentions:>9,}  human")
        else:
            print(f"    {name:<32} {mentions:>9,}  not a person — skipped")

    print(f"\n=== Relegation — bottom {int((1-RELEGATION_BAND)*100)}% "
          f"for {RELEGATION_PERIODS} consecutive periods ===")
    relegate = relegation_candidates(args.period)
    if relegate:
        for pid, name, ranks in relegate:
            print(f"  - {name:<32} ranks {ranks}")
    else:
        print("  none")

    print(f"\nWould promote {len(promote)}, relegate {len(relegate)}")

    if not args.apply:
        print("\nReport only. Re-run with --apply to make the changes.")
        return 0

    con = sqlite3.connect(PROJECT / "fame_index.db")
    for name, _ in promote:
        slug = name.lower().replace(" ", "-").replace(".", "").replace("'", "")
        con.execute(
            "insert into persons (name, slug, wikipedia_title, category, region, active) "
            "values (?,?,?,?,?,1)",
            (name, slug, name.replace(" ", "_"), "unknown", "unknown"))
    for pid, _, _ in relegate:
        con.execute("update persons set active=0 where id=?", (pid,))
    con.commit()
    con.close()
    print(f"\nApplied: {len(promote)} promoted, {len(relegate)} relegated.")
    print("Relegated people keep their history; they are simply no longer ranked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
