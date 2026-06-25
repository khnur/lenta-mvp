"""/feed must never 500 on an out-of-range user_id (int32 overflow)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from lenta_core.db import get_engine


def _infra_ok() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        import redis

        from lenta_core.config import settings

        redis.Redis.from_url(settings.redis_url).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _infra_ok(), reason="db/redis not reachable")


def test_feed_out_of_range_user_id_is_422_not_500():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        # beyond int32 -> would overflow the INTEGER column in assign_variant/db.get
        assert client.get("/feed?user_id=99999999999999999999&k=5").status_code == 422
        assert client.get("/feed?user_id=2147483648&k=5").status_code == 422
        # a valid-range but non-existent user still gets a graceful cold feed
        r = client.get("/feed?user_id=2147483647&k=5")
        assert r.status_code in (200, 503)  # 503 only if no model is trained yet


def test_feed_survives_impression_insert_fk_violation(monkeypatch):
    """A concurrent reset can make the impression insert raise IntegrityError;
    the feed response must still succeed (not 500)."""
    from sqlalchemy.exc import IntegrityError

    import api.routers.feed as feedmod
    from fastapi.testclient import TestClient

    from api.main import app

    def boom(*a, **k):
        raise IntegrityError("INSERT", {}, Exception("stale FK (simulated reset)"))

    monkeypatch.setattr(feedmod, "insert_events", boom)
    with TestClient(app) as client:
        r = client.get("/feed?user_id=1&k=5&variant=treatment")
        # impression logging fails internally, but the feed itself must be fine
        assert r.status_code in (200, 503), r.status_code
        if r.status_code == 200:
            assert len(r.json()["items"]) >= 1
