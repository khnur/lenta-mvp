"""The serialized model bundle stored in Postgres (``model_versions.artifact``).

We deliberately store **raw arrays + the LightGBM booster string** rather than
pickling library objects, so serving has no hard dependency on `implicit` and is
robust across library versions. The bundle carries everything needed to score:
ALS factors, popularity table, an item-feature snapshot, per-user aggregates,
and the ranker.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ModelBundle:
    version: int
    algo: str
    n_genres: int
    genre_names: list[str]
    factors: int

    # --- ALS retrieval ---
    als_user_factors: np.ndarray
    als_item_factors: np.ndarray
    als_user_ids: np.ndarray
    als_item_ids: np.ndarray

    # --- popularity baseline / fallback ---
    pop_ids: np.ndarray
    pop_scores: np.ndarray

    # --- item-feature snapshot (arrays aligned by item_ids) ---
    item_ids: np.ndarray
    item_genre_matrix: np.ndarray  # (n_items, n_genres) row-normalised
    item_primary: np.ndarray
    item_duration: np.ndarray
    item_upload_epoch: np.ndarray
    item_pop: np.ndarray
    item_creator: np.ndarray

    # --- per-user aggregates snapshot (ranker features) ---
    user_ids_agg: np.ndarray
    user_genre_profile: np.ndarray  # (n_users, n_genres)
    user_avg_wf: np.ndarray
    user_play_rate: np.ndarray
    user_hist_count: np.ndarray

    # --- ranker ---
    ranker_model_str: str
    feature_names: list[str]

    trained_at: float = 0.0

    # lookup maps (built on construction, not serialized to avoid drift)
    _als_u: dict = field(default_factory=dict, repr=False, compare=False)
    _als_i: dict = field(default_factory=dict, repr=False, compare=False)
    _item: dict = field(default_factory=dict, repr=False, compare=False)
    _uagg: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._als_u = {int(u): i for i, u in enumerate(self.als_user_ids)}
        self._als_i = {int(v): i for i, v in enumerate(self.als_item_ids)}
        self._item = {int(v): i for i, v in enumerate(self.item_ids)}
        self._uagg = {int(u): i for i, u in enumerate(self.user_ids_agg)}

    # ---- convenience accessors ------------------------------------------- #
    def has_user(self, user_id: int) -> bool:
        return int(user_id) in self._als_u and self.user_hist_count_for(user_id) > 0

    def user_hist_count_for(self, user_id: int) -> float:
        i = self._uagg.get(int(user_id))
        return float(self.user_hist_count[i]) if i is not None else 0.0

    def als_user_vector(self, user_id: int) -> np.ndarray | None:
        i = self._als_u.get(int(user_id))
        return None if i is None else self.als_user_factors[i]

    def item_index(self, video_id: int) -> int | None:
        return self._item.get(int(video_id))

    def user_profile(self, user_id: int) -> np.ndarray:
        i = self._uagg.get(int(user_id))
        if i is None:
            return np.zeros(self.n_genres)
        return self.user_genre_profile[i]

    # ---- (de)serialization ----------------------------------------------- #
    _SERIAL_FIELDS = (
        "version", "algo", "n_genres", "genre_names", "factors",
        "als_user_factors", "als_item_factors", "als_user_ids", "als_item_ids",
        "pop_ids", "pop_scores",
        "item_ids", "item_genre_matrix", "item_primary", "item_duration",
        "item_upload_epoch", "item_pop", "item_creator",
        "user_ids_agg", "user_genre_profile", "user_avg_wf", "user_play_rate",
        "user_hist_count",
        "ranker_model_str", "feature_names", "trained_at",
    )

    def to_bytes(self) -> bytes:
        payload = {k: getattr(self, k) for k in self._SERIAL_FIELDS}
        return pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_bytes(cls, blob: bytes) -> "ModelBundle":
        payload = pickle.loads(blob)
        return cls(**payload)
