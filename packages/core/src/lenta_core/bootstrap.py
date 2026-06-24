"""High-level orchestration reused by the CLI and the trainer service:
seed the database, and train + register a model version.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from .config import settings
from .db import init_db, reset_db, session_scope
from .ingest import counts, insert_events, insert_users, insert_videos
from .logging_conf import get_logger
from .mock.catalog import generate_catalog
from .mock.simulate import World, simulate_backfill
from .mock.users import generate_users
from .ml.train import train_bundle
from .registry import next_version, save_model_version

log = get_logger("lenta.bootstrap")


def seed_database(*, demo: bool = False, reset: bool = True, seed: int | None = None) -> dict:
    """Generate catalog + users + a historical event backfill, write to Postgres."""
    s = settings
    seed = s.seed if seed is None else seed
    rng = np.random.default_rng(seed)
    now = datetime.now(timezone.utc)

    n_videos, n_users = s.n_videos, s.n_users
    backfill_events, backfill_days = s.backfill_events, s.backfill_days
    if demo:  # a clean, quick, compelling starting state
        n_videos = min(n_videos, 400)
        n_users = min(n_users, 300)
        backfill_events = min(backfill_events, 25_000)
        backfill_days = min(backfill_days, 21)

    if reset:
        reset_db()
    else:
        init_db()

    log.info("seeding: %d videos, %d users, ~%d events", n_videos, n_users, backfill_events)
    videos = generate_catalog(
        n_videos, n_genres=s.n_genres, backfill_days=backfill_days, rng=rng, now=now
    )
    users = generate_users(n_users, n_genres=s.n_genres, rng=rng, now=now)

    with session_scope() as sess:
        insert_users(sess, users)
        insert_videos(sess, videos)

    world = World.from_rows(users, videos, n_genres=s.n_genres, rng=rng)
    events = simulate_backfill(
        world, backfill_events, rng=rng,
        start=now - timedelta(days=backfill_days), end=now,
    )
    with session_scope() as sess:
        insert_events(sess, events)
        c = counts(sess)
    log.info("seed complete: %s", c)
    return c


def train_and_register(*, notes: str = "", set_active: bool = True) -> tuple[int, dict]:
    """Train the next model version on current DB events and register it."""
    with session_scope() as sess:
        version = next_version(sess)
        bundle, metrics, rows = train_bundle(sess, version=version)
        save_model_version(
            sess, bundle, metrics=metrics, train_rows=rows, set_active=set_active, notes=notes
        )
    return version, metrics
