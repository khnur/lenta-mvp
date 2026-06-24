"""API smoke test via FastAPI TestClient. Skips when DB/Redis are unreachable."""

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


def test_health_and_docs():
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert "model_ready" in body and "db" in body and "redis" in body

        r2 = client.get("/")
        assert r2.status_code == 200
        assert "/feed" in r2.json()["endpoints"]
