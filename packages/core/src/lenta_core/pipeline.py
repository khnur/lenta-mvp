"""Pipeline-status helpers — records stage runs (ingest / feature_update /
retrain / deploy) for the dashboard's pipeline panel."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import PipelineRun, utcnow

STAGES = ["ingest", "feature_update", "retrain", "deploy"]


def start_stage(session: Session, stage: str, detail: dict | None = None) -> PipelineRun:
    run = PipelineRun(stage=stage, status="running", started_at=utcnow(), detail=detail or {})
    session.add(run)
    session.commit()
    return run


def finish_stage(
    session: Session, run: PipelineRun, *, status: str = "ok", detail: dict | None = None
) -> None:
    run.finished_at = utcnow()
    started = run.started_at
    if started is not None:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
    run.status = status
    if detail is not None:
        merged = dict(run.detail or {})
        merged.update(detail)
        run.detail = merged
    session.commit()


def latest_by_stage(session: Session) -> dict[str, PipelineRun]:
    out: dict[str, PipelineRun] = {}
    for stage in STAGES:
        run = (
            session.execute(
                select(PipelineRun)
                .where(PipelineRun.stage == stage)
                .order_by(PipelineRun.started_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if run:
            out[stage] = run
    return out


def recent_runs(session: Session, limit: int = 20) -> list[PipelineRun]:
    return list(
        session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        ).scalars()
    )


def prune_runs(session: Session, keep: int = 500) -> int:
    """Keep only the most recent ``keep`` pipeline-run rows (heartbeats accumulate)."""
    max_id = session.execute(select(func.max(PipelineRun.id))).scalar()
    if max_id is None:
        return 0
    threshold = max_id - keep
    if threshold <= 0:
        return 0
    return session.execute(delete(PipelineRun).where(PipelineRun.id < threshold)).rowcount
