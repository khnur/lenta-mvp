"""Eval metric tests: ranges + sanity."""

from __future__ import annotations

import numpy as np

from lenta_core.eval.offline import (
    coverage,
    evaluate_bundle,
    intra_list_diversity,
    ndcg_at_k,
    recall_at_k,
)
from lenta_core.eval.online import online_metrics


def test_metric_functions_valid_ranges():
    rec = [1, 2, 3, 4, 5]
    rel = {2, 4, 9}
    assert 0.0 <= recall_at_k(rec, rel, 5) <= 1.0
    assert 0.0 <= ndcg_at_k(rec, rel, 5) <= 1.0
    assert recall_at_k(rec, rel, 5) == 2 / 3
    assert ndcg_at_k(rec, [], 5) == 0.0
    assert coverage([[1, 2], [2, 3]], catalog_size=10, k=2) == 0.3


def test_intra_list_diversity_range():
    g = {1: np.array([1.0, 0.0]), 2: np.array([0.0, 1.0]), 3: np.array([1.0, 0.0])}
    d = intra_list_diversity([1, 2, 3], g)
    assert 0.0 <= d <= 1.0


def test_evaluate_bundle_in_range(tiny):
    bundle, df = tiny
    holdout = df.tail(800)
    now = float(holdout["ts"].max().timestamp())
    m = evaluate_bundle(bundle, holdout, k=10, now_epoch=now, max_users=40)
    for key in ("recall_at_k", "ndcg_at_k", "coverage", "diversity"):
        assert 0.0 <= m[key] <= 1.0, f"{key}={m[key]} out of range"
    assert isinstance(m["feed_genre_share"], dict)


def test_online_metrics_lift(tiny):
    _, df = tiny
    df = df.copy()
    df["variant"] = np.where(df.index % 2 == 0, "treatment", "control")
    m = online_metrics(df)
    assert "overall" in m and "per_variant" in m and "lift" in m
    assert 0.0 <= m["overall"]["ctr"] <= 1.0
