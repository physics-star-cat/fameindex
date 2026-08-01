#!/bin/bash
#
# monthly.sh — publish the Fame Index for the month that just ended.
#
# Run it on the 1st:
#
#     cd ~/Projects/websites/fameindex
#     ./monthly.sh
#
# It resolves the period itself (the month that just ended, never the current
# one — a part-month ranked as complete would show everyone crashing), reviews
# the roster, collects, checks, and publishes.
#
# Nothing is published if the data does not pass the quality check, and you are
# asked before anything goes live.
#
#     ./monthly.sh --period 2026-M07     a specific month
#     ./monthly.sh --dry-run             everything except commit and push
#     ./monthly.sh --yes                 no confirmation prompt
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
PY=.venv/bin/python

PERIOD=""; DRY=""; ASSUME_YES=""
while [ $# -gt 0 ]; do
    case "$1" in
        --period) PERIOD="$2"; shift 2 ;;
        --dry-run) DRY="--dry-run"; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        *) echo "unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$PERIOD" ]; then
    PERIOD=$($PY -c "from server.data.week_utils import last_complete_month; print(last_complete_month())")
fi
LABEL=$($PY -c "from server.data.week_utils import format_period; print(format_period('$PERIOD'))")

echo "=============================================="
echo "  Fame Index — $LABEL  ($PERIOD)"
echo "=============================================="
echo

# ---------------------------------------------------------------------------
# 1. Roster
# ---------------------------------------------------------------------------
# Reported, never applied automatically. Promotions and relegations change who
# the index is about, which is an editorial decision rather than a mechanical
# one. Apply with:  .venv/bin/python scripts/roster.py review $PERIOD --apply
echo "--- Roster review (report only) ---"
$PY scripts/roster.py review "$PERIOD" --limit 12 2>&1 | grep -vE "^(Roster:|[0-9]+ names)" || true
echo

if [ -z "$ASSUME_YES" ] && [ -z "$DRY" ]; then
    read -r -p "Publish $LABEL? [y/N] " reply
    case "$reply" in [yY]*) ;; *) echo "Stopped. Nothing published."; exit 0 ;; esac
    echo
fi

# ---------------------------------------------------------------------------
# 2. Collect, score, check, publish
# ---------------------------------------------------------------------------
# update.py refuses to publish if coverage is thin or if people have differing
# dimension coverage — the latter means they would be ranked under different
# weightings in the same table.
#
# Sources deliberately match the historical months. Reddit, YouTube and Google
# News cannot be fetched retrospectively, so enabling them would give this month
# a richer picture than every month before it and shift scores for reasons
# unrelated to fame. Pass --all-sources to update.py to opt in.
echo "--- Collect, score, publish ---"
if ! $PY scripts/update.py --period "$PERIOD" $DRY; then
    echo
    echo "Update failed or was refused. Common fixes:"
    echo "  gaps in coverage   .venv/bin/python scripts/fill_gaps.py $PERIOD"
    echo "  news mismatches    .venv/bin/python scripts/refresh_news.py $PERIOD"
    echo "  then re-run        ./monthly.sh --period $PERIOD"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Confirm it is actually live
# ---------------------------------------------------------------------------
if [ -z "$DRY" ]; then
    echo
    echo "--- Verifying (Vercel takes a minute) ---"
    sleep 60
    if curl -s -L --max-time 25 "https://fameindex.net/month/$PERIOD/" | grep -q "$LABEL"; then
        echo "  live: https://fameindex.net/month/$PERIOD/"
    else
        echo "  not visible yet — check https://vercel.com or retry in a minute"
    fi
fi

echo
echo "Done."
