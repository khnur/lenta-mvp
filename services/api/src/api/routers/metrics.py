from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from lenta_core.eval.online import online_metrics
from lenta_core.ingest import load_events_df_since
from lenta_core.models import utcnow
from lenta_core.schemas import MetricsResponse, VariantMetrics

from ..deps import get_db

router = APIRouter(tags=["metrics"])

_EMPTY = {
    "variant": "overall", "impressions": 0, "clicks": 0, "plays": 0,
    "ctr": 0.0, "avg_watch_seconds": 0.0, "avg_watch_fraction": 0.0,
    "avg_session_length": 0.0,
}


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    window_minutes: int = Query(30, ge=1, le=1440),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    df = load_events_df_since(db, utcnow() - timedelta(minutes=window_minutes))
    if df.empty:
        return MetricsResponse(
            window_minutes=window_minutes,
            overall=VariantMetrics(**_EMPTY),
            per_variant=[],
            lift={},
        )
    m = online_metrics(df)
    return MetricsResponse(
        window_minutes=window_minutes,
        overall=VariantMetrics(**m["overall"]),
        per_variant=[VariantMetrics(**v) for v in m["per_variant"]],
        lift=m["lift"],
    )
