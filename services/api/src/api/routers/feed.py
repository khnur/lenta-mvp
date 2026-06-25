from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from lenta_core.config import settings
from lenta_core.features.session import read_session_features
from lenta_core.ingest import insert_events
from lenta_core.ml.funnel import recommend
from lenta_core.schemas import PG_INT32_MAX
from lenta_core.models import User, Video, utcnow
from lenta_core.schemas import FeedResponse, FunnelDebug, VideoOut

from ..ab import assign_variant
from ..deps import get_db, get_redis, get_state
from ..state import AppState

router = APIRouter(tags=["serving"])


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    user_id: int = Query(..., ge=1, le=PG_INT32_MAX),
    k: int = Query(10, ge=1, le=50),
    variant: str | None = Query(None, pattern="^(control|treatment)$"),
    session_id: str | None = Query(None),
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
    r=Depends(get_redis),
) -> FeedResponse:
    if not state.model.ready:
        state.reload(db)
    if not state.model.ready:
        raise HTTPException(status_code=503, detail="No active model yet — seed + train first")

    v = assign_variant(db, user_id, variant)
    sid = session_id or f"web-{user_id}"
    sess = read_session_features(r, sid)
    bundle = state.model.bundle

    feed, debug = recommend(
        bundle, user_id, k,
        session=sess,
        now_epoch=time.time(),
        n_candidates=settings.als_candidates,
        max_per_genre=settings.rerank_max_per_genre,
        max_per_creator=settings.rerank_max_per_creator,
        fresh_slots=settings.rerank_fresh_slots,
        variant=v,
        booster=state.model.booster,
    )

    ids = [it["video_id"] for it in feed]
    vids = {vv.id: vv for vv in db.execute(select(Video).where(Video.id.in_(ids))).scalars()}

    now = utcnow()
    impressions = [
        {
            "user_id": user_id,
            "video_id": it["video_id"],
            "event_type": "impression",
            "watch_seconds": 0.0,
            "watch_fraction": 0.0,
            "session_id": sid,
            "variant": v,
            "ts": now,
            "context": {"source": "feed", "retrieval": debug["retrieval"], "score": it["score"]},
        }
        for it in feed
        if it["video_id"] in vids
    ]
    # Only log impressions for a real user (avoid a FK violation on ad-hoc /feed
    # previews for non-existent user_ids — the funnel still returns a cold feed).
    if impressions and db.get(User, user_id) is not None:
        insert_events(db, impressions)
        db.commit()

    items: list[VideoOut] = []
    for it in feed:
        vv = vids.get(it["video_id"])
        if not vv:
            continue
        items.append(
            VideoOut(
                id=vv.id,
                title=vv.title,
                creator_id=vv.creator_id,
                genres=vv.genres,
                tags=vv.tags,
                duration_seconds=vv.duration_seconds,
                upload_time=vv.upload_time,
                score=it["score"],
                stage=it["stage"],
            )
        )
    return FeedResponse(user_id=user_id, variant=v, k=k, items=items, funnel=FunnelDebug(**debug))
