"""
Blog post generator for the Fame Index.

Produces weekly blog post drafts based on the latest scoring data.
The voice is pithy and droll — not sensationalist. Think dry BBC
commentary rather than tabloid headlines.

Posts are structured around:
- This week's number one
- Biggest climbers
- Fastest fallers
- Notable new entries
"""

import random

from server.db.queries import get_scores_for_week, store_blog_post
from server.scoring.momentum import biggest_movers
from server.data.week_utils import previous_week


# Category-aware commentary templates
_NUMBER_ONE_HOLDS = {
    "musician": [
        "{name} remains at number one ({score:.0f}). The charts bow before them. Again.",
        "{name} is still top. {score:.0f} points. The streaming era made them inescapable.",
        "Still number one: {name} ({score:.0f}). At this point it's just furniture.",
    ],
    "politician": [
        "{name} holds the top spot ({score:.0f}). Whether they deserve attention and whether they're getting it are different questions.",
        "Still number one: {name} ({score:.0f}). The news cycle is nothing if not predictable.",
        "{name} remains at the summit ({score:.0f}). Fame and competence remain unrelated.",
    ],
    "actor": [
        "{name} holds the crown ({score:.0f}). Hollywood's attention economy is working as intended.",
        "Still number one: {name} ({score:.0f}). The press tour never ends.",
        "{name} continues at the top ({score:.0f}). Oscar season does its thing.",
    ],
    "athlete": [
        "{name} holds number one ({score:.0f}). Sports fame is the most honestly earned kind.",
        "Still top: {name} ({score:.0f}). Winning does tend to help.",
        "{name} remains at number one ({score:.0f}). The scoreboard doesn't lie and neither do we.",
    ],
    "business": [
        "{name} keeps the crown ({score:.0f}). Being a billionaire with opinions will do that.",
        "Still number one: {name} ({score:.0f}). Money buys many things, including attention.",
        "{name} holds the top ({score:.0f}). Tech moguls: famous for being famous for being rich.",
    ],
    "creator": [
        "{name} stays at number one ({score:.0f}). The algorithm rewards the algorithm's favourites.",
        "Still top: {name} ({score:.0f}). YouTube fame is the cockroach of celebrity — unkillable.",
        "{name} remains number one ({score:.0f}). Content, content, content.",
    ],
}

_NUMBER_ONE_NEW = {
    "musician": [
        "{name} takes the crown ({score:.0f}). A new single, a new controversy, or both.",
        "New at number one: {name} ({score:.0f}). The algorithm finally noticed what fans knew.",
    ],
    "politician": [
        "{name} seizes number one ({score:.0f}). Something happened. Check the news.",
        "New at the top: {name} ({score:.0f}). Political fame usually means political trouble.",
    ],
    "actor": [
        "{name} climbs to number one ({score:.0f}). A premiere, perhaps, or a red carpet moment gone viral.",
        "New at the top: {name} ({score:.0f}). Hollywood giveth.",
    ],
    "athlete": [
        "{name} takes number one ({score:.0f}). A big win, or a bigger controversy.",
        "New at the top: {name} ({score:.0f}). The world loves a winner.",
    ],
    "business": [
        "{name} reaches number one ({score:.0f}). They probably posted something.",
        "New at the top: {name} ({score:.0f}). Money talks, and this week it shouted.",
    ],
    "creator": [
        "{name} takes the crown ({score:.0f}). A viral moment broke through.",
        "New at number one: {name} ({score:.0f}). The internet made its choice.",
    ],
}

_CLIMBER_TEMPLATES = {
    "musician": [
        "{name} rose {delta:.0f} points. New release? Scandal? Same difference to the algorithm.",
        "{name} is up {delta:.0f}. Spotify playlists noticed.",
        "Up {delta:.0f}: {name}. The streaming numbers don't lie.",
    ],
    "politician": [
        "{name} surged {delta:.0f} points. Nobody gains political fame for doing something boring.",
        "Up {delta:.0f}: {name}. Parliament/Congress said something, presumably.",
        "{name} climbed {delta:.0f}. Headlines were made. Whether intentionally is unclear.",
    ],
    "actor": [
        "{name} rose {delta:.0f} points. A trailer dropped, or a paparazzi shot went viral.",
        "Up {delta:.0f}: {name}. The press tour paid off.",
        "{name} climbed {delta:.0f}. Hollywood's attention machine cranks forward.",
    ],
    "athlete": [
        "{name} surged {delta:.0f} points. A big performance, clearly.",
        "Up {delta:.0f}: {name}. Winning is the oldest form of marketing.",
        "{name} rose {delta:.0f}. The scoreboard speaks.",
    ],
    "business": [
        "{name} climbed {delta:.0f} points. They announced something, tweeted something, or bought something.",
        "Up {delta:.0f}: {name}. The market of attention rallied.",
        "{name} rose {delta:.0f}. Being controversial is free advertising.",
    ],
    "creator": [
        "{name} surged {delta:.0f} points. A video hit. The thumbnail worked.",
        "Up {delta:.0f}: {name}. The feed blessed them this week.",
        "{name} rose {delta:.0f}. Engagement bait caught something big.",
    ],
}

_FALLER_TEMPLATES = {
    "musician": [
        "{name} dropped {delta:.0f} points. No new music, no new drama, no new attention.",
        "Down {delta:.0f}: {name}. The playlist rotation moved on.",
        "{name} fell {delta:.0f}. Between albums is a lonely place.",
    ],
    "politician": [
        "{name} fell {delta:.0f} points. A slow news week for them. A blessing, probably.",
        "Down {delta:.0f}: {name}. Other politicians stole the oxygen.",
        "{name} dropped {delta:.0f}. The news cycle is a jealous god.",
    ],
    "actor": [
        "{name} dropped {delta:.0f} points. Between projects. The spotlight wanders.",
        "Down {delta:.0f}: {name}. Hollywood's goldfish memory strikes again.",
        "{name} fell {delta:.0f}. No premieres this week.",
    ],
    "athlete": [
        "{name} fell {delta:.0f} points. Off-season, or off-form. Either way, less attention.",
        "Down {delta:.0f}: {name}. A quiet week on the field.",
        "{name} dropped {delta:.0f}. Sports fame is ruthlessly present-tense.",
    ],
    "business": [
        "{name} dropped {delta:.0f} points. Didn't post. Didn't announce. Didn't exist, briefly.",
        "Down {delta:.0f}: {name}. The market of attention corrected.",
        "{name} fell {delta:.0f}. Even billionaires have quiet weeks.",
    ],
    "creator": [
        "{name} fell {delta:.0f} points. The algorithm giveth, the algorithm taketh away.",
        "Down {delta:.0f}: {name}. Upload schedule slipped, perhaps.",
        "{name} dropped {delta:.0f}. Yesterday's viral is today's forgotten.",
    ],
}

_NEW_ENTRY = [
    "{name} enters at #{rank}. Welcome to the fishbowl.",
    "New: {name} at #{rank}. Fame found them this week.",
    "{name} appears at #{rank}. First time on the index. Won't be the last.",
    "A new face: {name} at #{rank}. The world noticed.",
]

# Fallback for unknown categories
_GENERIC_CLIMBER = "{name} is up {delta:.0f} points. Something happened."
_GENERIC_FALLER = "{name} dropped {delta:.0f} points. The world moved on."
_GENERIC_HOLDS = "{name} stays at number one ({score:.0f}). Immovable."
_GENERIC_NEW_TOP = "{name} takes number one ({score:.0f}). A new era, possibly brief."


def _get_category_for_person(person_id: int, scores: list) -> str:
    """Look up a person's category from the scores list."""
    for sc in scores:
        if sc.person_id == person_id:
            return sc.person.category
    return "other"


def _commentary(templates: dict, category: str, **kwargs) -> str:
    """Pick a random template for the given category and format it."""
    pool = templates.get(category, templates.get("musician", []))
    if not pool:
        return ""
    return random.choice(pool).format(**kwargs)


def generate_weekly_post(week: str) -> dict:
    """
    Generate the weekly blog post for a given week.

    Args:
        week: ISO week string.

    Returns:
        Dict with keys:
        - "title": str (the post headline)
        - "content": str (full HTML content)
        - "summary": str (one-line summary for SEO)
        - "movers": dict (climbers and fallers featured)
    """
    scores = get_scores_for_week(week)
    if not scores:
        return {
            "title": f"Fame Index — Week {week}",
            "content": "<p>No data available for this week.</p>",
            "summary": f"Fame Index rankings for week {week}.",
            "movers": {"climbers": [], "fallers": []},
        }

    prev_week = previous_week(week)
    prev_scores = get_scores_for_week(prev_week)
    prev_top = prev_scores[0].person_id if prev_scores else None

    movers = biggest_movers(week, n=5)
    sections = []

    # --- Number One ---
    top = scores[0]
    cat = top.person.category or "musician"
    if top.person_id == prev_top:
        templates = _NUMBER_ONE_HOLDS
        commentary = _commentary(templates, cat, name=top.person.name, score=top.fame_score)
        if not commentary:
            commentary = _GENERIC_HOLDS.format(name=top.person.name, score=top.fame_score)
    else:
        templates = _NUMBER_ONE_NEW
        commentary = _commentary(templates, cat, name=top.person.name, score=top.fame_score)
        if not commentary:
            commentary = _GENERIC_NEW_TOP.format(name=top.person.name, score=top.fame_score)
    sections.append(f"<h3>This Week's Number One</h3>\n<p>{commentary}</p>")

    # --- Biggest Climbers ---
    if movers["climbers"]:
        climber_lines = []
        for pid, name, momentum in movers["climbers"][:5]:
            cat = _get_category_for_person(pid, scores)
            delta = abs(momentum)
            line = _commentary(_CLIMBER_TEMPLATES, cat, name=name, delta=delta)
            if not line:
                line = _GENERIC_CLIMBER.format(name=name, delta=delta)
            climber_lines.append(f"<li>{line}</li>")
        climbers_html = "<ul>\n" + "\n".join(climber_lines) + "\n</ul>"
        sections.append(f"<h3>Biggest Climbers</h3>\n{climbers_html}")

    # --- Fastest Fallers ---
    if movers["fallers"]:
        faller_lines = []
        for pid, name, momentum in movers["fallers"][:5]:
            cat = _get_category_for_person(pid, scores)
            delta = abs(momentum)
            line = _commentary(_FALLER_TEMPLATES, cat, name=name, delta=delta)
            if not line:
                line = _GENERIC_FALLER.format(name=name, delta=delta)
            faller_lines.append(f"<li>{line}</li>")
        fallers_html = "<ul>\n" + "\n".join(faller_lines) + "\n</ul>"
        sections.append(f"<h3>Fastest Fallers</h3>\n{fallers_html}")

    # --- New Entries ---
    prev_ids = {sc.person_id for sc in prev_scores} if prev_scores else set()
    new_entries = [
        sc for sc in scores
        if sc.person_id not in prev_ids and sc.rank
    ]
    if new_entries:
        entry_lines = []
        for sc in new_entries[:5]:
            line = random.choice(_NEW_ENTRY).format(name=sc.person.name, rank=sc.rank)
            entry_lines.append(f"<li>{line}</li>")
        entries_html = "<ul>\n" + "\n".join(entry_lines) + "\n</ul>"
        sections.append(f"<h3>New Entries</h3>\n{entries_html}")

    content = "\n\n".join(sections)

    # Build headline
    headline = _make_headline(top, movers, scores)
    title = f"Fame Index — Week {week}: {headline}"
    summary = f"{top.person.name} leads the Fame Index for week {week}."

    # Store in database
    store_blog_post(week, title, content)

    return {
        "title": title,
        "content": content,
        "summary": summary,
        "movers": movers,
    }


def _make_headline(top, movers: dict, scores: list) -> str:
    """Generate a pithy headline for the blog post."""
    parts = [top.person.name]
    if movers["climbers"]:
        climber_name = movers["climbers"][0][1]
        cat = _get_category_for_person(movers["climbers"][0][0], scores)
        verbs = {
            "musician": "Surges", "actor": "Rises", "politician": "Ascends",
            "athlete": "Storms Up", "business": "Rallies", "creator": "Breaks Through",
        }
        verb = verbs.get(cat, "Climbs")
        return f"{top.person.name} Reigns, {climber_name} {verb}"
    return f"{top.person.name} Holds the Crown"
