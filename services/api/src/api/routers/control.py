"""Control plane: retrain triggers, simulator control, DB reset."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lenta_core import simctl
from lenta_core.config import settings
from lenta_core.jobs import enqueue_job
from lenta_core.schemas import RetrainAck, SimControlIn, SimScenarioIn, SimStatus

from ..deps import get_db, get_redis

router = APIRouter(tags=["control"])


def _status(r) -> SimStatus:
    s = simctl.get_sim(r)
    return SimStatus(
        running=s["running"], rate=s["rate"], scenario=s["scenario"], emitted=s["emitted"]
    )


@router.post("/retrain", response_model=RetrainAck)
def post_retrain(db: Session = Depends(get_db)) -> RetrainAck:
    job = enqueue_job(db, "retrain", {"source": "api"})
    db.commit()
    return RetrainAck(job_id=job.id, status=job.status)


@router.post("/reset", response_model=RetrainAck)
def post_reset(db: Session = Depends(get_db)) -> RetrainAck:
    """Queue a full reset + reseed + retrain (handled by the trainer)."""
    if settings.demo_lock:
        raise HTTPException(
            status_code=403,
            detail="Reset is disabled on this deployment (DEMO_LOCK).",
        )
    job = enqueue_job(db, "reset", {"source": "api"})
    db.commit()
    return RetrainAck(job_id=job.id, status=job.status)


@router.post("/sim/start", response_model=SimStatus)
def sim_start(body: SimControlIn | None = None, r=Depends(get_redis)) -> SimStatus:
    simctl.set_running(r, True, rate=body.rate if body else None)
    return _status(r)


@router.post("/sim/stop", response_model=SimStatus)
def sim_stop(r=Depends(get_redis)) -> SimStatus:
    simctl.set_running(r, False)
    return _status(r)


@router.post("/sim/scenario", response_model=SimStatus)
def sim_scenario(body: SimScenarioIn, r=Depends(get_redis)) -> SimStatus:
    simctl.request_scenario(r, body.scenario, body.intensity)
    return _status(r)


@router.get("/sim/status", response_model=SimStatus)
def sim_status(r=Depends(get_redis)) -> SimStatus:
    return _status(r)
