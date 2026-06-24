"""Control-plane job queue (Postgres `jobs` table).

The api enqueues retrain jobs; the trainer polls + claims them. A DB table (vs
pure pub/sub) gives durability and a visible history for the dashboard.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import Job, utcnow


def enqueue_job(session: Session, job_type: str, payload: dict | None = None) -> Job:
    job = Job(type=job_type, status="queued", payload=payload or {})
    session.add(job)
    session.flush()
    return job


def queued_jobs(session: Session, job_type: str | None = None, *, lock: bool = False) -> list[Job]:
    q = select(Job).where(Job.status == "queued").order_by(Job.created_at)
    if job_type:
        q = q.where(Job.type == job_type)
    if lock:
        # row-level lock so a second poller/replica can't claim the same job
        q = q.with_for_update(skip_locked=True)
    return list(session.execute(q).scalars())


def claim_job(session: Session, job: Job) -> None:
    job.status = "running"
    job.started_at = utcnow()
    session.flush()


def finish_job(session: Session, job: Job, *, status: str = "done", result: dict | None = None) -> None:
    job.status = status
    job.result = result or {}
    job.finished_at = utcnow()
    session.flush()


def recent_jobs(session: Session, limit: int = 20) -> list[Job]:
    return list(
        session.execute(select(Job).order_by(Job.created_at.desc()).limit(limit)).scalars()
    )


def prune_jobs(session: Session, keep: int = 200) -> int:
    """Keep only the most recent ``keep`` job rows."""
    max_id = session.execute(select(func.max(Job.id))).scalar()
    if max_id is None:
        return 0
    threshold = max_id - keep
    if threshold <= 0:
        return 0
    return session.execute(delete(Job).where(Job.id < threshold)).rowcount
