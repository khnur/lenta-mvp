"""Registry round-trip through Postgres bytea. Skips when no DB is reachable."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from lenta_core.db import get_engine, init_db, session_scope
from lenta_core.ml.artifacts import ModelBundle
from lenta_core.registry import load_active_model, next_version, save_model_version


def _db_available() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="no database reachable")


def test_registry_roundtrips_artifact(tiny):
    bundle, _ = tiny
    # work on a copy so we don't mutate the shared session fixture
    copy = ModelBundle.from_bytes(bundle.to_bytes())
    init_db()
    with session_scope() as s:
        copy.version = next_version(s)
        mv = save_model_version(
            s, copy, metrics={"recall_at_k": 0.1, "ndcg_at_k": 0.05},
            train_rows=123, set_active=True, notes="pytest",
        )
        saved_version = mv.version
        assert mv.artifact_bytes > 0

    with session_scope() as s:
        loaded = load_active_model(s)
        assert loaded is not None
        mv2, restored = loaded
        assert mv2.version == saved_version
        assert restored.n_genres == bundle.n_genres
        assert restored.item_ids.shape == bundle.item_ids.shape
        assert restored.has_user(1) == bundle.has_user(1)
