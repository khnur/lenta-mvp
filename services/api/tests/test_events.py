"""/event must never 500 on a bad FK (e.g. a stale event after a reset)."""

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


def test_event_with_unknown_user_does_not_500():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        r = client.post(
            "/event",
            json={
                "user_id": 2_000_000_001,
                "video_id": 2_000_000_001,
                "event_type": "play",
                "session_id": "fk-test",
                "watch_seconds": 1.0,
                "watch_fraction": 0.5,
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False
