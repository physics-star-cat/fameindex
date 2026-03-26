"""
Database query helpers for the Fame Index.
"""

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from server.db import get_session
from server.db.models import Person, Score, Signal


def get_all_persons(active_only: bool = True) -> list[Person]:
    """Retrieve all tracked persons."""
    with get_session() as session:
        stmt = select(Person)
        if active_only:
            stmt = stmt.where(Person.active == True)  # noqa: E712
        return list(session.scalars(stmt).all())


def get_person_by_id(person_id: int) -> Person | None:
    """Retrieve a single person by ID."""
    with get_session() as session:
        return session.get(Person, person_id)


def get_scores_for_week(week: str) -> list[Score]:
    """Get all fame scores for a given week, ranked by score descending."""
    with get_session() as session:
        stmt = (
            select(Score)
            .options(joinedload(Score.person))
            .where(Score.week == week)
            .order_by(Score.fame_score.desc())
        )
        return list(session.scalars(stmt).unique().all())


def get_person_history(person_id: int, num_weeks: int = 12) -> list[Score]:
    """Get historical scores for a person, most recent first."""
    with get_session() as session:
        stmt = (
            select(Score)
            .options(joinedload(Score.person))
            .where(Score.person_id == person_id)
            .order_by(Score.week.desc())
            .limit(num_weeks)
        )
        return list(session.scalars(stmt).unique().all())


def get_signals_for_person_week(person_id: int, week: str) -> list[Signal]:
    """Get all signals for a person in a specific week."""
    with get_session() as session:
        stmt = (
            select(Signal)
            .where(Signal.person_id == person_id, Signal.week == week)
        )
        return list(session.scalars(stmt).all())


def get_dimension_signals(person_id: int, week: str, dimension: str) -> list[Signal]:
    """Get all signals for a person in a specific dimension and week."""
    with get_session() as session:
        stmt = (
            select(Signal)
            .where(
                Signal.person_id == person_id,
                Signal.week == week,
                Signal.dimension == dimension,
            )
        )
        return list(session.scalars(stmt).all())


def get_historical_signals(person_id: int, source: str, num_weeks: int = 12) -> list[Signal]:
    """Get historical signal values for normalisation baselines."""
    with get_session() as session:
        stmt = (
            select(Signal)
            .where(Signal.person_id == person_id, Signal.source == source)
            .order_by(Signal.week.desc())
            .limit(num_weeks)
        )
        return list(session.scalars(stmt).all())


def store_signals(signals: list[dict]) -> None:
    """Store a batch of signals in the database."""
    with get_session() as session:
        for sig in signals:
            obj = Signal(
                person_id=sig["person_id"],
                week=sig["week"],
                source=sig["source"],
                dimension=sig["dimension"],
                raw_value=sig["raw_value"],
                normalised_value=sig.get("normalised_value", 0.0),
            )
            session.add(obj)
        session.commit()


def store_scores(scores: list[dict]) -> None:
    """Store a batch of scores in the database."""
    with get_session() as session:
        for sc in scores:
            obj = Score(
                person_id=sc["person_id"],
                week=sc["week"],
                fame_score=sc["fame_score"],
                momentum=sc.get("momentum", 0.0),
                rank=sc.get("rank"),
                dim_search=sc.get("dim_search", 0.0),
                dim_news=sc.get("dim_news", 0.0),
                dim_social=sc.get("dim_social", 0.0),
                dim_cultural=sc.get("dim_cultural", 0.0),
                dim_institutional=sc.get("dim_institutional", 0.0),
                sentiment_polarity=sc.get("sentiment_polarity", 0.0),
                controversy_index=sc.get("controversy_index", 0.0),
            )
            session.add(obj)
        session.commit()


def get_person_by_slug(slug: str) -> Person | None:
    """Retrieve a single person by slug."""
    with get_session() as session:
        stmt = select(Person).where(Person.slug == slug)
        return session.scalars(stmt).first()


def get_all_scored_weeks() -> list[str]:
    """Get all weeks that have scores, most recent first."""
    with get_session() as session:
        stmt = (
            select(Score.week)
            .distinct()
            .order_by(Score.week.desc())
        )
        return list(session.scalars(stmt).all())


def get_blog_post(week: str):
    """Get a blog post by week."""
    from server.db.models import BlogPost
    with get_session() as session:
        stmt = select(BlogPost).where(BlogPost.week == week)
        return session.scalars(stmt).first()


def get_all_blog_posts():
    """Get all published blog posts, most recent first."""
    from server.db.models import BlogPost
    with get_session() as session:
        stmt = (
            select(BlogPost)
            .where(BlogPost.published == True)  # noqa: E712
            .order_by(BlogPost.week.desc())
        )
        return list(session.scalars(stmt).all())


def store_blog_post(week: str, title: str, content: str) -> None:
    """Store or update a blog post."""
    from server.db.models import BlogPost
    with get_session() as session:
        stmt = select(BlogPost).where(BlogPost.week == week)
        existing = session.scalars(stmt).first()
        if existing:
            existing.title = title
            existing.content = content
            existing.published = True
        else:
            session.add(BlogPost(week=week, title=title, content=content, published=True))
        session.commit()


def upsert_signal(person_id: int, week: str, source: str, dimension: str,
                  raw_value: float, normalised_value: float = 0.0) -> None:
    """Insert or update a single signal."""
    with get_session() as session:
        stmt = (
            select(Signal)
            .where(
                Signal.person_id == person_id,
                Signal.week == week,
                Signal.source == source,
            )
        )
        existing = session.scalars(stmt).first()
        if existing:
            existing.raw_value = raw_value
            existing.normalised_value = normalised_value
            existing.dimension = dimension
        else:
            session.add(Signal(
                person_id=person_id,
                week=week,
                source=source,
                dimension=dimension,
                raw_value=raw_value,
                normalised_value=normalised_value,
            ))
        session.commit()
