"""
Main build orchestrator for the Fame Index static site.

Reads scored data from the database, renders Jinja2 templates into
static HTML pages, and writes them to site/output/. This is the only
bridge between the private server code and the public site.

Generated pages:
- index.html (global ranking — same as latest week)
- /person/{slug}.html (individual profiles)
- /week/{week}.html (weekly snapshots)
- /blog/{week}.html (weekly blog posts)
"""

import importlib.util
import os

from jinja2 import Environment, FileSystemLoader

from server.db.queries import (
    get_all_persons,
    get_scores_for_week,
    get_person_history,
    get_all_scored_weeks,
    get_blog_post,
    get_all_blog_posts,
)
from server.data.week_utils import previous_week, week_to_dates
from server.scoring.momentum import biggest_movers

# Import schema module from the same directory (avoids 'site' name collision
# with Python's built-in site module)
_schema_path = os.path.join(os.path.dirname(__file__), "schema.py")
_spec = importlib.util.spec_from_file_location("site_build_schema", _schema_path)
_schema_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema_mod)
person_schema = _schema_mod.person_schema
ranking_schema = _schema_mod.ranking_schema
blog_post_schema = _schema_mod.blog_post_schema

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# Teletext page number scheme
PAGE_HOME = 100
PAGE_CATEGORIES = {
    "musician": 110,
    "actor": 111,
    "athlete": 112,
    "politician": 113,
    "business": 114,
    "creator": 115,
}
PAGE_REGIONS = {
    "global": 120,
    "us": 121,
    "uk": 122,
    "eu": 123,
    "asia": 124,
}
PAGE_PERSON_BASE = 200
PAGE_WEEK_BASE = 300
PAGE_BLOG_BASE = 400


def _get_env() -> Environment:
    """Create a Jinja2 environment with the templates directory."""
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )


def _write_page(path: str, html: str) -> None:
    """Write an HTML string to the output directory."""
    full_path = os.path.join(OUTPUT_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(html)


def _build_rankings_data(week: str) -> list[dict]:
    """Query scores for a week and build template-ready ranking dicts."""
    scores = get_scores_for_week(week)
    prev = previous_week(week)
    prev_scores = get_scores_for_week(prev)

    # Build a lookup of previous week's ranks
    prev_ranks = {}
    for sc in prev_scores:
        prev_ranks[sc.person_id] = sc.rank

    rankings = []
    for sc in scores:
        prev_rank = prev_ranks.get(sc.person_id)
        if prev_rank and sc.rank:
            change = prev_rank - sc.rank  # positive = climbed
        else:
            change = 0

        rankings.append({
            "rank": sc.rank or 0,
            "name": sc.person.name,
            "slug": sc.person.slug,
            "category": sc.person.category,
            "region": sc.person.region,
            "score": round(sc.fame_score, 1),
            "momentum": round(sc.momentum, 1),
            "change": change,
        })

    return rankings


def build_site(week: str) -> None:
    """
    Build the entire static site for a given week.

    Generates all HTML pages from templates and scored data, writes
    them to the output directory.

    Args:
        week: ISO week string for the current build.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Build the main ranking page (also serves as index)
    ranking_html = build_ranking_page(week)
    _write_page("index.html", ranking_html)

    # Build category pages
    for category in PAGE_CATEGORIES:
        cat_html = build_category_page(week, category)
        if cat_html:
            _write_page(f"category/{category}/index.html", cat_html)

    # Build region pages
    for region in PAGE_REGIONS:
        region_html = build_region_page(week, region)
        if region_html:
            _write_page(f"region/{region}/index.html", region_html)

    # Build the week page for the current week
    week_html = build_week_page(week)
    _write_page(f"week/{week}/index.html", week_html)

    # Build person profile pages
    persons = get_all_persons(active_only=True)
    for i, person in enumerate(persons):
        person_html = build_person_page(person.id, page_num=PAGE_PERSON_BASE + (i % 100))
        _write_page(f"person/{person.slug}/index.html", person_html)

    # Build blog index and individual post pages
    posts = get_all_blog_posts()
    blog_index_html = build_blog_index()
    _write_page("blog/index.html", blog_index_html)
    for post in posts:
        blog_html = build_blog_page(post.week)
        if blog_html:
            _write_page(f"blog/{post.week}/index.html", blog_html)

    # Build previous week pages (last 12 weeks)
    all_weeks = get_all_scored_weeks()
    for w in all_weeks[:12]:
        if w != week:  # already built current week
            wk_html = build_week_page(w)
            _write_page(f"week/{w}/index.html", wk_html)

    # Generate sitemap and robots.txt
    build_sitemap(week, persons, posts, all_weeks[:12])


def build_ranking_page(week: str) -> str:
    """
    Generate the main ranking page HTML.

    Args:
        week: ISO week string.

    Returns:
        Rendered HTML string.
    """
    env = _get_env()
    template = env.get_template("ranking.html")

    rankings = _build_rankings_data(week)[:100]
    schema = ranking_schema(rankings, week)

    return template.render(
        week=week,
        rankings=rankings,
        ranking_schema=schema,
        page_number=PAGE_HOME,
    )


def build_category_page(week: str, category: str) -> str:
    """Generate a ranking page filtered by category."""
    env = _get_env()
    template = env.get_template("ranking.html")

    all_rankings = _build_rankings_data(week)
    rankings = [r for r in all_rankings if r.get("category") == category]
    if not rankings:
        return ""

    # Re-rank within category and limit to 20
    rankings = rankings[:20]
    for i, entry in enumerate(rankings, 1):
        entry["rank"] = i

    schema = ranking_schema(rankings, week)
    page_num = PAGE_CATEGORIES.get(category, 110)

    return template.render(
        week=week,
        rankings=rankings,
        ranking_schema=schema,
        page_number=page_num,
        filter_label=category.title(),
    )


def build_region_page(week: str, region: str) -> str:
    """Generate a ranking page filtered by region."""
    env = _get_env()
    template = env.get_template("ranking.html")

    all_rankings = _build_rankings_data(week)
    rankings = [r for r in all_rankings if r.get("region") == region]
    if not rankings:
        return ""

    for i, entry in enumerate(rankings, 1):
        entry["rank"] = i

    schema = ranking_schema(rankings, week)
    page_num = PAGE_REGIONS.get(region, 120)

    return template.render(
        week=week,
        rankings=rankings,
        ranking_schema=schema,
        page_number=page_num,
        filter_label=region.upper(),
    )


def build_person_page(person_id: int, page_num: int = PAGE_PERSON_BASE) -> str:
    """
    Generate an individual person's profile page.

    Args:
        person_id: Database ID for the person.

    Returns:
        Rendered HTML string.
    """
    env = _get_env()
    template = env.get_template("person.html")

    history = get_person_history(person_id, num_weeks=12)
    if not history:
        return ""

    latest = history[0]
    person_data = {
        "name": latest.person.name,
        "slug": latest.person.slug,
        "category": latest.person.category,
        "score": round(latest.fame_score, 1),
        "rank": latest.rank or 0,
        "momentum": round(latest.momentum, 1),
        "sentiment": round(latest.sentiment_polarity, 2),
        "controversy": round(latest.controversy_index, 1),
        "history": [
            {
                "week": sc.week,
                "score": round(sc.fame_score, 1),
                "rank": sc.rank or 0,
            }
            for sc in history
        ],
    }

    schema = person_schema(person_data)

    return template.render(
        person=person_data,
        person_schema=schema,
        page_number=page_num,
    )


def build_week_page(week: str) -> str:
    """
    Generate a weekly snapshot page.

    Args:
        week: ISO week string.

    Returns:
        Rendered HTML string.
    """
    env = _get_env()
    template = env.get_template("week.html")

    rankings = _build_rankings_data(week)
    movers = biggest_movers(week, n=3)

    highlights = {
        "number_one": rankings[0]["name"] if rankings else "—",
        "biggest_climber": movers["climbers"][0][1] if movers["climbers"] else "—",
        "fastest_faller": movers["fallers"][0][1] if movers["fallers"] else "—",
    }

    prev = previous_week(week)
    # Determine next week (if scores exist for it)
    all_weeks = get_all_scored_weeks()
    next_week = None
    for i, w in enumerate(all_weeks):
        if w == week and i > 0:
            next_week = all_weeks[i - 1]
            break

    week_num = int(week.split("-W")[1]) if "-W" in week else 0
    return template.render(
        week=week,
        rankings=rankings,
        highlights=highlights,
        previous_week=prev,
        next_week=next_week,
        page_number=PAGE_WEEK_BASE + (week_num % 100),
    )


def build_blog_page(week: str) -> str:
    """
    Generate a blog post page for a given week.

    Args:
        week: ISO week string.

    Returns:
        Rendered HTML string, or empty string if no post exists.
    """
    env = _get_env()
    template = env.get_template("blog_post.html")

    post = get_blog_post(week)
    if not post:
        return ""

    monday, _ = week_to_dates(week)

    # Find adjacent posts for navigation
    all_posts = get_all_blog_posts()
    post_weeks = [p.week for p in all_posts]
    prev_week = None
    next_week = None
    for i, pw in enumerate(post_weeks):
        if pw == week:
            if i < len(post_weeks) - 1:
                prev_week = post_weeks[i + 1]
            if i > 0:
                next_week = post_weeks[i - 1]
            break

    post_data = {
        "title": post.title,
        "content": post.content,
        "week": week,
        "date": monday.strftime("%Y-%m-%d"),
        "summary": post.content[:160] if post.content else "",
        "previous_week": prev_week,
        "next_week": next_week,
    }

    schema = blog_post_schema(post_data)

    week_num = int(week.split("-W")[1]) if "-W" in week else 0
    return template.render(
        post=post_data,
        blog_schema=schema,
        page_number=PAGE_BLOG_BASE + (week_num % 100),
    )


def build_blog_index() -> str:
    """Generate the blog index page listing all published posts."""
    env = _get_env()
    template = env.get_template("blog_index.html")

    posts = get_all_blog_posts()
    post_list = [
        {"week": p.week, "title": p.title}
        for p in posts
    ]

    return template.render(
        posts=post_list,
        page_number=PAGE_BLOG_BASE,
    )


SITE_URL = "https://fameindex.net"


def build_sitemap(week: str, persons: list, posts: list, weeks: list) -> None:
    """
    Generate sitemap.xml and robots.txt.

    Args:
        week: Current ISO week string.
        persons: List of Person objects.
        posts: List of BlogPost objects.
        weeks: List of week strings with scores.
    """
    from datetime import date

    today = date.today().isoformat()

    urls = []

    # Homepage — highest priority, changes weekly
    urls.append(_sitemap_url("/", today, "weekly", "1.0"))

    # Category pages
    for category in PAGE_CATEGORIES:
        urls.append(_sitemap_url(f"/category/{category}/", today, "weekly", "0.8"))

    # Region pages
    for region in PAGE_REGIONS:
        urls.append(_sitemap_url(f"/region/{region}/", today, "weekly", "0.8"))

    # Person profiles — change weekly
    for person in persons:
        urls.append(_sitemap_url(f"/person/{person.slug}/", today, "weekly", "0.7"))

    # Week snapshots — don't change once published
    for w in weeks:
        priority = "0.9" if w == week else "0.5"
        freq = "weekly" if w == week else "never"
        urls.append(_sitemap_url(f"/week/{w}/", today, freq, priority))

    # Blog posts
    urls.append(_sitemap_url("/blog/", today, "weekly", "0.6"))
    for post in posts:
        urls.append(_sitemap_url(f"/blog/{post.week}/", today, "never", "0.6"))

    # Build XML
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{url['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        xml_lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_lines.append(f"    <priority>{url['priority']}</priority>")
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")

    sitemap_xml = "\n".join(xml_lines) + "\n"
    _write_page("sitemap.xml", sitemap_xml)

    # robots.txt
    robots = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    _write_page("robots.txt", robots)


def _sitemap_url(path: str, lastmod: str, changefreq: str, priority: str) -> dict:
    return {
        "loc": f"{SITE_URL}{path}",
        "lastmod": lastmod,
        "changefreq": changefreq,
        "priority": priority,
    }
