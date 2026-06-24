from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import get_db, get_state
from ..state import AppState

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db), state: AppState = Depends(get_state)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "redis": state.ping_redis(),
        "model_ready": state.model.ready,
        "model_version": state.model.version,
    }


@router.get("/")
def root(state: AppState = Depends(get_state)) -> dict:
    return {
        "service": "lenta-api",
        "model_version": state.model.version,
        "endpoints": [
            "/feed", "/event", "/metrics", "/models", "/retrain",
            "/sim/start", "/sim/stop", "/sim/scenario", "/sim/status",
            "/pipeline/status", "/events/recent", "/sessions/active",
            "/report", "/users/sample", "/health", "/docs",
        ],
    }
