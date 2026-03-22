"""
Database package for the Fame Index.

Provides the SQLAlchemy engine, session factory, and base model class.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from server.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)


def get_session():
    """Get a new database session."""
    return Session()


def init_db():
    """Create all tables. Idempotent — safe to call multiple times."""
    from server.db import models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(engine)
