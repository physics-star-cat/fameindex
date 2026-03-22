"""
Wikidata SPARQL data source.

Queries Wikidata for structured information about a person's awards,
nominations, and institutional recognition. This is the best free
source for structured award data — it covers Oscars, Grammys, Emmys,
Nobel Prizes, and thousands of other awards globally.

API: https://query.wikidata.org/
Rate limits: 60 seconds of query processing time per minute.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "FameIndex/1.0 (research project)"}
REQUEST_DELAY = 2.0  # Be polite — rate limit is based on processing time


def fetch_awards_count(wikipedia_title: str) -> dict:
    """
    Count awards and nominations for a person via Wikidata.

    Looks up the person by their English Wikipedia article title,
    then counts P166 (awards received) and P1411 (nominated for).

    Args:
        wikipedia_title: The person's Wikipedia article title (with underscores).

    Returns:
        Dict with keys:
        - "awards": int (number of awards received)
        - "nominations": int (number of nominations)
        - "total": int (awards + nominations)
        Returns zeros on error.
    """
    empty = {"awards": 0, "nominations": 0, "total": 0}

    # SPARQL query: find person by Wikipedia article, count awards + nominations
    query = """
    SELECT
        (COUNT(DISTINCT ?award) AS ?awardCount)
        (COUNT(DISTINCT ?nomination) AS ?nominationCount)
    WHERE {
        ?person wdt:P31 wd:Q5 .
        ?article schema:about ?person ;
                 schema:isPartOf <https://en.wikipedia.org/> ;
                 schema:name "%s"@en .
        OPTIONAL { ?person wdt:P166 ?award . }
        OPTIONAL { ?person wdt:P1411 ?nomination . }
    }
    """ % wikipedia_title.replace("_", " ").replace('"', '\\"')

    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", {}).get("bindings", [])
        if not results:
            return empty

        row = results[0]
        awards = int(row.get("awardCount", {}).get("value", 0))
        nominations = int(row.get("nominationCount", {}).get("value", 0))

        return {
            "awards": awards,
            "nominations": nominations,
            "total": awards + nominations,
        }

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Wikidata SPARQL error for %s: %s", wikipedia_title, e)
        return empty


def institutional_score(wikipedia_title: str) -> float:
    """
    Calculate a raw institutional recognition score.

    Awards are weighted more heavily than nominations.

    Args:
        wikipedia_title: The person's Wikipedia article title.

    Returns:
        Raw score (awards * 3 + nominations * 1). Higher = more recognised.
    """
    data = fetch_awards_count(wikipedia_title)
    return data["awards"] * 3.0 + data["nominations"] * 1.0
