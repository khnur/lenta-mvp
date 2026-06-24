"""Content-based retrieval — the cold-start fallback.

Builds a user's genre/tag profile from their watch history and scores items by
cosine similarity. Used when ALS has no signal for a user (brand-new user) and
to surface brand-new videos (no interactions yet, so invisible to ALS).
"""

from __future__ import annotations

import numpy as np


def normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.clip(norms, 1e-9, None)


def user_genre_profile(
    watched_genre_vectors: list[np.ndarray], weights: list[float], n_genres: int
) -> np.ndarray:
    """Watch-weighted average of the genre vectors a user engaged with."""
    if not watched_genre_vectors:
        return np.zeros(n_genres)
    M = np.vstack(watched_genre_vectors)
    w = np.asarray(weights, dtype=float).reshape(-1, 1)
    profile = (M * w).sum(axis=0)
    s = profile.sum()
    return profile / s if s > 0 else profile


def content_scores(item_genre_matrix: np.ndarray, profile: np.ndarray) -> np.ndarray:
    """Cosine similarity of a user profile to every item's genre vector."""
    if profile.sum() <= 0:
        return np.zeros(item_genre_matrix.shape[0])
    p = profile / (np.linalg.norm(profile) + 1e-9)
    items = normalize_rows(item_genre_matrix)
    return items @ p
