"""Model bundle serialization round-trip (the unit stored in Postgres bytea)."""

from __future__ import annotations

import time

import numpy as np

from lenta_core.ml.artifacts import ModelBundle
from lenta_core.ml.funnel import recommend


def test_bundle_bytes_roundtrip(tiny):
    bundle, _ = tiny
    blob = bundle.to_bytes()
    assert isinstance(blob, bytes) and len(blob) > 0

    restored = ModelBundle.from_bytes(blob)
    assert restored.version == bundle.version
    assert restored.n_genres == bundle.n_genres
    np.testing.assert_array_equal(restored.item_ids, bundle.item_ids)
    np.testing.assert_allclose(restored.als_user_factors, bundle.als_user_factors)
    # lookup maps rebuilt on load
    assert restored.has_user(1) == bundle.has_user(1)


def test_roundtrip_preserves_predictions(tiny):
    bundle, _ = tiny
    restored = ModelBundle.from_bytes(bundle.to_bytes())
    now = time.time()
    f1, _ = recommend(bundle, 1, 10, now_epoch=now)
    f2, _ = recommend(restored, 1, 10, now_epoch=now)
    assert [i["video_id"] for i in f1] == [i["video_id"] for i in f2]
