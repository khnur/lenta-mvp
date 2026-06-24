"""Funnel + cold-start serving tests (no DB)."""

from __future__ import annotations

import time

from lenta_core.ml.funnel import recommend


def test_funnel_returns_k_items(tiny):
    bundle, _ = tiny
    feed, debug = recommend(bundle, user_id=1, k=10, now_epoch=time.time())
    assert len(feed) == 10
    assert debug["catalog"] >= debug["candidates"] >= debug["feed"]
    assert debug["retrieval"] in {"als", "content", "popularity"}
    # scores are predicted watch fractions, clipped to [0, 1]
    assert all(0.0 <= it["score"] <= 1.0 for it in feed)


def test_cold_start_user_still_gets_feed(tiny):
    bundle, _ = tiny
    feed, debug = recommend(bundle, user_id=999_999, k=10, now_epoch=time.time())
    assert len(feed) > 0
    assert debug["cold_start"] is True


def test_control_variant_is_popularity(tiny):
    bundle, _ = tiny
    feed, debug = recommend(bundle, user_id=1, k=8, now_epoch=time.time(), variant="control")
    assert debug["retrieval"] == "popularity"
    assert len(feed) == 8
    assert all(it["stage"] == "popularity" for it in feed)


def test_rerank_caps_per_genre(tiny):
    bundle, _ = tiny
    feed, _ = recommend(
        bundle, user_id=2, k=12, now_epoch=time.time(), max_per_genre=3, max_per_creator=99
    )
    genres = [int(bundle.item_primary[bundle.item_index(it["video_id"])]) for it in feed]
    for g in set(genres):
        assert genres.count(g) <= 3 + 1  # cap, allowing the freshness backfill slack


def test_diversity_present(tiny):
    bundle, _ = tiny
    feed, _ = recommend(bundle, user_id=3, k=10, now_epoch=time.time())
    primaries = {int(bundle.item_primary[bundle.item_index(it["video_id"])]) for it in feed}
    assert len(primaries) >= 2  # not all one genre
