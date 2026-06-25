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


def reset_db(*, attempts: int = 6) -> None:
    """Wipe all data but keep the schema (TRUNCATE ... RESTART IDENTITY).

    Used by the 'reset DB' demo control. Truncating rather than dropping means
    concurrent api request handlers / the simulator never observe missing tables
    mid-reset — they just briefly see empty tables, which the code handles.

    TRUNCATE needs an ACCESS EXCLUSIVE lock on every table; under live write
    traffic (the simulator hits /feed + /event at ~180/s) that can deadlock or
    block against in-flight inserts. We cap the wait with a short lock_timeout
    and retry on deadlock/timeout with backoff so a reset reliably lands.
    """
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    init_db()  # ensure the schema exists first
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    last: Exception | None = None
    for i in range(attempts):
        try:
            with get_engine().begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '4s'"))
                conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
            return
        except DBAPIError as exc:  # deadlock (40P01) / lock_timeout (55P03)
            code = getattr(getattr(exc, "orig", None), "sqlstate", None)
            if code not in ("40P01", "55P03"):
                raise
            last = exc
            time.sleep(0.4 * (i + 1))
    if last is not None:
        raise last
