"""The canonical ranker feature spec — the single source of train/serve parity.

Add a feature here and it is automatically used by both the training-matrix
builder (trainer) and the serving funnel (api). The order of FEATURE_NAMES is
the column order of the matrix fed to LightGBM.
"""

from __future__ import annotations

import numpy as np

FEATURE_NAMES: list[str] = [
    "als_score",            # retrieval: latent factor dot product
    "content_score",        # retrieval: cosine(user profile, item genres)
    "user_item_affinity",   # dot(user genre profile, item genre vector)
    "pop_score",            # item base popularity
    "item_age_days",        # freshness
    "item_duration_log",    # log(1 + duration_seconds)
    "item_primary_genre",   # categorical (genre index)
    "u_hist_count_log",     # log(1 + user history size)
    "u_avg_wf",             # user's historical avg watch fraction
    "u_play_rate",          # user's plays / impressions
    "session_genre_match",  # share of session so far matching item primary genre
    "session_len",          # items seen in the session so far
    "tod_match",            # time-of-day match for the item's primary genre
    "hour",                 # hour of day (0-23)
]

# Names LightGBM should treat as categorical.
CATEGORICAL_FEATURES: list[str] = ["item_primary_genre"]


def feature_row(
    *,
    als_score: float,
    content_score: float,
    user_item_affinity: float,
    pop_score: float,
    item_age_days: float,
    item_duration_log: float,
    item_primary_genre: int,
    u_hist_count_log: float,
    u_avg_wf: float,
    u_play_rate: float,
    session_genre_match: float,
    session_len: float,
    tod_match: float,
    hour: int,
) -> list[float]:
    """Build one feature row in canonical FEATURE_NAMES order."""
    return [
        float(als_score),
        float(content_score),
        float(user_item_affinity),
        float(pop_score),
        float(item_age_days),
        float(item_duration_log),
        float(item_primary_genre),
        float(u_hist_count_log),
        float(u_avg_wf),
        float(u_play_rate),
        float(session_genre_match),
        float(session_len),
        float(tod_match),
        float(hour),
    ]


def categorical_indices() -> list[int]:
    return [FEATURE_NAMES.index(n) for n in CATEGORICAL_FEATURES]


def to_matrix(rows: list[list[float]]) -> np.ndarray:
    return np.asarray(rows, dtype=np.float64)
