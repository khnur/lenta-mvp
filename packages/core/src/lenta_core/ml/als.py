"""ALS implicit-feedback collaborative filtering (candidate generation).

We weight implicit signals by intent: a completed play counts far more than a
bare impression. Training returns raw factor matrices that the serving funnel
scores with a plain dot product (no `implicit` dependency at serve time).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from threadpoolctl import threadpool_limits

from ..logging_conf import get_logger

log = get_logger("lenta.als")

# implicit weighting of one event toward the (user, item) confidence.
_EVENT_WEIGHT = {"impression": 0.1, "click": 1.0, "play": 2.0}
_PLAY_WATCH_BONUS = 6.0  # added as bonus * watch_fraction on plays


def event_weight(event_type: str, watch_fraction: float) -> float:
    w = _EVENT_WEIGHT.get(event_type, 0.0)
    if event_type == "play":
        w += _PLAY_WATCH_BONUS * float(watch_fraction or 0.0)
    return w


def build_interaction_matrix(
    events: pd.DataFrame,
    user_ids: np.ndarray,
    item_ids: np.ndarray,
    *,
    now_epoch: float | None = None,
    half_life_days: float = 3.0,
) -> sp.csr_matrix:
    """Aggregate events into a (n_users x n_items) confidence CSR matrix.

    When ``now_epoch`` is given, weights decay with event age (half-life in days)
    so recent behaviour dominates and the model adapts to preference shifts.
    """
    uidx = {int(u): i for i, u in enumerate(user_ids)}
    iidx = {int(v): i for i, v in enumerate(item_ids)}

    w = events["event_type"].map(_EVENT_WEIGHT).fillna(0.0).to_numpy(dtype=float)
    play_mask = (events["event_type"] == "play").to_numpy()
    w = w + play_mask * _PLAY_WATCH_BONUS * events["watch_fraction"].fillna(0.0).to_numpy(float)

    if now_epoch is not None:
        ts = pd.to_datetime(events["ts"], utc=True).astype("int64").to_numpy() / 1e9
        age_days = np.clip((now_epoch - ts) / 86400.0, 0, None)
        w = w * np.power(0.5, age_days / max(half_life_days, 1e-6))

    rows = events["user_id"].map(uidx).to_numpy()
    cols = events["video_id"].map(iidx).to_numpy()
    valid = ~(pd.isna(rows) | pd.isna(cols)) & (w > 0)

    mat = sp.coo_matrix(
        (w[valid], (rows[valid].astype(int), cols[valid].astype(int))),
        shape=(len(user_ids), len(item_ids)),
        dtype=np.float32,
    )
    return mat.tocsr()


def train_als(
    events: pd.DataFrame,
    user_ids: np.ndarray,
    item_ids: np.ndarray,
    *,
    factors: int = 64,
    iterations: int = 18,
    regularization: float = 0.05,
    seed: int = 42,
    now_epoch: float | None = None,
    half_life_days: float = 3.0,
) -> dict:
    """Train ALS and return factor matrices aligned to ``user_ids`` / ``item_ids``."""
    from implicit.als import AlternatingLeastSquares

    ui = build_interaction_matrix(
        events, user_ids, item_ids, now_epoch=now_epoch, half_life_days=half_life_days
    )
    log.info(
        "ALS: %d users x %d items, %d nonzeros, factors=%d",
        ui.shape[0], ui.shape[1], ui.nnz, factors,
    )
    model = AlternatingLeastSquares(
        factors=factors,
        iterations=iterations,
        regularization=regularization,
        random_state=seed,
        use_gpu=False,
    )
    # Avoid the OpenBLAS threadpool perf trap implicit warns about.
    with threadpool_limits(limits=1, user_api="blas"):
        model.fit(ui, show_progress=False)

    return {
        "user_factors": np.asarray(model.user_factors, dtype=np.float32),
        "item_factors": np.asarray(model.item_factors, dtype=np.float32),
        "user_ids": np.asarray(user_ids, dtype=np.int64),
        "item_ids": np.asarray(item_ids, dtype=np.int64),
        "factors": factors,
    }


def als_candidate_scores(
    user_factors_row: np.ndarray, item_factors: np.ndarray
) -> np.ndarray:
    """Score all items for one user via dot product of latent factors."""
    return item_factors @ user_factors_row
