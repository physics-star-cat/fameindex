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

import json
import logging
import random
import re
from pathlib import Path

from server.blog.reasons import describe_move, describe_new_entry
from server.db.queries import get_scores_for_week, store_blog_post
from server.scoring.momentum import biggest_movers
from server.data.week_utils import previous_period, period_to_dates


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

# Fallback for unknown categories
_GENERIC_CLIMBER = "{name} is up {delta:.0f} points. Something happened."
_GENERIC_FALLER = "{name} dropped {delta:.0f} points. The world moved on."
_GENERIC_HOLDS = "{name} stays at number one ({score:.0f}). Immovable."
_GENERIC_NEW_TOP = "{name} takes number one ({score:.0f}). A new era, possibly brief."


# ---------------------------------------------------------------------------
# Search titles and descriptions
# ---------------------------------------------------------------------------
# Owner's rule: the title tells the searcher what they get. Outcome first, brand
# last, month spelled out ("September 2026", never "2026-M09"). Titles must fit
# a search result (~60 chars), descriptions 155.

TITLE_MAX = 60
DESCRIPTION_MAX = 155

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]

_CLIMBER_VERBS = {
    "musician": "Surges", "actor": "Rises", "politician": "Ascends",
    "athlete": "Storms Up", "business": "Rallies", "creator": "Breaks Through",
}


def period_human(period: str, in_sentence: bool = False) -> str:
    """
    '2026-M09' -> 'September 2026'; legacy '2026-W13' -> 'Week of 23 March 2026'
    ('the week of ...' when it sits mid-sentence). Anything else unchanged.
    """
    if period and "-M" in period:
        year_str, m_str = period.split("-M", 1)
        try:
            return f"{_MONTH_NAMES[int(m_str) - 1]} {year_str}"
        except (ValueError, IndexError):
            return period
    if period and "-W" in period:
        try:
            start, _ = period_to_dates(period)
        except ValueError:
            return period
        label = f"week of {start.day} {_MONTH_NAMES[start.month - 1]} {start.year}"
        return f"the {label}" if in_sentence else label[0].upper() + label[1:]
    return period


def post_title(top_name: str, period: str) -> str:
    """'Ed Sheeran Tops the Fame Index, September 2026' — shortened to fit."""
    when = period_human(period)
    for title in (
        f"{top_name} Tops the Fame Index, {when}",
        f"{top_name} Is No. 1, {when}",
        f"{top_name} Tops the Fame Index",
    ):
        if len(title) <= TITLE_MAX:
            return title
    return f"{top_name} Is No. 1"[:TITLE_MAX]


def post_description(top_name: str, period: str,
                     climber: str | None = None, faller: str | None = None) -> str:
    """Outcome first: who is number one, then the biggest moves. <=155 chars."""
    lead = f"{top_name} is No. 1 in the Fame Index for {period_human(period, in_sentence=True)}."
    moves = []
    if climber:
        moves.append(f"Biggest climber: {climber}.")
    if faller:
        moves.append(f"Biggest faller: {faller}.")
    tail = "Who rose, who fell, and why."
    for parts in ([lead, *moves, tail], [lead, *moves], [lead, *moves[:1]], [lead]):
        text = " ".join(parts)
        if len(text) <= DESCRIPTION_MAX:
            return text
    return lead[:DESCRIPTION_MAX]


# Titles stored before 2026-10-13: "Fame Index — 2026-M09: Ed Sheeran Reigns,
# Olaf Scholz Ascends" / "Fame Index — Week 2026-W04: The Weeknd Holds the Crown".
_LEGACY_TITLE = re.compile(
    r"^Fame Index — (?:Week )?\S+: (?P<top>.+?) "
    r"(?:Reigns(?:, (?P<climber>.+?) (?:" + "|".join(
        sorted(set(_CLIMBER_VERBS.values()) | {"Climbs"}, key=len, reverse=True)
    ) + r"))?|Holds the Crown)$"
)
_CURRENT_TITLE = re.compile(r"^(?P<top>.+?) (?:Tops the Fame Index|Is No\. 1)\b")

# One mover line in a stored post. Current posts: "Olaf Scholz up 26 — ...";
# the early weekly posts used rotating phrasings ("Up 3: BTS.", "Rosalía
# dropped 15 points.").
_MOVER_PATTERNS = (
    re.compile(r"^(?:Up|Down) \d+: (?P<name>.+?)\."),
    re.compile(r"^(?P<name>.+?) (?:is up|is down|up|down|surged|rose|climbed|"
               r"fell|dropped) \d+"),
)


def _first_mover(content: str, heading: str, skip: str | None) -> str | None:
    """Name of the first person listed under a post section, other than skip."""
    section = re.search(rf"<h3>{heading}</h3>\s*<ul>(.*?)</ul>", content or "", re.S)
    if not section:
        return None
    for item in re.findall(r"<li>(.*?)</li>", section.group(1), re.S):
        text = re.sub(r"<[^>]+>", "", item).strip()
        for pattern in _MOVER_PATTERNS:
            m = pattern.match(text)
            if m:
                name = m.group("name").strip()
                if name != skip:
                    return name
                break
    return None


def post_meta(period: str, stored_title: str, content: str) -> dict:
    """
    Search title and description for a stored post, whatever style its title
    was stored in. The render step uses this so that posts written before the
    title rule changed ship the same style as new ones, without rewriting the
    database (posts and their URLs are untouched).
    """
    legacy = _LEGACY_TITLE.match(stored_title or "")
    current = None if legacy else _CURRENT_TITLE.match(stored_title or "")
    match = legacy or current
    if not match:
        # Unknown shape: keep the stored title rather than guess at a name.
        return {"title": stored_title, "description": ""}
    top = match.group("top")
    climber = (legacy.group("climber") if legacy else None) or \
        _first_mover(content, "Biggest Climbers", skip=top)
    faller = _first_mover(content, "Fastest Fallers", skip=top)
    return {
        "title": post_title(top, period) if legacy else stored_title,
        "description": post_description(top, period, climber, faller),
    }


def _get_category_for_person(person_id: int, scores: list) -> str:
    """Look up a person's category from the scores list."""
    for sc in scores:
        if sc.person_id == person_id:
            return sc.person.category
    return "other"


NOTES_DIR = Path(__file__).resolve().parents[2] / "data" / "month_notes"


def month_notes(period: str) -> dict[str, str]:
    """
    Hand-researched reasons for one month, keyed by person's name.

    Signals say what moved, not what happened. Each note states a checked
    real-world event; data/month_notes/README.md gives the rules.
    """
    path = NOTES_DIR / f"{period}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _mover_line(name: str, direction: str, delta: float, reason: str | None,
                note: str | None) -> str:
    line = f"{name} {direction} {delta:.0f}"
    detail = "; ".join(x for x in (reason, note) if x)
    return f"{line} — {detail}." if detail else f"{line}."


def _commentary(templates: dict, category: str, **kwargs) -> str:
    """Pick a random template for the given category and format it."""
    pool = templates.get(category, [])
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
            "title": f"Fame Index, {period_human(week)}",
            "content": "<p>No data available for this period.</p>",
            "summary": f"Fame Index rankings for {period_human(week, in_sentence=True)}.",
            "movers": {"climbers": [], "fallers": []},
        }

    prev_week = previous_period(week)
    prev_scores = get_scores_for_week(prev_week)
    prev_top = prev_scores[0].person_id if prev_scores else None

    movers = biggest_movers(week, n=5)
    notes = month_notes(week)
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
    if notes.get(top.person.name):
        # A checked reason replaces the stock line rather than following it.
        commentary = f"{top.person.name} ({top.fame_score:.0f}): {notes[top.person.name]}."
    sections.append(f"<h3>Number One</h3>\n<p>{commentary}</p>")

    # --- Biggest Climbers ---
    if movers["climbers"]:
        climber_lines = []
        for pid, name, momentum in movers["climbers"][:3]:
            delta = abs(momentum)
            # The reason comes from whichever stored signal actually moved most.
            # If nothing moved enough to name, we say nothing rather than
            # reaching for a stock line — that is how the old generator ended up
            # attributing the same phrase to two different people in one post.
            reason = describe_move(pid, week, prev_week, rising=True)
            line = _mover_line(name, "up", delta, reason, notes.get(name))
            climber_lines.append(f"<li>{line}</li>")
        climbers_html = "<ul>\n" + "\n".join(climber_lines) + "\n</ul>"
        sections.append(f"<h3>Biggest Climbers</h3>\n{climbers_html}")

    # --- Fastest Fallers ---
    if movers["fallers"]:
        faller_lines = []
        for pid, name, momentum in movers["fallers"][:3]:
            delta = abs(momentum)
            reason = describe_move(pid, week, prev_week, rising=False)
            line = _mover_line(name, "down", delta, reason, notes.get(name))
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
        for sc in new_entries:
            # New to our table, not new to fame: someone can be famous for years
            # before joining. Say why they are here, never that fame just found them.
            reason = notes.get(sc.person.name) or describe_new_entry(
                sc.person_id, (week, period_human(week, in_sentence=True)))
            if not notes.get(sc.person.name):
                logging.getLogger(__name__).warning(
                    "new entry %s has no written reason in data/month_notes/%s.json",
                    sc.person.name, week)
            line = f"{sc.person.name} joins the table at #{sc.rank}"
            line += f": {reason}." if reason else "."
            entry_lines.append(f"<li>{line}</li>")
        entries_html = "<ul>\n" + "\n".join(entry_lines) + "\n</ul>"
        sections.append(f"<h3>New to the Table</h3>\n{entries_html}")

    content = "\n\n".join(sections)

    # Search title and description: outcome first, month spelled out. The
    # climber (never the number one — see _make_headline) goes in the
    # description, which has room for it.
    climber = next((c[1] for c in movers["climbers"] if c[0] != top.person_id), None)
    faller = movers["fallers"][0][1] if movers["fallers"] else None
    title = post_title(top.person.name, week)
    summary = post_description(top.person.name, week, climber, faller)

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
    # Skip the number one when choosing a climber. Someone can top the chart AND
    # be the biggest riser — Christopher Nolan did both in 2026-M07 — which
    # produced the headline "Christopher Nolan Reigns, Christopher Nolan Climbs".
    climbers = [c for c in movers["climbers"] if c[0] != top.person_id]
    if climbers:
        climber_name = climbers[0][1]
        cat = _get_category_for_person(climbers[0][0], scores)
        verb = _CLIMBER_VERBS.get(cat, "Climbs")
        return f"{top.person.name} Reigns, {climber_name} {verb}"
    return f"{top.person.name} Holds the Crown"
