#!/bin/bash
#
# weekly_update.sh — Friday build trigger for the Fame Index.
#
# Runs the full weekly cycle:
# 1. Fetch fresh data from all sources
# 2. Recalculate all scores
# 3. Generate the weekly blog post
# 4. Rebuild the static site
# 5. Deploy to CDN
#
# Intended to be run via cron every Friday at a set time.
# Usage: ./weekly_update.sh [WEEK]
# If WEEK is omitted, uses the current ISO week.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Determine the week (either from arg or current date)
if [ -n "${1:-}" ]; then
    WEEK="$1"
else
    WEEK=$(python -c "from datetime import date; d=date.today(); print(f'{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}')")
fi

echo "=== Fame Index Weekly Update ==="
echo "Week: $WEEK"
echo "Started: $(date)"

# Step 1: Run data pipeline
echo "[1/5] Fetching data..."
python -c "
from server.db import init_db
from server.db.queries import get_all_persons
from server.data.pipeline import run_pipeline
init_db()
persons = [{'id': p.id, 'name': p.name, 'wikipedia_title': p.wikipedia_title,
            'spotify_id': p.spotify_id, 'tmdb_id': p.tmdb_id}
           for p in get_all_persons()]
result = run_pipeline('$WEEK', persons=persons)
print(f'  Processed {result[\"persons_processed\"]} persons, {result[\"signals_collected\"]} signals')
if result['errors']:
    for e in result['errors']:
        print(f'  WARNING: {e}')
"

# Step 2: Score all persons
echo "[2/5] Calculating scores..."
python -c "
from server.scoring.engine import score_all
from server.db.queries import store_scores
result = score_all('$WEEK')
store_scores(result)
print(f'  Scored {len(result)} persons')
"

# Step 3: Generate blog post
echo "[3/5] Generating blog post..."
python -c "
from server.blog.generator import generate_weekly_post
post = generate_weekly_post('$WEEK')
print(f'  Title: {post[\"title\"]}')
"

# Step 4: Build static site
echo "[4/5] Building site..."
python -c "
from site_build import build_site
build_site('$WEEK')
print('  Site built to site/output/')
" 2>/dev/null || python -c "
import importlib.util, os
spec = importlib.util.spec_from_file_location('gen', os.path.join('site', 'build', 'generate.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.build_site('$WEEK')
print('  Site built to site/output/')
"

# Step 5: Deploy
echo "[5/5] Deploying..."
"$SCRIPT_DIR/deploy.sh"

echo "=== Complete: $(date) ==="
