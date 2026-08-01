#!/usr/bin/env python3
"""
update.py — the one command that publishes a quarter of the Fame Index.

Run it when a quarter closes:

    python scripts/update.py                 # latest complete quarter
    python scripts/update.py --period 2026-Q2
    python scripts/update.py --dry-run       # do everything except commit/push
    python scripts/update.py --no-push       # build and commit, don't publish

Replaces scripts/weekly_update.sh, which embedded Python inside shell heredocs
with '$WEEK' string interpolation — fragile, untestable, and never actually run.

Sequence: collect -> score -> write post -> build site -> commit -> push.
Vercel deploys from the push, which is more robust unattended than `vercel
--prod` (that needs a live CLI token).

Nothing is committed unless every prior step succeeded. A half-published quarter
is worse than an unpublished one.
"""

import argparse
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

PROJECT = Path(__file__).resolve().parent.parent

logger = logging.getLogger("update")


def run_git(*args: str) -> str:
    """Run a git command in the project root, raising on failure."""
    result = subprocess.run(
        ["git", *args], cwd=PROJECT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def collect_and_score(period: str) -> dict:
    """Fetch signals and compute scores for a period."""
    from server.data.pipeline import run_pipeline
    from server.db import init_db
    from server.db.queries import get_all_persons, store_scores
    from server.scoring.engine import score_all

    init_db()
    persons = [
        {"id": p.id, "name": p.name, "wikipedia_title": p.wikipedia_title,
         "spotify_id": p.spotify_id, "tmdb_id": p.tmdb_id}
        for p in get_all_persons()
    ]
    logger.info("  roster: %d people", len(persons))

    result = run_pipeline(period, persons=persons)
    logger.info("  signals: %d  errors: %d",
                result["signals_collected"], len(result["errors"]))

    scores = score_all(period)
    store_scores(scores)
    logger.info("  scored: %d people", len(scores))

    return {"signals": result["signals_collected"],
            "errors": len(result["errors"]),
            "scored": len(scores),
            "persons": len(persons)}


def check_data_quality(period: str, roster: int) -> list[str]:
    """
    Refuse to publish obviously broken data.

    Every source used to swallow its exceptions and return 0, so a rate-limited
    fetch was stored as fact — 68 people once showed exactly 0 Wikipedia
    pageviews across a whole quarter, and the resulting rank movements were
    entirely fictional. The sources now raise, but a bad run can still leave
    coverage too thin to rank fairly, so check before publishing rather than
    after someone reads it.
    """
    import sqlite3
    problems = []
    con = sqlite3.connect(PROJECT / "fame_index.db")

    rows = con.execute(
        "select source, count(*), sum(raw_value=0) from signals where week=? group by source",
        (period,)).fetchall()
    if not rows:
        return [f"no signals at all for {period}"]

    for source, total, zeros in rows:
        if total < roster * 0.8:
            problems.append(f"{source}: only {total}/{roster} people covered")
        if source in ("wikipedia_pageviews", "gdelt_count") and zeros > total * 0.1:
            problems.append(f"{source}: {zeros}/{total} are zero — likely failed fetches")

    # Uniform dimension coverage matters: weights are re-normalised over the
    # dimensions a person actually has, so if some people carry a dimension and
    # others do not, they are being ranked under different rules in one table.
    shapes = {}
    for (pid,) in con.execute(
            "select distinct person_id from signals where week=?", (period,)):
        dims = tuple(sorted(d for (d,) in con.execute(
            "select distinct dimension from signals where week=? and person_id=?",
            (period, pid))))
        shapes[dims] = shapes.get(dims, 0) + 1
    if len(shapes) > 1:
        problems.append(
            f"people have differing dimension coverage {shapes} — "
            "they would be ranked under different weightings")

    con.close()
    return problems


def build(period: str) -> None:
    """Generate the blog post and render the static site."""
    from server.blog.generator import generate_weekly_post
    post = generate_weekly_post(period)
    logger.info("  post: %s", post["title"])

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generate", PROJECT / "site" / "build" / "generate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.build_site(period)
    logger.info("  site built to site/output/")


def publish(period: str, push: bool) -> None:
    """Commit the built site and push, letting Vercel deploy."""
    if not run_git("status", "--porcelain"):
        logger.info("  nothing changed — already published?")
        return

    run_git("add", "-A", "site/output", "fame_index.db")
    run_git("commit", "-m", f"{period}: rankings and quarterly update")
    logger.info("  committed")

    if push:
        run_git("push", "origin", "HEAD")
        logger.info("  pushed — Vercel will deploy")
    else:
        logger.info("  --no-push: commit made, not pushed")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a quarter of the Fame Index.")
    ap.add_argument("--period", help="Quarter, e.g. 2026-Q2. Defaults to the latest complete one.")
    ap.add_argument("--dry-run", action="store_true", help="Collect, score and build; do not commit")
    ap.add_argument("--no-push", action="store_true", help="Commit but do not push")
    ap.add_argument("--force", action="store_true", help="Publish even if quality checks fail")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from server.data.week_utils import last_complete_quarter
    period = args.period or last_complete_quarter()

    logs = PROJECT / "logs"
    logs.mkdir(exist_ok=True)
    handler = logging.FileHandler(logs / f"update-{period}.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)

    print(f"=== Fame Index — {period} ===")
    print(f"started {datetime.now():%Y-%m-%d %H:%M}\n")

    try:
        print("[1/4] collecting and scoring")
        stats = collect_and_score(period)

        print("[2/4] checking data quality")
        problems = check_data_quality(period, stats["persons"])
        if problems:
            print("\n  DATA QUALITY PROBLEMS:")
            for p in problems:
                print(f"    - {p}")
            if not args.force:
                print("\n  Refusing to publish. Investigate, or re-run with --force.")
                return 1
            print("\n  --force given, continuing anyway.")
        else:
            print("  looks sound")

        print("[3/4] generating post and building site")
        build(period)

        print("[4/4] publishing")
        if args.dry_run:
            print("  --dry-run: stopping before commit")
        else:
            publish(period, push=not args.no_push)

    except Exception as e:
        logger.exception("update failed")
        print(f"\nFAILED: {e}")
        return 1

    print(f"\n=== done {datetime.now():%H:%M} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
