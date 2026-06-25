"""DEMO_LOCK disables the destructive /reset endpoint (403) for public demos."""

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


def test_reset_blocked_when_demo_locked(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    from lenta_core.config import settings as core_settings

    with TestClient(app) as client:
        # locked -> 403, and /health advertises the lock
        monkeypatch.setattr(core_settings, "demo_lock", True)
        assert client.post("/reset").status_code == 403
        assert client.get("/health").json().get("demo_lock") is True

        # unlocked (default) -> reset is accepted again, health flag is false
        monkeypatch.setattr(core_settings, "demo_lock", False)
        assert client.post("/reset").status_code == 200
        assert client.get("/health").json().get("demo_lock") is False
