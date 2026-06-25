"""Read endpoints that feed the dashboard's live panels."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from lenta_core.features.session import active_session_count, recent_active_sessions
from lenta_core.jobs import recent_jobs
from lenta_core.models import Event, User, Video
from lenta_core.registry import list_versions

from ..deps import get_db, get_redis

router = APIRouter(tags=["dashboard"])


@router.get("/events/recent")
def events_recent(
    limit: int = Query(40, ge=1, le=200), db: Session = Depends(get_db)
) -> list[dict]:
    rows = db.execute(
        select(
            Event.id, Event.user_id, Event.video_id, Event.event_type,
            Event.variant, Event.watch_fraction, Event.ts, Video.title,
        )
        .join(Video, Event.video_id == Video.id)
        .order_by(Event.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "video_id": r.video_id,
            "title": r.title,
            "event_type": r.event_type,
            "variant": r.variant,
            "watch_fraction": round(float(r.watch_fraction or 0.0), 3),
            "ts": r.ts,
        }
        for r in rows
    ]


@router.get("/sessions/active")
def sessions_active(r=Depends(get_redis)) -> dict:
    now = time.time()
    return {
        "active_count": active_session_count(r, now_epoch=now),
        "sessions": recent_active_sessions(r, now_epoch=now),
    }


@router.get("/users/sample")
def users_sample(n: int = Query(8, ge=1, le=50), db: Session = Depends(get_db)) -> list[int]:
    rows = db.execute(select(User.id).order_by(User.id).limit(n)).all()
    return [r[0] for r in rows]


@router.get("/jobs/recent")
def jobs_recent(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": j.id, "type": j.type, "status": j.status,
            "created_at": j.created_at, "finished_at": j.finished_at, "result": j.result,
        }
        for j in recent_jobs(db, 15)
    ]


@router.get("/report")
def report(db: Session = Depends(get_db)) -> dict:
    """One-line plain-English summary of what the latest retrain changed."""
    versions = list_versions(db, limit=2)
    if not versions:
        return {"text": "No models trained yet.", "version": None}
    cur = versions[0]
    cm = cur.metrics or {}
    if len(versions) < 2:
        return {
            "text": (
                f"Model v{cur.version} active — NDCG@10={cm.get('ndcg_at_k', 0):.3f}, "
                f"recall@10={cm.get('recall_at_k', 0):.3f}, coverage={cm.get('coverage', 0):.2f}."
            ),
            "version": cur.version,
        }
    prev = versions[1]
    pm = prev.metrics or {}
    d_ndcg = cm.get("ndcg_at_k", 0) - pm.get("ndcg_at_k", 0)
    d_recall = cm.get("recall_at_k", 0) - pm.get("recall_at_k", 0)

    cs = cm.get("feed_genre_share", {}) or {}
    ps = pm.get("feed_genre_share", {}) or {}
    deltas = [(g, cs.get(g, 0) - ps.get(g, 0)) for g in set(cs) | set(ps)]
    movers = sorted(deltas, key=lambda x: -abs(x[1]))
    risers = sorted(deltas, key=lambda x: -x[1])
    parts = [f"After retrain v{cur.version}:"]
    # Lead with the biggest *rising* genre — the intuitive "X rose" story, and the
    # one a genre_shift produces; fall back to the biggest absolute mover.
    lead = None
    if risers and risers[0][1] >= 0.01:
        lead = risers[0]
    elif movers and abs(movers[0][1]) >= 0.01:
        lead = movers[0]
    if lead:
        g, d = lead
        parts.append(f"{g} share of feeds {'rose' if d >= 0 else 'fell'} {abs(d) * 100:.0f}%,")
    parts.append(f"NDCG@10 {d_ndcg:+.3f}, recall@10 {d_recall:+.3f}.")
    return {
        "text": " ".join(parts),
        "version": cur.version,
        "prev_version": prev.version,
        "delta_ndcg": round(d_ndcg, 4),
        "delta_recall": round(d_recall, 4),
        "genre_movers": [{"genre": g, "delta": round(d, 4)} for g, d in movers[:6]],
    }
