from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from lenta_core.eval.online import online_metrics_sql
from lenta_core.models import utcnow
from lenta_core.schemas import MetricsResponse, VariantMetrics

from ..deps import get_db

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    window_minutes: int = Query(30, ge=1, le=1440),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    cutoff = utcnow() - timedelta(minutes=window_minutes)
    m = online_metrics_sql(db, cutoff=cutoff)
    return MetricsResponse(
        window_minutes=window_minutes,
        overall=VariantMetrics(**m["overall"]),
        per_variant=[VariantMetrics(**v) for v in m["per_variant"]],
        lift=m["lift"],
    )
