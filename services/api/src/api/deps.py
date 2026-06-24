"""FastAPI dependencies: db session, app state, redis."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from lenta_core.db import get_session

from .state import AppState


def get_db() -> Iterator[Session]:
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def get_state(request: Request) -> AppState:
    return request.app.state.svc


def get_redis(request: Request):
    return request.app.state.svc.redis
