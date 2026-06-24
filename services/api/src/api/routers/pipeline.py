from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from lenta_core.ingest import counts
from lenta_core.pipeline import STAGES, latest_by_stage, recent_runs
from lenta_core.registry import active_version
from lenta_core.schemas import PipelineStageStatus, PipelineStatusResponse

from ..deps import get_db

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status(db: Session = Depends(get_db)) -> PipelineStatusResponse:
    latest = latest_by_stage(db)
    stages = []
    for stage in STAGES:
        run = latest.get(stage)
        stages.append(
            PipelineStageStatus(
                stage=stage,
                status=run.status if run else "idle",
                last_run=run.started_at if run else None,
                duration_ms=run.duration_ms if run else None,
                detail=run.detail if run else None,
            )
        )
    runs = [
        PipelineStageStatus(
            stage=r.stage,
            status=r.status,
            last_run=r.started_at,
            duration_ms=r.duration_ms,
            detail=r.detail,
        )
        for r in recent_runs(db, 20)
    ]
    return PipelineStatusResponse(
        stages=stages,
        active_model_version=active_version(db),
        total_events=counts(db)["events"],
        runs=runs,
    )
