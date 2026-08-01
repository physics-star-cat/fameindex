"""
GDELT news volume via BigQuery.

Replaces the GDELT DOC API, which rate-limits without documenting a limit and
blocks an IP for hours after a burst. During the 2026-Q1/Q2 backfill it cost
roughly 60 seconds per person in exponential backoff and still returned almost
nothing.

BigQuery serves the same underlying data with no rate limiting, and — crucially —
answers for the WHOLE ROSTER IN ONE QUERY. Measured on 121 people for one
quarter: 1.07 GB scanned, about $0.007, ten seconds. Querying per person would
have scanned ~129 GB for the identical answer.

Cost control: every query is dry-run first. BigQuery reports bytes scanned
without executing, for free, so a query is never run without knowing its size.
The partition filter is what keeps it cheap — the same query without a date
filter scans 79 GB instead of 1.

Requires: BigQuery API enabled, the service account holding roles/bigquery.jobUser
on the GCP project, and the bigquery scope on the credential.
"""

import logging
import os
from pathlib import Path

from server.data.week_utils import period_to_dates

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", "lifebynumbers")
BIGQUERY_SCOPE = "https://www.googleapis.com/auth/bigquery"

# Refuse to run anything larger than this. A correctly partitioned quarterly
# query is ~1 GB; anything approaching double figures means the partition filter
# has been lost, which is the one mistake that actually costs money.
MAX_SCAN_GB = 10.0

# Date-partitioned GKG. The unpartitioned `gdeltv2.gkg` table works but cannot
# be filtered cheaply.
GKG_TABLE = "`gdelt-bq.gdeltv2.gkg_partitioned`"

# Diacritics are stripped from BOTH sides before matching.
#
# GDELT stores names unaccented, so a byte-exact LIKE missed "Beyoncé",
# "Kylian Mbappé", "Rosalía" and anyone else with an accent — they came back
# with no news signal at all, which is worse than a wrong number: people with
# and without a news dimension get ranked under different weightings.
#
# NORMALIZE(x, NFD) decomposes accented characters into base + combining mark,
# then \pM strips the marks. "Beyoncé" -> "beyonce".
# Strip diacritics AND punctuation before matching, on both sides.
#
# GDELT normalises names when extracting them: "Robert Downey Jr." is stored as
# "Robert Downey Jr", and "Charli D'Amelio" as "Charli Damelio". Our roster keeps
# the human spelling, so a byte-exact LIKE missed both.
#
# Deliberately NOT loosened further. Matching on surname alone would conflate
# Giorgia Meloni with Christopher Meloni, and Robert Downey Jr with Emma, Doug
# and Susan Downey — all of whom appear in the same quarter. Where GDELT's form
# genuinely differs (it drops the forename for Ocasio-Cortez), that belongs in
# persons.aliases, not in a looser pattern.
# Separators are REMOVED, not replaced with a space. Replacing them turned
# "Charli D'Amelio" into "charli d amelio", which still failed to match GDELT's
# "Charli Damelio". Collapsing to "charlidamelio" matches both, and likewise
# "Robert Downey Jr." against "Robert Downey Jr".
_STRIP = (
    r"REGEXP_REPLACE("
    r"REGEXP_REPLACE(NORMALIZE(LOWER({}), NFD), r'\pM', '')"
    r", r'[^a-z0-9]+', '')"
)

_ROSTER_SQL = f"""
SELECT p AS person, COUNT(*) AS mentions
FROM {GKG_TABLE},
     UNNEST(SPLIT(V2Persons, ';')) AS raw
CROSS JOIN UNNEST(@names) AS p
WHERE _PARTITIONTIME BETWEEN TIMESTAMP(@start) AND TIMESTAMP(@end)
  AND raw != ''
  AND {_STRIP.format('raw')} LIKE CONCAT('%', {_STRIP.format('p')}, '%')
GROUP BY p
"""


def _client():
    """BigQuery client using the shared service account."""
    from google.cloud import bigquery
    from google.oauth2 import service_account

    key = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path.home() / ".config/google/service-account.json"),
    )
    creds = service_account.Credentials.from_service_account_file(
        key, scopes=[BIGQUERY_SCOPE])
    return bigquery.Client(credentials=creds, project=GCP_PROJECT)


def estimate_scan_gb(names: list[str], period: str) -> float:
    """Dry-run the roster query and report gigabytes scanned. Costs nothing."""
    from google.cloud import bigquery

    start, end = period_to_dates(period)
    job = _client().query(_ROSTER_SQL, job_config=bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False,
        query_parameters=[
            bigquery.ArrayQueryParameter("names", "STRING", names),
            bigquery.ScalarQueryParameter("start", "STRING", start.isoformat()),
            bigquery.ScalarQueryParameter("end", "STRING", end.isoformat()),
        ]))
    return job.total_bytes_processed / 1024 ** 3


def news_counts_for_roster(names: list[str], period: str) -> dict[str, int]:
    """
    News mention counts for every supplied name in one period.

    Returns a name -> count mapping. Names GDELT never mentioned are absent
    rather than zero: the caller must be able to tell "not mentioned" from "not
    asked", and a fabricated zero is precisely the bug that made the first
    backfill worthless.

    Raises if the query would scan more than MAX_SCAN_GB, or on any BigQuery
    error — never returns partial or invented data.
    """
    from google.cloud import bigquery

    if not names:
        return {}

    gb = estimate_scan_gb(names, period)
    if gb > MAX_SCAN_GB:
        raise RuntimeError(
            f"refusing to run: query would scan {gb:.1f} GB "
            f"(limit {MAX_SCAN_GB} GB) — the partition filter is probably lost")
    logger.info("GDELT/BigQuery %s: scanning %.2f GB for %d names",
                period, gb, len(names))

    start, end = period_to_dates(period)
    rows = _client().query(_ROSTER_SQL, job_config=bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("names", "STRING", names),
            bigquery.ScalarQueryParameter("start", "STRING", start.isoformat()),
            bigquery.ScalarQueryParameter("end", "STRING", end.isoformat()),
        ])).result()

    counts = {r.person: int(r.mentions) for r in rows}
    logger.info("GDELT/BigQuery %s: %d/%d names matched",
                period, len(counts), len(names))
    return counts
