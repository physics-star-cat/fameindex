#!/bin/bash
#
# deploy.sh — Deploy the Fame Index static site via Vercel.
#
# For production deploys, push to main on GitHub (physics-star-cat/fameindex).
# Vercel auto-deploys from the main branch.
#
# For preview deploys, use: vercel
# For manual production deploy, use: vercel --prod

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/site/output"

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory not found. Run the build first."
    exit 1
fi

echo "Deploying from: $OUTPUT_DIR"
echo "Target: Vercel (fameindex.net)"

if ! command -v vercel &> /dev/null; then
    echo "Vercel CLI not installed. Install with: npm i -g vercel"
    echo "Or push to main branch for automatic deployment."
    exit 1
fi

vercel --prod
