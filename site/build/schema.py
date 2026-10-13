"""
Structured data (JSON-LD) generation for SEO.

Produces schema.org markup to embed in HTML pages. This helps search
engines understand the content and display rich results.

Schemas used:
- Person: For individual profile pages
- ItemList: For ranking pages
- BlogPosting: For weekly blog posts
- WebSite: For the site root
"""

import json


SITE_URL = "https://fameindex.net"


def _script_tag(data: dict) -> str:
    """Wrap a JSON-LD object in a <script> tag."""
    return (
        '<script type="application/ld+json">'
        + json.dumps(data, ensure_ascii=False)
        + "</script>"
    )


def website_schema() -> str:
    """Generate JSON-LD for the WebSite + Organization entity on the homepage."""
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Fame Index",
        "url": SITE_URL,
        "description": "Monthly fame rankings of public figures, measured by data rather than opinion.",
    }
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Fame Index",
        "url": SITE_URL,
        "description": "Monthly fame rankings of public figures, measured by data rather than opinion.",
    }
    return _script_tag(website) + "\n" + _script_tag(org)


def person_schema(person: dict) -> str:
    """
    Generate JSON-LD for a Person entity.

    Args:
        person: Dict with person data (name, slug, category, score, rank).

    Returns:
        JSON-LD script tag as a string.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": person["name"],
        "url": f"{SITE_URL}/person/{person['slug']}",
    }
    if person.get("category"):
        data["description"] = (
            f"{person['name']} — {person['category']}. "
            f"Fame Index score: {person.get('score', 0):.0f}/100."
        )
    return _script_tag(data)


def ranking_schema(rankings: list, week: str) -> str:
    """
    Generate JSON-LD for a ranked list (ItemList).

    Args:
        rankings: List of dicts with name, slug, score, rank keys.
        week: ISO week string.

    Returns:
        JSON-LD script tag as a string.
    """
    items = []
    for entry in rankings:
        items.append({
            "@type": "ListItem",
            "position": entry["rank"],
            "name": entry["name"],
            "url": f"{SITE_URL}/person/{entry['slug']}",
        })

    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Fame Index — {_period_name(week)} League Table",
        "description": f"Monthly fame league table for {_period_name(week)}.",
        "url": f"{SITE_URL}/{'month' if '-M' in week else 'quarter' if '-Q' in week else 'week'}/{week}",
        "numberOfItems": len(items),
        "itemListElement": items,
    }
    return _script_tag(data)


_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _period_name(period: str) -> str:
    """'2026-M09' -> 'September 2026'; other periods unchanged."""
    if "-M" in period:
        y, m = period.split("-M", 1)
        try:
            return f"{_MONTHS[int(m) - 1]} {y}"
        except (ValueError, IndexError):
            pass
    return period


def blog_post_schema(post: dict) -> str:
    """
    Generate JSON-LD for a BlogPosting.

    Args:
        post: Dict with title, summary, week, date, content keys.

    Returns:
        JSON-LD script tag as a string.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post["title"],
        "description": post.get("summary", ""),
        "url": f"{SITE_URL}/blog/{post['week']}",
        "datePublished": post.get("date", ""),
        "publisher": {
            "@type": "Organization",
            "name": "Fame Index",
            "url": SITE_URL,
        },
    }
    return _script_tag(data)
