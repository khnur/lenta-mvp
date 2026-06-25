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


def test_event_with_oversized_strings_is_422_not_500():
    """Over-length variant / session_id used to overflow their varchar columns
    and surface as a 500; they must now be rejected at validation."""
    from fastapi.testclient import TestClient

    from api.main import app

    base = {
        "user_id": 1,
        "video_id": 1,
        "event_type": "impression",
        "session_id": "ok",
    }
    with TestClient(app) as client:
        # variant must be one of the A/B values, not an arbitrary (long) string
        r = client.post("/event", json={**base, "variant": "totally-bogus-variant"})
        assert r.status_code == 422
        # session_id is bounded to the column width (64)
        r = client.post("/event", json={**base, "session_id": "x" * 500})
        assert r.status_code == 422


def test_event_rejects_bad_enum_and_range():
    from fastapi.testclient import TestClient

    from api.main import app

    base = {"user_id": 1, "video_id": 1, "session_id": "ok"}
    with TestClient(app) as client:
        assert client.post("/event", json={**base, "event_type": "like"}).status_code == 422
        assert (
            client.post(
                "/event", json={**base, "event_type": "play", "watch_fraction": 1.5}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/event", json={**base, "event_type": "play", "watch_seconds": -5.0}
            ).status_code
            == 422
        )
