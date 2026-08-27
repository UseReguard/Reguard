"""SQLAlchemy engine + session management.

Works with both SQLite (default) and PostgreSQL (set DATABASE_URL).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from compliance.config import DATABASE_URL, SQLALCHEMY_ECHO


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_engine():
    """Create SQLAlchemy engine based on DATABASE_URL.

    SQLite-specific args:
    - check_same_thread=False (we use a single thread per request)

    PostgreSQL-specific args:
    - pool_pre_ping=True (handles dropped connections)
    """
    connect_args = {}
    engine_kwargs = {"echo": SQLALCHEMY_ECHO}

    if DATABASE_URL.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        engine_kwargs["pool_pre_ping"] = True

    return create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)


_engine = None
_SessionLocal = None


def get_session_factory():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = get_engine()
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for a transactional session.

    Usage:
        with session_scope() as session:
            session.add(obj)
            ...
        # commits on exit, rolls back on exception
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables. Idempotent — safe to run multiple times."""
    from . import models  # noqa: F401 (register models)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


if __name__ == "__main__":
    # Allow `python3 src/db.py` to create the DB
    print(f"DATABASE_URL={DATABASE_URL}")
    init_db()
    print("Database initialized.")