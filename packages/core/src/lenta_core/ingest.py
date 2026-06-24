"""Bulk inserts (seeding) + single-event ingestion (serving path)."""

from __future__ import annotations

from datetime import timezone

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from .models import Event, User, Video, utcnow


def insert_users(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    session.execute(insert(User), rows)
    return len(rows)


def insert_videos(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    session.execute(insert(Video), rows)
    return len(rows)


def insert_events(session: Session, rows: list[dict], *, batch: int = 5000) -> int:
    """Bulk-insert event dicts in batches."""
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        session.execute(insert(Event), chunk)
        total += len(chunk)
    return total


def insert_event(session: Session, ev: dict) -> Event:
    """Insert one event (serving ingestion path) and return the ORM row."""
    row = Event(
        user_id=ev["user_id"],
        video_id=ev["video_id"],
        event_type=ev["event_type"],
        watch_seconds=ev.get("watch_seconds", 0.0),
        watch_fraction=ev.get("watch_fraction", 0.0),
        session_id=ev["session_id"],
        variant=ev.get("variant") or "treatment",
        ts=ev.get("ts") or utcnow(),
        context=ev.get("context"),
    )
    session.add(row)
    session.flush()
    return row


def counts(session: Session) -> dict[str, int]:
    return {
        "users": int(session.execute(select(func.count(User.id))).scalar() or 0),
        "videos": int(session.execute(select(func.count(Video.id))).scalar() or 0),
        "events": int(session.execute(select(func.count(Event.id))).scalar() or 0),
    }


def load_events_df(session: Session, *, since_days: int | None = None) -> pd.DataFrame:
    """Load events into a DataFrame for training / metrics."""
    q = select(
        Event.user_id,
        Event.video_id,
        Event.event_type,
        Event.watch_seconds,
        Event.watch_fraction,
        Event.session_id,
        Event.variant,
        Event.ts,
    )
    if since_days is not None:
        cutoff = utcnow() - pd.Timedelta(days=since_days)
        q = q.where(Event.ts >= cutoff)
    rows = session.execute(q).all()
    df = pd.DataFrame(
        rows,
        columns=[
            "user_id", "video_id", "event_type", "watch_seconds",
            "watch_fraction", "session_id", "variant", "ts",
        ],
    )
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def recent_events_df(session: Session, *, window_minutes: int) -> pd.DataFrame:
    cutoff = utcnow() - pd.Timedelta(minutes=window_minutes)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return load_events_df_since(session, cutoff)


def load_events_df_since(session: Session, cutoff) -> pd.DataFrame:
    rows = session.execute(
        select(
            Event.user_id, Event.video_id, Event.event_type, Event.watch_seconds,
            Event.watch_fraction, Event.session_id, Event.variant, Event.ts,
        ).where(Event.ts >= cutoff)
    ).all()
    df = pd.DataFrame(
        rows,
        columns=[
            "user_id", "video_id", "event_type", "watch_seconds",
            "watch_fraction", "session_id", "variant", "ts",
        ],
    )
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df
