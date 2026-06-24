"""Offline ranking metrics + a held-out evaluation driver.

Metrics: Recall@K, NDCG@K (binary relevance from held-out plays), catalog
coverage, and intra-list (genre) diversity.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..ml.artifacts import ModelBundle
from ..ml.funnel import recommend
from ..ml.ranker import load_booster

RELEVANT_WF = 0.3  # a play counts as "relevant" if watched at least this fraction


def recall_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    topk = set(recommended[:k])
    return len(topk & relevant) / len(relevant)


def ndcg_at_k(recommended: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    dcg = 0.0
    for i, v in enumerate(recommended[:k]):
        if v in relevant:
            dcg += 1.0 / math.log2(i + 2)
    ideal = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def coverage(reco_lists: list[list[int]], catalog_size: int, k: int) -> float:
    if catalog_size <= 0:
        return 0.0
    seen: set[int] = set()
    for lst in reco_lists:
        seen.update(lst[:k])
    return len(seen) / catalog_size


def intra_list_diversity(reco_list: list[int], genre_lookup: dict[int, np.ndarray]) -> float:
    """1 - mean pairwise cosine similarity of item genre vectors."""
    vecs = [genre_lookup[v] for v in reco_list if v in genre_lookup]
    if len(vecs) < 2:
        return 0.0
    M = np.vstack(vecs)
    M = M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)
    sims = M @ M.T
    n = len(vecs)
    off = (sims.sum() - np.trace(sims)) / (n * (n - 1))
    return float(1.0 - off)


def evaluate_bundle(
    bundle: ModelBundle,
    holdout: pd.DataFrame,
    *,
    k: int = 10,
    now_epoch: float,
    max_users: int = 200,
    seed: int = 42,
) -> dict:
    """Evaluate a bundle against held-out future plays."""
    plays = holdout[(holdout["event_type"] == "play") & (holdout["watch_fraction"] >= RELEVANT_WF)]
    relevant: dict[int, set[int]] = {
        int(u): set(int(v) for v in g)
        for u, g in plays.groupby("user_id")["video_id"]
    }
    if not relevant:
        return {"recall_at_k": 0.0, "ndcg_at_k": 0.0, "coverage": 0.0,
                "diversity": 0.0, "k": k, "n_users": 0}

    rng = np.random.default_rng(seed)
    users = list(relevant.keys())
    if len(users) > max_users:
        users = list(rng.choice(users, size=max_users, replace=False))

    genre_lookup = {int(v): bundle.item_genre_matrix[i] for i, v in enumerate(bundle.item_ids)}
    booster = load_booster(bundle.ranker_model_str)

    recalls, ndcgs, divs, reco_lists = [], [], [], []
    for uid in users:
        feed, _ = recommend(bundle, int(uid), k, now_epoch=now_epoch, booster=booster)
        rec = [it["video_id"] for it in feed]
        rel = relevant[int(uid)]
        recalls.append(recall_at_k(rec, rel, k))
        ndcgs.append(ndcg_at_k(rec, rel, k))
        divs.append(intra_list_diversity(rec, genre_lookup))
        reco_lists.append(rec)

    return {
        "recall_at_k": round(float(np.mean(recalls)), 4),
        "ndcg_at_k": round(float(np.mean(ndcgs)), 4),
        "coverage": round(coverage(reco_lists, len(bundle.item_ids), k), 4),
        "diversity": round(float(np.mean(divs)), 4),
        "k": k,
        "n_users": len(users),
    }
