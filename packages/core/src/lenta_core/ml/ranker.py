"""LightGBM ranker. Target = **predicted watch-time fraction** (NOT click
probability): ranking on clicks breeds clickbait; watch-time optimises the
retention goal in the tech task.

The training matrix is built from the *same* feature spec the serving funnel
uses (``features.ranking``), so there is no train/serve skew.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..features.item import time_of_day_match
from ..features.ranking import FEATURE_NAMES, categorical_indices, feature_row, to_matrix
from ..logging_conf import get_logger

log = get_logger("lenta.ranker")


def build_training_matrix(
    events: pd.DataFrame,
    *,
    als: dict,
    item_index: dict[int, int],
    item_genre_matrix: np.ndarray,
    item_primary: np.ndarray,
    item_duration: np.ndarray,
    item_upload_epoch: np.ndarray,
    item_pop: np.ndarray,
    genre_names: list[str],
    user_agg: dict,
    n_genres: int,
) -> tuple[np.ndarray, np.ndarray]:
    """One row per impression; label = watch fraction achieved on that item."""
    # --- lookups ---
    als_u = {int(u): i for i, u in enumerate(als["user_ids"])}
    als_i = {int(v): i for i, v in enumerate(als["item_ids"])}
    uf, vf = als["user_factors"], als["item_factors"]

    uagg_idx = {int(u): i for i, u in enumerate(user_agg["user_ids_agg"])}
    profile = user_agg["user_genre_profile"]
    avg_wf = user_agg["user_avg_wf"]
    play_rate = user_agg["user_play_rate"]
    hist_count = user_agg["user_hist_count"]

    ev = events.sort_values("ts")
    ts_dt = pd.to_datetime(ev["ts"], utc=True)
    ev = ev.assign(tsepoch=ts_dt.astype("int64") / 1e9, hod=ts_dt.dt.hour.to_numpy())

    # label: max watch_fraction per (session, video)
    plays = ev[ev["event_type"] == "play"]
    label_lookup = (
        plays.groupby(["session_id", "video_id"])["watch_fraction"].max().to_dict()
    )

    rows: list[list[float]] = []
    labels: list[float] = []

    # iterate per session to reconstruct running session features
    for sid, grp in ev.groupby("session_id", sort=False):
        seen_genres: list[int] = []
        for r in grp.itertuples(index=False):
            etype = r.event_type
            vid = int(r.video_id)
            ii = item_index.get(vid)
            if etype != "impression" or ii is None:
                if etype == "impression":
                    continue
                # clicks/plays advance nothing extra here (genre tracked on impression)
                continue
            uid = int(r.user_id)
            pg = int(item_primary[ii])

            # retrieval features
            ui = als_u.get(uid)
            vj = als_i.get(vid)
            als_score = float(vf[vj] @ uf[ui]) if (ui is not None and vj is not None) else 0.0
            prof = profile[uagg_idx[uid]] if uid in uagg_idx else np.zeros(n_genres)
            igv = item_genre_matrix[ii]
            denom = (np.linalg.norm(prof) * np.linalg.norm(igv)) + 1e-9
            content_score = float(prof @ igv) / denom
            affinity = float(prof @ igv)

            # session features from prior impressions in this session
            slen = len(seen_genres)
            match = (seen_genres.count(pg) / slen) if slen else 0.0

            hour = int(r.hod)
            ua = uagg_idx.get(uid)
            rows.append(
                feature_row(
                    als_score=als_score,
                    content_score=content_score,
                    user_item_affinity=affinity,
                    pop_score=float(item_pop[ii]),
                    item_age_days=max(0.0, (r.tsepoch - float(item_upload_epoch[ii])) / 86400.0),
                    item_duration_log=math.log1p(float(item_duration[ii])),
                    item_primary_genre=pg,
                    u_hist_count_log=math.log1p(float(hist_count[ua]) if ua is not None else 0.0),
                    u_avg_wf=float(avg_wf[ua]) if ua is not None else 0.0,
                    u_play_rate=float(play_rate[ua]) if ua is not None else 0.0,
                    session_genre_match=match,
                    session_len=float(slen),
                    tod_match=time_of_day_match(genre_names[pg], hour),
                    hour=hour,
                )
            )
            labels.append(float(label_lookup.get((sid, vid), 0.0)))
            seen_genres.append(pg)

    X = to_matrix(rows)
    y = np.asarray(labels, dtype=np.float64)
    log.info("ranker training matrix: %d rows x %d features", X.shape[0], len(FEATURE_NAMES))
    return X, y


def train_ranker(X: np.ndarray, y: np.ndarray, *, seed: int = 42) -> str:
    """Train a LightGBM regressor on watch-fraction; return its model string."""
    from lightgbm import LGBMRegressor

    model = LGBMRegressor(
        objective="regression",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.85,
        subsample_freq=1,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        n_jobs=2,
        verbosity=-1,
    )
    model.fit(
        X,
        y,
        feature_name=FEATURE_NAMES,
        categorical_feature=categorical_indices(),
    )
    return model.booster_.model_to_string()


def load_booster(model_str: str):
    import lightgbm as lgb

    return lgb.Booster(model_str=model_str)


def predict(booster, X: np.ndarray) -> np.ndarray:
    preds = booster.predict(X)
    return np.clip(np.asarray(preds, dtype=np.float64), 0.0, 1.0)
