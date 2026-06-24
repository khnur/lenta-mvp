"""End-to-end training orchestration: DB events -> ModelBundle + offline metrics.

Time-based split (train on the past, evaluate on held-out future) so the metrics
reflect real generalisation, not memorisation.
"""

from __future__ import annotations

from datetime import timezone

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..eval.offline import evaluate_bundle
from ..features.ranking import FEATURE_NAMES
from ..features.user import build_user_aggregates
from ..ingest import load_events_df
from ..logging_conf import get_logger
from ..mock.catalog import genre_list
from ..models import User, Video
from .als import train_als
from .artifacts import ModelBundle
from .popularity import popularity_table
from .ranker import build_training_matrix, train_ranker

log = get_logger("lenta.train")


def _epoch(ts) -> float:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.timestamp()


def load_item_snapshot(session: Session, n_genres: int) -> dict:
    videos = session.execute(select(Video).order_by(Video.id)).scalars().all()
    names = genre_list(n_genres)
    gindex = {g: i for i, g in enumerate(names)}
    ids, G, prim, dur, up, pop, cr = [], [], [], [], [], [], []
    for v in videos:
        vec = np.zeros(n_genres)
        idxs = [gindex[g] for g in v.genres if g in gindex] or [0]
        vec[idxs] = 1.0
        vec /= vec.sum()
        ids.append(v.id)
        G.append(vec)
        prim.append(idxs[0])
        dur.append(float(v.duration_seconds))
        up.append(_epoch(v.upload_time))
        pop.append(float(v.base_popularity))
        cr.append(int(v.creator_id))
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


def train_bundle(
    session: Session,
    *,
    version: int,
    n_genres: int | None = None,
    factors: int = 64,
    holdout_fraction: float = 0.15,
    k: int = 10,
    seed: int | None = None,
) -> tuple[ModelBundle, dict, int]:
    n_genres = n_genres or settings.n_genres
    seed = settings.seed if seed is None else seed

    events = load_events_df(session)
    if events.empty:
        raise ValueError("train_bundle: no events to train on (seed first)")

    snap = load_item_snapshot(session, n_genres)
    user_ids = np.asarray(
        [u[0] for u in session.execute(select(User.id).order_by(User.id)).all()], dtype=np.int64
    )
    item_index = {int(v): i for i, v in enumerate(snap["item_ids"])}

    # ---- time-based split ----
    events = events.sort_values("ts")
    cutoff = events["ts"].quantile(1.0 - holdout_fraction)
    train = events[events["ts"] <= cutoff]
    holdout = events[events["ts"] > cutoff]
    if train.empty or holdout["event_type"].eq("play").sum() < 10:
        train, holdout = events, events  # tiny dataset fallback
    now_epoch = _epoch(events["ts"].max())

    log.info("training v%d: %d train events, %d holdout", version, len(train), len(holdout))

    # ---- retrieval + baselines ----
    als = train_als(train, user_ids, snap["item_ids"], factors=factors, seed=seed)
    pop_ids, pop_scores = popularity_table(train, now_epoch=_epoch(cutoff))

    user_agg = build_user_aggregates(
        train, user_ids,
        item_index=item_index,
        item_genre_matrix=snap["item_genre_matrix"],
        n_genres=n_genres,
    )

    # ---- ranker ----
    X, y = build_training_matrix(
        train,
        als=als,
        item_index=item_index,
        item_genre_matrix=snap["item_genre_matrix"],
        item_primary=snap["item_primary"],
        item_duration=snap["item_duration"],
        item_upload_epoch=snap["item_upload_epoch"],
        item_pop=snap["item_pop"],
        genre_names=snap["genre_names"],
        user_agg=user_agg,
        n_genres=n_genres,
    )
    ranker_str = train_ranker(X, y, seed=seed)

    bundle = ModelBundle(
        version=version,
        algo="als+lightgbm",
        n_genres=n_genres,
        genre_names=snap["genre_names"],
        factors=factors,
        als_user_factors=als["user_factors"],
        als_item_factors=als["item_factors"],
        als_user_ids=als["user_ids"],
        als_item_ids=als["item_ids"],
        pop_ids=pop_ids,
        pop_scores=pop_scores,
        item_ids=snap["item_ids"],
        item_genre_matrix=snap["item_genre_matrix"],
        item_primary=snap["item_primary"],
        item_duration=snap["item_duration"],
        item_upload_epoch=snap["item_upload_epoch"],
        item_pop=snap["item_pop"],
        item_creator=snap["item_creator"],
        user_ids_agg=user_agg["user_ids_agg"],
        user_genre_profile=user_agg["user_genre_profile"],
        user_avg_wf=user_agg["user_avg_wf"],
        user_play_rate=user_agg["user_play_rate"],
        user_hist_count=user_agg["user_hist_count"],
        ranker_model_str=ranker_str,
        feature_names=FEATURE_NAMES,
        trained_at=now_epoch,
    )

    metrics = evaluate_bundle(
        bundle, holdout, k=k, now_epoch=_epoch(holdout["ts"].max()), seed=seed
    )
    # genre-share of feeds is the headline the dashboard reports on
    metrics["train_events"] = int(len(train))
    log.info("v%d metrics: %s", version, metrics)
    return bundle, metrics, int(len(X))
