"""
Database models for the Fame Index.

Uses SQLAlchemy 2.0 ORM with SQLite in development and PostgreSQL in production.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db import Base


class Person(Base):
    """A public figure tracked by the Fame Index."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    wikipedia_title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="other")
    region: Mapped[str] = mapped_column(String(50), default="global")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Optional identifiers for cultural output sources
    spotify_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    scores: Mapped[list["Score"]] = relationship(back_populates="person")
    signals: Mapped[list["Signal"]] = relationship(back_populates="person")


class Score(Base):
    """A weekly fame score for a person."""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    week: Mapped[str] = mapped_column(String(10), nullable=False)

    # Headline score
    fame_score: Mapped[float] = mapped_column(Float, default=0.0)
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, nullable=True)

    # Five public dimension scores (0-100 each)
    dim_search: Mapped[float] = mapped_column(Float, default=0.0)
    dim_news: Mapped[float] = mapped_column(Float, default=0.0)
    dim_social: Mapped[float] = mapped_column(Float, default=0.0)
    dim_cultural: Mapped[float] = mapped_column(Float, default=0.0)
    dim_institutional: Mapped[float] = mapped_column(Float, default=0.0)

    # Metadata
    sentiment_polarity: Mapped[float] = mapped_column(Float, default=0.0)
    controversy_index: Mapped[float] = mapped_column(Float, default=0.0)

    person: Mapped["Person"] = relationship(back_populates="scores")


class Signal(Base):
    """A raw data signal from a specific source for a person in a week."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    week: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)  # search/news/social/cultural/institutional
    raw_value: Mapped[float] = mapped_column(Float, default=0.0)
    normalised_value: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    person: Mapped["Person"] = relationship(back_populates="signals")


class BlogPost(Base):
    """A generated blog post for a given week."""

    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    week: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
