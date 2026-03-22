"""
Server configuration for the Fame Index.

Handles environment-specific settings (dev vs prod), database connection
strings, API keys, and scoring parameters. All sensitive values are read
from environment variables, never hardcoded.
"""

import os

# Environment
ENV = os.getenv("FAME_ENV", "development")

# Database
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = f"sqlite:///{os.path.join(_PROJECT_ROOT, 'fame_index.db')}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

# API keys (sourced from environment)
GOOGLE_TRENDS_API_KEY = os.getenv("GOOGLE_TRENDS_API_KEY", "")
WIKIPEDIA_USER_AGENT = os.getenv("WIKIPEDIA_USER_AGENT", "FameIndex/1.0")

# Dimension weights (private IP — never exposed to client)
# These determine how the five public dimension scores combine
# into the single headline fame score. The weights sum to 1.0.
DIMENSION_WEIGHTS = {
    "search": 0.30,       # Wikipedia pageviews + Google Trends
    "news": 0.25,         # GDELT + Google News
    "social": 0.20,       # Reddit + Wiki edits + YouTube
    "cultural": 0.15,     # Spotify + TMDB
    "institutional": 0.10,  # Wikidata awards/nominations
}

# Build settings
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "site", "output")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "site", "build", "templates")
