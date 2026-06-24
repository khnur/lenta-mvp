"""SQLAlchemy engine + session helpers. The engine is created lazily."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_session() -> Session:
    """Return a new Session. Caller is responsible for closing it."""
    return _session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error, always close."""
    s = get_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    """Create all tables if they do not exist (idempotent)."""
    Base.metadata.create_all(get_engine())


def reset_db() -> None:
    """Wipe all data but keep the schema (TRUNCATE ... RESTART IDENTITY).

    Used by the 'reset DB' demo control. Truncating rather than dropping means
    concurrent api request handlers / the simulator never observe missing tables
    mid-reset — they just briefly see empty tables, which the code handles.
    """
    from sqlalchemy import text

    init_db()  # ensure the schema exists first
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
