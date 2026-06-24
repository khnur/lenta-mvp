"""Test fixtures: build a small ModelBundle entirely in memory (no Postgres),
so the funnel/eval tests run anywhere."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from lenta_core.features.ranking import FEATURE_NAMES
from lenta_core.features.user import build_user_aggregates
from lenta_core.mock.catalog import generate_catalog, genre_list
from lenta_core.mock.simulate import World, simulate_backfill
from lenta_core.mock.users import generate_users
from lenta_core.ml.als import train_als
from lenta_core.ml.artifacts import ModelBundle
from lenta_core.ml.popularity import popularity_table
from lenta_core.ml.ranker import build_training_matrix, train_ranker

NG = 8


def _epoch(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _snapshot(videos: list[dict], n_genres: int) -> dict:
    names = genre_list(n_genres)
    gindex = {g: i for i, g in enumerate(names)}
    ids, G, prim, dur, up, pop, cr = [], [], [], [], [], [], []
    for v in videos:
        vec = np.zeros(n_genres)
        idxs = [gindex[g] for g in v["genres"] if g in gindex] or [0]
        vec[idxs] = 1.0
        vec /= vec.sum()
        ids.append(v["id"])
        G.append(vec)
        prim.append(idxs[0])
        dur.append(float(v["duration_seconds"]))
        up.append(_epoch(v["upload_time"]))
        pop.append(float(v["base_popularity"]))
        cr.append(int(v["creator_id"]))
    return {
        "genre_names": names,
        "item_ids": np.asarray(ids, dtype=np.int64),
        "item_genre_matrix": np.asarray(G),
        "item_primary": np.asarray(prim, dtype=np.int64),
        "item_duration": np.asarray(dur),
        "item_upload_epoch": np.asarray(up),
        "item_pop": np.asarray(pop),
        "item_creator": np.asarray(cr, dtype=np.int64),
    }


def build_tiny_bundle(seed: int = 0) -> tuple[ModelBundle, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    videos = generate_catalog(60, n_genres=NG, backfill_days=14, rng=rng, now=now)
    users = generate_users(50, n_genres=NG, rng=rng, now=now)
    world = World.from_rows(users, videos, n_genres=NG, rng=rng)
    events = simulate_backfill(
        world, 4000, rng=rng, start=now - timedelta(days=14), end=now
    )
    df = pd.DataFrame(events)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    snap = _snapshot(videos, NG)
    user_ids = np.asarray([u["id"] for u in users], dtype=np.int64)
    item_index = {int(v): i for i, v in enumerate(snap["item_ids"])}
    now_epoch = _epoch(df["ts"].max())

    als = train_als(
        df, user_ids, snap["item_ids"], factors=16, iterations=6, seed=seed,
        now_epoch=now_epoch,
    )
    pop_ids, pop_scores = popularity_table(df, now_epoch=now_epoch)
    uagg = build_user_aggregates(
        df, user_ids, item_index=item_index,
        item_genre_matrix=snap["item_genre_matrix"], n_genres=NG, now_epoch=now_epoch,
    )
    X, y, w = build_training_matrix(
        df, als=als, item_index=item_index,
        item_genre_matrix=snap["item_genre_matrix"], item_primary=snap["item_primary"],
        item_duration=snap["item_duration"], item_upload_epoch=snap["item_upload_epoch"],
        item_pop=snap["item_pop"], genre_names=snap["genre_names"], user_agg=uagg,
        n_genres=NG, now_epoch=now_epoch,
    )
    ranker_str = train_ranker(X, y, sample_weight=w, seed=seed)

    bundle = ModelBundle(
        version=1, algo="als+lightgbm", n_genres=NG, genre_names=snap["genre_names"],
        factors=16,
        als_user_factors=als["user_factors"], als_item_factors=als["item_factors"],
        als_user_ids=als["user_ids"], als_item_ids=als["item_ids"],
        pop_ids=pop_ids, pop_scores=pop_scores,
        item_ids=snap["item_ids"], item_genre_matrix=snap["item_genre_matrix"],
        item_primary=snap["item_primary"], item_duration=snap["item_duration"],
        item_upload_epoch=snap["item_upload_epoch"], item_pop=snap["item_pop"],
        item_creator=snap["item_creator"],
        user_ids_agg=uagg["user_ids_agg"], user_genre_profile=uagg["user_genre_profile"],
        user_avg_wf=uagg["user_avg_wf"], user_play_rate=uagg["user_play_rate"],
        user_hist_count=uagg["user_hist_count"],
        ranker_model_str=ranker_str, feature_names=FEATURE_NAMES, trained_at=now_epoch,
    )
    return bundle, df


@pytest.fixture(scope="session")
def tiny():
    return build_tiny_bundle(seed=0)
