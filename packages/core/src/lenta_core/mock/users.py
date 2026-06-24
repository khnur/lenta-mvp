"""User generation: each user has a latent per-genre affinity vector that the
simulator uses to drive choices. The recommender never sees these directly —
it must *learn* them from behaviour."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

# A handful of named cohorts, each peaked on a couple of genre indices, so that
# collaborative filtering has real structure to discover.
_COHORTS: list[tuple[str, list[int]]] = [
    ("comedy_fans", [0, 3]),
    ("drama_buffs", [1, 9]),
    ("gamers", [4, 2]),
    ("sports_news", [5, 6]),
    ("learners", [10, 7]),
    ("foodie_travel", [8, 9]),
    ("kids_family", [11, 0]),
    ("eclectic", []),  # flat-ish taste
]


def generate_users(
    n_users: int,
    *,
    n_genres: int,
    rng: np.random.Generator,
    now: datetime | None = None,
) -> list[dict]:
    """Generate ``n_users`` user rows with latent affinity vectors (ids 1..n)."""
    now = now or datetime.now(timezone.utc)
    users: list[dict] = []
    for i in range(n_users):
        uid = i + 1
        cohort_name, peaks = _COHORTS[int(rng.integers(0, len(_COHORTS)))]
        affinity = _affinity_vector(peaks, n_genres, rng)
        created = now - timedelta(days=float(rng.uniform(1, 365)))
        users.append(
            {
                "id": uid,
                "cohort": cohort_name,
                "affinity": affinity.tolist(),
                "is_synthetic": True,
                "created_at": created,
            }
        )
    return users


def _affinity_vector(peaks: list[int], n_genres: int, rng: np.random.Generator) -> np.ndarray:
    """A softmax-normalised affinity vector, optionally peaked on cohort genres."""
    base = rng.gamma(shape=0.5, size=n_genres)
    for p in peaks:
        if p < n_genres:
            base[p] += rng.uniform(2.5, 5.0)
    vec = base / base.sum()
    return vec.astype(np.float64)


def new_user_rows(
    start_id: int,
    count: int,
    *,
    n_genres: int,
    rng: np.random.Generator,
    cohort: str = "cold_start",
    now: datetime | None = None,
) -> list[dict]:
    """Brand-new users (used by the cold_start_wave scenario)."""
    now = now or datetime.now(timezone.utc)
    rows: list[dict] = []
    for j in range(count):
        uid = start_id + j
        peaks = list(rng.choice(n_genres, size=2, replace=False))
        rows.append(
            {
                "id": uid,
                "cohort": cohort,
                "affinity": _affinity_vector(peaks, n_genres, rng).tolist(),
                "is_synthetic": True,
                "created_at": now,
            }
        )
    return rows
