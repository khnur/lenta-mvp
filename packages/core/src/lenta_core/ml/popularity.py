"""Popularity baseline (the A/B control) and global fallback.

Recency-weighted play counts: recent engagement counts more, so the baseline
itself drifts as behaviour shifts — a fair, non-trivial control.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def popularity_table(
    events: pd.DataFrame, *, now_epoch: float, half_life_days: float = 14.0
) -> tuple[np.ndarray, np.ndarray]:
    """Return (video_ids, scores) sorted by recency-weighted engagement, desc."""
    plays = events[events["event_type"].isin(["play", "click"])].copy()
    if plays.empty:
        return np.array([], dtype=np.int64), np.array([], dtype=float)

    ts = pd.to_datetime(plays["ts"], utc=True).astype("int64") / 1e9
    age_days = np.clip((now_epoch - ts.to_numpy()) / 86400.0, 0, None)
    decay = np.power(0.5, age_days / half_life_days)
    # plays weighted by watch_fraction, clicks count a little
    base = np.where(
        plays["event_type"].to_numpy() == "play",
        1.0 + plays["watch_fraction"].fillna(0.0).to_numpy(float),
        0.3,
    )
    plays["w"] = base * decay
    agg = plays.groupby("video_id")["w"].sum().sort_values(ascending=False)
    return agg.index.to_numpy(dtype=np.int64), agg.to_numpy(dtype=float)


def top_popular(pop_ids: np.ndarray, pop_scores: np.ndarray, k: int) -> list[tuple[int, float]]:
    n = min(k, len(pop_ids))
    smax = float(pop_scores[0]) if len(pop_scores) else 1.0
    return [(int(pop_ids[i]), float(pop_scores[i] / (smax + 1e-9))) for i in range(n)]
